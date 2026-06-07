#!/usr/bin/env python3
"""
P1-1: 363个模板标签三级分类, 替换前端固定86标签
输出: knowledge/template_tags_v2.json
"""
import json, re
from pathlib import Path

def load_templates():
    with open(Path(__file__).resolve().parent / "knowledge/template_fields.json", encoding="utf-8") as f:
        return json.load(f)["templates"]

def classify_level3(name, category):
    """三级子分类: 根据模板名+一级分类进行细分类"""
    # 妇产科
    if "胎儿" in name or "孕" in name or "胎" in name or "妊娠" in name or "早孕" in name or "中孕" in name or "晚孕" in name or "胎盘" in name or "羊水" in name or "脐带" in name or "BPD" in name:
        return "产科"
    if "子宫" in name or "内膜" in name or "宫颈" in name or "节育" in name:
        return "子宫"
    if "卵巢" in name or "囊肿" in name:
        if "卵巢" in name: return "卵巢"
    if "输卵管" in name or "盆腔" in name or "附件" in name:
        return "附件/盆腔"

    # 腹部
    if "肝" in name or "肝硬" in name or "脂肪肝" in name or "肝炎" in name or "肝囊肿" in name or "肝血" in name or "肝内" in name:
        return "肝脏"
    if "胆囊" in name or "胆" in name or "胆石" in name or "胆息肉" in name:
        return "胆囊/胆道"
    if "胰" in name:
        return "胰腺"
    if "脾" in name:
        return "脾脏"
    if "肾" in name or "肾炎" in name or "肾囊肿" in name or "肾结石" in name or "肾积水" in name:
        return "肾脏"
    if "膀胱" in name or "输尿管" in name:
        return "膀胱/输尿管"
    if "前列腺" in name:
        return "前列腺"
    if "胃肠" in name or "胃" in name or "肠" in name or "阑尾" in name or "腹" in name:
        return "胃肠道"
    if "结石" in name:
        return "结石类"

    # 心脏
    if "瓣" in name or "二尖瓣" in name or "主动脉瓣" in name or "三尖瓣" in name or "肺动脉瓣" in name:
        return "瓣膜病"
    if "室间隔" in name or "心房" in name or "心室" in name or "房室" in name:
        return "心腔/心壁"
    if "心包" in name or "积液" in name:
        return "心包"
    if "冠心" in name or "心肌" in name or "缺血" in name:
        return "冠心病/心肌"

    # 甲状腺乳腺
    if "甲状腺" in name:
        return "甲状腺"
    if "乳腺" in name:
        return "乳腺"
    if "淋巴结" in name:
        return "淋巴结"
    if "腮腺" in name:
        return "腮腺"
    if "睾丸" in name or "附睾" in name or "阴囊" in name or "精索" in name:
        return "男性浅表"

    # 血管
    if "颈动脉" in name or "颈" in name:
        return "颈动脉/颅外"
    if "椎动脉" in name or "TCD" in name or "基底动脉" in name or "脑动脉" in name or "经颅" in name:
        return "脑血管/TCD"
    if "下肢" in name or "静脉" in name:
        return "下肢血管"
    if "动脉" in name or "血管" in name:
        return "动脉/血管"

    # 泌尿
    if "前列腺" in name:
        return "前列腺"
    if "膀胱" in name:
        return "膀胱"
    if "肾脏" in name or "肾" in name:
        return "肾脏"

    # 骨骼肌肉
    if "膝" in name:
        return "膝关节"
    if "髋" in name:
        return "髋关节"
    if "肩" in name:
        return "肩关节"
    if "踝" in name or "腕" in name:
        return "小关节"
    if "骨" in name or "腱" in name or "肌肉" in name:
        return "骨骼/肌腱"

    return "其他"

# ============================================================
CATEGORY_MAP = {
    "妇产(子宫/卵巢/胎儿)": "妇产",
    "腹部(肝胆胰脾肾等)": "腹部",
    "心脏(瓣膜/心腔/心包)": "心脏",
    "甲状腺/乳腺/浅表": "浅表",
    "血管(TCD/颈动脉/下肢)": "血管",
    "泌尿(前列腺/膀胱)": "泌尿",
    "骨骼肌肉(关节/肌腱)": "骨骼肌肉",
    "通用": "通用",
}

def main():
    templates = load_templates()
    result = {
        "_description": "模板标签三级分类 v2 — 363个模板完整标签库",
        "_total": 0,
        "categories": [],
    }

    for cat in templates:
        cat_name = cat["name"]
        level1 = cat_name
        entries = []

        for t in cat["templates"]:
            level3 = classify_level3(t["name"], cat_name)
            entries.append({
                "name": t["name"],
                "level1": level1,
                "level2": CATEGORY_MAP.get(level1, "通用"),  # 二级映射
                "level3": level3,
                "template_id": t["id"],
                "fields_count": len(t["fields"]),
            })

        # 按三级分类排序
        entries.sort(key=lambda x: (x["level3"], x["name"]))

        result["categories"].append({
            "level1": level1,
            "level2": CATEGORY_MAP.get(level1, "通用"),
            "templates": entries,
            "count": len(entries),
        })

        result["_total"] += len(entries)

    # 保存
    out = Path(__file__).resolve().parent / "knowledge" / "template_tags_v2.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 统计
    print("Template Tags v2 — 363 templates, 3-level classification")
    print("=" * 60)
    for cat in result["categories"]:
        print("%-30s %3d templates" % (cat["level1"], len(cat["templates"])))
        # 三级子分类
        level3_counts = {}
        for t in cat["templates"]:
            l3 = t["level3"]
            level3_counts[l3] = level3_counts.get(l3, 0) + 1
        for l3, cnt in sorted(level3_counts.items(), key=lambda x: -x[1]):
            print("  %-28s %3d" % ("  -> " + l3, cnt))

    print()
    print("Output: knowledge/template_tags_v2.json (%.0f KB)" % (out.stat().st_size / 1024))


if __name__ == "__main__":
    main()
