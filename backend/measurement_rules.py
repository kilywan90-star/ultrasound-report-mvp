"""
超声测量值 — 本地硬校验规则库 v2.0
====================================
来源:
  1) 长沙医院3067条真实报告 (statistical analysis)
  2) ASE/EACVI 2024 成人心脏超声指南
  3) ISUOG 2024 产科超声指南
  4) 中国颈动脉超声检查规范
  5) AIUM腹部超声正常值

用途: 增强版 validators.validate_numerical_ranges()
      当规则引擎(field_asr_hints)找不到对应规则时, 回退到这里的硬编码值
"""

# ══════════════════════════════════════════
# 心脏超声 (成人) — ASE/EACVI 2024
# ══════════════════════════════════════════
CARDIAC_RULES = {
    "LVEDD":       {"min": 38, "max": 56, "unit": "mm", "desc": "左室舒张末内径"},
    "LVESD":       {"min": 22, "max": 40, "unit": "mm", "desc": "左室收缩末内径"},
    "IVS":         {"min": 6,  "max": 11, "unit": "mm", "desc": "室间隔厚度"},
    "LVPW":        {"min": 6,  "max": 11, "unit": "mm", "desc": "左室后壁厚度"},
    "AO":          {"min": 20, "max": 38, "unit": "mm", "desc": "主动脉内径"},
    "LA":          {"min": 19, "max": 40, "unit": "mm", "desc": "左房内径"},
    "RV":          {"min": 15, "max": 30, "unit": "mm", "desc": "右室内径"},
    "PA":          {"min": 12, "max": 28, "unit": "mm", "desc": "肺动脉内径"},
    "EF":          {"min": 55, "max": 80, "unit": "%", "desc": "左室射血分数"},
    "心率":        {"min": 45, "max": 200, "unit": "bpm", "desc": "心率"},
    "胎心率":      {"min": 100, "max": 180, "unit": "bpm", "desc": "胎心率"},
    "AV_Vmax":     {"min": 0.5, "max": 4.0, "unit": "m/s", "desc": "主动脉瓣峰值流速"},
    "E_vel":       {"min": 0.3, "max": 1.5, "unit": "m/s", "desc": "二尖瓣E峰流速"},
    "A_vel":       {"min": 0.2, "max": 1.0, "unit": "m/s", "desc": "二尖瓣A峰流速"},
}

# ══════════════════════════════════════════
# 产科 — ISUOG 2024 (简化, 全周期通用范围)
# ══════════════════════════════════════════
OBSTETRIC_RULES = {
    "BPD":         {"min": 22, "max": 100, "unit": "mm", "desc": "双顶径(14-40周)"},
    "HC":          {"min": 50, "max": 360, "unit": "mm", "desc": "头围(14-40周)"},
    "AC":          {"min": 40, "max": 380, "unit": "mm", "desc": "腹围(14-40周)"},
    "FL":          {"min": 8,  "max": 82, "unit": "mm", "desc": "股骨长(14-40周)"},
    "HL":          {"min": 8,  "max": 72, "unit": "mm", "desc": "肱骨长(14-40周)"},
    "AFI":         {"min": 3,  "max": 28, "unit": "cm", "desc": "羊水指数"},
    "MVP":         {"min": 2,  "max": 10, "unit": "cm", "desc": "羊水最大深度"},
    "CRL":         {"min": 5,  "max": 90, "unit": "mm", "desc": "头臀长(6-14周)"},
    "NT":          {"min": 0.5, "max": 6.0, "unit": "mm", "desc": "颈项透明层"},
}

# ══════════════════════════════════════════
# 腹部 — 长沙3067条真实数据统计 + AIUM指南
# ══════════════════════════════════════════
ABDOMINAL_RULES = {
    "肝脏右叶斜径":    {"min": 80, "max": 165, "unit": "mm", "desc": "肝右叶最大斜径"},
    "门静脉内径":      {"min": 6,  "max": 15, "unit": "mm", "desc": "门静脉内径"},
    "胆囊长径":        {"min": 35, "max": 110, "unit": "mm", "desc": "胆囊长径"},
    "胆囊壁厚度":      {"min": 1,  "max": 5,  "unit": "mm", "desc": "胆囊壁厚度"},
    "胆总管内径":      {"min": 2,  "max": 10, "unit": "mm", "desc": "胆总管内径"},
    "胰头厚度":        {"min": 12, "max": 38, "unit": "mm", "desc": "胰头厚度"},
    "胰体厚度":        {"min": 8,  "max": 28, "unit": "mm", "desc": "胰体厚度"},
    "脾脏厚度":        {"min": 20, "max": 50, "unit": "mm", "desc": "脾脏厚度"},
    "肾脏长径":        {"min": 70, "max": 140, "unit": "mm", "desc": "肾脏长径"},
    "肾皮质厚度":      {"min": 6,  "max": 24, "unit": "mm", "desc": "肾皮质厚度"},
    "肾脏前后径":      {"min": 30, "max": 65, "unit": "mm", "desc": "肾脏前后径"},
    "前列腺体积":      {"min": 10, "max": 45, "unit": "ml", "desc": "前列腺体积"},
}

# ══════════════════════════════════════════
# 甲状腺/乳腺
# ══════════════════════════════════════════
SMALL_PARTS_RULES = {
    "甲状腺叶长径":     {"min": 30, "max": 70, "unit": "mm", "desc": "甲状腺叶长径"},
    "甲状腺叶短径":     {"min": 8,  "max": 25, "unit": "mm", "desc": "甲状腺叶短径"},
    "甲状腺峡部厚度":   {"min": 1,  "max": 6,  "unit": "mm", "desc": "峡部厚度"},
    "乳腺结节长径":     {"min": 1,  "max": 60, "unit": "mm", "desc": "乳腺结节大小"},
}

# ══════════════════════════════════════════
# 血管 — Mannheim共识 + 中国颈动脉指南
# ══════════════════════════════════════════
VASCULAR_RULES = {
    "颈总动脉IMT":   {"min": 0.3, "max": 1.5, "unit": "mm", "desc": "颈总动脉内膜中层厚度"},
    "颈动脉斑块厚度": {"min": 0.8, "max": 6.0, "unit": "mm", "desc": "颈动脉斑块厚度"},
    "ICA收缩期峰值流速": {"min": 20, "max": 200, "unit": "cm/s", "desc": "颈内动脉PSV"},
    "狭窄率":        {"min": 0, "max": 100, "unit": "%", "desc": "血管狭窄率"},
}

# ══════════════════════════════════════════
# 通用绝对硬上限 (防止LLM幻觉)
# ══════════════════════════════════════════
ABSOLUTE_LIMITS = {
    "心率_硬上限": 500,     # 超过此值必定是幻觉/错误
    "EF_硬上限":   100,     # EF不可能超过100%
    "胎儿体重_硬上限": 6000, # 超过6kg必定是幻觉
    "胎儿体重_硬下限": 200,  # 低于200g不合理
    "任意尺寸_硬上限_mm": 500,  # 超过500mm在超声中几乎不可能
}

# ── 合并所有规则 ──
ALL_HARD_RULES = {}
ALL_HARD_RULES.update(CARDIAC_RULES)
ALL_HARD_RULES.update(OBSTETRIC_RULES)
ALL_HARD_RULES.update(ABDOMINAL_RULES)
ALL_HARD_RULES.update(SMALL_PARTS_RULES)
ALL_HARD_RULES.update(VASCULAR_RULES)


def get_hard_rule(field_id: str) -> dict | None:
    """根据字段名查找硬编码规则"""
    return ALL_HARD_RULES.get(field_id)


def check_absolute_limits(value: float, unit: str) -> str | None:
    """绝对硬上限检查, 返回错误消息或None"""
    if unit in ('bpm', '次/分'):
        if value > ABSOLUTE_LIMITS["心率_硬上限"]:
            return f"心率值 {value} bpm 超过生理极限(>{ABSOLUTE_LIMITS['心率_硬上限']}), 可能是识别错误"
    if unit == '%':
        if value > ABSOLUTE_LIMITS["EF_硬上限"]:
            return f"百分比值 {value}% 超过100%, 不可能"
    if unit in ('mm', 'cm', '毫米', '厘米'):
        mm_val = value * 10 if unit in ('cm', '厘米') else value
        if mm_val > ABSOLUTE_LIMITS["任意尺寸_硬上限_mm"]:
            return f"尺寸值 {value}{unit} ({mm_val:.0f}mm) 超过超声可探及范围"
    return None
