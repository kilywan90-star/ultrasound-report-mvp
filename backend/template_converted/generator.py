"""CSV模板 → 结构化HTML模板 转换器

从 1长沙范本.csv 读取模板，将 INFO1 中的测量槽位(mm)替换为 {_key} 占位符，
输出为 Python 模块文件（.py），供 fill.py 使用。
"""
import re, csv, os, json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_KNOWLEDGE = _HERE.parent / "knowledge"
_CSV_PATH = _KNOWLEDGE / "1长沙范本.csv"
_OUTPUT_DIR = _HERE

# 测量字段上下文 → key 映射表
_MEASUREMENT_KEY_MAP = [
    (r"大小|大小约", "size"),
    (r"长径|长度|长约", "length"),
    (r"厚|厚度|厚约", "thick"),
    (r"宽|宽度|宽约", "width"),
    (r"深|深度|深约", "depth"),
    (r"内径|直径|径", "diameter"),
    (r"斜径", "oblique"),
    (r"前后径", "ap"),
    (r"横径", "transverse"),
    (r"上下径", "vertical"),
    (r"面积", "area"),
    (r"周长", "perimeter"),
]

# 反义词对（用于检测选项组）
_ANTONYM_PAIRS = None


def _load_antonyms():
    global _ANTONYM_PAIRS
    if _ANTONYM_PAIRS is not None:
        return _ANTONYM_PAIRS
    ap_path = _KNOWLEDGE / "antonym_pairs.json"
    if ap_path.exists():
        with open(ap_path, "r", encoding="utf-8") as f:
            _ANTONYM_PAIRS = json.load(f)
    else:
        _ANTONYM_PAIRS = {}
    return _ANTONYM_PAIRS


def _infer_key_from_context(prefix: str) -> str:
    """根据测量值前面的文本推断key名"""
    for pat, key in _MEASUREMENT_KEY_MAP:
        if re.search(pat, prefix):
            return key
    # 回退：取最后两个汉字
    chars = re.findall(r'[一-鿿]', prefix)
    if chars:
        return ''.join(chars[-2:])
    return "m"


def _detect_option_groups(info1: str) -> list[tuple[int, int, str, str, str]]:
    """检测 info1 中的选项组（反义词对）

    Returns: [(start, end, word_A, word_B, group_key), ...]
    """
    antonyms = _load_antonyms()
    found = []
    for word_a, word_b in antonyms.items():
        if isinstance(word_b, str):
            # 单个反义词对
            for a, b in [(word_a, word_b), (word_b, word_a)]:
                pos_a = info1.find(a)
                pos_b = info1.find(b)
                if pos_a >= 0 and pos_b >= 0:
                    start = min(pos_a, pos_b)
                    end = max(pos_a, pos_b) + max(len(a), len(b))
                    key = f"_{a[:2]}_{b[:2]}"
                    found.append((start, end, a, b, key))
        elif isinstance(word_b, list):
            for wb in word_b:
                pos_a = info1.find(word_a)
                pos_b = info1.find(wb)
                if pos_a >= 0 and pos_b >= 0:
                    start = min(pos_a, pos_b)
                    end = max(pos_a, pos_b) + max(len(word_a), len(wb))
                    key = f"_{word_a[:2]}_{wb[:2]}"
                    found.append((start, end, word_a, wb, key))
    return found


def _parse_info1_to_html(info1: str) -> tuple[str, dict[str, str], list, list, dict, set]:
    """将原始INFO1转换为结构化HTML

    Returns:
        (html, fields, measurements_patterns, options_list, opt_reset, option_keys)
    """
    if not info1:
        return "", {}, [], [], {}, set()

    fields = {}
    measurements_patterns = []
    options_list = []
    opt_reset = {}
    option_keys = set()

    # 先检测选项组
    opt_groups = _detect_option_groups(info1)

    # 分割段落（按换行或'。'）
    paragraphs = re.split(r'(?<=[。；!?])|\\n', info1)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    html_parts = []
    meas_counter = 0

    for para in paragraphs:
        # 检查是否是标题（末尾无句号，较短）
        is_label = len(para) < 30 and not para.endswith('。') and not para.endswith('；')
        current = para

        # --- 处理选项组 ---
        for (start, end, a, b, key) in opt_groups:
            if a in current and b in current:
                current = current.replace(a, f"[{{{key}_A}}{a}|{{{key}_B}}{b}]", 1)
                options_list.append((re.escape(a), f"{key}_A"))
                options_list.append((re.escape(b), f"{key}_B"))
                opt_reset[f"{key}_A"] = (f"{key}_A", f"{key}_B")
                option_keys.add(f"{key}_A")
                option_keys.add(f"{key}_B")

        # --- 处理测量槽位 ---
        # 模式1: 数值+mm/毫米 (如 "约 5 mm" → 提取"5"为示例值后删掉)
        def _replace_meas(m):
            nonlocal meas_counter
            prefix = current[max(0, m.start()-12):m.start()]
            key = _infer_key_from_context(prefix)
            field_key = f"_{key}_{meas_counter}"

            # 生成上下文提取正则
            ctx = re.sub(r'\s*[×xX\*乘]\s*$', '', prefix.strip())  # 去掉尾部x符号
            # 取最后一段汉字: 过滤掉x、mm、数字等非汉字
            ctx_chars = re.findall(r'[一-鿿]+', ctx)
            if ctx_chars:
                search_ctx = ctx_chars[-1]
                if len(search_ctx) >= 1:
                    # 关键: 用 search_ctx 匹配后面的数字 + 可选的单位
                    pat = f"(?:{re.escape(search_ctx)})\\s*(?:约|为|是|大)?\\s*(\\d+(?:\\.\\d+)?)\\s*(?:mm|毫米|cm|厘米)"
                    # 如果这个正则和已有的一样, 跳过
                    if not any(p[1] == field_key for p in measurements_patterns):
                        measurements_patterns.append((pat, field_key))

            fields[field_key] = ctx[-8:] if ctx else f"测量{meas_counter}"
            meas_counter += 1
            return f"{{{field_key}}}mm"

        # 先清理残留的旧格式"x"占位符和空格分隔的mm（如 "x mm" → "mm", " x mm" → "mm"）
        current = re.sub(r'[×xX\*乘]\s*(?=\{|mm|毫米)', '', current)
        current = re.sub(r'\b[×xX\*乘]\s*', '', current)

        current = re.sub(r'(?:约|大小|厚|长|宽|深|内径|径)?\s*(?:\d+(?:\.\d+)?)?\s*(?:mm|毫米)', _replace_meas, current)

        # 模式2: × 模式 (如 "约 × mm" 或 "约 5×3 mm")
        def _replace_x(m):
            nonlocal meas_counter
            prefix = current[max(0, m.start()-10):m.start()]
            key = _infer_key_from_context(prefix)
            field_key = f"_{key}_{meas_counter}"

            ctx = re.sub(r'\s*[×xX\*乘]\s*$', '', prefix.strip())
            ctx_chars = re.findall(r'[一-鿿]+', ctx)
            if ctx_chars:
                search_ctx = ctx_chars[-1]
                if len(search_ctx) >= 1:
                    pat = f"(?:{re.escape(search_ctx)})\\s*(?:约|为|是|大)?\\s*(\\d+(?:\\.\\d+)?)\\s*[×xX\\*乘]\\s*(\\d+(?:\\.\\d+)?)"
                    if not any(p[1] == field_key for p in measurements_patterns):
                        measurements_patterns.append((pat, field_key))

            fields[field_key] = ctx[-6:] if ctx else f"测量{meas_counter}"
            meas_counter += 1
            return f"× {{{field_key}}}mm"

        current = re.sub(r'[×xX\*乘]\s*mm', _replace_x, current)

        # 清理示例数值 (如 "5{_size_0}mm" → "{_size_0}mm")
        current = re.sub(r'(\d+(?:\.\d+)?)(?=\{[^}]+\}mm)', '', current)
        current = re.sub(r'(\d+(?:\.\d+)?)(?=\{[^}]+\}mm)', '', current)  # 再跑一遍清理残余

        # 包裹段落
        if is_label:
            html_parts.append(f'<b class="rpt-label">{current}</b>')
        else:
            html_parts.append(f'<div class="rpt-sec">{current}</div>')

    html = "\n".join(html_parts)

    # 如果没有选项组，生成简单的"无异常/有异常"选项
    if not options_list:
        for kw_neg in ["未见", "正常", "光滑", "规则", "清晰"]:
            if kw_neg in info1:
                options_list.append((re.escape(kw_neg), f"_norm_{kw_neg}"))
                option_keys.add(f"_norm_{kw_neg}")
                break

    return html, fields, measurements_patterns, options_list, opt_reset, option_keys


def _categorize_template(name: str, info1: str, group: str, module: str) -> str:
    """根据模板名和内容推断分类"""
    category_map = {
        "心脏": ["心脏", "心内", "二尖瓣", "三尖瓣", "主动脉瓣", "室间隔", "心包", "EF", "FS"],
        "腹部": ["肝脏", "胆囊", "胰腺", "脾脏", "双肾", "腹部", "门静脉", "胆总管"],
        "甲状腺": ["甲状腺", "甲状旁腺", "峡部"],
        "乳腺": ["乳腺", "腋窝", "乳头", "乳晕"],
        "妇科": ["子宫", "卵巢", "附件", "盆腔", "内膜", "宫颈"],
        "泌尿": ["前列腺", "膀胱", "精囊", "睾丸", "附睾"],
        "血管": ["颈动脉", "椎动脉", "颈总", "颈内", "颈外", "IMT", "斑块", "下肢血管"],
        "产科": ["胎儿", "孕囊", "胎盘", "羊水", "脐带", "胎心", "BPD", "双顶径"],
    }

    text = name + info1
    scores = {}
    for cat, kws in category_map.items():
        score = sum(1 for kw in kws if kw in text)
        if score > 0:
            scores[cat] = score

    if group and "心" in group:
        scores["心脏"] = scores.get("心脏", 0) + 5
    if group and ("腹" in group or "肝" in group or "胆" in group or "脾" in group):
        scores["腹部"] = scores.get("腹部", 0) + 5

    if scores:
        return max(scores, key=scores.get)
    return "其他"


def _generate_module(templates: list[dict], module_name: str, category: str) -> str:
    """生成单个模块的Python源码"""
    lines = [
        f'"""自动生成 — {module_name} 结构化模板"""',
        'from template_converted import register_templates',
        '',
        f'_TPL = {{',
    ]

    for tpl in templates:
        name = tpl["name"]
        info1 = tpl.get("info1", "")
        info2 = tpl.get("info2", "")
        html, fields, meas, opts, opt_reset, option_keys = _parse_info1_to_html(info1)

        # 转义HTML
        html_escaped = html.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n')

        lines.append(f"    '{name}': {{")
        lines.append(f"        'html': '{html_escaped}',")
        lines.append(f"        'fields': {json.dumps(fields, ensure_ascii=False)},")

        # 测量提取正则
        if meas:
            meas_json = json.dumps(meas, ensure_ascii=False)
            lines.append(f"        'measurements': {meas_json},")
        else:
            lines.append(f"        'measurements': [],")

        # 选项提取
        if opts:
            opts_json = json.dumps(opts, ensure_ascii=False)
            lines.append(f"        'options': {opts_json},")
        else:
            lines.append(f"        'options': [],")

        # 互斥组
        opt_reset_json = {}
        for k, v in opt_reset.items():
            opt_reset_json[k] = list(v) if isinstance(v, tuple) else v
        lines.append(f"        'opt_reset': {json.dumps(opt_reset_json, ensure_ascii=False)},")

        # option_keys
        ok_json = json.dumps(list(option_keys), ensure_ascii=False)
        lines.append(f"        'option_keys': {ok_json},")

        lines.append(f"    }},")

    lines.append('}')
    lines.append('')
    lines.append(f"register_templates(_TPL, category='{category}')")
    lines.append('')
    return '\n'.join(lines)


def run():
    """主转换入口"""
    if not _CSV_PATH.exists():
        print(f"[generator] CSV不存在: {_CSV_PATH}")
        return

    with open(_CSV_PATH, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # 收集有效模板
    templates = []
    seen_names = set()
    for row in rows:
        name = (row.get("DISCNAME") or "").strip()
        info1 = (row.get("INFO1") or "").strip()
        if not name or name in ("0", "NULL") or not info1:
            continue
        if name in seen_names:
            continue
        seen_names.add(name)
        info2 = (row.get("INFO2") or "").strip()
        group = (row.get("DISCGROUP") or "").strip()
        module = (row.get("MODULENAME") or "").strip()

        templates.append({
            "name": name,
            "info1": info1,
            "info2": info2,
            "group": group,
            "module": module,
        })

    print(f"[generator] CSV加载: {len(templates)} 有效模板")

    # 分类
    categories = {}
    for tpl in templates:
        cat = _categorize_template(tpl["name"], tpl["info1"], tpl["group"], tpl["module"])
        categories.setdefault(cat, []).append(tpl)

    print(f"[generator] 分类统计:")
    for cat, ctpls in sorted(categories.items(), key=lambda x: -len(x[1])):
        print(f"  {cat}: {len(ctpls)}")

    # 生成模块文件
    module_map = {
        "腹部": ("abdomen", "腹部"),
        "心脏": ("cardiac", "心脏"),
        "甲状腺": ("thyroid", "甲状腺"),
        "乳腺": ("breast", "乳腺"),
        "妇科": ("gynecology", "妇科"),
        "泌尿": ("urology", "泌尿"),
        "血管": ("vascular", "血管"),
        "产科": ("obstetrics", "产科"),
        "其他": ("other", "其他"),
    }

    output_dir = _OUTPUT_DIR

    for cat, ctpls in categories.items():
        file_key, _ = module_map.get(cat, ("other", "其他"))
        code = _generate_module(ctpls, file_key, cat)
        out_path = output_dir / f"{file_key}.py"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(code)
        print(f"[generator] 生成: {out_path.name} ({len(ctpls)} 模板)")

    # 生成注册器导入代码
    import_lines = []
    for cat, ctpls in categories.items():
        file_key, _ = module_map.get(cat, ("other", "其他"))
        import_lines.append(f"from template_converted.{file_key} import *  # {len(ctpls)} templates")

    print(f"\n[generator] 完成! 请在 __init__.py 中添加:")
    for line in import_lines:
        print(f"  {line}")

    print(f"\n总计: {len(templates)} 模板 → {len(categories)} 类别")


if __name__ == "__main__":
    run()
