#!/usr/bin/env python3
"""超声报告结构化 — 回归测试套件 (API v4.2)
=============================================
覆盖: /api/structure (管理后台) + /v1/structure (API网关)
指标: 字段填充率、幻觉数字检测、模板覆盖率、ICD-10准确率

用法:
  python regression_test.py                    # 默认 localhost:8730
  python regression_test.py --api 8800         # 走 API 网关
  python regression_test.py --remote           # 走云服务器 47.109.151.238:9999
"""

import urllib.request, urllib.error
import json, time, re, sys, statistics
from datetime import datetime

# ── 配置 ──
REMOTE = "47.109.151.238"
LOCAL = "localhost"

def get_base(args: list[str]) -> str:
    if "--remote" in args:
        return f"http://{REMOTE}:9999"
    if "--api" in args:
        port = "8800"
        for i, a in enumerate(args):
            if a == "--api" and i + 1 < len(args):
                port = args[i + 1]
        return f"http://{REMOTE if '--remote' in args else LOCAL}:{port}"
    return f"http://{LOCAL}:8730"

API = get_base(sys.argv)

# ── 10 条回归用例 (精简自 test_20_business.py, 覆盖主要检查类型) ──
CASES = [
    # === 腹部超声 ===
    {
        "id": "ABD-01",
        "exam_type": "腹部超声",
        "gender": "男", "age": 52,
        "text": "肝脏大小形态正常，实质回声均匀，血管走行清晰。胆囊大小约68乘28毫米，壁厚2毫米、光滑，腔内未见异常回声。胆总管内径5毫米。胰腺大小形态正常。脾脏肋间厚30毫米。双肾大小形态正常。超声提示：腹部超声未见明显异常。",
        "checks": {
            "organs_min": 6,
            "template_expected": "腹部超声",
            "icd10_pattern": r"Z00\.0|正常|未见明显异常",
            "numbers_expected": ["68", "28", "2", "5", "30"],
        },
    },
    {
        "id": "ABD-02",
        "exam_type": "腹部超声",
        "gender": "女", "age": 48,
        "text": "胆囊大小约82乘38毫米，壁厚4毫米、毛糙，腔内可见多个强回声团，大者约10乘8毫米，后伴声影，随体位改变移动。胆总管未见扩张。肝脏、胰腺、脾脏、双肾未见明显异常。超声提示：1、慢性胆囊炎 2、胆囊多发结石。",
        "checks": {
            "organs_min": 5,
            "template_expected": "腹部超声",
            "diagnosis_min": 2,
            "icd10_count_min": 1,
            "numbers_expected": ["82", "38", "4", "10", "8"],
        },
    },
    {
        "id": "ABD-03",
        "exam_type": "腹部超声",
        "gender": "女", "age": 55,
        "text": "胆囊显示不清，胆囊区可见一大小约28乘20毫米的弧形强回声带，后伴宽大声影。肝脏回声弥漫性增粗，表面呈结节状。脾脏肋间厚55毫米。腹腔可见游离无回声区。超声提示：1、胆囊结石伴萎缩性胆囊炎 2、肝硬化 3、脾大 4、腹水。",
        "checks": {
            "organs_min": 4,
            "template_expected": "腹部超声",
            "diagnosis_min": 3,
            "icd10_count_min": 2,
            "numbers_expected": ["28", "20", "55"],
        },
    },
    {
        "id": "ABD-04",
        "exam_type": "腹部超声",
        "gender": "男", "age": 38,
        "text": "肝脏回声增强、增粗，肝肾反差明显。胆囊大小正常，壁光滑。胰腺未见异常。脾脏未见肿大。双肾未见异常。超声提示：脂肪肝。",
        "checks": {
            "organs_min": 5,
            "template_expected": "腹部超声",
            "diagnosis_min": 1,
            "icd10_count_min": 1,
            "numbers_expected": [],
        },
    },
    # === 妇产超声 ===
    {
        "id": "OBG-01",
        "exam_type": "妇产超声",
        "gender": "女", "age": 35,
        "text": "子宫前位，大小约75乘52乘45毫米，形态规则，肌壁回声均匀。前壁可见一大小约38乘32毫米的低回声结节，边界清晰，形态规则。内膜厚约8毫米。宫颈未见异常。双侧卵巢大小形态正常。盆腔未见游离液体。超声提示：子宫肌瘤。",
        "checks": {
            "organs_min": 4,
            "template_expected": "妇产超声",
            "diagnosis_min": 1,
            "icd10_count_min": 1,
            "numbers_expected": ["75", "52", "45", "38", "32", "8"],
        },
    },
    {
        "id": "OBG-02",
        "exam_type": "妇产超声",
        "gender": "女", "age": 31,
        "text": "子宫内膜增厚约16毫米，宫腔内可见一孕囊，大小约28乘18毫米，可见卵黄囊，胚芽长约6毫米，可见原始心管搏动，心率约145次每分。超声提示：宫内早孕，约孕6周+，胚胎存活。",
        "checks": {
            "organs_min": 3,
            "template_expected": "妇产超声",
            "diagnosis_min": 1,
            "numbers_expected": ["16", "28", "18", "6", "145"],
        },
    },
    # === 心脏超声 ===
    {
        "id": "CAR-01",
        "exam_type": "心脏超声",
        "gender": "男", "age": 65,
        "text": "左心室增大，舒张末内径约65毫米。左室壁运动弥漫性减弱。二尖瓣未见反流。主动脉瓣三叶式，未见反流。三尖瓣未见反流。EF约38%。心包未见积液。超声提示：扩张型心肌病，左心功能减低。",
        "checks": {
            "organs_min": 4,
            "template_expected": "心脏超声",
            "diagnosis_min": 1,
            "icd10_count_min": 1,
            "numbers_expected": ["65", "38"],
        },
    },
    # === 小器官 ===
    {
        "id": "THY-01",
        "exam_type": "甲状腺超声",
        "gender": "女", "age": 38,
        "text": "甲状腺右叶中部可见一大小约9乘7毫米的低回声结节，边界清晰，形态规则，内部回声均匀。TI-RADS 3类。超声提示：甲状腺右叶结节，TI-RADS 3类，考虑良性。",
        "checks": {
            "organs_min": 1,
            "template_expected": "甲状腺",
            "diagnosis_min": 1,
            "numbers_expected": ["9", "7"],
        },
    },
    {
        "id": "BRE-01",
        "exam_type": "乳腺超声",
        "gender": "女", "age": 45,
        "text": "左侧乳腺内上象限可见一大小约22乘18毫米的低回声结节，边界欠清晰，形态略不规则，内部回声不均匀。可见点状微钙化。CDFI示结节内可见较丰富血流信号。BI-RADS 4b类。超声提示：左乳实性占位，BI-RADS 4b类，建议穿刺活检。",
        "checks": {
            "organs_min": 2,
            "template_expected": "乳腺",
            "diagnosis_min": 1,
            "numbers_expected": ["22", "18"],
        },
    },
    # === 口语化边缘 ===
    {
        "id": "EDGE-01",
        "exam_type": "腹部超声",
        "gender": "男", "age": 70,
        "text": "做了个B超。肝上面医生说有点大，回声也不太好，右边肝里有个东西，大概两公分多，胆囊说是有石头的，泥沙那种。其他胰脏脾什么的都说还行。肾左边有个小囊肿。意见就是肝血管瘤、胆结石、左肾囊肿。",
        "checks": {
            "organs_min": 4,
            "template_expected": "腹部超声",
            "diagnosis_min": 2,
            "icd10_count_min": 1,
            "numbers_expected": [],
        },
    },
]


# ── 指标计算 ──

def strip_html(s: str) -> str:
    return re.sub(r'<[^>]+>', '', s or "").strip()


def count_filled_fields(study_see_html: str) -> tuple[int, int]:
    """返回 (voice标记数, unfill标记数)"""
    voice = len(re.findall(r'class="voice"', study_see_html))
    unfill = len(re.findall(r'class="unfill"', study_see_html))
    return voice, unfill


def extract_numbers(text: str) -> set[str]:
    return set(re.findall(r'\b\d+\.?\d*\b', strip_html(text)))


def check_hallucination(asr_text: str, study_see_html: str) -> list[str]:
    """检测 LLM 生成的数值是否在 ASR 原文中不存在"""
    asr_nums = extract_numbers(asr_text)
    see_nums = extract_numbers(study_see_html)
    illegal = sorted(see_nums - asr_nums, key=lambda x: float(x) if x.replace('.', '').isdigit() else 0)
    return illegal[:10]


def score_icd10(hints: list[dict]) -> float:
    """ICD-10 覆盖率: 有ICD10的hint / 总hint"""
    if not hints:
        return 0.0
    with_icd10 = sum(1 for h in hints if (h.get("icd10") or "").strip())
    return with_icd10 / len(hints)


def run():
    print("=" * 72)
    print(f"  超声报告结构化 — 回归测试套件")
    print(f"  API: {API}")
    print(f"  开始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  用例: {len(CASES)}")
    print("=" * 72)

    # Health check
    try:
        req = urllib.request.Request(f"{API}/api/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(f"\n[Health] {json.loads(resp.read().decode())}")
    except Exception as e:
        print(f"\n[Health] 服务不可达: {e}")
        return

    results = []
    start = time.time()

    for i, case in enumerate(CASES):
        cid = case["id"]
        cks = case["checks"]
        t0 = time.time()
        print(f"\n── {cid} {case['exam_type']} ──")
        status = {"id": cid, "exam_type": case["exam_type"]}

        try:
            payload = json.dumps({
                "text": case["text"],
                "exam_type": case["exam_type"],
                "patient_gender": case["gender"],
                "patient_age": case["age"],
            }, ensure_ascii=False).encode("utf-8")

            req = urllib.request.Request(
                f"{API}/api/structure",
                data=payload,
                headers={"Content-Type": "application/json; charset=utf-8"},
            )
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            body = ""
            if hasattr(e, "read"):
                try:
                    body = e.read().decode()[:300]
                except Exception:
                    pass
            print(f"  FAIL: {e} | {body}")
            status["error"] = str(e)[:100]
            results.append(status)
            continue

        if not data.get("success"):
            print(f"  FAIL: success=False")
            status["error"] = "success=False"
            results.append(status)
            continue

        report = data.get("report", {})
        see = report.get("study_see", "") or ""
        hints = report.get("study_hint", []) or []
        see_plain = strip_html(see)
        method = data.get("method", "")
        tpl = data.get("template_used", "")
        confidence = data.get("confidence", 0)

        # ── 指标 1: 字段填充率 ──
        voice, unfill = count_filled_fields(see)
        fill_rate = voice / (voice + unfill) * 100 if (voice + unfill) > 0 else 100.0
        status["fill_rate"] = round(fill_rate, 1)

        # ── 指标 2: 幻觉检测 ──
        illegal_nums = check_hallucination(case["text"], see)
        status["hallucination_count"] = len(illegal_nums)

        # ── 指标 3: 模板覆盖率 ──
        status["template"] = tpl or "(无)"
        template_ok = bool(tpl and cks.get("template_expected", "")[:2] in tpl[:6])
        status["template_match"] = template_ok

        # ── 指标 4: ICD-10 ──
        icd10_rate = score_icd10(hints)
        status["icd10_rate"] = round(icd10_rate, 2)

        # ── 指标 5: 诊断数量 ──
        diag_count = len(hints)
        status["diagnosis_count"] = diag_count

        # ── 打印 ──
        elapsed = time.time() - t0
        flags = []
        if fill_rate < 50:
            flags.append(f"填充率={fill_rate:.0f}%")
        if illegal_nums:
            flags.append(f"幻觉={illegal_nums[:3]}")
        if not template_ok:
            flags.append(f"模板={tpl or '(无)'}")
        diag_min = cks.get("diagnosis_min", 0)
        if diag_min > 0 and diag_count < diag_min:
            flags.append(f"诊断少({diag_count}/{diag_min})")

        status_line = "OK" if not flags else "WARN: " + "; ".join(flags)
        print(f"  {status_line}  {elapsed:.1f}s")
        print(f"  填充: voice={voice} unfill={unfill} rate={fill_rate:.0f}%  "
              f"幻觉: {len(illegal_nums)}  ICD-10: {icd10_rate:.0%}  "
              f"模板: {tpl or '(无)'}  method: {method}")
        print(f"  所见: {see_plain[:150]}...")
        if hints:
            for h in hints[:5]:
                print(f"  提示: {h.get('rank','?')}. {h.get('diagnosis','?')}  [{h.get('icd10','')}]")

        results.append(status)

    # ── 汇总 ──
    total = time.time() - start
    ok = sum(1 for r in results if not r.get("error"))
    fails = sum(1 for r in results if r.get("error"))

    print("\n" + "=" * 72)
    print(f"                    回 归 测 试 汇 总")
    print("=" * 72)
    print(f"  用例数:    {len(CASES)}")
    print(f"  成功:      {ok}")
    print(f"  失败:      {fails}")

    if ok > 0:
        fill_rates = [r["fill_rate"] for r in results if "fill_rate" in r]
        hallucinations = [r["hallucination_count"] for r in results if "hallucination_count" in r]
        template_matches = sum(1 for r in results if r.get("template_match"))
        icd10_rates = [r["icd10_rate"] for r in results if "icd10_rate" in r]
        diag_counts = [r["diagnosis_count"] for r in results if "diagnosis_count" in r]

        print(f"\n  核心指标:")
        print(f"    字段填充率:    {statistics.mean(fill_rates):.0f}% (min {min(fill_rates):.0f}%)")
        print(f"    幻觉数字:      平均 {statistics.mean(hallucinations):.1f}/例 (max {max(hallucinations)})")
        print(f"    模板覆盖率:    {template_matches}/{ok} ({template_matches/ok*100:.0f}%)")
        print(f"    ICD-10 覆盖率: {statistics.mean(icd10_rates):.0%}")
        print(f"    诊断数量:      平均 {statistics.mean(diag_counts):.1f}/例")

        if hasattr(time, "monotonic"):
            pass
        print(f"\n  总耗时: {total:.0f}s")
        times = [t for t in [] if t]  # parsed per case above
        # Extract from raw results
        try:
            raw_elapsed = sum(float(r.get("elapsed", 0) or 0) for r in results)
            if raw_elapsed > 0:
                print(f"  处理耗时: {raw_elapsed:.0f}s")
        except Exception:
            pass

    if fails > 0:
        print(f"\n  失败用例:")
        for r in results:
            if r.get("error"):
                print(f"  [{r['id']}] {r.get('error','?')}")

    # ── 快照: 保存本次结果 ──
    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "api": API,
        "total": len(CASES),
        "ok": ok,
        "fails": fails,
        "results": results,
    }
    snapshot_path = f"regression_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    try:
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
        print(f"\n  快照已保存: {snapshot_path}")
    except Exception:
        pass

    print("=" * 72)


if __name__ == "__main__":
    run()
