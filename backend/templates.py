"""超声报告模板定义 — 五大类检查模板"""

TEMPLATES = {
    "abdomen": {
        "name": "腹部超声",
        "organs": ["肝脏", "胆囊", "胆总管", "胰腺", "脾脏", "左肾", "右肾", "膀胱", "前列腺", "子宫", "卵巢", "腹腔"],
        "fields": {
            "size": "大小（如'左叶68×142mm'）",
            "shape": "形态（正常/增大/缩小/饱满/不规则）",
            "border": "边界（清晰/模糊/光滑/不规则/毛糙）",
            "echo_pattern": "回声（均匀/不均匀/增粗/增强/减低/细腻）",
            "lesions": {
                "location": "位置",
                "size": "大小",
                "echo": "回声类型（无回声/低回声/等回声/高回声/混合回声/强回声）",
                "border": "边界（清晰/模糊/不规则/有包膜）",
                "morphology": "形态（圆形/类圆形/不规则形/分叶状）",
                "acoustic_shadow": "后方声影",
                "acoustic_enhancement": "后方增强",
                "blood_flow": "血流信号（无/少量/中等量/丰富）",
            },
            "intrahepatic_duct": "肝内胆管（未见扩张/轻度扩张/明显扩张）",
            "common_bile_duct": "胆总管内径",
        },
    },

    "cardiac": {
        "name": "心脏超声",
        "organs": [
            "左心室", "左心房", "右心室", "右心房",
            "二尖瓣", "主动脉瓣", "三尖瓣", "肺动脉瓣",
            "室间隔", "左室后壁", "心包",
        ],
        "fields": {
            "size": "内径(mm)",
            "thickness": "厚度(mm)",
            "motion": "运动（正常/减弱/增强/矛盾运动）",
            # 心脏特有字段
            "ef": "EF值(%)",
            "fs": "FS值(%)",
            "e_a_ratio": "E/A比值",
            # 反流/狭窄
            "regurgitation": "反流程度（无/轻度/中度/重度）",
            "stenosis": "狭窄程度（无/轻度/中度/重度）",
            "valve_area": "瓣口面积(cm²)",
            "velocity": "峰值流速(cm/s)",
            "gradient": "跨瓣压差(mmHg)",
            # 室间隔/后壁
            "ivs_motion": "室间隔运动（正常/反常）",
            "systolic_thickening": "收缩期增厚率(%)",
            # 心包
            "effusion": "积液（无/少量/中量/大量）",
            "effusion_depth": "积液深度(mm)",
            # 病灶
            "lesions": {
                "location": "位置",
                "size": "大小",
                "description": "描述（团块/血栓/赘生物/粘液瘤）",
                "mobility": "活动度",
            },
        },
    },

    "obgyn": {
        "name": "妇产超声",
        "organs": ["子宫", "宫颈", "左侧卵巢", "右侧卵巢", "盆腔"],
        "fields": {
            "size": "大小(如'72×52×45mm')",
            "position": "位置（前位/后位/中位）",
            "myometrium": "肌壁回声（均匀/不均匀）",
            "endometrium": "内膜厚度(mm)",
            "shape": "形态（规则/不规则）",
            "lesions": {
                "location": "位置",
                "size": "大小",
                "echo": "回声类型",
                "border": "边界",
                "description": "描述（肌瘤/囊肿/息肉/占位/畸胎瘤）",
            },
            "pelvic_fluid": "盆腔积液深度(mm)",
        },
        # 产科专用子模板（有胎儿时才用）
        "fetus_schema": {
            "bpd": "双顶径(mm)",
            "hc": "头围(mm)",
            "ac": "腹围(mm)",
            "fl": "股骨长(mm)",
            "hr": "胎心率(bpm)",
            "efw": "估测体重(g)",
            "ga_by_biometry": "超声孕周",
            "placenta_position": "胎盘位置（前壁/后壁/宫底/侧壁）",
            "placenta_grade": "胎盘成熟度（0/I/II/III）",
            "placenta_thickness": "胎盘厚度(mm)",
            "placenta_to_os": "胎盘下缘距宫颈内口(mm)",
            "afi": "羊水指数(mm)",
            "mvp": "最大羊水深度(mm)",
            "presentation": "胎位（头位/臀位/横位）",
            "cord_vessels": "脐血管数",
            "fetal_anomaly": "胎儿结构异常描述",
        },
    },

    "vascular": {
        "name": "血管超声",
        "organs": ["颈总动脉", "颈内动脉", "颈外动脉", "椎动脉", "下肢动脉", "下肢静脉", "腹主动脉"],
        "fields": {
            "imt": "内膜中层厚度(mm)",
            "diameter": "内径(mm)",
            "plaques": {
                "location": "位置",
                "size": "大小",
                "echo": "回声类型（低回声/等回声/高回声/混合回声）",
                "stenosis": "狭窄程度(%)",
            },
            "flow_velocity": {
                "psv": "收缩期峰值流速(cm/s)",
                "edv": "舒张末期流速(cm/s)",
                "ri": "阻力指数",
            },
            "thrombus": {
                "location": "位置",
                "extent": "范围",
                "recanalization": "再通情况",
            },
            "aneurysm": {
                "location": "位置",
                "diameter": "最大内径(mm)",
                "length": "长度(mm)",
            },
        },
    },

    "thyroid": {
        "name": "甲状腺/乳腺/小器官超声",
        "organs": ["甲状腺左叶", "甲状腺右叶", "甲状腺峡部", "左侧乳腺", "右侧乳腺",
                   "左侧腮腺", "右侧腮腺", "左侧睾丸", "右侧睾丸", "淋巴结"],
        "fields": {
            "size": "大小",
            "echo": "回声（均匀/不均匀/减低/增强）",
            "vascularity": "血供（正常/增多/火海征）",
            "glandular": "腺体结构",
            "nodules": {
                "location": "位置",
                "size": "大小",
                "echo": "回声类型",
                "border": "边界（清晰/模糊/不规则）",
                "shape": "形态（规则/不规则/纵横比>1）",
                "calcification": "钙化（无/微钙化/粗大钙化）",
                "tirads": "TI-RADS分类（1/2/3/4a/4b/4c/5）",
                "birads": "BI-RADS分类",
            },
        },
    },
}

# 模板自动匹配规则
TEMPLATE_MATCH = {
    "腹部": "abdomen", "肝胆": "abdomen", "泌尿": "abdomen",
    "心脏": "cardiac", "心超": "cardiac", "心彩": "cardiac",
    "妇科": "obgyn", "妇产": "obgyn", "产科": "obgyn", "子宫": "obgyn", "卵巢": "obgyn",
    "颈动脉": "vascular", "下肢血管": "vascular", "血管": "vascular", "下肢静脉": "vascular",
    "甲状腺": "thyroid", "乳腺": "thyroid", "小器官": "thyroid", "睾丸": "thyroid", "腮腺": "thyroid",
}


def match_template(exam_type: str) -> str:
    """根据检查类型自动匹配模板"""
    for keyword, tpl in TEMPLATE_MATCH.items():
        if keyword in exam_type:
            return tpl
    return "abdomen"  # 默认腹部


def template_prompt(tpl_key: str) -> str:
    """为指定模板生成 LLM 结构化提示词中的字段说明部分"""
    tpl = TEMPLATES.get(tpl_key, TEMPLATES["abdomen"])
    organs = "、".join(tpl["organs"])

    def _fields_desc(fields, indent=6):
        lines = []
        sp = " " * indent
        for k, v in fields.items():
            if isinstance(v, dict):
                lines.append(f"{sp}{k}: {{")
                lines.extend(_fields_desc(v, indent + 2))
                lines.append(f"{sp}}}")
            else:
                lines.append(f'{sp}"{k}": "{v}"')
        return lines

    desc_lines = [
        f'  "findings": [',
        f'      {{',
        f'        "organ": "{organs}之一",',
    ]
    desc_lines.extend(_fields_desc(tpl["fields"], 8))
    desc_lines.append("      }")
    desc_lines.append("  ]")

    # 产科额外说明
    if tpl_key == "obgyn":
        desc_lines.append("")
        desc_lines.append("  // 如果有胎儿，在 findings 中额外添加一条:")
        desc_lines.append('  {"organ": "胎儿", ...胎儿测量字段...}')
        fetus_lines = [f'      "{k}": "{v}"' for k, v in tpl.get("fetus_schema", {}).items()]
        desc_lines.extend(fetus_lines)

    return "\n".join(desc_lines)
