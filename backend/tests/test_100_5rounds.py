"""100条短语音数据集 5轮准确度测试"""
import json, urllib.request, re, time, statistics

with open('test_100_short.json', encoding='utf-8') as f:
    data = json.load(f)

API = "http://localhost:9999"
items = data['items']

for round_num in range(1, 6):
    print(f"\n{'='*60}")
    print(f"  Round {round_num}/5 — 100 short texts ({len(items)} items)")
    print(f"{'='*60}")

    results = []
    t0 = time.time()
    ok_count = 0
    err_count = 0

    for i, item in enumerate(items):
        oral = item['oral_text']
        expected = item['expected_diagnosis']

        payload = json.dumps({'text': oral, 'exam_type': '腹部超声'}, ensure_ascii=False).encode('utf-8')
        t1 = time.time()

        try:
            req = urllib.request.Request(API + '/api/structure', data=payload, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            err_count += 1
            results.append({'i': i, 'ok': False, 'error': True, 'http': e.code, 'elapsed': time.time() - t1})
            continue
        except Exception as e:
            err_count += 1
            results.append({'i': i, 'ok': False, 'error': True, 'msg': str(e)[:100], 'elapsed': time.time() - t1})
            continue

        elapsed = time.time() - t1
        success = result.get('success', False)
        tpl = result.get('template_used', '')
        method = result.get('method', '')
        report = result.get('report', {})
        see = (report.get('study_see', '') or '')[:300]
        hints = report.get('study_hint', [])
        hint_texts = [h.get('diagnosis', '') for h in hints]

        # Check if expected diagnosis keywords appear in output
        exp_words = re.findall(r'[一-鿿]{2,}', expected)
        hit_words = [w for w in exp_words if (w in see or any(w in h for h in hint_texts))]
        ok = len(hit_words) >= max(1, len(exp_words) * 0.4) if exp_words else False

        if ok: ok_count += 1

        results.append({
            'i': i, 'ok': ok, 'elapsed': elapsed,
            'template': tpl, 'method': method,
            'expected': expected, 'hints': hint_texts[:3],
        })

        pct = int((i + 1) / len(items) * 100)
        if pct % 20 == 0:
            interim_ok = sum(1 for r in results if r.get('ok'))
            t = time.time() - t0
            print(f"  {pct:3d}% ({i+1}/{len(items)})  ok={interim_ok}  errors={err_count}  elapsed={t:.0f}s")

    # Round stats
    total_elapsed = time.time() - t0
    print(f"\n  Round {round_num} Summary:")
    print(f"    Total: {len(results)}  OK: {ok_count}  Errors: {err_count}  Accuracy: {ok_count/len(results)*100:.1f}%")

    ok_results = [r for r in results if r.get('ok')]
    if ok_results:
        avg_time = statistics.mean([r['elapsed'] for r in ok_results])
        print(f"    Avg time: {avg_time:.1f}s  Total: {total_elapsed:.0f}s")

    # Store for comparison
    if round_num == 1:
        round1_ok = ok_count
        round1_total = len(results)

final_ok = ok_count
final_total = len(results)

print(f"\n{'='*60}")
print(f"  Final: {final_ok}/{final_total} ({final_ok/final_total*100:.1f}%) across 5 rounds")
print(f"  Round 1 baseline: {round1_ok}/{round1_total}")
print(f"{'='*60}")
