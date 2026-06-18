"""
平板专用 API — 候选模板 + 偏好学习 + 一键填充

使用主系统的 search_candidates 9层打分 + template_loader
"""
import logging
import re
import json as _json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from preference_learner import rank_candidates
from db import doctor_preference_log, _conn, report_create as db_report_create
from template_loader import get_template_by_name, load_templates, search_candidates
from template_converted import lookup_template, setup as tc_setup
from template_converted.fill import fill_converted_template
from routers.structure import (
    _wrap_hints_with_toggle, _preserve_numbers, _quick_recommendation, _make_response,
    _quick_extract_entities, _append_uncovered_findings,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/pad", tags=["平板"])


def _get_pipeline():
    try:
        from pipeline import pipeline as _p
        return _p
    except Exception:
        return None


def _get_doctor_id(name: str) -> int:
    if not name:
        return 0
    try:
        c = _conn()
        row = c.execute("SELECT id FROM doctors WHERE name=?", (name,)).fetchone()
        return row["id"] if row else 0
    except Exception:
        return 0


def _cand_to_dict(c: dict) -> dict:
    """将 search_candidates 的返回转为候选模板格式"""
    return {
        "template_id": c.get("name", ""),
        "template_name": c.get("name", ""),
        "score": c.get("score", 0) / 300.0,  # 原始分最高~300, 归一化到0~1
        "site": c.get("module", ""),
        "discgroup": c.get("group", ""),
        "description": c.get("info1_preview", ""),
        "diagnosis": c.get("name", ""),
        "source": "template_loader",
    }


class CandidatesQuery(BaseModel):
    text: str = Field(..., min_length=1)
    exam_type: str = "腹部超声"
    doctor_name: str = ""
    site: str = ""


class FillQuery(BaseModel):
    text: str = Field(..., min_length=1)
    exam_type: str = "腹部超声"
    doctor_name: str = ""
    template_name: str = ""
    patient_id: str = None
    patient_name: str = None
    patient_gender: str = None
    patient_age: int = None
    clinical_diag: str = None


@router.post("/candidates")
async def get_candidates(body: CandidatesQuery):
    """返回 search_candidates 9层评分 + 偏好加权后的候选模板列表"""
    load_templates()
    tc_setup()

    # 1. 用主系统的 search_candidates 做9层评分
    from routing import classify as _route_classify
    route_result = _route_classify(body.text, body.exam_type)
    raw_candidates = search_candidates(
        body.text, body.exam_type, limit=8,
        category=route_result.get("category"),
        doctor=body.doctor_name,
    )

    if not raw_candidates:
        return {
            "candidates": [],
            "auto_fill": False,
            "show_selection": False,
            "needs_more": True,
            "top_conf": 0,
        }

    # 2. 转为统一格式
    candidates = [_cand_to_dict(c) for c in raw_candidates]

    # 3. 偏好加权排序
    doctor_id = _get_doctor_id(body.doctor_name)
    ranked = rank_candidates(
        candidates=candidates,
        doctor_id=doctor_id,
        doctor_name=body.doctor_name,
        site=body.site or body.exam_type,
    )

    # 4. 补充分组信息
    for c in ranked.get('candidates', []):
        name = c.get('template_name', '')
        if not c.get('discgroup'):
            conv = lookup_template(name)
            if conv:
                c['discgroup'] = conv.get('group', '')
                c['site'] = conv.get('visc', '') or c.get('site', '')

    return ranked


@router.post("/fill")
async def fill_with_template(body: FillQuery):
    """用医生指定的模板名填充文本"""
    if not body.template_name or not body.text:
        raise HTTPException(400, "模板和文本不能为空")

    A = body.text
    exam_type = body.exam_type or "腹部超声"
    warnings = []

    # 1. 用 converted 模板填充（最准确的路径）
    tc_setup()
    load_templates()
    converted = lookup_template(body.template_name)

    if converted:
        report = fill_converted_template(
            A,
            converted.get("html", ""),
            converted.get("fields", {}),
            converted.get("measurements", []),
            converted.get("options", []),
            converted.get("opt_reset", {}),
            set(converted.get("option_keys", [])),
            pre_extracted=_quick_extract_entities(A),
        )
        method = "pad_converted_fill"
    else:
        # 回退：用 template_loader 的 info1
        tpl = get_template_by_name(body.template_name)
        if tpl and tpl.get("info1"):
            report = {
                "study_see": tpl["info1"],
                "study_hint": [{"rank": 1, "diagnosis": body.template_name, "icd10": ""}],
                "recommendation": "",
            }
            method = "pad_template_fill"
        else:
            # 兜底：直接用 pipeline 生成
            pipeline = _get_pipeline()
            if pipeline:
                result = pipeline.process(A, body.doctor_name)
                r = result.get('report', {})
                report = {
                    "study_see": r.get('description', A),
                    "study_hint": [{"rank": 1, "diagnosis": r.get('template_name', body.template_name), "icd10": ""}],
                    "recommendation": r.get('diagnosis', ''),
                }
                method = "pad_pipeline_fill"
            else:
                report = {
                    "study_see": A,
                    "study_hint": [{"rank": 1, "diagnosis": body.template_name, "icd10": ""}],
                    "recommendation": "",
                }
                method = "pad_raw_fill"

    report = _wrap_hints_with_toggle(report)
    report, warnings = _preserve_numbers(A, report, warnings)

    # 阳性发现兜底
    report = _append_uncovered_findings(A, report)

    # 规则建议（无LLM调用）
    _rule_rec = _quick_recommendation(A, body.template_name, report, exam_type)
    if _rule_rec:
        report["recommendation"] = _rule_rec

    # 记录医生偏好
    if body.doctor_name:
        doctor_id = _get_doctor_id(body.doctor_name)
        try:
            doctor_preference_log(
                doctor_id=doctor_id,
                doctor_name=body.doctor_name,
                template_id=body.template_name,
                template_name=body.template_name,
                site=exam_type,
                discgroup="",
            )
        except Exception as e:
            logger.warning(f"记录偏好失败: {e}")

    # 保存报告
    if body.patient_id and body.patient_id.strip():
        try:
            pid = int(body.patient_id)
            db_report_create(pid, body.template_name, A, report)
        except Exception as e:
            logger.warning(f"报告保存失败: {e}")

    return _make_response(report, body, method, body.template_name, 0.85, warnings, A)
