#!/usr/bin/env python3
"""
LoRA 本地模型 vs 火山方舟 Doubao — AB 对比测试

用法:
  python backend/scripts/benchmark_ab.py              # 默认跑50条
  python backend/scripts/benchmark_ab.py --count 100   # 跑100条
  python backend/scripts/benchmark_ab.py --mode lora   # 只跑LoRA
  python backend/scripts/benchmark_ab.py --mode volc   # 只跑火山
"""
import sys, os, time, json, re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.chdir(str(Path(__file__).resolve().parent.parent))

# ===== 100条测试用例 =====
TEST_CASES = [
    ("肝脏大小正常，回声均匀，未见明显异常", "腹部超声"),
    ("胆囊壁毛糙，见1.2cm强回声团，伴声影", "腹部超声"),
    ("甲状腺左叶见0.5×0.3cm低回声结节，边界清晰", "甲状腺超声"),
    ("胎儿头位，双顶径8.5cm，股骨长6.7cm，羊水正常，胎心140次/分", "产科超声"),
    ("子宫前位，肌壁间见多个低回声结节，最大约1.5×1.2cm", "腹部超声"),
    ("右侧乳腺外上象限见1.2×0.8cm低回声肿块，边界清", "乳腺超声"),
    ("颈动脉内膜毛糙，见斑块形成，IMT约1.2mm", "血管超声"),
    ("双肾大小正常，集合系统未见分离", "腹部超声"),
    ("肝脏大小正常，胆囊壁毛糙，胰腺正常，脾脏未见肿大", "腹部超声"),
    ("前列腺稍大，大小约4.5×3.5×3.0cm", "泌尿超声"),
    ("肝脏大小正常，回声均匀", "腹部超声"),
    ("胆囊结石，大小约1.5cm", "腹部超声"),
    ("甲状腺回声不均匀，实质弥漫性病变", "甲状腺超声"),
    ("双顶径8.5cm，股骨长6.7cm", "产科超声"),
    ("子宫肌瘤，大小约3.0×2.5cm", "腹部超声"),
    ("乳腺增生，双侧小叶增生", "乳腺超声"),
    ("颈动脉斑块形成", "血管超声"),
    ("双肾囊肿，大小约2.0cm", "腹部超声"),
    ("肝脏脂肪沉积", "腹部超声"),
    ("甲状腺结节，TI-RADS 3类", "甲状腺超声"),
    ("胆囊息肉，大小约0.5cm", "腹部超声"),
    ("盆腔积液，深约1.2cm", "腹部超声"),
    ("双侧乳腺未见明确占位性病变", "乳腺超声"),
    ("甲状腺全切术后复查", "甲状腺超声"),
    ("前列腺增生", "泌尿超声"),
    ("肝囊肿单发", "腹部超声"),
    ("胆囊壁毛糙", "腹部超声"),
    ("颈动脉内中膜增厚", "血管超声"),
    ("双侧颈动脉未见明显异常", "血管超声"),
    ("双侧肾上腺区未见明显异常", "腹部超声"),
    ("肝内钙化灶", "腹部超声"),
    ("脾脏未见肿大", "腹部超声"),
    ("胰腺大小形态正常", "腹部超声"),
    ("双肾未见明显异常", "腹部超声"),
    ("膀胱未见明显异常", "泌尿超声"),
    ("子宫大小正常", "腹部超声"),
    ("卵巢大小正常", "腹部超声"),
    ("心脏各房室内径正常", "心脏超声"),
    ("二尖瓣轻度返流", "心脏超声"),
    ("三尖瓣轻度返流", "心脏超声"),
    ("主动脉瓣退行性变", "心脏超声"),
    ("心包腔未见积液", "心脏超声"),
    ("左室收缩功能正常", "心脏超声"),
    ("心内结构未见明显异常", "心脏超声"),
    ("左室假腱索", "心脏超声"),
    ("肝血管瘤，大小约1.5cm", "腹部超声"),
    ("肾结石，大小约0.6cm", "腹部超声"),
    ("肾积水，轻度", "腹部超声"),
    ("输尿管未见扩张", "腹部超声"),
    ("肝内胆管未见扩张", "腹部超声"),
    ("肝脏大小形态正常，包膜完整", "腹部超声"),
    ("胆囊大小正常，壁光滑", "腹部超声"),
    ("胰腺大小形态正常，回声均匀", "腹部超声"),
    ("脾脏大小正常", "腹部超声"),
    ("双肾大小形态正常", "腹部超声"),
    ("膀胱充盈好，壁光滑", "泌尿超声"),
    ("前列腺大小正常", "泌尿超声"),
    ("甲状腺大小正常，回声均匀", "甲状腺超声"),
    ("双侧乳腺大小正常", "乳腺超声"),
    ("心脏大小正常", "心脏超声"),
    ("颈动脉内膜光滑", "血管超声"),
    ("肝内多发囊肿", "腹部超声"),
    ("胆囊多发结石", "腹部超声"),
    ("胆囊息肉样病变", "腹部超声"),
    ("胆囊胆固醇结晶", "腹部超声"),
    ("胆囊壁增厚", "腹部超声"),
    ("脂肪肝轻度", "腹部超声"),
    ("脂肪肝中重度", "腹部超声"),
    ("肝内胆管结石", "腹部超声"),
    ("肝硬化", "腹部超声"),
    ("肝大", "腹部超声"),
    ("脾大", "腹部超声"),
    ("脾囊肿", "腹部超声"),
    ("脾内钙化灶", "腹部超声"),
    ("副脾", "腹部超声"),
    ("肾囊肿多发", "腹部超声"),
    ("肾错构瘤", "腹部超声"),
    ("肾结石多发", "腹部超声"),
    ("双肾多发结石", "腹部超声"),
    ("前列腺稍大", "泌尿超声"),
    ("前列腺钙化灶", "泌尿超声"),
    ("前列腺囊肿", "泌尿超声"),
    ("前列腺增大", "泌尿超声"),
    ("附睾头囊肿", "泌尿超声"),
    ("精索静脉曲张", "泌尿超声"),
    ("睾丸附睾未见异常", "泌尿超声"),
    ("子宫肌瘤多发", "腹部超声"),
    ("子宫腺肌症", "腹部超声"),
    ("子宫内膜息肉", "腹部超声"),
    ("卵巢囊肿", "腹部超声"),
    ("宫颈多发囊肿", "腹部超声"),
    ("绝经后子宫", "腹部超声"),
    ("盆腔积液", "腹部超声"),
    ("甲状腺单发结节", "甲状腺超声"),
    ("甲状腺多发结节", "甲状腺超声"),
    ("甲状腺无回声结节", "甲状腺超声"),
    ("桥本氏甲状腺炎", "甲状腺超声"),
    ("颈部淋巴结未见肿大", "甲状腺超声"),
    ("双侧乳腺未见明确占位性病变，腺体结构清晰", "乳腺超声"),
    ("心脏各瓣膜形态正常，启闭好", "心脏超声"),
    ("颈动脉内膜光滑，IMT正常", "血管超声"),
]


def score_result(text, report):
    """给报告质量打分 (0-100) — 只评估内容质量, 不偏袒任何引擎"""
    score = 30  # 基础分
    see = report.get("study_see", "") or ""
    hints = report.get("study_hint", [])
    rec = report.get("recommendation", "") or ""
    see_plain = re.sub(r'<[^>]+>', '', see)

    # 内容长度（合理的报告至少有一定篇幅）
    if len(see_plain) >= 10: score += 10
    if len(see_plain) >= 30: score += 10
    if len(see_plain) >= 60: score += 5

    # 诊断提示
    if len(hints) > 0: score += 15
    if len(hints) >= 2: score += 5

    # 建议
    if rec and len(rec) >= 4: score += 5

    # 数值保留—这是客观指标
    nums = re.findall(r'\d+(?:\.\d+)?', text)
    if nums:
        kept = sum(1 for n in nums if n in see_plain)
        score += int(kept / len(nums) * 15)

    # 关键词覆盖（客观指标，越多的原文医学术语出现在报告中越好）
    keywords = re.findall(r'[一-鿿]{2,}', text)
    if keywords:
        covered = sum(1 for kw in keywords if kw in see_plain)
        score += int(covered / len(keywords) * 20)

    return min(score, 100)


def run_volc(test_cases, count):
    from main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)

    results = []
    for text, exam in test_cases[:count]:
        t0 = time.time()
        try:
            r = client.post('/api/structure', json={'text': text, 'exam_type': exam})
            dt = time.time() - t0
            if r.status_code == 200:
                d = r.json()
                score = score_result(text, d['report'])
                results.append({
                    'text': text[:30], 'exam': exam,
                    'method': d.get('method', '?'),
                    'score': score, 'time': round(dt, 2),
                    'rec': d['report'].get('recommendation', '')[:20],
                    'hints': len(d['report'].get('study_hint', [])),
                    'see_len': len(d['report'].get('study_see', '')),
                })
            else:
                results.append({'text': text[:30], 'error': str(r.status_code)})
        except Exception as e:
            results.append({'text': text[:30], 'error': str(e)[:50]})
    return results


def run_lora(test_cases, count):
    """用本地 LoRA 模型跑测试（走完整管线, 和火山方舟同样的流程）"""
    from routers.structure import _USE_LOCAL_LLM, _LOCAL_LLM_AVAILABLE
    if not _LOCAL_LLM_AVAILABLE:
        print("LoRA 本地模型不可用, 跳过")
        return []

    from main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)

    results = []
    for text, exam in test_cases[:count]:
        t0 = time.time()
        try:
            r = client.post('/api/structure', json={'text': text, 'exam_type': exam})
            dt = time.time() - t0
            if r.status_code == 200:
                d = r.json()
                score = score_result(text, d['report'])
                results.append({
                    'text': text[:30], 'exam': exam,
                    'method': d.get('method', '?'),
                    'score': score, 'time': round(dt, 2),
                    'rec': d['report'].get('recommendation', '')[:20],
                    'hints': len(d['report'].get('study_hint', [])),
                    'see_len': len(d['report'].get('study_see', '')),
                })
            else:
                results.append({'text': text[:30], 'error': str(r.status_code)})
        except Exception as e:
            results.append({'text': text[:30], 'error': str(e)[:50]})
    return results




def run_deepseek(test_cases, count):
    """用 DeepSeek 跑测试"""
    import openai
    client = openai.OpenAI(
        api_key="sk-43ffc7dafcec4369a039436377694820",
        base_url="https://api.deepseek.com/v1",
    )
    results = []
    for text, exam in test_cases[:count]:
        t0 = time.time()
        try:
            system = f"你是一位超声科主任医师。基于口述生成规范化超声报告。检查类型: {exam}"
            prompt = f"ASR口述: " + text
            resp = client.chat.completions.create(
                model="deepseek-chat",
                temperature=0.1, max_tokens=2048, timeout=30,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            )
            content = resp.choices[0].message.content
            dt = time.time() - t0
            report = {}
            try:
                report = json.loads(content)
            except:
                report = {"study_see": content, "study_hint": [], "recommendation": ""}
            score = score_result(text, report)
            results.append({
                'text': text[:30], 'exam': exam,
                'method': 'deepseek',
                'score': score, 'time': round(dt, 2),
                'rec': report.get('recommendation', '')[:20],
                'hints': len(report.get('study_hint', [])),
                'see_len': len(report.get('study_see', '')),
            })
        except Exception as e:
            results.append({'text': text[:30], 'error': str(e)[:50]})
    return results



def run_deepseek(test_cases, count):
    """用 DeepSeek 跑测试"""
    import openai
    client = openai.OpenAI(
        api_key="sk-43ffc7dafcec4369a039436377694820",
        base_url="https://api.deepseek.com/v1",
    )
    results = []
    for text, exam in test_cases[:count]:
        t0 = time.time()
        try:
            system = f"你是一位超声科主任医师。基于口述生成规范化超声报告。检查类型: {exam}"
            resp = client.chat.completions.create(
                model="deepseek-chat",
                temperature=0.1, max_tokens=2048, timeout=30,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"ASR口述: " + text},
                ],
            )
            content = resp.choices[0].message.content
            dt = time.time() - t0
            report = {}
            try:
                report = json.loads(content)
            except:
                report = {"study_see": content, "study_hint": [], "recommendation": ""}
            score = score_result(text, report)
            results.append({
                'text': text[:30], 'exam': exam,
                'method': 'deepseek',
                'score': score, 'time': round(dt, 2),
                'rec': report.get('recommendation', '')[:20],
                'hints': len(report.get('study_hint', [])),
                'see_len': len(report.get('study_see', '')),
            })
        except Exception as e:
            results.append({'text': text[:30], 'error': str(e)[:50]})
    return results

def print_report(results, label):
    scores = [r.get('score', 0) for r in results if 'score' in r]
    times = [r.get('time', 0) for r in results if 'time' in r]
    errors = [r for r in results if 'error' in r]

    print(f"\n{'='*55}")
    print(f"  {label}")
    print(f"{'='*55}")
    print(f"  总: {len(results)} | 成功: {len(scores)} | 失败: {len(errors)}")
    if scores:
        print(f"  平均分: {sum(scores)/len(scores):.1f}")
        print(f"  最高: {max(scores)} | 最低: {min(scores)}")
    if times:
        print(f"  平均耗时: {sum(times)/len(times):.2f}s | 总耗时: {sum(times):.1f}s")
    if errors:
        for e in errors[:3]:
            print(f"  ! {e['text']}: {e.get('error','')}")



if __name__ == "__main__":
    count = 50
    mode = "all"
    for arg in sys.argv[1:]:
        if arg.startswith('--count='): count = int(arg.split('=')[1])
        elif arg.startswith('--mode='): mode = arg.split('=')[1]

    cases = TEST_CASES[:count]
    print(f"测试: {len(cases)}条, mode={mode}")

    results = {}

    if mode in ('all', 'volc'):
        print(chr(10) + "--- 火山方舟测试中 ---")
        results['volc'] = run_volc(cases, count)
        print_report(results['volc'], '火山方舟 Doubao')

    if mode in ('all', 'deepseek'):
        print(chr(10) + "--- DeepSeek 测试中 ---")
        results['deepseek'] = run_deepseek(cases, count)
        print_report(results['deepseek'], 'DeepSeek V3')

    if mode in ('all', 'lora'):
        print(chr(10) + "--- 本地 LoRA 测试中 ---")
        results['lora'] = run_lora(cases, count)
        print_report(results['lora'], '本地 LoRA + Qwen2.5-3B')

    if 'deepseek' in results:
        d = results['deepseek']
        ds = [r['score'] for r in d if 'score' in r]
        dt_sum = sum(r['time'] for r in d if 'time' in r)
        if ds:
            print(f"  {'DeepSeek平均分':20s} {sum(ds)/len(ds):.1f}/100")
        print(f"  {'DeepSeek总耗时':20s} {dt_sum:.1f}s")

    if 'volc' in results and 'lora' in results:
        v, l = results['volc'], results['lora']
        vs = [r['score'] for r in v if 'score' in r]
        ls = [r['score'] for r in l if 'score' in r]
        vt = sum(r['time'] for r in v if 'time' in r)
        lt = sum(r['time'] for r in l if 'time' in r)

        print(chr(10) + "=" * 55)
        print("  AB 对比")
        print("=" * 55)
        print(f"  {'指标':20s} {'火山方舟':15s} {'LoRA本地':15s}")
        print("  " + "-" * 50)
        if vs and ls:
            print(f"  {'平均分':20s} {sum(vs)/len(vs):.1f}/100      {sum(ls)/len(ls):.1f}/100")
        print(f"  {'总耗时':20s} {vt:.1f}s          {lt:.1f}s")
        if vs and ls:
            n = min(len(vs), len(ls))
            w = sum(1 for i in range(n) if vs[i] > ls[i])
            l_ = sum(1 for i in range(n) if vs[i] < ls[i])
            t_ = sum(1 for i in range(n) if vs[i] == ls[i])
            print(f"  {'火山胜/平/LoRA胜':20s} {w}/{t_}/{l_}")
        print()
