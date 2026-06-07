"""
意图预识别引擎 (Intent Pre-Detector) — v1.0

核心思路:
  在 ASR 转写和结构化提取之间插入一个「意图预识别」层,
  输入 6 个字段 (姓名/性别/年龄/住院号/申请科室/诊断/申请项目),
  输出一套「约束向量」注入后续的结构化管道,
  使模板匹配和 LLM 生成从"无上下文猜测"变为"有锚点推理"。

加速原理:
  1. 约束向量大幅缩小搜索空间:
     - 模板候选从 ~250 个缩到 1-3 个
     - 如「申请科室=产科」→ 直接走胎儿模板, 跳过全部 SITE×DISEASE 扫描
  2. 对于 83% 的常规体检场景 (据 HIS operational_stats)
     可直接走模板路线, 省去 LLM 调用 (~5s → ~10ms)

准确度原理:
  1. 开单诊断提供「锚点目标」:
     如诊断「输尿管结石」→ 预期在 study_hint 中出现「N20.1 输尿管结石」
     若 ASR 文本未命中 → 触发语音提示「请确认输尿管结石情况」
  2. 年龄+性别缩小正常值范围:
     如 72 岁男性 → 前列腺增生检出率 23%, 颈动脉斑块 10.5%
     若 ASR 未提及 → 置信度标低
  3. 申请科室提供检查途径上下文:
     如「泌尿外科」→ 经直肠前列腺超声
     如「体检中心」→ 常规腹部彩超 (预期「未见异常」)
"""

from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

# ============================================================
# 1. 数据结构
# ============================================================
@dataclass
class PatientContext:
    """患者上下文 — 从 HIS/医生录入系统获取的 6 个字段"""
    name: str = ""
    gender: str = ""           # "男" / "女"
    age: int = 0
    inpatient_id: str = ""     # 住院号 (ZY_ZYBRJLK.ZYH)
    outpatient_id: str = ""    # 门诊号 (SF_BRXXK.BLH)
    department: str = ""       # 申请科室 (如 "泌尿外科"/"体检中心"/"产科")
    clinical_diag: str = ""    # 开单临床诊断 (如 "输尿管结石" / "健康体检")
    exam_item: str = ""        # 申请检查项目 (如 "腹部彩超(肝胆胰脾肾)")

@dataclass
class IntentVector:
    """意图向量 — 注入后续管道的约束"""
    # 模板匹配约束
    target_template_key: str = ""           # 预判的模板 key (如 "abdomen"/"obgyn")
    candidate_template_indices: list = field(default_factory=list)  # 候选模板索引 [0-3个]

    # 检查类型/途经
    exam_type_resolved: str = ""            # 解析后的检查类型
    exam_route: str = ""                    # "经腹"/"经阴道"/"经直肠"/"经胸"
    exam_organs_expected: list = field(default_factory=list)  # 预期覆盖的脏器

    # 诊断锚点
    diag_anchor_organ: str = ""             # 诊断对应的目标器官
    diag_anchor_icd10: str = ""             # 诊断对应的 ICD-10
    expected_findings: list = field(default_factory=list)  # 预期阳性发现

    # 约束
    sex_guard_enabled: bool = True          # 是否启用性别守卫
    age_guard_enabled: bool = True
    skip_llm: bool = False                  # 是否可直接用模板 (无需 LLM)
    confidence_boost: float = 0.0           # 诊断锚点给匹配置信度加分

    # 提示
    voice_prompts: list = field(default_factory=list)  # 需要提醒医生补充的内容

    # 统计
    prediction_source: str = ""             # "diagnosis_exact" / "department" / "exam_item" / "age_gender" / "default"


# ============================================================
# 2. 核心路由表
# ============================================================

# === 科室 → 检查类型 + 检查途径 + 重点关注器官 ===
DEPT_ROUTE = {
    "体检中心": {
        "exam_type": "abdomen",
        "exam_route": "经腹",
        "expected_organs": ["肝脏","胆囊","胰腺","脾脏","双肾"],
        "note": "常规筛查, 预期'未见异常'概率高 (49.2% per HIS)",
        "skip_llm_probability": 0.60,  # 60% 直接走模板
    },
    "泌尿外科": {
        "exam_type": "abdomen",
        "exam_route": "经腹",
        "expected_organs": ["双肾","输尿管","膀胱","前列腺"],
        "note": "关注结石/积水/增生",
    },
    "产科": {
        "exam_type": "obgyn",
        "exam_route": "经腹",
        "expected_organs": ["胎儿","胎盘","羊水","脐带","宫颈"],
        "note": "胎儿模板专用通道, 跳过全部通用匹配",
        "skip_llm_probability": 0.80,
        "force_fetal_template": True,
    },
    "妇科": {
        "exam_type": "obgyn",
        "exam_route": "经阴道/经腹",
        "expected_organs": ["子宫","卵巢","附件","盆腔"],
    },
    "心内科": {
        "exam_type": "cardiac",
        "exam_route": "经胸",
        "expected_organs": ["左心室","左心房","右心室","右心房","二尖瓣","主动脉瓣"],
    },
    "神经内科": {
        "exam_type": "tcd",
        "exam_route": "经颅",
        "expected_organs": ["大脑中动脉","椎动脉","基底动脉"],
    },
    "血管外科": {
        "exam_type": "vascular",
        "exam_route": "经皮",
        "expected_organs": ["颈动脉","下肢动脉","下肢静脉"],
    },
    "内分泌科": {
        "exam_type": "thyroid",
        "exam_route": "经皮",
        "expected_organs": ["甲状腺","甲状旁腺"],
        "note": "关注结节/弥漫性病变",
    },
    "乳腺外科": {
        "exam_type": "thyroid",
        "exam_route": "经皮",
        "expected_organs": ["乳腺","腋窝淋巴结"],
    },
    "消化内科": {
        "exam_type": "abdomen",
        "exam_route": "经腹",
        "expected_organs": ["肝脏","胆囊","胰腺","脾脏"],
    },
    "肾内科": {
        "exam_type": "abdomen",
        "exam_route": "经腹",
        "expected_organs": ["双肾","输尿管","膀胱"],
    },
}

# === 诊断 → ICD10 + 目标器官 + 预期发现 ===
# (从 HIS diagnoses.csv 高频诊断 + 现有 ICD10_MAP 提取)
DIAG_ANCHORS = {
    "输尿管结石":     {"icd10": "N20.1", "organ": "输尿管",  "expected": ["输尿管扩张","肾盂积水","强回声团"]},
    "肾结石":        {"icd10": "N20.0", "organ": "肾脏",    "expected": ["强回声团","肾盂积水","结石"]},
    "胆囊结石":       {"icd10": "K80.2", "organ": "胆囊",   "expected": ["胆囊内强回声","声影","胆囊壁增厚"]},
    "胆囊结石伴急性胆囊炎": {"icd10": "K80.0", "organ": "胆囊","expected": ["胆囊增大","囊壁增厚","Murphy征阳性"]},
    "脂肪肝":         {"icd10": "K76.0", "organ": "肝脏",   "expected": ["回声增强","肝肾反差","血管显示不清"]},
    "肝囊肿":         {"icd10": "K76.8", "organ": "肝脏",   "expected": ["囊性占位","无回声","后方增强"]},
    "肝血管瘤":       {"icd10": "D18.0", "organ": "肝脏",   "expected": ["高回声团","边界清晰","血流信号"]},
    "肝硬化":         {"icd10": "K74.6", "organ": "肝脏",   "expected": ["回声增粗","表面不光滑","门静脉增宽"]},
    "胆囊息肉":       {"icd10": "K82.8", "organ": "胆囊",   "expected": ["附壁高回声","无声影","不随体位移动"]},
    "前列腺增生":     {"icd10": "N40",   "organ": "前列腺", "expected": ["体积增大","突入膀胱","残余尿"]},
    "子宫肌瘤":       {"icd10": "D25.9", "organ": "子宫",   "expected": ["低回声团块","边界清晰","变形"]},
    "子宫腺肌症":     {"icd10": "N80.0", "organ": "子宫",   "expected": ["肌壁增厚","回声不均","小囊性暗区"]},
    "卵巢囊肿":       {"icd10": "N83.2", "organ": "卵巢",   "expected": ["囊性占位","无回声","边界清晰"]},
    "甲状腺结节":     {"icd10": "E04.1", "organ": "甲状腺", "expected": ["低回声结节","形态规则/不规则","钙化"]},
    "乳腺增生":       {"icd10": "N60.1", "organ": "乳腺",   "expected": ["腺体增厚","回声不均","导管扩张"]},
    "颈动脉斑块":     {"icd10": "I65.2", "organ": "颈动脉", "expected": ["内膜增厚","斑块","狭窄"]},
    "冠心病":         {"icd10": "I25.1", "organ": "心脏",   "expected": ["室壁运动","EF值","瓣膜"]},
    "高血压病":       {"icd10": "I10",   "organ": "心脏",   "expected": ["左室肥厚","EF值","升主动脉"]},
    "心房颤动":       {"icd10": "I48",   "organ": "心脏",   "expected": ["左房增大","附壁血栓","二尖瓣"]},
    "妊娠":           {"icd10": "Z34.9", "organ": "胎儿",   "expected": ["胎心","羊水","胎盘","胎儿测值"],
                      "force_fetal_template": True},
    "健康体检":       {"icd10": "Z00.0", "organ": "",       "expected": [], "note": "常规筛查无特定锚点"},
}

# === 检查项目名称 → 模板 + 脏器 ===
EXAM_ITEM_ROUTE = {
    "腹部彩超":            "abdomen",
    "腹部超声":            "abdomen",
    "肝胆胰脾":            "abdomen",
    "肝胆胰脾肾":          "abdomen",
    "泌尿系超声":          "abdomen",  # routes to abdomen templates, focuses on kidney/bladder/prostate
    "前列腺膀胱彩超":      "abdomen",
    "心脏彩超":            "cardiac",
    "心彩超":              "cardiac",
    "心超":                "cardiac",
    "妇产超声":            "obgyn",
    "妇科彩超":            "obgyn",
    "产科超声":            "obgyn",
    "早孕检查":            "obgyn",
    "中孕筛查":            "obgyn",
    "四维彩超":            "obgyn",
    "甲状腺彩超":          "thyroid",
    "乳腺彩超":            "thyroid",
    "颈动脉彩超":          "vascular",
    "下肢血管超声":        "vascular",
    "脑血管彩超":          "tcd",
    "经颅多普勒":          "tcd",
    "TCD":                 "tcd",
    "阴道彩超":            "obgyn",
}

# === 年龄 → 高概率阳性发现 ===
AGE_EXPECTATIONS = [
    # (min_age, max_age, organ, finding, probability, source)
    (50, 150, "前列腺", "前列腺增生", 0.23, "HIS ops_stats USS-003"),
    (50, 150, "颈动脉", "动脉硬化/斑块", 0.105, "HIS ops_stats"),
    (40, 150, "肝脏", "脂肪肝", 0.099, "HIS ops_stats USS-001"),
    (45, 150, "甲状腺", "结节", 0.265, "HIS ops_stats USS-002"),
    (60, 150, "心脏", "舒张功能减低", 0.095, "HIS ops_stats USS-004"),
    (20, 40,  "子宫", "子宫肌瘤", 0.05, "HIS diagnoses D25.9"),
]


# ============================================================
# 3. 意图预识别引擎
# ============================================================
def detect_intent(ctx: PatientContext) -> IntentVector:
    """
    输入 6 个字段 → 输出 IntentVector

    匹配优先级:
      1. 开单临床诊断 (DIAG_ANCHORS) — 最强约束
      2. 申请检查项目 (EXAM_ITEM_ROUTE) — 精确检查类型
      3. 申请科室 (DEPT_ROUTE) — 科室路由
      4. 年龄+性别 (AGE_EXPECTATIONS) — 弱约束

    每层约束叠加到 IntentVector, 后续管道按需取用
    """
    iv = IntentVector()

    # ── 层1: 开单临床诊断 (最强) ──
    diag_key = None
    for kw in sorted(DIAG_ANCHORS.keys(), key=len, reverse=True):
        if kw in ctx.clinical_diag:
            diag_key = kw
            break

    if diag_key:
        anchor = DIAG_ANCHORS[diag_key]
        iv.diag_anchor_organ = anchor["organ"]
        iv.diag_anchor_icd10 = anchor["icd10"]
        iv.expected_findings = anchor.get("expected", [])
        iv.confidence_boost = 15.0  # 诊断锚点给匹配置信度 +15
        iv.prediction_source = "diagnosis_exact"

        # 产科诊断 → 强制胎儿模板
        if anchor.get("force_fetal_template"):
            iv.target_template_key = "obgyn"
            iv.exam_type_resolved = "产科超声"
            iv.skip_llm = True
            iv.confidence_boost = 30.0

    # ── 层2: 申请检查项目 ──
    exam_key = None
    for kw in sorted(EXAM_ITEM_ROUTE.keys(), key=len, reverse=True):
        if kw in ctx.exam_item:
            exam_key = kw
            break

    if exam_key:
        tpl_key = EXAM_ITEM_ROUTE[exam_key]
        if not iv.target_template_key:  # 不被诊断锚点覆盖
            iv.target_template_key = tpl_key
            iv.exam_type_resolved = exam_key

        if not iv.prediction_source:
            iv.prediction_source = "exam_item"

    # ── 层3: 申请科室 ──
    dept_key = None
    for kw in DEPT_ROUTE:
        if kw in ctx.department:
            dept_key = kw
            break

    if dept_key:
        route = DEPT_ROUTE[dept_key]
        if not iv.target_template_key:
            iv.target_template_key = route["exam_type"]
        if not iv.exam_type_resolved:
            iv.exam_type_resolved = route.get("exam_type", ctx.exam_item)
        iv.exam_route = route.get("exam_route", "")
        iv.exam_organs_expected = route.get("expected_organs", [])

        if not iv.prediction_source:
            iv.prediction_source = "department"

        # 产科科室 → 强制胎儿模板
        if route.get("force_fetal_template"):
            iv.target_template_key = "obgyn"
            iv.exam_type_resolved = "产科超声"
            iv.skip_llm = True
            iv.confidence_boost = 30.0

        # 体检中心 → 常规筛查, 可跳过 LLM
        if "体检" in ctx.department and ctx.clinical_diag in ("健康体检", "", "未见异常", "体检"):
            iv.skip_llm = True

    # ── 层4: 年龄+性别弱约束 ──
    if ctx.gender and ctx.age:
        for lo, hi, organ, finding, prob, source in AGE_EXPECTATIONS:
            if lo <= ctx.age <= hi:
                iv.expected_findings.append(f"{finding}(检出率~{prob*100:.0f}%)")

        # 性别守卫
        iv.sex_guard_enabled = True
        iv.age_guard_enabled = True

        if not iv.prediction_source:
            iv.prediction_source = "age_gender"

    # ── 兜底 ──
    if not iv.target_template_key:
        iv.target_template_key = "abdomen"
        iv.exam_type_resolved = ctx.exam_item or "腹部超声"
        iv.prediction_source = "default"

    # ── 生成语音提示 ──
    _generate_prompts(ctx, diag_key, iv)

    return iv


def _generate_prompts(ctx: PatientContext, diag_key: str | None, iv: IntentVector):
    """根据缺失信息生成语音提示"""
    prompts = []

    # 诊断锚点提示: 告知医生本次检查的预期目标
    if diag_key and iv.expected_findings:
        prompts.append(f"本次检查关注{iv.diag_anchor_organ}的{'、'.join(iv.expected_findings[:2])}")

    # 年龄相关提示
    if ctx.age >= 50 and ctx.gender == "男":
        prompts.append("提醒: 本年龄段前列腺增生检出率约23%，如有排尿症状请口述")

    # 性别守卫预检
    if ctx.gender == "男" and iv.target_template_key == "obgyn":
        prompts.append("注意: 当前患者性别为男性，检查类型为妇产超声，请确认")

    iv.voice_prompts = prompts


# ============================================================
# 4. 集成入口
# ============================================================
def apply_intent_to_structure_request(intent: IntentVector, original_exam_type: str) -> dict:
    """
    将意图向量注入 /api/structure 的 StructureRequest 上下文
    替换 main.py 的 structure() 函数中硬编码的 exam_type 路由
    """
    return {
        # 覆盖检查类型: 意图引擎解析的更准确
        "exam_type": intent.exam_type_resolved or original_exam_type,

        # 模板关键词: 传给 template_filler / template_engine_v2
        "template_key": intent.target_template_key,

        # 是否跳过 LLM: 体检中心+健康体检 可直接用模板
        "skip_llm": intent.skip_llm,

        # 匹配置信度加分
        "confidence_boost": intent.confidence_boost,

        # 期望的阳性发现: 注入 LLM system prompt
        "expected_findings": intent.expected_findings,
        "diag_anchor_organ": intent.diag_anchor_organ,
        "diag_anchor_icd10": intent.diag_anchor_icd10,

        # 检查途径
        "exam_route": intent.exam_route,

        # 约束开关
        "sex_guard_enabled": intent.sex_guard_enabled,
        "age_guard_enabled": intent.age_guard_enabled,

        # 语音提示
        "voice_prompts": intent.voice_prompts,

        # 意图识别来源
        "intent_source": intent.prediction_source,
    }
