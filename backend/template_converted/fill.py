"""结构化超声模板填充引擎 — 通用版 template_fetal.py"""
import re
from cn_num import cn_to_arabic

_FILLED_CLS = 'voice'     # AI/正则填充值 → <b class="voice">
_EMPTY_CLS = 'unfill'     # 未填占位符 → <i class="unfill">

def fill_converted_template(
    raw_text: str,
    template_html: str,
    fields: dict[str, str],
    measurements: list,
    options: list,
    opt_reset: dict[str, tuple],
    option_keys: set,
) -> dict:
    """通用填充引擎 — 泛化了 template_fetal.py 的 fill_fetal_template()

    Args:
        raw_text: ASR文本
        template_html: 结构化HTML模板（含{_key}和[选项]组）
        fields: {_key: 中文标签} 映射
        measurements: [(regex, key), ...] 测量提取规则
        options: [(regex, key), ...] 选项检测规则
        opt_reset: {key: (mutual_keys...)} 互斥组
        option_keys: 所有选项key的集合
    """
    # 标准化
    text = cn_to_arabic(raw_text)
    text = re.sub(r'(\d+(?:\.\d+)?)\s*公斤', lambda m: str(int(float(m.group(1))*1000))+'克', text)
    text = re.sub(r'(\d+(?:\.\d+)?)\s*(?:kg|千克)', lambda m: str(int(float(m.group(1))*1000))+'克', text, flags=re.IGNORECASE)

    # 提取数值
    vals = {}
    for pat, key in measurements:
        m = re.search(pat, text)
        if m:
            try:
                vals[key] = m.group(1)
            except IndexError:
                pass  # 无捕获组的模式（如状态描述）

    # 提取选项
    opts = {}
    for pat, key in options:
        if re.search(pat, text):
            for rk in opt_reset.get(key, (key,)):
                opts[rk] = False
            opts[key] = True

    # === 构建HTML ===
    see = template_html

    # 第1步: 处理[选项组]
    def _clean(m):
        parts = m.group(1).split("|")
        for p in parts:
            for key in option_keys:
                val = opts.get(key)
                if val and ("{" + key + "}") in p:
                    cleaned = re.sub(r"\{[^}]+\}", "", p).strip()
                    if not cleaned:
                        return ""
                    if val is True:
                        return f' <b class="{_FILLED_CLS}">{cleaned}</b> '
                    return f" {cleaned} "
        first = re.sub(r"\{[^}]+\}", "", parts[0]).strip() if parts else ""
        return f" {first} "
    see = re.sub(r"\[([^\]]*?)\]", _clean, see)

    # 第2步: 替换数值占位符
    for key in sorted(fields.keys(), key=len, reverse=True):
        v = vals.get(key, "")
        if v and v != "___":
            see = see.replace("{" + key + "}", f'<b class="{_FILLED_CLS}">{v}</b>')
        else:
            see = see.replace("{" + key + "}", f'<i class="{_EMPTY_CLS}">__</i>')

    # 第3步: 清理残余
    for key in option_keys:
        see = see.replace("{" + key + "}", "")
    see = re.sub(r"\{_[^}]+\}", f'<i class="{_EMPTY_CLS}">__</i>', see)
    see = re.sub(r"[ ]{2,}", " ", see).strip()

    return {
        "patient_info": {"name": None, "gender": None, "age": None, "exam_id": None},
        "exam_info": {"modality": None, "device": None, "exam_date": None},
        "study_see": '<div class="rpt-html">' + see + '</div>',
        "study_hint": [],
        "recommendation": "",
        "_template_matched": "structured_template",
        "_method": "converted_fill",
    }
