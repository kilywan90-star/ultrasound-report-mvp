"""超声报告语音结构化 — 20轮专业业务逻辑测试"""

import httpx
import json
import time
import statistics

API = "http://localhost:8700"

# 20条完整的业务场景测试用例
# 每条包含：患者信息、检查类型、口述文本、期望的脏器数、期望诊断数、期望ICD-10
CASES = [
    # === 腹部超声 (1-8) ===
    {
        "patient": {"name":"张建国","gender":"男","age":52,"exam_type":"腹部超声","exam_part":"肝胆胰脾"},
        "text":"肝脏形态饱满，左叶前后径72毫米，右叶斜径148毫米，回声增粗、不均匀。肝内可见一个大小约15乘12毫米的无回声区，边界清晰，后方回声增强。胆囊大小约68乘28毫米，壁厚2毫米、光滑，腔内未见异常回声。胆总管内径5毫米。胰腺大小形态正常，回声均匀。脾脏肋间厚32毫米，回声均匀。超声提示：1、脂肪肝 2、肝囊肿。建议定期复查。",
        "expected": {"tpl":"abdomen","organs_min":5,"diag_min":2,"icd10_min":1}
    },
    {
        "patient": {"name":"李秀英","gender":"女","age":48,"exam_type":"腹部超声","exam_part":"肝胆脾肾"},
        "text":"胆囊大小约82乘38毫米，壁厚4毫米、毛糙，腔内可见多个强回声团，大者约10乘8毫米，后伴声影，随体位改变移动。胆总管未见扩张。肝脏、胰腺、脾脏、双肾未见明显异常。超声提示：1、慢性胆囊炎 2、胆囊多发结石。",
        "expected": {"tpl":"abdomen","organs_min":5,"diag_min":2,"icd10_min":1}
    },
    {
        "patient": {"name":"王建国","gender":"男","age":61,"exam_type":"腹部超声","exam_part":"泌尿系"},
        "text":"右肾上极可见一大小约48乘42毫米的无回声区，边界清晰，后方回声增强，内部透声好。左肾中部可见一个大小约8乘6毫米的强回声团，后伴声影。左肾集合系统轻度分离约14毫米。膀胱充盈良好，壁光滑，腔内未见异常回声。前列腺大小约45乘35乘30毫米，形态饱满，向膀胱内突出约12毫米。超声提示：1、右肾囊肿 2、左肾结石伴轻度肾积水 3、前列腺增生。",
        "expected": {"tpl":"abdomen","organs_min":4,"diag_min":3,"icd10_min":1}
    },
    {
        "patient": {"name":"赵伟","gender":"男","age":45,"exam_type":"腹部超声","exam_part":"肝胆胰脾"},
        "text":"肝脏右叶可见一大小约22乘18毫米的高回声结节，边界清晰，周边可见低回声晕。肝脏左叶大小正常，实质回声均匀。胆囊大小正常，壁光滑。胰腺、脾脏未见异常。超声提示：肝血管瘤，建议定期复查。",
        "expected": {"tpl":"abdomen","organs_min":4,"diag_min":1,"icd10_min":1}
    },
    {
        "patient": {"name":"陈桂花","gender":"女","age":55,"exam_type":"腹部超声","exam_part":"全腹"},
        "text":"胆囊显示不清，胆囊区可见一大小约28乘20毫米的弧形强回声带，后伴宽大声影。肝脏回声弥漫性增粗，表面呈结节状，肝右叶斜径142毫米。肝内血管走行紊乱。脾脏肋间厚55毫米。腹腔可见游离无回声区，肝肾隐窝深约20毫米，下腹部深约35毫米。超声提示：1、充满型胆囊结石伴萎缩性胆囊炎 2、肝硬化伴门脉高压 3、脾大 4、腹水。",
        "expected": {"tpl":"abdomen","organs_min":4,"diag_min":3,"icd10_min":1}
    },
    {
        "patient": {"name":"周明","gender":"男","age":38,"exam_type":"腹部超声","exam_part":"肝胆"},
        "text":"胆囊大小约52乘22毫米，壁不厚。腔内可见泥沙样强回声沉积于后壁，范围约35乘15毫米，无声影，随体位改变缓慢移动。肝脏、胆总管、胰腺、脾脏未见异常。超声提示：胆囊泥沙样结石。",
        "expected": {"tpl":"abdomen","organs_min":5,"diag_min":1,"icd10_min":1}
    },
    {
        "patient": {"name":"吴丽","gender":"女","age":42,"exam_type":"腹部超声","exam_part":"肝胆胰脾"},
        "text":"胰腺头颈部可见一大小约38乘30毫米的低回声肿块，边界模糊，形态不规则，内部回声不均匀。胰管扩张约5毫米。肝内外胆管未见扩张。肝脏、胆囊、脾脏未见异常。超声提示：胰头占位性病变，建议增强CT检查。",
        "expected": {"tpl":"abdomen","organs_min":4,"diag_min":1,"icd10_min":0}
    },
    {
        "patient": {"name":"郑磊","gender":"男","age":28,"exam_type":"腹部超声","exam_part":"肝胆脾"},
        "text":"肝脏大小形态正常，实质回声均匀，血管走行清晰。胆囊大小正常，壁光滑。胆总管内径5毫米。胰腺大小形态正常。脾脏肋间厚30毫米，回声均匀。双肾大小形态正常，实质回声均匀。超声提示：腹部超声未见明显异常。",
        "expected": {"tpl":"abdomen","organs_min":6,"diag_min":1,"icd10_min":0}
    },

    # === 妇产超声 (9-13) ===
    {
        "patient": {"name":"刘芳","gender":"女","age":35,"exam_type":"妇产超声","exam_part":"子宫附件"},
        "text":"子宫前位，大小约75乘52乘45毫米，形态规则，肌壁回声均匀。前壁可见一大小约38乘32毫米的低回声结节，边界清晰，形态规则。内膜厚约8毫米。宫颈未见异常。双侧卵巢大小形态正常。盆腔未见游离液体。超声提示：子宫肌瘤。",
        "expected": {"tpl":"obgyn","organs_min":4,"diag_min":1,"icd10_min":1}
    },
    {
        "patient": {"name":"孙莉","gender":"女","age":28,"exam_type":"妇产超声","exam_part":"子宫附件"},
        "text":"右侧卵巢可见一大小约45乘40毫米的无回声囊性结构，壁薄光滑，内部透声好。左侧卵巢大小形态正常。子宫前位，大小正常，内膜厚约7毫米。宫颈正常。盆腔未见积液。超声提示：右侧卵巢单纯性囊肿，建议随访。",
        "expected": {"tpl":"obgyn","organs_min":4,"diag_min":1,"icd10_min":1}
    },
    {
        "patient": {"name":"马丽娜","gender":"女","age":31,"exam_type":"妇产超声","exam_part":"早孕检查"},
        "text":"子宫内膜增厚约16毫米，宫腔内可见一孕囊，大小约28乘18毫米，可见卵黄囊，胚芽长约6毫米，可见原始心管搏动，心率约145次每分。双侧卵巢可见，黄体可见。盆腔未见积液。超声提示：宫内早孕，约孕6周+，胚胎存活。",
        "expected": {"tpl":"obgyn","organs_min":3,"diag_min":1,"icd10_min":0}
    },
    {
        "patient": {"name":"何婷","gender":"女","age":40,"exam_type":"妇产超声","exam_part":"妇科检查"},
        "text":"子宫后位，大小约82乘58乘48毫米，肌壁回声不均匀，弥漫性增粗增强，以后壁为著。内膜厚约5毫米。双侧卵巢显示清晰，大小正常。盆腔未见游离液体。超声提示：子宫腺肌症。",
        "expected": {"tpl":"obgyn","organs_min":3,"diag_min":1,"icd10_min":1}
    },
    {
        "patient": {"name":"黄晓燕","gender":"女","age":26,"exam_type":"妇产超声","exam_part":"妇科检查"},
        "text":"双侧附件区未见明确异常回声团。子宫大小形态正常，内膜厚约6毫米。盆腔可见中等量游离无回声区，子宫直肠陷凹深约30毫米。超声提示：盆腔积液，请结合临床。",
        "expected": {"tpl":"obgyn","organs_min":3,"diag_min":1,"icd10_min":0}
    },

    # === 心脏超声 (14-16) ===
    {
        "patient": {"name":"郭建华","gender":"男","age":65,"exam_type":"心脏超声","exam_part":"心彩+心功能"},
        "text":"左心室增大，舒张末内径约65毫米，收缩末内径约50毫米。室间隔及左室后壁厚度正常。左室壁运动弥漫性减弱。二尖瓣形态正常，未见反流。主动脉瓣三叶式，未见反流。三尖瓣未见反流。EF约38%。心包未见积液。超声提示：扩张型心肌病，左心功能减低。",
        "expected": {"tpl":"cardiac","organs_min":5,"diag_min":2,"icd10_min":1}
    },
    {
        "patient": {"name":"钱大妈","gender":"女","age":72,"exam_type":"心脏超声","exam_part":"心脏检查"},
        "text":"主动脉瓣回声增强、钙化，瓣叶开放受限。瓣上峰值流速约430厘米每秒，平均跨瓣压差约48毫米汞柱。瓣口面积约0.7平方厘米。左心室向心性肥厚，室间隔厚约15毫米，左室后壁厚约14毫米。左心房增大，前后径约42毫米。二尖瓣未见反流。心包未见积液。超声提示：主动脉瓣重度狭窄伴左心室肥厚。",
        "expected": {"tpl":"cardiac","organs_min":4,"diag_min":1,"icd10_min":1}
    },
    {
        "patient": {"name":"杨老伯","gender":"男","age":68,"exam_type":"心脏超声","exam_part":"心彩超"},
        "text":"左心室壁节段性运动异常，前壁中下段、前间隔中段运动减弱。左心室舒张末内径约58毫米。EF约42%。二尖瓣轻度反流。主动脉瓣三叶，钙化，轻度反流。右心房室大小正常。心包未见积液。超声提示：冠心病，左心室节段性室壁运动异常，心功能减低。",
        "expected": {"tpl":"cardiac","organs_min":4,"diag_min":2,"icd10_min":1}
    },

    # === 小器官 (17-19) ===
    {
        "patient": {"name":"白女士","gender":"女","age":38,"exam_type":"甲状腺超声","exam_part":"甲状腺检查"},
        "text":"甲状腺左叶大小约46乘15乘13毫米，右叶大小约48乘17乘15毫米，峡部厚约3毫米。右叶中部可见一大小约9乘7毫米的低回声结节，边界清晰，形态规则，内部回声均匀。CDFI显示结节内少量点状血流信号。TI-RADS 3类。超声提示：甲状腺右叶结节，TI-RADS 3类，考虑良性。",
        "expected": {"tpl":"thyroid","organs_min":1,"diag_min":1,"icd10_min":0}
    },
    {
        "patient": {"name":"林女士","gender":"女","age":45,"exam_type":"乳腺超声","exam_part":"乳腺检查"},
        "text":"双侧乳腺腺体结构清晰，腺体层轻度增生。左侧乳腺内上象限可见一大小约22乘18毫米的低回声结节，边界欠清晰，形态略不规则，内部回声不均匀。可见点状微钙化。CDFI示结节内可见较丰富血流信号。BI-RADS 4b类。右侧乳腺未见明确占位。双侧腋窝可见数个淋巴结，大者约15乘8毫米，皮髓质分界清晰。超声提示：左乳实性占位，BI-RADS 4b类，建议穿刺活检。",
        "expected": {"tpl":"thyroid","organs_min":3,"diag_min":1,"icd10_min":0}
    },
    {
        "patient": {"name":"韩先生","gender":"男","age":58,"exam_type":"颈动脉超声","exam_part":"颈部血管"},
        "text":"双侧颈总动脉内膜中层厚度增厚，右侧约1.3毫米，左侧约1.2毫米。右侧颈总动脉分叉处可见一大小约18乘4毫米的不均质回声斑块，表面不规则。左侧颈内动脉起始段可见一大小约12乘3毫米的混合回声斑块。CDFI示管腔内血流通畅，未见明显狭窄加速。超声提示：双侧颈动脉粥样硬化伴斑块形成。",
        "expected": {"tpl":"vascular","organs_min":3,"diag_min":1,"icd10_min":1}
    },

    # === 口语化/边缘场景 (20) ===
    {
        "patient": {"name":"魏老五","gender":"男","age":70,"exam_type":"腹部超声","exam_part":"全腹"},
        "text":"做了个B超。肝上面医生说有点大，回声也不太好，右边肝里有个东西，大概两公分多，医生说可能是血管瘤，让半年后再查。胆囊说是有石头的，泥沙那种，不大。其他胰脏脾什么的都说还行。肾左边有个小囊肿。意见就是肝血管瘤、胆结石、左肾囊肿。",
        "expected": {"tpl":"abdomen","organs_min":5,"diag_min":2,"icd10_min":1}
    },
]


def test_all():
    print("=" * 70)
    print("超声报告语音结构化 — 20轮专业业务逻辑测试")
    print(f"API: {API}")
    print(f"开始: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    results = []
    total_start = time.time()

    # Step 0: Health check
    try:
        r = httpx.get(f"{API}/api/health", timeout=5)
        print(f"\n[初始化] Health: {r.json()['version']}")
    except Exception as e:
        print(f"[初始化] 服务未连接: {e}")
        return

    for idx, case in enumerate(CASES):
        case_start = time.time()
        p = case["patient"]
        exp = case["expected"]
        tpl_tag = f"[测试{idx+1:2d}] {p['name']} {p['exam_type']}"
        print(f"\n{tpl_tag}")
        steps_ok = []

        try:
            # Step 1: 患者入队
            r = httpx.post(f"{API}/api/patients/quick-add", json=p, timeout=10)
            if r.is_success and r.json()["success"]:
                pid = r.json()["patient"]["id"]
                steps_ok.append(f"入队(id={pid})")
                print(f"  1.入队: {p['name']} {p['gender']}{p['age']}岁 {p['exam_type']} → id={pid}")
            else:
                print(f"  1.入队失败: {r.text[:100]}")
                continue

            # Step 2: 患者状态更新为"检查中"
            r = httpx.put(f"{API}/api/patients/{pid}/status?status=检查中", timeout=10)
            if r.is_success:
                steps_ok.append("状态→检查中")
                print(f"  2.状态: 已缴费 → 检查中")

            # Step 3: 结构化提取
            r = httpx.post(f"{API}/api/structure", json={
                "text": case["text"],
                "exam_type": p["exam_type"],
                "patient_id": pid,
            }, timeout=90)
            if not r.is_success:
                print(f"  3.结构化失败: {r.text[:150]}")
                continue
            data = r.json()
            if data.get("warning"):
                print(f"  3.WARN: {data['warning']}")
            report = data["report"]
            rid = data["report_id"]
            f_count = len(report.get("findings", []))
            d_count = len(report.get("impression", []))
            icd10s = [imp["icd10"] for imp in report.get("impression", []) if imp.get("icd10")]
            steps_ok.append(f"结构化")

            # Step 4: 验证
            checks = []
            if f_count >= exp["organs_min"]:
                checks.append(f"organs>={exp['organs_min']} OK")
            else:
                checks.append(f"organs LOW({f_count}<{exp['organs_min']})")
            if d_count >= exp["diag_min"]:
                checks.append(f"diag>={exp['diag_min']} OK")
            else:
                checks.append(f"diag LOW({d_count}<{exp['diag_min']})")
            if exp["icd10_min"] > 0 and len(icd10s) < exp["icd10_min"]:
                checks.append(f"ICD10 MISSING")
            elif exp["icd10_min"] > 0:
                checks.append(f"ICD10:{','.join(icd10s[:3])} OK")
            print(f"  3.结构化: {f_count}个脏器 {d_count}项诊断 {' | '.join(checks)}")
            org_names = [f["organ"] for f in report.get("findings", [])]
            diag_names = [imp["diagnosis"] for imp in report.get("impression", [])]
            print(f"    | organs: {', '.join(org_names)}")
            print(f"    | diagnosis: {', '.join(diag_names)}")
            if icd10s:
                print(f"    | ICD10: {', '.join(icd10s)}")

            # Step 5: 模拟医生勾选操作（去除第1条finding）
            if f_count >= 2 and rid:
                findings = report.get("findings", [])
                findings[0]["checked"] = False  # 模拟医生又掉第一个
                # 保存
                r = httpx.post(f"{API}/api/reports/{rid}/save", json={"report": report}, timeout=30)
                if r.is_success:
                    steps_ok.append("勾选+保存")
                    print(f"  4.勾选操作: 移除「{findings[0].get('organ','')}」→ 保存成功")

            # Step 6: 确认发送
            if rid:
                r = httpx.post(f"{API}/api/reports/{rid}/send", json={"report": report}, timeout=30)
                if r.is_success:
                    steps_ok.append("发送PACS")
                    print(f"  5.发送PACS: {r.json().get('message','OK')}")

            # Step 7: 验证患者状态
            r = httpx.get(f"{API}/api/patients/queue", timeout=10)
            pts = r.json().get("patients", [])
            pt_final = next((x for x in pts if x["id"] == pid), None)
            if pt_final:
                print(f"  6.最终状态: {pt_final['status']}")

            elapsed = time.time() - case_start
            results.append({
                "idx": idx + 1,
                "name": p["name"],
                "exam": p["exam_type"],
                "elapsed": f"{elapsed:.1f}s",
                "ok": len(steps_ok) >= 4,
                "steps": steps_ok,
            })
            print(f"  {elapsed:.1f}s steps: {' > '.join(steps_ok)}")

        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}")
            results.append({"idx": idx + 1, "name": p["name"], "ok": False, "error": str(e)})

    total = time.time() - total_start
    ok = sum(1 for r in results if r["ok"])
    fail = len(results) - ok

    print("\n" + "=" * 70)
    print(f"                        测 试 汇 总")
    print("=" * 70)
    print(f"  总用例:  {len(CASES)}")
    print(f"  通过:    {ok} ({ok/len(CASES)*100:.0f}%)")
    print(f"  失败:    {fail}")
    print(f"  总耗时:  {total:.0f}s")

    if ok > 0:
        times = [float(r["elapsed"].rstrip('s')) for r in results if r.get("elapsed")]
        if times:
            print(f"  平均延迟: {statistics.mean(times):.1f}s")
            print(f"  中位延迟: {statistics.median(times):.1f}s")
            print(f"  最快:    {min(times):.1f}s")
            print(f"  最慢:    {max(times):.1f}s")

    if fail > 0:
        print(f"\n  失败用例:")
        for r in results:
            if not r["ok"]:
                print(f"  [{r['idx']:2d}] {r['name']}: {r.get('error','')}")

    print("=" * 70)


if __name__ == "__main__":
    test_all()
