"""模板路由规则 — 预分类 + 路径分派"""
import re
from typing import Optional

# ── 12类预分类规则 ──
ROUTES = [
    {
        "name": "fetal",
        "keywords": ["胎儿","孕囊","胎盘","羊水","脐带","胎心","双顶径","BPD","头围","腹围","股骨长","四维","中孕","早孕","排畸"],
        "exam_types": ["产科超声"],
        "category": "fetal",
        "priority": 100,
    },
    {
        "name": "cardiac",
        "keywords": ["心脏","二尖瓣","三尖瓣","主动脉瓣","心包","EF","EF%","FS","E/A","房室","室间隔","左室","右房","心功能"],
        "exam_types": ["心脏超声"],
        "category": "cardiac",
        "priority": 80,
    },
    {
        "name": "thyroid",
        "keywords": ["甲状腺","甲状旁腺","峡部","TI-RADS","TI?RADS"],
        "exam_types": ["甲状腺超声"],
        "category": "thyroid",
        "priority": 80,
    },
    {
        "name": "breast",
        "keywords": ["乳腺","腋窝","乳头","BI-RADS","BI?RADS"],
        "exam_types": ["乳腺超声"],
        "category": "breast",
        "priority": 80,
    },
    {
        "name": "liver_gall",
        "keywords": ["肝脏","肝内","门静脉","胆囊","胆总管","胰腺","脾脏"],
        "exam_types": ["腹部超声"],
        "category": "abdomen",
        "priority": 60,
    },
    {
        "name": "kidney",
        "keywords": ["双肾","肾脏","集合系统","肾盂","输尿管","肾上腺"],
        "exam_types": ["腹部超声"],
        "category": "abdomen",
        "priority": 60,
    },
    {
        "name": "gynecology",
        "keywords": ["子宫","卵巢","附件","盆腔","内膜","宫颈","阴道"],
        "exam_types": ["妇科超声"],
        "category": "gynecology",
        "priority": 80,
    },
    {
        "name": "prostate",
        "keywords": ["前列腺","膀胱","精囊","睾丸","附睾"],
        "exam_types": ["泌尿超声"],
        "category": "urology",
        "priority": 80,
    },
    {
        "name": "vascular",
        "keywords": ["颈动脉","椎动脉","颈总","颈内","颈外","IMT","斑块","下肢血管","动脉"],
        "exam_types": ["血管超声"],
        "category": "vascular",
        "priority": 80,
    },
    {
        "name": "abdomen",
        "keywords": ["腹部","肝肾","腹部"],
        "exam_types": ["腹部超声"],
        "category": "abdomen",
        "priority": 30,
    },
    {
        "name": "other",
        "keywords": [],
        "exam_types": [],
        "category": "other",
        "priority": 0,
    },
]

# 器官关键词（用于多器官检测）
ORGAN_KEYWORDS = ["肝脏","胆囊","胰腺","脾脏","双肾","子宫","卵巢","附件","甲状腺","乳腺","心脏","颈动脉","前列腺","膀胱"]


def classify(text: str, exam_type: str = "") -> dict:
    """预分类输入文本

    Returns:
        {"route": 路由名, "category": 分类, "is_fetal": bool,
         "is_multi": bool, "organ_count": int, "priority": int}
    """
    best = ROUTES[-1]  # 默认兜底

    # 1. 按exam_type匹配
    if exam_type:
        for r in ROUTES:
            if exam_type in r["exam_types"]:
                # 检查关键词是否命中
                kw_hits = sum(1 for kw in r["keywords"] if kw in text)
                if kw_hits > 0 or not r["keywords"]:
                    if r["priority"] > best.get("priority", 0):
                        best = r
                    break

    # 2. 按关键词匹配（如果exam_type没命中）
    for r in sorted(ROUTES, key=lambda x: -x["priority"]):
        kw_hits = sum(1 for kw in r["keywords"] if kw in text)
        if kw_hits > 0:
            if r["priority"] > best.get("priority", 0):
                best = r
            break

    # 3. 多器官检测
    organ_count = sum(1 for o in ORGAN_KEYWORDS if o in text)
    is_multi = organ_count >= 3 or (len(text) > 100 and organ_count >= 2)

    return {
        "route": best["name"],
        "category": best["category"],
        "is_fetal": best["name"] == "fetal",
        "is_multi": is_multi,
        "organ_count": organ_count,
        "priority": best["priority"],
    }
