"""
超声语音报告系统 - 患者数据验证器
性别冲突、妊娠冲突检测
"""
from rule_engine import get_rule

FEMALE_ONLY_ORGANS = set(get_rule("validation.sex_guard.female_only", []))
MALE_ONLY_ORGANS = set(get_rule("validation.sex_guard.male_only", []))

PREG_KW = get_rule("validation.contradictions", [])


def detect_sex_conflict(text: str, patient_gender: str | None) -> str | None:
    """检测性别冲突, 返回警告文本"""
    if not patient_gender:
        return None
    if patient_gender == "男":
        conflicts = [o for o in FEMALE_ONLY_ORGANS if o in text]
        if conflicts:
            return "性别冲突: 患者为男性, 但文本包含女性器官: " + "、".join(conflicts)
    elif patient_gender == "女":
        conflicts = [o for o in MALE_ONLY_ORGANS if o in text]
        if conflicts:
            return "性别冲突: 患者为女性, 但文本包含男性器官: " + "、".join(conflicts)
    return None


def mask_conflict_organs(text: str, patient_gender: str | None) -> str:
    """将冲突器官词替换为 [待确认]"""
    if not patient_gender:
        return text
    if patient_gender == "男":
        for o in FEMALE_ONLY_ORGANS:
            text = text.replace(o, "[待确认]")
    elif patient_gender == "女":
        for o in MALE_ONLY_ORGANS:
            text = text.replace(o, "[待确认]")
    return text


def detect_pregnancy_conflict(text: str, exam_type: str, patient_gender: str | None) -> str | None:
    """检测妊娠词汇与患者上下文的冲突"""
    preg_cfg = get_rule("validation", {}).get("pregnancy_guard", {})
    pregnancy_kw = set(preg_cfg.get("pregnancy_kw", ["孕囊", "胎心", "胎盘", "羊水", "脐带", "早孕", "中孕"]))
    found = [kw for kw in pregnancy_kw if kw in text]
    if not found:
        return None
    if patient_gender == "男":
        return "严重冲突: 男性患者文本含妊娠相关词汇: " + "、".join(found)
    if exam_type and "产" not in exam_type and "妇" not in exam_type and "孕" not in exam_type:
        return "注意: 非妇产检查中出现妊娠词汇: " + "、".join(found)
    return None
