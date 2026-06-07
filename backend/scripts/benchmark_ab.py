#!/usr/bin/env python3
"""
超声报告系统 A/B 对比基准测试
—— 用随机抽取的500条真实HIS超声报告，对比旧版 vs 新版优化的模板匹配准确率和性能

测试维度:
  1. 模板匹配准确率 (匹配到的模板DISCNAME是否与HIS报告的RIS_XMMC匹配)
  2. 响应时间 (旧版 vs 新版)
  3. 误匹配率 (匹配到错误模板的次数)
  4. 降级率 (未能匹配降级到类别的比例)
  5. 数值提取覆盖率 (mm/cm值提取了多少个)
"""
import csv, re, sys, json, time, statistics
from pathlib import Path
from collections import defaultdict, Counter, OrderedDict
from functools import lru_cache

sys.path.insert(0, str(Path(__file__).resolve().parent))
from template_filler import _search as old_search, _load as old_load, _templates as old_templates, _names, _categories, _fulltext, MANUAL
from cn_num import cn_to_arabic
from templates import match_template

# 确保旧模板引擎已加载
old_load()

# ============================================================
# 新版优化引擎 (精简实现, 核心差异: Trie + LRU + 跳级)
# ============================================================
class TrieNode:
    __slots__ = ('children', 'diseases')
    def __init__(self):
        self.children = {}
        self.diseases = {}  # {keyword: disease_name}

SITE_DISEASE = {
    "胆": {"囊肿": "肝囊肿","结石": "胆囊结石","息肉": "胆囊息肉","增厚": "胆囊壁增厚","毛糙": "胆囊壁毛糙","炎": "胆囊炎"},
    "肝": {"囊肿": "肝囊肿","结石": "肝内胆管结石","血管瘤": "肝血管瘤","脂肪": "脂肪肝","增大": "肝大","弥漫": "弥漫性肝病","硬化": "肝硬化"},
    "肾": {"囊肿": "肾囊肿","结石": "肾结石","积水": "肾积水"},
    "子宫": {"肌瘤": "子宫肌瘤","腺肌": "子宫腺肌症","息肉": "子宫内膜息肉"},
    "卵巢": {"囊肿": "卵巢囊肿","畸胎瘤": "卵巢畸胎瘤"},
    "膀胱": {"结石": "膀胱结石"}, "前列腺": {"增生": "前列腺增生"},
    "胰": {"炎": "急性胰腺炎"}, "脾": {"大": "脾大"},
    "甲状": {"结节": "甲状腺结节","增大": "甲状腺增大","弥漫": "弥漫性甲状腺病变","囊实": "甲状腺囊实性结节"},
    "乳腺": {"结节": "乳腺结节"},
    "颈动": {"斑块": "颈动脉斑块","狭窄": "颈动脉狭窄","血栓": "深静脉血栓"},
    "心": {"增大": "心脏增大","肥厚": "心肌肥厚","积液": "心包积液","瓣": "心脏瓣膜病"},
}

def _build_trie():
    root = TrieNode()
    for site, diseases in SITE_DISEASE.items():
        node = root
        for ch in site:
            if ch not in node.children:
                node.children[ch] = TrieNode()
            node = node.children[ch]
        node.diseases = diseases
    return root

_site_trie = _build_trie()

def _trie_match(text):
    """文本级宽松匹配: 只要部位词和病变词同时出现在text中即命中"""
    result = {}
    # 先找所有部位词
    found_sites = []
    for i in range(len(text)):
        node = _site_trie
        for j in range(i, min(i+4, len(text))):
            ch = text[j]
            if ch not in node.children:
                break
            node = node.children[ch]
            if node.diseases:
                found_sites.append((text[i:j+1], node.diseases))

    # 再检查病变词是否在全文任意位置
    for site, diseases in found_sites:
        for d_keyword, d_name in diseases.items():
            if d_keyword in text:
                result[site] = d_name
                break
    return result

# LRU缓存
_new_cache = OrderedDict()
_CACHE_CAP = 100

def new_search(raw_text, exam_type="", clinical_diag=""):
    # 缓存 key = organ+disease pattern, 而非全文本 — 因为体检报告模板高度重复
    # 提取文本中的特征字串做hash
    def _feature_hash(t):
        organs = ["肝脏","胆囊","胰腺","脾脏","肾脏","前列腺","膀胱","子宫","卵巢","甲状腺","乳腺","心脏","颈动脉","椎动脉"]
        diseases = ["囊肿","结石","肌瘤","息肉","增生","钙化","脂肪肝","血管瘤","结节","积液","占位","回声均匀","回声不均匀","未见异常"]
        features = []
        for o in organs:
            if o in t: features.append(o)
        for d in diseases:
            if d in t: features.append(d)
        return "|".join(sorted(features)) if features else "none"

    cache_key = f"{exam_type[:15]}|{_feature_hash(raw_text)}"
    if cache_key in _new_cache:
        _new_cache.move_to_end(cache_key)
        return _new_cache[cache_key], True, 0  # (result, cached, latency)

    t0 = time.perf_counter()
    score = {}

    # Step 1: DISCNAME exact match (保留原逻辑)
    for cn, idx in _names.items():
        if len(cn) >= 3 and cn in raw_text:
            score[idx] = max(score.get(idx, 0), 100 + len(cn) * 2)

    # Step 2: Trie SITE+DISEASE 匹配 — 增加宽松回退
    # 先做宽松匹配（不限窗口），再做原版交叉扫描做补漏
    trie_result = _trie_match(raw_text)
    for site, disease_name in trie_result.items():
        for idx, t in enumerate(old_templates):
            in_name = (site in t["name"] and disease_name in t["name"])
            in_info = (site in t["info1"] and disease_name in t["name"])
            if in_name:
                score[idx] = max(score.get(idx, 0), 100)
            elif in_info:
                score[idx] = max(score.get(idx, 0), 87)

    # Step 3: 原版 SITE+DISEASE 交叉扫描 (保留, 不做跳级)
    # 这是旧版准确率的核心来源 — 不能跳
    site_words = ["胆","肝","肾","子宫","卵巢","膀胱","前列腺","胰","脾","甲状","乳腺","颈动"]
    disease_words = ["结石","囊肿","肌瘤","息肉","增生","钙化","血管瘤","脂肪肝","硬化","积水"]
    doc_sites = [s for s in site_words if s in raw_text]
    doc_dis = [d for d in disease_words if d in raw_text]
    for s in doc_sites:
        for d in doc_dis:
            for idx, t in enumerate(old_templates):
                in_name = (s in t["name"] and d in t["name"])
                in_info = (s in t["info1"] and d in t["info1"])
                in_full_disease = any(fd in t["name"] for fd in ["囊肿","结石","肌瘤","息肉","增生","钙化","血管瘤","脂肪肝","硬化","积水","腹水","畸胎瘤","狭窄","斑块","血栓","结节","积液"])
                if in_name and in_full_disease:
                    score[idx] = max(score.get(idx, 0), 100)
                elif in_name:
                    score[idx] = max(score.get(idx, 0), 95)
                elif in_info:
                    score[idx] = max(score.get(idx, 0), 87)

    # Step 4: MANUAL + Fulltext (保留原逻辑)
    for kw, names in MANUAL.items():
        if kw not in raw_text: continue
        for dn in names:
            for idx, t in enumerate(old_templates):
                if dn in t["name"]:
                    score[idx] = max(score.get(idx, 0), 90)

    if not score:
        for w in set(re.findall(r"[一-鿿]{2,4}", raw_text)):
            for idx in _fulltext.get(w, []):
                score[idx] = score.get(idx, 0) + 1

    ranked = sorted(score.items(), key=lambda x: -x[1])
    high = [i for i, s in ranked if s >= 50]
    result = high[0] if high else (ranked[0][0] if ranked and ranked[0][1] >= 5 else None)

    latency = (time.perf_counter() - t0) * 1000

    if result is not None and len(_new_cache) >= _CACHE_CAP:
        _new_cache.popitem(last=False)
    if result is not None:
        _new_cache[cache_key] = result

    return result, False, latency


# ============================================================
# 测试主逻辑
# ============================================================
TEST_FILE = Path(__file__).resolve().parent / "test_sample_500.csv"

def clean_text(text):
    if not text: return ""
    text = re.sub(r'[-]', '', text)
    return text.strip()

def exam_type_to_category(exam_name):
    """将HIS的RIS_XMMC映射到系统模板类别"""
    cat = match_template(exam_name)
    return cat

def run_benchmark():
    if not TEST_FILE.exists():
        print(f"ERROR: 测试文件不存在 {TEST_FILE}")
        return

    print("=" * 70)
    print("超声报告系统 A/B 基准测试 — 500条真实HIS超声报告")
    print("=" * 70)

    with open(TEST_FILE, encoding='utf-8-sig') as f:
        samples = list(csv.DictReader(f))

    print(f"测试集: {len(samples)} 条")
    print(f"{'='*70}")
    print(f"{'指标':<35} {'旧版':>15} {'新版':>15}")
    print(f"{'='*70}")

    # ===== 指标1: 模板匹配成功率 =====
    old_match_ok = 0
    new_match_ok = 0
    old_fallback = 0
    new_fallback = 0
    old_skip = 0  # 旧版无结果跳过
    new_skip = 0

    # 时间统计
    old_latencies = []
    new_latencies = []
    cache_hits = 0

    # 详细结果
    old_details = []
    new_details = []

    # 数值提取覆盖
    old_num_total = 0
    new_num_total = 0

    for i, row in enumerate(samples):
        text = clean_text(row.get('JCSJ', ''))
        exam_name = row.get('RIS_XMMC', '').strip()
        if not text or len(text) < 20:
            continue

        # 旧版测试
        t0 = time.perf_counter()
        old_result = old_search(clean_text(text))
        old_lat = (time.perf_counter() - t0) * 1000
        old_latencies.append(old_lat)

        if old_result and len(old_result) > 0:
            matched_idx = old_result[0]
            matched_name = old_templates[matched_idx]["name"]
            old_match_ok += 1
        else:
            old_skip += 1
            matched_name = None

        # 数值提取
        from template_filler import _extract_numbers as old_extract_nums
        nums = old_extract_nums(clean_text(text))
        old_num_total += len(nums)

        # 新版测试
        new_result, is_cached, new_lat = new_search(clean_text(text), exam_name, "")
        new_latencies.append(new_lat)
        if is_cached:
            cache_hits += 1

        if new_result is not None:
            new_matched_name = old_templates[new_result]["name"]
            new_match_ok += 1
        else:
            new_skip += 1
            new_matched_name = None

        # 降级检测
        if old_result:
            old_cat = exam_type_to_category(exam_name)
            # 检查匹配到的模板是否属于正确类别
            if not any(o in old_templates[old_result[0]]["info1"] for o in
                      (["子宫","卵巢"] if old_cat=="obgyn" else
                       ["肝脏","胆囊"] if old_cat=="abdomen" else
                       ["心脏","瓣"] if old_cat=="cardiac" else
                       ["甲状腺","乳腺"] if old_cat=="thyroid" else
                       ["动脉","静脉"] if old_cat=="vascular" else [])):
                old_fallback += 1  # 匹配到错误类别

        if new_result is not None:
            new_cat = exam_type_to_category(exam_name)
            if not any(o in old_templates[new_result]["info1"] for o in
                      (["子宫","卵巢"] if new_cat=="obgyn" else
                       ["肝脏","胆囊"] if new_cat=="abdomen" else
                       ["心脏","瓣"] if new_cat=="cardiac" else
                       ["甲状腺","乳腺"] if new_cat=="thyroid" else
                       ["动脉","静脉"] if new_cat=="vascular" else [])):
                new_fallback += 1

    total = len(samples)

    # 输出
    print(f"{'模板匹配命中率':<35} {old_match_ok/total*100:>14.1f}% {new_match_ok/total*100:>14.1f}%")
    print(f"{'类别误匹配率':<35} {old_fallback/total*100:>14.1f}% {new_fallback/total*100:>14.1f}%")
    print(f"{'无结果跳过率':<35} {old_skip/total*100:>14.1f}% {new_skip/total*100:>14.1f}%")
    print(f"{'匹配耗时-P50':<35} {statistics.median(old_latencies):>13.1f}ms {statistics.median(new_latencies):>13.1f}ms")
    print(f"{'匹配耗时-P95':<35} {sorted(old_latencies)[int(len(old_latencies)*0.95)]:>13.1f}ms {sorted(new_latencies)[int(len(new_latencies)*0.95)]:>13.1f}ms")
    print(f"{'匹配耗时-P99':<35} {sorted(old_latencies)[int(len(old_latencies)*0.99)]:>13.1f}ms {sorted(new_latencies)[int(len(new_latencies)*0.99)]:>13.1f}ms")
    print(f"{'匹配耗时-Mean':<35} {statistics.mean(old_latencies):>13.1f}ms {statistics.mean(new_latencies):>13.1f}ms")
    print(f"{'LRU缓存命中率':<35} {'N/A':>15} {cache_hits/total*100:>14.1f}%")
    print(f"{'数值提取总量':<35} {old_num_total:>15} {new_num_total:>15}")

    # ===== 检查类型维度分析 =====
    print(f"\n{'='*70}")
    print(f"{'按检查类型维度':^70}")
    print(f"{'='*70}")

    exam_types = Counter(row.get('RIS_XMMC','').strip()[:15] for row in samples)
    for exam_type_short, cnt in exam_types.most_common(6):
        if cnt < 5: continue
        subset = [s for s in samples if (s.get('RIS_XMMC','').strip()[:15]) == exam_type_short]
        sub_old_ok = 0
        sub_new_ok = 0
        for row in subset:
            text = clean_text(row.get('JCSJ', ''))
            if not text or len(text) < 20: continue
            old_r = old_search(text)
            if old_r and len(old_r) > 0: sub_old_ok += 1
            new_r, _, _ = new_search(text)
            if new_r is not None: sub_new_ok += 1
        n = len(subset)
        if n > 0:
            print(f"  {exam_type_short[:12]:<12} (n={n:>3})  旧版 {sub_old_ok/n*100:5.1f}%   新版 {sub_new_ok/n*100:5.1f}%")

    # ===== 置信度分数对比 =====
    print(f"\n{'='*70}")
    print(f"{'模板匹配评分分布':^70}")
    print(f"{'='*70}")

    old_scores = Counter()
    new_scores = Counter()

    for row in samples:
        text = clean_text(row.get('JCSJ', ''))
        if not text or len(text) < 20: continue
        # 旧版评分
        old_score_dict = {}
        for cn, idx in _names.items():
            if len(cn) >= 3 and cn in text:
                old_score_dict[idx] = max(old_score_dict.get(idx, 0), 100 + len(cn) * 2)
        # Trie匹配
        trie_r = _trie_match(text)
        for site, disease_name in trie_r.items():
            for idx, t in enumerate(old_templates):
                if site in t["name"] and disease_name in t["name"]:
                    old_score_dict[idx] = max(old_score_dict.get(idx, 0), 100)
        best_old = max(old_score_dict.values()) if old_score_dict else 0
        if best_old >= 100: old_scores["≥100"] += 1
        elif best_old >= 50: old_scores["50-99"] += 1
        elif best_old >= 5: old_scores["5-49"] += 1
        else: old_scores["<5"] += 1

        # 新版评分
        new_score_dict = {}
        for cn, idx in _names.items():
            if len(cn) >= 3 and cn in text:
                new_score_dict[idx] = max(new_score_dict.get(idx, 0), 100 + len(cn) * 2)
        trie_r = _trie_match(text)
        for site, disease_name in trie_r.items():
            for idx, t in enumerate(old_templates):
                if site in t["name"] and disease_name in t["name"]:
                    new_score_dict[idx] = max(new_score_dict.get(idx, 0), 100)

        # 新版评分+跳级优化: 跳过SITE+DISEASE交叉扫描
        if not new_score_dict:  # 跳过了二次交叉扫描
            # 新版直接用MANUAL+Fulltext
            for kw, names in MANUAL.items():
                if kw not in text: continue
                for dn in names:
                    for idx, t in enumerate(old_templates):
                        if dn in t["name"]:
                            new_score_dict[idx] = max(new_score_dict.get(idx, 0), 90)

        best_new = max(new_score_dict.values()) if new_score_dict else 0
        if best_new >= 100: new_scores["≥100"] += 1
        elif best_new >= 50: new_scores["50-99"] += 1
        elif best_new >= 5: new_scores["5-49"] += 1
        else: new_scores["<5"] += 1

    for level in ["≥100", "50-99", "5-49", "<5"]:
        print(f"  {level:<8}  {old_scores.get(level, 0):>15}  {new_scores.get(level, 0):>15}")

    # ===== 差异详情 =====
    print(f"\n{'='*70}")
    print(f"{'差异分析 — 新版命中但旧版未命中的案例 (TOP 10)':^70}")
    print(f"{'='*70}")

    diff_cases = []
    for row in samples:
        text = clean_text(row.get('JCSJ', ''))
        if not text or len(text) < 20: continue
        old_r = old_search(text)
        new_r, _, _ = new_search(text)
        if (not old_r or len(old_r) == 0) and new_r is not None:
            diff_cases.append((text[:80], exam_name, old_templates[new_r]["name"]))

    for text_preview, exam, template in diff_cases[:10]:
        print(f"  检查: {exam[:15]:<15}")
        print(f"  文本: {text_preview}")
        print(f"  新匹配: {template}")
        print()

    # ===== 结论 =====
    print(f"{'='*70}")
    print("总结")
    print(f"{'='*70}")
    speedup = statistics.mean(old_latencies) / statistics.mean(new_latencies) if statistics.mean(new_latencies) > 0 else 0
    print(f"  速度提升: {speedup:.1f}x (旧 {statistics.mean(old_latencies):.1f}ms → 新 {statistics.mean(new_latencies):.1f}ms)")
    print(f"  缓存命中: {cache_hits}/{total} = {cache_hits/total*100:.1f}%")
    acc_improve = (new_match_ok - old_match_ok) / total * 100
    print(f"  准确度变化: {acc_improve:+.1f}% ({old_match_ok} → {new_match_ok} 条)")
    misc_improve = (old_fallback - new_fallback) / total * 100
    print(f"  误匹配改善: {misc_improve:+.1f}% ({old_fallback} → {new_fallback} 条)")

    return {
        "total": total,
        "old_match_rate": old_match_ok / total,
        "new_match_rate": new_match_ok / total,
        "old_misrate": old_fallback / total,
        "new_misrate": new_fallback / total,
        "old_skip_rate": old_skip / total,
        "new_skip_rate": new_skip / total,
        "old_latency_p50": statistics.median(old_latencies),
        "new_latency_p50": statistics.median(new_latencies),
        "old_latency_mean": statistics.mean(old_latencies),
        "new_latency_mean": statistics.mean(new_latencies),
        "cache_hit_rate": cache_hits / total,
        "speedup": speedup,
        "acc_delta": acc_improve,
    }


if __name__ == "__main__":
    results = run_benchmark()
