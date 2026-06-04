"""
固定模板 + 意图识别 API
新增 /api/fixed-template/structure 端点:
  - 输入: text(ASR文本) + fixed_template(用户自定义固定模板, 可空)
  - 输出: 模板填充结果(study_see), 不修改模板原文, 只把变量填入
"""
import re, json
from pathlib import Path
from collections import defaultdict

# ============================================================
# 1. 模板知识库 (从模板表.csv 提取的7大类标签)
# ============================================================
TEMPLATE_TAGS = {
    "腹部": ["正常体检","脂肪肝","肝囊肿","肝硬化","胆囊息肉","胆囊结石","胆囊炎","肝血管瘤","胰腺炎","脾大","腹水","肝内钙化灶","肝实质回声改变","门静脉增宽","胆总管结石","胆管扩张","肾结石","肾囊肿","肾积水","综合腹部","双肾未见异常"],
    "妇产": ["早孕","中孕","晚孕","子宫肌瘤","卵巢囊肿","子宫内膜息肉","宫颈囊肿","盆腔积液","前置胎盘","异位妊娠","子宫腺肌症","多囊卵巢","输卵管积水","宫内节育器","剖宫产切口","附件囊肿"],
    "心脏": ["二尖瓣反流","主动脉瓣反流","三尖瓣反流","室间隔缺损","心包积液","左室舒张功能减低","左房增大","肺动脉高压","心肌肥厚","房间隔缺损","法洛四联症","冠心病"],
    "甲状腺乳腺": ["甲状腺结节","桥本氏甲状腺炎","乳腺增生","乳腺结节","乳腺纤维腺瘤","TI-RADS 3类","BI-RADS 2类","甲状腺弥漫性病变","甲状腺囊实性结节","甲状腺癌"],
    "血管": ["颈动脉斑块","颈动脉狭窄","椎动脉狭窄","下肢动脉硬化","深静脉血栓","动脉粥样硬化","锁骨下动脉狭窄","腹主动脉瘤","肾动脉狭窄"],
    "泌尿前列腺": ["前列腺增生","前列腺钙化","前列腺增生伴钙化","膀胱结石","膀胱憩室","膀胱残余尿","精索静脉曲张","睾丸鞘膜积液","附睾炎"],
    "其他": ["TCD正常","TCD异常","膝关节积液","髋关节积液","胸水定位","体表包块","腹股沟疝","阑尾炎","小儿肠套叠"],
}

# 固定模板样本 (从 report_structures.json 提取)
DEFAULT_TEMPLATES = {
    "腹部": "肝脏: {liver_size} {liver_echo} {liver_vessel}\n胆囊: {gall_size} {gall_wall} {gall_content}\n胰腺: {pancreas_size} {pancreas_echo}\n脾脏: {spleen_size} {spleen_echo}\n双肾: {kidney_size} {kidney_echo} {kidney_pelvis}\n{CDFI}",
    "妇产": "子宫: {uterus_pos} {uterus_size} {uterus_myo}\n内膜: {endometrium}\n卵巢: 左侧{left_ovary} 右侧{right_ovary}\n盆腔: {pelvis}",
    "心脏": "各房室: {chambers}\n室间隔与左室壁: {ivs_lvpw}\n瓣膜: {valves}\n心包: {pericardium}\n{CDFI}",
    "甲状腺乳腺": "甲状腺左叶: {left_thyroid}\n甲状腺右叶: {right_thyroid}\n峡部: {isthmus}\n{CDFI}",
    "血管": "颈总动脉: {cca}\n颈内动脉: {ica}\n颈外动脉: {eca}\n椎动脉: {va}\n{plaque}",
    "泌尿前列腺": "前列腺: {prostate_size} {prostate_echo}\n膀胱: {bladder}\n残余尿: {residual_urine}",
    "其他": "{custom}",
}

CATEGORY_MAP = {
    "abdomen": "腹部",
    "obgyn": "妇产",
    "cardiac": "心脏",
    "thyroid": "甲状腺乳腺",
    "vascular": "血管",
    "泌尿前列腺": "泌尿前列腺",
    "心血管": "血管",
    "其他": "其他",
}

# ============================================================
# 2. 意图识别: ASR文本 → 最匹配的模板类别
# ============================================================
def detect_template_category(text: str) -> dict:
    """
    识别 ASR 文本的意图, 返回 {category, template_key, confidence}
    优先级: 关键词→器官覆盖→长文本权重
    """
    score = defaultdict(float)

    # 类别关键词权重
    category_kw = {
        "妇产": {"子宫":20,"卵巢":15,"孕囊":30,"胎儿":20,"胎心":20,"胎盘":20,"羊水":20,"宫颈":12,"内膜":12,"早孕":25,"中孕":25,"盆腔":8},
        "心脏": {"二尖瓣":20,"主动脉瓣":20,"三尖瓣":20,"心包":18,"室间隔":18,"心室":15,"心房":15,"EF":12,"舒张":12,"反流":15},
        "血管": {"颈动脉":20,"椎动脉":18,"斑块":18,"IMT":15,"流速":12,"基底动脉":15,"动脉":8,"静脉":7},
        "甲状腺乳腺": {"甲状腺":20,"乳腺":20,"结节":10,"TI-RADS":18,"BI-RADS":18,"峡部":12,"腋窝":10},
        "泌尿前列腺": {"前列腺":20,"膀胱":15,"残余尿":15,"钙化灶":10,"睾丸":12,"附睾":12,"精索":10},
        "腹部": {"肝脏":15,"胆囊":15,"胰腺":15,"脾脏":12,"肾脏":12,"胆总管":12,"门静脉":12,"脂肪肝":18,"结石":10,"囊肿":8},
    }

    for cat, keywords in category_kw.items():
        for kw, weight in keywords.items():
            if kw in text:
                score[cat] += weight

    # 器官覆盖数量加分
    organ_sets = {
        "妇产": {"子宫","卵巢","宫颈","胎儿","胎盘","羊水","孕囊"},
        "心脏": {"二尖瓣","主动脉瓣","三尖瓣","心室","心房","室间隔","心包","肺动脉"},
        "腹部": {"肝脏","胆囊","胰腺","脾脏","肾脏"},
        "甲状腺乳腺": {"甲状腺","乳腺"},
        "血管": {"颈动脉","椎动脉","基底动脉","动脉","静脉"},
        "泌尿前列腺": {"前列腺","膀胱","睾丸","附睾"},
    }
    for cat, organs in organ_sets.items():
        hits = sum(1 for o in organs if o in text)
        if hits >= 2:
            score[cat] += hits * 5

    if not score:
        return {"category": "腹部", "template_key": "腹部", "confidence": 0.3, "is_fetal": False}

    best = max(score, key=score.get)
    conf = min(score[best] / 50, 0.99)

    # 心血管 → 血管 (统一类别名)
    unified = best
    if best == "心血管":
        unified = "血管"

    is_fetal = False
    if unified == "妇产":
        fetal_kw = {"胎儿","孕囊","胎心","胎盘","羊水","BPD","双顶径","股骨长","股骨","头围","腹围","胎位","早孕","中孕","晚孕","脐带"}
        is_fetal = any(kw in text for kw in fetal_kw)

    return {"category": unified, "template_key": unified, "confidence": conf, "is_fetal": is_fetal}


# ============================================================
# 3. 字段抽取: 从 ASR 文本中抽取变量 → 填入固定模板
# ============================================================
def extract_fields_for_template(text: str, category: str) -> dict:
    """从 ASR 文本中按模板类别抽取字段"""
    fields = {}

    if category == "妇产":
        # 子宫
        m = re.search(r'子宫.*?(前|后|中)[位]', text)
        if m: fields["uterus_pos"] = m.group(0)
        m = re.search(r'(?:宫体|子宫).*?(\d+\.?\d*)\s*[×xX乘]\s*(\d+\.?\d*)\s*[×xX乘]\s*(\d+\.?\d*)\s*(?:cm|厘米)', text)
        if m: fields["uterus_size"] = m.group(0)
        m = re.search(r'(?:肌壁|肌层).*?(均匀|不均匀)', text)
        if m: fields["uterus_myo"] = m.group(0)

        # 内膜
        m = re.search(r'(?:内膜|子宫内膜).*?(\d+\.?\d*)\s*(?:mm|毫米|cm)', text)
        if m: fields["endometrium"] = m.group(0)

        # 卵巢
        m = re.search(r'(?:左侧|左).*?卵巢.*?(\d+\.?\d*)\s*[×xX乘]\s*(\d+\.?\d*)\s*(?:cm|厘米)', text)
        if m: fields["left_ovary"] = m.group(0)
        m = re.search(r'(?:右侧|右).*?卵巢.*?(\d+\.?\d*)\s*[×xX乘]\s*(\d+\.?\d*)\s*(?:cm|厘米)', text)
        if m: fields["right_ovary"] = m.group(0)

        # 盆腔
        m = re.search(r'盆腔.*?((未见)?积液)', text)
        if m: fields["pelvis"] = m.group(0)

        # 胎儿字段
        m = re.search(r'孕囊.*?(\d+\.?\d*)\s*[×xX乘]\s*(\d+\.?\d*)\s*(?:cm|厘米)', text)
        if m: fields["uterus_pos"] = (fields.get("uterus_pos","") + " 孕囊" + m.group(0)).strip()
        m = re.search(r'胎心率?\s*(\d+)', text)
        if m: fields["endometrium"] = (fields.get("endometrium","") + " 胎心" + m.group(1)).strip()
        m = re.search(r'(?:胎盘).*?([前后左右]壁)', text)
        if m: fields["pelvis"] = (fields.get("pelvis","") + " 胎盘" + m.group(1)).strip()

    elif category == "腹部":
        # 肝脏
        m = re.search(r'肝脏.*?((正常|增大|回声增强|回声不均|脂肪肝))', text)
        if m: fields["liver_size"] = m.group(0)[:30]
        m = re.search(r'肝脏.*?(回声\S+)', text)
        if m: fields["liver_echo"] = m.group(1)
        m = re.search(r'(肝内血管|门静脉|肝静脉)\S*', text)
        if m: fields["liver_vessel"] = m.group(0)[:30]

        # 胆囊
        m = re.search(r'胆囊.*?((正常|增大|息肉|结石|沉积|小))', text)
        if m: fields["gall_size"] = m.group(0)[:30]
        m = re.search(r'囊壁\S*', text)
        if m: fields["gall_wall"] = m.group(0)[:20]
        m = re.search(r'(腔内|囊内)\S*', text)
        if m: fields["gall_content"] = m.group(0)[:30]

        # 胰腺
        m = re.search(r'胰腺.*?((正常|增大|回声\S+|胰管))', text)
        if m: fields["pancreas_size"] = m.group(0)[:20]
        m = re.search(r'胰腺.*?(回声\S+)', text)
        if m: fields["pancreas_echo"] = m.group(1)[:15]

        # 脾脏
        m = re.search(r'脾\S*.*?((正常|增大|缩小))', text)
        if m: fields["spleen_size"] = m.group(0)[:20]

        # 肾脏
        m = re.search(r'(双肾|肾脏).*?((正常|增大|结石|囊肿|积水|分离))', text)
        if m: fields["kidney_size"] = m.group(0)[:30]
        m = re.search(r'(集合系|肾盂)\S*', text)
        if m: fields["kidney_pelvis"] = m.group(0)[:20]

    elif category == "心脏":
        m = re.search(r'各房室\S*', text)
        if m: fields["chambers"] = m.group(0)[:30]
        m = re.search(r'(?:室间隔|IVS|左室壁|LVPW)\S*', text)
        if m: fields["ivs_lvpw"] = m.group(0)[:30]
        m = re.search(r'(二尖瓣|主动脉瓣|三尖瓣|肺动脉瓣)\S*', text)
        if m: fields["valves"] = m.group(0)[:40]
        m = re.search(r'(心包|积液)\S*', text)
        if m: fields["pericardium"] = m.group(0)[:20]

    elif category == "甲状腺乳腺":
        m = re.search(r'(左侧|左叶|右叶).*?(\d+\.?\d*)\s*[×xX乘]\s*(\d+\.?\d*)', text)
        if m: fields["left_thyroid"] = m.group(0)[:30]
        m = re.search(r'(右侧|右叶).*?(\d+\.?\d*)\s*[×xX乘]\s*(\d+\.?\d*)', text)
        if m: fields["right_thyroid"] = m.group(0)[:30]
        m = re.search(r'峡部.*?(\d+\.?\d*)', text)
        if m: fields["isthmus"] = m.group(0)[:20]

    elif category == "血管":
        m = re.search(r'(颈总动脉|CCA)\S*', text)
        if m: fields["cca"] = m.group(0)[:30]
        m = re.search(r'(颈内动脉|ICA)\S*', text)
        if m: fields["ica"] = m.group(0)[:30]
        m = re.search(r'(颈外动脉|ECA)\S*', text)
        if m: fields["eca"] = m.group(0)[:30]
        m = re.search(r'(椎动脉|VA)\S*', text)
        if m: fields["va"] = m.group(0)[:30]
        m = re.search(r'(斑块|IMT|内膜)\S*', text)
        if m: fields["plaque"] = m.group(0)[:40]

    elif category == "泌尿前列腺":
        m = re.search(r'前列腺.*?((大小|约)\S*)', text)
        if m: fields["prostate_size"] = m.group(0)[:30]
        m = re.search(r'前列腺.*?(回声\S+|钙化)', text)
        if m: fields["prostate_echo"] = m.group(0)[:30]
        m = re.search(r'膀胱\S*', text)
        if m: fields["bladder"] = m.group(0)[:30]
        m = re.search(r'残余尿\S*', text)
        if m: fields["residual_urine"] = m.group(0)[:20]

    # CDFI 通用字段
    m = re.search(r'(CDFI|未见异常血流|血流信号|彩色多普勒)\S*', text)
    if m: fields["CDFI"] = "CDFI: " + m.group(0)[:60]

    return fields


# ============================================================
# 4. 填入固定模板
# ============================================================
def fill_fixed_template(fixed_template: str, fields: dict) -> str:
    """用抽取的字段填入固定模板, 不动模板原文, 未识别字段保留模板占位"""
    result = fixed_template
    for key, val in fields.items():
        placeholder = "{" + key + "}"
        if placeholder in result:
            result = result.replace(placeholder, f'<b class="voice">{val}</b>')
    # 未填充的占位符保留原样(不删除)
    return result


# ============================================================
# 5. 一键入口: ASR文本 → 模板识别 + 字段抽取 + 填入
# ============================================================
def process_with_fixed_template(text: str, fixed_template: str = "") -> dict:
    """
    一键处理: 意图识别 → 字段抽取 → 填入固定模板
    """
    # Step 1: 意图识别
    intent = detect_template_category(text)

    # Step 2: 字段抽取
    fields = extract_fields_for_template(text, intent["category"])

    # Step 3: 选模板 (优先用户自定义, 否则用系统默认)
    if fixed_template and fixed_template.strip():
        template_text = fixed_template.strip()
    else:
        template_text = DEFAULT_TEMPLATES.get(intent["category"], DEFAULT_TEMPLATES["其他"])

    # Step 4: 填入
    filled = fill_fixed_template(template_text, fields)

    return {
        "category": intent["category"],
        "confidence": intent["confidence"],
        "is_fetal": intent.get("is_fetal", False),
        "fields_extracted": fields,
        "template_used": intent["category"],
        "filled_template": filled,
        "study_see": filled,
        "study_hint": _generate_hints_from_fields(fields, intent["category"]),
        "tags": TEMPLATE_TAGS.get(intent["category"], []),
        "all_tags": TEMPLATE_TAGS,
    }


def _generate_hints_from_fields(fields: dict, category: str) -> list[dict]:
    """从抽取的字段中推断初步诊断提示"""
    hints = []
    # 从CDFI/异常字段推断
    for key, val in fields.items():
        val_lower = str(val).lower() if val else ""
        if any(kw in val_lower for kw in ["结石", "囊肿", "息肉", "增生", "钙化", "肌瘤", "结节", "斑块"]):
            hints.append({"rank": len(hints) + 1, "diagnosis": val, "icd10": ""})
    return hints
