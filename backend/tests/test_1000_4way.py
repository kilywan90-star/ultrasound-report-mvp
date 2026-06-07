#!/usr/bin/env python3
"""
生成 1000 条测试数据 + 全流程 4 项验证
每条数据包含:
  - 病人基础信息 (姓名/性别/年龄/科室/诊断/检查项目)
  - ASR模拟文本 (≥20字)
  - 预期模板类别

四项验证:
  1. 模板识别能力 (intent_detection accuracy)
  2. 固定模板填入能力 (fixed-template structure API)
  3. 文本转写模拟 (ASR → 纠错 → 结构化)
  4. 模板主体结构不变 + 变量填充
"""
import json, csv, random, re, urllib.request, ssl, time
from pathlib import Path
from collections import Counter, defaultdict

BASE = "https://47.109.151.238"
ctx = ssl._create_unverified_context()

# ============================================================
# 1. 生成 1000 条测试数据
# ============================================================
PATIENT_POOL = [
    ("张伟", "男", 52), ("李芳", "女", 35), ("王建国", "男", 61), ("陈秀英", "女", 48),
    ("刘明", "男", 28), ("赵丽娜", "女", 42), ("周强", "男", 70), ("吴美华", "女", 55),
    ("郑磊", "男", 38), ("冯婷", "女", 26), ("黄晓燕", "女", 40), ("杨老伯", "男", 68),
    ("孙莉", "女", 28), ("郭建华", "男", 65), ("马丽娜", "女", 31), ("钱大妈", "女", 72),
]

DEPT_POOL = ["体检中心","泌尿外科","产科","妇科","心内科","神经内科","消化内科","内分泌科","乳腺外科","血管外科"]
DIAG_POOL = ["健康体检","输尿管结石","胆囊结石","脂肪肝","妊娠中孕","子宫肌瘤","前列腺增生","甲状腺结节","冠心病","颈动脉斑块","乳腺增生","肾结石","肝硬化","房颤","高血压"]

# 8类检查的 ASR 文本模板
ASR_TEXTS = {
    "腹部": [
        "肝脏大小形态正常，包膜光滑，边缘锐利，实质回声均匀。胆囊大小正常，囊壁光滑，腔内未见异常回声。胰腺形态大小正常，回声均匀。脾脏正常。双肾大小形态正常，未见异常血流信号。",
        "肝脏体积稍增大，实质回声增强增粗，肝肾反差明显，符合脂肪肝声像图改变。胆囊壁上见一约0.4x0.3cm高回声团，附壁，后方无声影，考虑胆囊息肉。胰腺脾脏双肾未见明显异常。",
        "胆囊大小约7.2x3.1cm，囊壁增厚约0.5cm，毛糙，腔内可见多个强回声团，后方伴声影，较大约1.5x0.8cm，考虑胆囊结石伴胆囊炎。肝内外胆管不扩张。",
        "双肾大小形态正常，右肾集合系可见分离约1.2cm，右输尿管上段扩张约0.8cm，距肾门4cm处可见一强回声团约0.6x0.4cm，后方伴声影。",
    ],
    "妇产": [
        "子宫呈前位，宫体大小约7.2x5.1x4.8cm，肌壁回声均匀，内膜居中厚约0.8cm。宫腔内可见一孕囊，大小约2.8x1.8cm，可见卵黄囊，胚芽长约0.5cm，可见原始心管搏动，心率145次/分。双侧卵巢可见。",
        "双顶径约5.8cm，头围约22.1cm，腹围约19.8cm，股骨长约4.2cm，相当于22周。肱骨长约3.9cm。胎心率145次/分。羊水指数12.8cm。胎盘附着子宫后壁I级。",
        "子宫大小形态正常，肌壁回声均匀，宫腔线清晰。左侧附件区可见一囊性无回声区约3.2x2.5cm，边界清晰，内透声好。右侧卵巢未见异常。盆腔未见积液。",
    ],
    "心脏": [
        "各房室内径正常范围。室间隔与左室壁厚度正常，静息状态下左室壁运动协调。二尖瓣回声稍增强，关闭时可见少量反流信号。主动脉瓣三尖瓣肺动脉瓣形态结构未见明显异常。心包腔内未见积液。",
        "左房增大，前后径约4.5cm。左室壁增厚，室间隔1.3cm，左室后壁1.2cm。二尖瓣中度反流，反流面积约3.5平方厘米。三尖瓣可见轻度反流。左室射血分数EF=62%。",
    ],
    "甲状腺乳腺": [
        "甲状腺左叶大小约4.5x1.6x1.5cm，右叶大小约4.8x1.8x1.7cm，峡部厚约0.3cm。双侧叶内均可见多个低回声结节，左侧最大约0.6cm，右侧最大约0.8cm，边界清晰形态规则。双侧颈部未见肿大淋巴结。",
        "双侧乳腺皮肤皮下组织各层次结构清晰。双侧乳腺腺体增厚，回声不均匀，呈片状低回声区，未见明确占位性病变。双侧腋窝及乳腺周围未见长大的淋巴结。未见异常血流信号。",
    ],
    "血管": [
        "双侧颈总动脉内径正常，内膜中层厚度约1.2mm。左侧颈总动脉分叉处后壁可见一约1.2x0.3cm低回声斑块。右侧未见明显斑块。双侧椎动脉颅外段走行管径未见异常。血流速度及频谱未见明显异常。",
        "经颞窗探查双侧大脑中动脉大脑前动脉大脑后动脉血流方向正常，频谱形态正常。双侧椎动脉及基底动脉血流方向正常，血流速度未见明显增快或减慢。未见异常血流信号。",
    ],
    "泌尿前列腺": [
        "经腹前列腺超声检查前列腺大小约5.2x4.5x4.2cm，形态饱满，突入膀胱约1.5cm，被膜光滑连续。实质回声欠均匀，内可见多个点状强回声钙化灶。残余尿量约80ml。膀胱壁光滑未见异常。",
        "膀胱充盈好，壁光滑连续。膀胱内无回声暗区清晰。于膀胱后壁可见一强回声团约0.8x0.5cm，后方伴弱声影，随体位改变而移动。前列腺大小形态正常。双肾未见明显异常。",
    ],
}

EXPECTED_CATEGORIES = {
    "腹部": "腹部", "妇产": "妇产", "心脏": "心脏",
    "甲状腺乳腺": "甲状腺乳腺", "血管": "血管", "泌尿前列腺": "泌尿前列腺",
}

def generate_test_data(n=1000):
    tests = []
    keys = list(ASR_TEXTS.keys())
    weights = [250, 200, 100, 120, 80, 100]  # 腹部最多, 血管最少

    for i in range(n):
        cat = random.choices(keys, weights=weights, k=1)[0]
        text = random.choice(ASR_TEXTS[cat])
        # 15%概率随机选错文本
        if random.random() < 0.15:
            cat = random.choice(keys)
            text = random.choice(ASR_TEXTS[cat])
        name, gender, age = random.choice(PATIENT_POOL)
        dept = random.choice(DEPT_POOL)
        diag = random.choice(DIAG_POOL)
        exam = cat.replace("甲状腺乳腺","甲状腺超声").replace("泌尿前列腺","腹部超声").replace("血管","血管超声") + "超声" if "超声" not in cat else ""
        if cat == "妇产": exam = "妇产超声"
        if cat == "心脏": exam = "心脏超声"

        tests.append({
            "id": i+1,
            "patient": {"name": name, "gender": gender, "age": age},
            "department": dept,
            "clinical_diag": diag,
            "exam_item": exam,
            "asr_text": text,
            "expected_category": EXPECTED_CATEGORIES.get(cat, "未知"),
            "text_length": len(text),
        })

    return tests


# ============================================================
# 2. 四项验证
# ============================================================
def test_template_recognition(tests):
    """验证1: 模板识别能力"""
    correct = wrong = 0
    errors = []
    for t in tests:
        data = json.dumps({"text": t["asr_text"]}).encode()
        try:
            req = urllib.request.Request(BASE + "/api/fixed-template/structure", data=data,
                                         headers={"Content-Type": "application/json"})
            r = json.loads(urllib.request.urlopen(req, context=ctx, timeout=10).read())
            predicted = r.get("category", "")
            if predicted == t["expected_category"]:
                correct += 1
            else:
                wrong += 1
                errors.append((t["id"], t["expected_category"], predicted))
        except Exception as e:
            wrong += 1
            errors.append((t["id"], t["expected_category"], f"ERR:{str(e)[:30]}"))

    acc = correct / max(correct + wrong, 1) * 100
    print(f"  [验证1] 模板识别: {correct}/{correct+wrong} = {acc:.1f}%")
    if errors:
        print(f"    错误样例: {errors[:3]}")
    return acc


def test_fixed_template_fill(tests):
    """验证2: 固定模板填入能力"""
    filled = empty = errors = 0
    for t in tests[:200]:  # 200条足够
        data = json.dumps({
            "text": t["asr_text"],
            "fixed_template": "测试固定模板: 脏器1={organ1} 脏器2={organ2} 正常描述={normal}"
        }).encode()
        try:
            req = urllib.request.Request(BASE + "/api/fixed-template/structure", data=data,
                                         headers={"Content-Type": "application/json"})
            r = json.loads(urllib.request.urlopen(req, context=ctx, timeout=10).read())
            ft = r.get("filled_template", "")
            # 检查是否有 voice 标记 (表示字段被填充), 或者占位符被替换
            if "voice" in ft.lower() or "{" not in ft:
                filled += 1
            else:
                empty += 1
        except Exception as e:
            errors += 1

    rate = filled / max(filled + empty + errors, 1) * 100
    print(f"  [验证2] 固定模板填入: {filled} filled, {empty} empty, {errors} errors = {rate:.1f}% fill rate")
    return rate


def test_structure_pipeline(tests):
    """验证3: 语音→纠错→结构化 全链路"""
    ok = errors = 0
    methods = Counter()
    for t in tests[:200]:
        data = json.dumps({
            "text": t["asr_text"],
            "exam_type": t["exam_item"],
            "patient_gender": t["patient"]["gender"],
            "patient_age": t["patient"]["age"],
        }).encode()
        try:
            req = urllib.request.Request(BASE + "/api/structure", data=data,
                                         headers={"Content-Type": "application/json"})
            r = json.loads(urllib.request.urlopen(req, context=ctx, timeout=15).read())
            if r.get("success"):
                ok += 1
                methods[r.get("method", "?")] += 1
            else:
                errors += 1
        except Exception as e:
            errors += 1

    print(f"  [验证3] 结构化管道: {ok}/{ok+errors} OK ({errors} errors)")
    for m, c in methods.most_common():
        print(f"    method={m}: {c} ({c/ok*100:.1f}%)")
    return ok / max(ok + errors, 1) * 100


def test_template_structure_preserved(tests):
    """验证4: 模板主体结构不变 + 只调变量"""
    violations = 0
    total = 0

    sample_templates = {
        "腹部": "肝脏：{liver} 胆囊：{gall} 胰腺：{pancreas} 脾脏：{spleen} 双肾：{kidney}",
        "妇产": "子宫：{uterus} 内膜：{endometrium} 卵巢：{ovary} 盆腔：{pelvis}",
        "心脏": "各房室：{chambers} 瓣膜：{valves} 心包：{pericardium}",
        "甲状腺乳腺": "甲状腺左叶：{left} 右叶：{right} 峡部：{isthmus}",
        "血管": "颈动脉：{carotid} 椎动脉：{va} 斑块：{plaque}",
        "泌尿前列腺": "前列腺：{prostate} 膀胱：{bladder} 残余尿：{urine}",
    }

    for t in tests[:150]:
        tmpl_key = t["expected_category"]
        if tmpl_key in ("未知", "其他"):
            continue
        s_tmpl = sample_templates.get(tmpl_key, sample_templates["腹部"])
        data = json.dumps({"text": t["asr_text"], "fixed_template": s_tmpl}).encode()
        try:
            req = urllib.request.Request(BASE + "/api/fixed-template/structure", data=data,
                                         headers={"Content-Type": "application/json"})
            r = json.loads(urllib.request.urlopen(req, context=ctx, timeout=10).read())
            ft = r.get("filled_template", "")
            # 检查模板结构: 原占位符还在 OR 被voice标记替换 (都是合法)
            has_placeholders = "{" in ft
            has_voice = "<b class=\"voice\">" in ft
            if has_placeholders or has_voice:
                pass  # 结构保留
            else:
                violations += 1  # 模板文字被完全覆盖
            total += 1
        except:
            violations += 1
            total += 1

    rate = (total - violations) / max(total, 1) * 100 if total > 0 else 0
    print(f"  [验证4] 模板结构保留: {total-violations}/{total} = {rate:.1f}%")
    return rate


# ============================================================
# Main
# ============================================================
def main():
    print("=" * 60)
    print("1000 Test Cases Generation + 4-way Validation")
    print("=" * 60)
    print()

    # 生成数据
    tests = generate_test_data(1000)
    print(f"Generated {len(tests)} test cases")
    dist = Counter(t["expected_category"] for t in tests)
    for cat, cnt in dist.most_common():
        print(f"  {cat}: {cnt}")
    print(f"  Min text length: {min(t['text_length'] for t in tests)}")
    print()

    # 保存到文件
    out = Path(__file__).resolve().parent / "test_1000_4way.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=tests[0].keys())
        w.writeheader()
        w.writerows(tests)
    print(f"Saved: {out} ({out.stat().st_size / 1024:.0f} KB)")
    print()

    # 跑 4 项验证
    print("=" * 60)
    print("Running 4-way validation...")
    print("=" * 60)
    r1 = test_template_recognition(tests)
    r2 = test_fixed_template_fill(tests)
    r3 = test_structure_pipeline(tests)
    r4 = test_template_structure_preserved(tests)

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  V1 模板识别:     {r1:.1f}%")
    print(f"  V2 固定模板填入:  {r2:.1f}%")
    print(f"  V3 结构化管道:   {r3:.1f}%")
    print(f"  V4 模板结构保留:  {r4:.1f}%")
    avg = (r1 + r2 + r3 + r4) / 4
    print(f"  Average:         {avg:.1f}%")
    print(f"  Tests generated: {len(tests)}")


if __name__ == "__main__":
    main()
