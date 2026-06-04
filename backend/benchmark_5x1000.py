#!/usr/bin/env python3
"""
规则修复后的 5轮×1000条 循环基准测试
测量: 匹配准确率/误匹配率/跳过率/耗时/缓存命中率 — 每轮统计
"""
import csv, re, sys, time, statistics, random
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, str(Path(__file__).resolve().parent))

from template_filler import _search as old_search, _load, _templates, _names
from template_engine_v2 import search_optimized
from template_engine_v2 import _cache as te2_cache
from templates import match_template

_load()

TEST_FILE = Path(__file__).resolve().parent / "test_sample_1000.csv"

CAT_ORGANS_MAP = {
    'obgyn':    ['子宫','卵巢','附件','胎儿','妊娠','孕'],
    'abdomen':  ['肝脏','胆囊','胰腺','脾脏','肾脏','膀胱','前列腺','腹腔','腹'],
    'cardiac':  ['心脏','心室','心房','瓣','心包','肺动脉','室间隔','二尖瓣','主动脉瓣','三尖瓣'],
    'thyroid':  ['甲状腺','乳腺','淋巴结','睾丸','腮腺'],
    'vascular': ['动脉','静脉','血栓','斑块','流速','IMT','颈动脉','椎动脉'],
    'tcd':      ['椎动脉','基底动脉','脑动脉','大脑','经颅'],
}

def clean_text(text):
    if not text: return ""
    return re.sub(r'[-]', '', text).strip()

def is_mismatch(template_idx, exam_name):
    """模板器官是否匹配检查类型类别"""
    if template_idx is None: return False
    expected = match_template(exam_name)
    if expected not in CAT_ORGANS_MAP: return False
    info = _templates[template_idx]["info1"]
    return not any(o in info for o in CAT_ORGANS_MAP[expected])

def run_round(samples, round_no, warm=False):
    """单轮测试"""
    te2_cache.clear()
    n = len(samples)

    old_ok = new_ok = 0
    old_mis = new_mis = 0
    old_skip = new_skip = 0
    old_times = []; new_times = []
    cache_hits = 0

    for row in samples:
        text = clean_text(row.get('JCSJ', ''))
        exam = row.get('RIS_XMMC', '').strip()
        if not text or len(text) < 20: continue

        # --- 旧版 ---
        t0 = time.perf_counter()
        o_idx = old_search(text)
        old_times.append((time.perf_counter() - t0) * 1000)

        if o_idx:
            old_ok += 1
            if is_mismatch(o_idx[0], exam): old_mis += 1
        else:
            old_skip += 1

        # --- 新版 ---
        t0 = time.perf_counter()
        pre_len = len(te2_cache)
        n_idx = search_optimized(text, exam)
        post_len = len(te2_cache)
        new_times.append((time.perf_counter() - t0) * 1000)
        if post_len == pre_len and len(te2_cache) > 0:
            cache_hits += 1

        if n_idx:
            new_ok += 1
            if is_mismatch(n_idx[0], exam): new_mis += 1
        else:
            new_skip += 1

    # 统计
    p50_old = statistics.median(old_times) if old_times else 0
    p95_old = sorted(old_times)[int(n*0.95)] if old_times else 0
    p50_new = statistics.median(new_times) if new_times else 0
    p95_new = sorted(new_times)[int(n*0.95)] if new_times else 0

    print(
        'R%d  %s  match  old=%4d(%5.1f%%)  new=%4d(%5.1f%%)  '
        'mis  old=%3d(%4.1f%%)  new=%3d(%4.1f%%)  '
        'skip  old=%3d  new=%3d  '
        'p50  old=%5.0fus  new=%5.0fus  '
        'cache=%4d(%5.1f%%)'
        % (
            round_no,
            '(W)' if warm else '   ',
            old_ok, old_ok/n*100, new_ok, new_ok/n*100,
            old_mis, old_mis/n*100, new_mis, new_mis/n*100,
            old_skip, new_skip,
            p50_old*1000, p50_new*1000,
            cache_hits, cache_hits/n*100,
        )
    )
    sys.stdout.flush()

    return {
        'round': round_no, 'warm': warm, 'n': n,
        'old': {'ok': old_ok, 'mis': old_mis, 'skip': old_skip, 'p50_us': p50_old*1000, 'p95_us': p95_old*1000},
        'new': {'ok': new_ok, 'mis': new_mis, 'skip': new_skip, 'p50_us': p50_new*1000, 'p95_us': p95_new*1000},
        'cache_hits': cache_hits, 'cache_hit_rate': cache_hits/n*100,
    }


def main():
    with open(TEST_FILE, encoding='utf-8-sig') as f:
        samples = list(csv.DictReader(f))

    n = len(samples)
    print('=' * 100)
    print('5 Rounds x %d Samples — Rule-Fixed Benchmark' % n)
    print('=' * 100)
    print('R#  state  match  old/hit  new/hit  |  mis  old  new  |  skip  old  new  |  p50 old/us  new/us  |  cache hit')
    print('-' * 100)

    results = []

    # Round 1: 冷启动
    results.append(run_round(samples, 1, warm=False))

    # Round 2-5: 热运行 (缓存100条已覆盖主模式, 4轮够稳定)
    for r in range(2, 6):
        # 每轮打乱顺序, 模拟真实使用中不同患者顺序
        rng = random.Random(r * 100 + 42)
        shuffled = samples[:]
        rng.shuffle(shuffled)
        results.append(run_round(shuffled, r, warm=True))

    # --- 汇总 ---
    print('-' * 100)
    warm_results = [r for r in results if r['warm']]
    avg_old_ok = sum(r['old']['ok'] for r in warm_results) / len(warm_results)
    avg_new_ok = sum(r['new']['ok'] for r in warm_results) / len(warm_results)
    avg_old_mis = sum(r['old']['mis'] for r in warm_results) / len(warm_results)
    avg_new_mis = sum(r['new']['mis'] for r in warm_results) / len(warm_results)
    avg_old_p50 = sum(r['old']['p50_us'] for r in warm_results) / len(warm_results)
    avg_new_p50 = sum(r['new']['p50_us'] for r in warm_results) / len(warm_results)
    avg_cache = sum(r['cache_hit_rate'] for r in warm_results) / len(warm_results)

    print()
    print('=== 4轮热运行平均 ===')
    print('  匹配率:   old %5.1f%%  →  new %5.1f%%  (%+.1f%%)' %
          (avg_old_ok/n*100, avg_new_ok/n*100, (avg_new_ok-avg_old_ok)/n*100))
    print('  误匹配:   old %4.1f%%  →  new %4.1f%%  (%+.1f%%)' %
          (avg_old_mis/n*100, avg_new_mis/n*100, (avg_new_mis-avg_old_mis)/n*100))
    print('  延迟P50:  old %5.0fus  →  new %5.0fus  (%.1fx)' %
          (avg_old_p50, avg_new_p50, avg_old_p50/max(avg_new_p50, 0.01)))
    print('  缓存命中: %.1f%%' % avg_cache)


if __name__ == '__main__':
    main()
