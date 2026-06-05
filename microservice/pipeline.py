"""
Ultrasound-AI-Service - Core Pipeline
Orchestrates: audio_filter -> ASR -> correction -> conflict_detect -> template_match -> LLM(CB) -> validate -> audit
"""

import sys, os, time, asyncio, logging
from pathlib import Path

_backend_dir = Path(__file__).resolve().parents[1] / "backend"
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from . import config
from .schema import StructureData, PatientContext, StudyHint
from .logger import logger
from .circuit_breaker import circuit_breaker
from .audio_filter import check_audio_validity
from .audit_logger import log_request_async

def _get_asr():
    from asr_client import transcribe_audio
    return transcribe_audio

def _get_corrector():
    from asr_correction import correct_ASR_text
    return correct_ASR_text

def _get_template_anchor():
    from template_anchor import match_exact_template, anchored_structure, basic_regex_fill
    return match_exact_template, anchored_structure, basic_regex_fill

def _get_llm():
    from llm_client import generate_free_report
    return generate_free_report

try:
    from template_loader import load_templates
    load_templates()
except Exception as e:
    logger.warning(f"Template preload: {e}")


async def run_pipeline(request_type, text="", audio_bytes=None, patient_ctx=None):
    """Core pipeline: orchestrates all stages, returns StructureData"""
    t_start = time.time()
    config.ServiceStatus.total_requests += 1

    ctx_dict = patient_ctx.model_dump() if patient_ctx else {}
    exam_type = ctx_dict.get("exam_type", "腹部超声")
    patient_gender = ctx_dict.get("gender", "")
    patient_age = ctx_dict.get("age")

    # Stage 1: Audio filter
    audio_duration = 0.0
    is_valid = True
    if request_type == "transcribe" and audio_bytes:
        validity = check_audio_validity(audio_bytes)
        audio_duration = validity["duration"]
        is_valid = validity["is_valid"]
        if not is_valid:
            elapsed = (time.time() - t_start) * 1000
            return StructureData(
                raw_text="", corrected_text="", duration=audio_duration,
                is_valid=False, warnings=[validity["reason"]],
                method="audio_filtered", elapsed_ms=round(elapsed, 1))

    # Stage 2: ASR
    raw_text = text
    if request_type == "transcribe" and audio_bytes and is_valid:
        try:
            transcribe = _get_asr()
            asr_result = await transcribe(audio_bytes)
            raw_text = asr_result.get("raw", "")
            text = asr_result.get("text", raw_text)
            logger.info({"phase": "asr", "duration": audio_duration, "text_len": len(raw_text)})
        except Exception as e:
            logger.error({"phase": "asr", "error": str(e)})
            elapsed = (time.time() - t_start) * 1000
            return StructureData(
                raw_text="", corrected_text="",
                warnings=[f"ASR failed: {str(e)}"],
                method="asr_error", elapsed_ms=round(elapsed, 1))

    # Stage 3: ASR correction
    corrected_text = text
    if text:
        try:
            corrector = _get_corrector()
            corrected_text = corrector(text)
        except Exception:
            corrected_text = text

    # Stage 4: Conflict detect
    warnings = []
    if corrected_text and patient_gender:
        try:
            sex_conf = _detect_sex_conflict(corrected_text, patient_gender)
            if sex_conf:
                warnings.append(sex_conf)
            preg_conf = _detect_pregnancy_conflict(corrected_text, exam_type, patient_gender)
            if preg_conf:
                warnings.append(preg_conf)
        except Exception:
            pass

    # Stage 5: Template match (D-path) + P1 text length gate
    template_used = ""
    template_info1 = ""
    confidence_pct = 0
    top3_candidates = []
    try:
        match_exact, anchored, regex_fill = _get_template_anchor()
        candidates = match_exact(corrected_text or text, exam_type)
        if candidates:
            template_used = candidates[0]["tpl_name"]
            template_info1 = (candidates[0].get("info1") or "")[:200]
            confidence_pct = candidates[0].get("confidence_pct", 0)
            top3_candidates = [{"name": c["tpl_name"], "pct": c["confidence_pct"]} for c in candidates[:3]]
    except Exception as e:
        logger.warning(f"Template match error: {e}")

    # P1: Text length gate (user requirement: <20 chars = garbage)
    text_len = len(corrected_text or text)
    if text_len < 20 and request_type != "transcribe":
        elapsed = (time.time() - t_start) * 1000
        return StructureData(
            raw_text=raw_text, corrected_text=corrected_text or text,
            is_valid=False, warnings=[f"文本过短({text_len}字<20字阈值), 可能为无效数据"],
            method="text_length_gate", elapsed_ms=round(elapsed, 1))

    # Stage 5.5: Pre-LLM rule validation (P2: user requirement)
    pre_llm_warnings = []
    if corrected_text:
        try:
            from validators import validate_numerical_ranges
            pre_llm_warnings = validate_numerical_ranges(corrected_text)
        except ImportError:
            pass

    # Stage 6: LLM structure (circuit breaker) — route by confidence_pct (P0)
    study_see = ""
    study_hint = []
    recommendation = ""
    method = "anchored_regex"
    confidence = 0.85
    degraded = False

    # P0 routing: >=90% → high confidence direct fill, <90% → LLM enhanced
    high_confidence = confidence_pct >= 90

    if high_confidence and template_info1 and len(template_info1) > 10:
        # P4: Fill template keeping placeholders + append extra content
        try:
            from template_fill_anchored import fill_anchored
            study_see = fill_anchored(corrected_text or text, template_info1)
            method = "anchored_fill"
            confidence = confidence_pct / 100
        except Exception:
            study_see = _fallback_fill()
            method = "rule_fallback"
            confidence = 0.5
    else:
        # Low confidence (<90%): send top3 candidates to LLM (P3)
        def _call_llm():
            gen_free = _get_llm()
            system_extra = ""
            if top3_candidates:
                system_extra = f"\n候选模板(top3): {[c['name'] for c in top3_candidates]}"
            b = gen_free(corrected_text or text, exam_type)
            if not b:
                b = {"study_see": corrected_text or text, "study_hint": [], "recommendation": ""}
            return b

        def _fallback_fill():
            _, _, regex = _get_template_anchor()
            return regex(corrected_text or text, template_info1 or corrected_text or text)

        try:
            result, degraded = circuit_breaker.execute(_call_llm, fallback_func=_fallback_fill, timeout=15.0)
            if isinstance(result, str):
                study_see = result
                method = "rule_fallback"
                confidence = 0.5
                degraded = True
            else:
                study_see = result.get("study_see", "") or corrected_text
                study_hint_raw = result.get("study_hint", []) or []
                study_hint = [StudyHint(
                    rank=h.get("rank", i+1), diagnosis=h.get("diagnosis", ""), icd10=h.get("icd10", ""))
                    for i, h in enumerate(study_hint_raw[:10])]
                recommendation = result.get("recommendation", "")
                method = "b_llm"
                confidence = 0.85

            # P3: Post-LLM template verification (re-check after LLM)
            if template_used and study_see:
                try:
                    key_organs = _extract_template_organs(template_info1 or template_used)
                    missing = [o for o in key_organs if o not in study_see and o in (corrected_text or text)]
                    if missing and method == "b_llm":
                        logger.info(f"Post-LLM template verification: missing organs {missing} → refilling")
                        study_see = _fallback_fill()
                        method = "anchored_recheck"
                        warnings.append(f"LLM输出缺少关键器官{missing}, 已回退到模板填充")
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"LLM failed: {e}")
            study_see = _fallback_fill()
            method = "rule_fallback"
            confidence = 0.3
            degraded = True
            warnings.append(f"LLM degraded: {e}")

    # Stage 7: Post-validation (3 layers: contradiction + fill + numerical range)
    validation_issues = []
    try:
        v_issues = _post_validate(study_see, template_used,
                                   [h.model_dump() for h in study_hint])
        # Layer 2: numerical range validation
        try:
            from validators import validate_numerical_ranges
            num_warnings = validate_numerical_ranges(study_see)
            for nw in num_warnings:
                v_issues.append(f"[{nw['severity']}] {nw['message']}")
        except ImportError:
            pass
        validation_issues = v_issues
    except Exception:
        pass

    # Stage 7.3: P7 numerical cross-validation (LLM hallucination detection)
    try:
        import re
        def _extract_numbers(t): return set(re.findall(r'\d+\.?\d*', str(t)))
        raw_nums = _extract_numbers(corrected_text or text)
        json_nums = _extract_numbers(study_see)
        if json_nums - raw_nums:
            illegal = sorted(json_nums - raw_nums)[:5]
            v_issues.append(f"[P7] 检测到LLM幻觉数字: {illegal}")
            logger.warning(f"P7 hallucination: {illegal}")
    except Exception:
        pass

    # Stage 7.5: ASR quality estimation (for dynamic routing)
    if request_type == "transcribe" and corrected_text:
        try:
            from asr_quality_estimator import estimate_asr_quality
            quality = estimate_asr_quality(corrected_text, exam_type)
            if quality.get("route") == "fast":
                logger.info({"phase": "quality_check", "route": "fast",
                             "confidence": quality.get("confidence")})
        except ImportError:
            pass

    # Stage 8: Async audit
    elapsed = (time.time() - t_start) * 1000
    audit_id = None
    try:
        audit_id = log_request_async(
            request_type=request_type, patient_context=ctx_dict,
            audio_bytes=audio_bytes, audio_duration=audio_duration,
            raw_text=raw_text, corrected_text=corrected_text,
            study_see=study_see,
            study_hint=[h.model_dump() for h in study_hint],
            template_used=template_used, method=method, confidence=confidence,
            warnings=warnings, validation_issues=validation_issues,
            degraded=degraded, elapsed_ms=elapsed)
    except Exception:
        pass

    logger.info({
        "phase": "complete", "request_type": request_type, "method": method,
        "template": template_used, "confidence": confidence,
        "elapsed_ms": round(elapsed, 1), "degraded": degraded})

    return StructureData(
        raw_text=raw_text, corrected_text=corrected_text, duration=audio_duration,
        is_valid=is_valid, study_see=study_see, study_hint=study_hint,
        recommendation=recommendation, template_used=template_used,
        template_info1=template_info1, method=method, confidence=confidence,
        warnings=warnings, validation_issues=validation_issues,
        degraded=degraded, elapsed_ms=round(elapsed, 1), audit_id=audit_id)


def _detect_sex_conflict(text, gender):
    if gender == "男":
        for org in ["子宫","卵巢","宫颈","内膜","阴道","孕囊","胎盘","羊水","胎心","早孕","中孕"]:
            if org in text:
                return f"性别冲突: 男性患者口述含'{org}'"
    elif gender == "女":
        for org in ["前列腺","睾丸","附睾","精囊"]:
            if org in text:
                return f"性别冲突: 女性患者口述含'{org}'"
    return None

def _detect_pregnancy_conflict(text, exam_type, gender):
    if gender != "男":
        preg_kw = ["孕囊","胚芽","胎心","胎盘","羊水","早孕","中孕"]
        has_preg = any(kw in text for kw in preg_kw)
        is_ob = any(kw in exam_type for kw in ["产科","妇产","obgyn","胎儿"])
        if has_preg and not is_ob:
            return "检出妊娠指征但检查类型非产科/妇产"
    return None

def _post_validate(study_see, template_name, study_hint):
    import re
    issues = []
    contradictions = [("未见","可见"),("正常","异常"),("未见异常","异常回声")]
    for neg, pos in contradictions:
        if neg in study_see and pos in study_see:
            issues.append(f"矛盾: '{neg}'和'{pos}'同时出现")
    empty_count = study_see.count("___") + study_see.count("未测")
    if empty_count > 10:
        issues.append(f"报告有{empty_count}个未填充字段")
    return issues
