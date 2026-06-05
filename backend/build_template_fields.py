#!/usr/bin/env python3
"""
模板库结构化转换: 将 模板表.csv (558条有效模板)
拆解为 字段级数据结构, 每条模板 = 固定文本段 + 可变字段列表(每个字段8项属性)
输出: template_fields.json
"""
import csv, re, json
from pathlib import Path
from collections import defaultdict

CSV_PATH = Path(os.environ.get("TEMPLATE_CSV", ""))
OUT_PATH = Path(__file__).resolve().parent / "knowledge" / "template_fields.json"

# ============================================================
# 1. 解析模板表
# ============================================================
def parse_all_templates():
    rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8-sig")))
    templates = []

    for row in rows:
        name = (row.get("DISCNAME") or "").strip()
        if not name or name in ("0", "NULL"): continue
        info1 = (row.get("INFO1") or "").strip()
        info2 = (row.get("INFO2") or "").strip()
        mod = (row.get("MODULENAME") or "general").strip()
        grp = (row.get("DISCGROUP") or "").strip()
        visc = (row.get("VISCNAME") or "").strip()

        if not info1 or len(info1) < 20: continue
        if not re.search(r'[一-鿿]{4,}', info1): continue

        # 解析固定文本段和可变字段
        segments, fields = parse_info1(info1)

        # 确定分类
        category = classify_template(name, info1, mod, visc)

        templates.append({
            "template_id": "temp_%04d" % len(templates),
            "name": name,
            "category": category,
            "module": mod,
            "organ": visc,
            "group": grp,
            "segments": segments,
            "fields": fields,
            "raw_info1": info1[:500],
            "raw_info2": info2[:200] if info2 else "",
        })

    return templates


# ============================================================
# 2. 解析INFO1: 拆分固定文本段和提取可变字段
# ============================================================
def parse_info1(info1):
    """将 INFO1 拆分为 segments (固定文本) + fields (可变字段)"""
    segments = []
    fields = []
    field_idx = 1

    # 第一步: 以 + 号分割段落
    paragraphs = info1.split("+")

    for para_idx, para in enumerate(paragraphs):
        para = para.strip()
        if not para: continue

        # 提取 [选项;选项] 语法 → 可变字段 (单选)
        options = re.findall(r"\[([^\]]+)\]", para)
        for opt in options:
            choices = [c.strip() for c in opt.split(";") if c.strip()]
            if len(choices) >= 2:
                field_name = choices[0][:8]  # 取第一个选项前8字作为字段名
                fields.append({
                    "field_id": "fld_%s_%03d" % (para_idx, field_idx),
                    "name": field_name,
                    "type": "enum",
                    "choices": choices,
                    "paragraph": para_idx,
                    "synonyms": choices[:3],
                    "required": False,
                })
                field_idx += 1

        # 提取 mm 占位符 → 可变字段 (数值)
        mm_positions = [m.start() for m in re.finditer(r"(?<!\d)mm(?![\d×xX\*])", para)]
        for pos in mm_positions:
            # 找 mm 前面最近的文字作为字段名
            before = para[max(0, pos-15):pos].strip()
            field_name = before[-6:] if len(before) > 6 else before
            field_name = re.sub(r"[  ×xX\*\-]+", "", field_name)
            if not field_name: field_name = "unk"
            fields.append({
                "field_id": "fld_%s_%03d" % (para_idx, field_idx),
                "name": field_name,
                "type": "numeric",
                "unit": "mm",
                "paragraph": para_idx,
                "synonyms": [field_name],
                "required": False,
            })
            field_idx += 1

        # 去掉选项和mm后, 剩余文字作为固定文本段
        fixed = para
        fixed = re.sub(r"\[[^\]]+\]", "", fixed)  # 去选项
        fixed = re.sub(r"\bmm\b", "__mm__", fixed)  # 标mm占位
        fixed = fixed.strip()
        if fixed and len(fixed) > 3:
            segments.append({
                "paragraph": para_idx,
                "type": "fixed",
                "text": fixed,
            })

    return segments, fields


# ============================================================
# 3. 模板分类
# ============================================================
def classify_template(name, info1, mod, visc):
    text = name + info1
    if any(k in text for k in ["子宫", "卵巢", "输卵管", "盆腔", "宫颈", "阴道", "胎儿", "妊娠", "孕", "胎盘", "羊水", "附件", "内膜"]):
        return "obgyn"
    if any(k in text for k in ["甲状腺", "乳腺", "腮腺", "淋巴结", "睾丸", "附睾", "阴囊"]):
        return "thyroid_breast"
    if any(k in text for k in ["心脏", "二尖瓣", "主动脉瓣", "三尖瓣", "心室", "心房", "心包", "室间隔", "肺动脉"]):
        return "cardiac"
    if any(k in text for k in ["颈动脉", "椎动脉", "基底动脉", "动脉", "静脉", "血栓", "斑块", "流速", "TCD", "经颅"]):
        return "vascular"
    if any(k in text for k in ["前列腺", "膀胱", "输尿管", "精囊", "尿道", "残余尿"]):
        return "urology"
    if any(k in text for k in ["肝脏", "胆囊", "胰腺", "脾脏", "肾脏", "胆管", "门静脉", "腹腔", "腹膜", "胃肠", "阑尾"]):
        return "abdomen"
    if any(k in text for k in ["膝关节", "髋关节", "肩关节", "踝关节", "腕", "肌腱", "肌肉", "骨骼"]):
        return "musculoskeletal"
    return "general"


# ============================================================
# 4. 生成结构化JSON
# ============================================================
def main():
    templates = parse_all_templates()
    print("Parsed %d templates" % len(templates))

    # 按分类统计
    cats = defaultdict(int)
    for t in templates:
        cats[t["category"]] += 1
    print("\nCategory distribution:")
    for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
        print("  %-20s %3d" % (cat, cnt))

    # 统计字段
    total_fields = sum(len(t["fields"]) for t in templates)
    total_segments = sum(len(t["segments"]) for t in templates)
    print("\nTotal fields: %d" % total_fields)
    print("Total fixed segments: %d" % total_segments)
    print("Fields per template: %.1f" % (total_fields / max(len(templates), 1)))
    print()

    # 输出样本
    for t in templates[:3]:
        print("=== %s [%s] ===" % (t["name"][:30], t["category"]))
        print("  Segments: %d" % len(t["segments"]))
        for s in t["segments"][:2]:
            print("    [S%d] %s" % (s["paragraph"], s["text"][:80]))
        print("  Fields: %d" % len(t["fields"]))
        for f in t["fields"][:3]:
            print("    [%s] %s (%s)" % (f["field_id"], f["name"][:20], f["type"]))
        print()

    # 写入JSON
    out = {
        "_description": "结构化模板库 — 字段级解析。每条模板=固定文本段+可变字段(8属性)",
        "_source": "模板表.csv (558条有效模板)",
        "_date": "2026-06-04",
        "_total_templates": len(templates),
        "_total_fields": total_fields,
        "template_categories": {
            "abdomen": "腹部(肝胆胰脾肾等)",
            "obgyn": "妇产(子宫/卵巢/胎儿)",
            "cardiac": "心脏(瓣膜/心腔/心包)",
            "thyroid_breast": "甲状腺/乳腺/浅表",
            "vascular": "血管(TCD/颈动脉/下肢)",
            "urology": "泌尿(前列腺/膀胱)",
            "musculoskeletal": "骨骼肌肉(关节/肌腱)",
            "general": "通用",
        },
        "templates": templates,
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("Output: %s (%.0f KB)" % (OUT_PATH, OUT_PATH.stat().st_size / 1024))
    return out


if __name__ == "__main__":
    main()
