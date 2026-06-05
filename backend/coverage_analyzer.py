#!/usr/bin/env python3
"""
Ultrasound Template Coverage Analyzer + Auto-Fixer
自动检测模板匹配覆盖不足的类型, 并自动补全 tags + match_keywords

用法:
  python coverage_analyzer.py                # 分析 + 诊断
  python coverage_analyzer.py --fix          # 自动修复
  python coverage_analyzer.py --benchmark    # 批量测试1000条
"""

import sys, os, json, csv, re, argparse
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent))

# ── Config ──
TAG_FILE = Path(__file__).parent / "knowledge" / "template_tags_v2.json"
RULE_FILE = Path(__file__).parent / "knowledge" / "master_rules.json"
CSV_FILE = Path(os.environ.get("TEMPLATE_CSV", ""))
TEST_FILE = Path(__file__).parent / "test_sample_1000.csv"

# ── Load  ──
def load_all():
    with open(TAG_FILE, encoding='utf-8') as f:
        tags = json.load(f)
    with open(RULE_FILE, encoding='utf-8') as f:
        rules = json.load(f)
    match_kw = rules.get("templates", {}).get("match_keywords", {})

    csv_data = {}
    if CSV_FILE.exists():
        with open(CSV_FILE, encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                name = (row.get('DISCNAME') or '').strip()
                if name and name not in ('0', 'NULL', ''):
                    csv_data[name] = dict(row)
    return tags, match_kw, csv_data


# ── Diagnostics ──

def diagnose_template_coverage(tags, match_kw, csv_data):
    """检查哪些模板类型覆盖不足"""
    issues = []

    # 1. match_kw 有但 tags 没有
    tag_names = set()
    for cat in tags.get("categories", []):
        for t in cat.get("templates", []):
            tag_names.add(t.get("name", ""))

    kw_only = set(match_kw.keys()) - tag_names
    if kw_only:
        issues.append({
            "type": "match_kw_only",
            "severity": "high",
            "count": len(kw_only),
            "items": sorted(kw_only)[:20],
            "fix": "这些模板在match_keywords中有定义但不在template_tags中, P1-P4评分无法生效"
        })

    # 2. CSV 有但 match_kw 没有 (覆盖不足)
    csv_names = set()
    for name, row in csv_data.items():
        info1 = (row.get('INFO1') or '').strip()
        if len(info1) > 20:  # 只看有实质内容的
            csv_names.add(name)

    uncovered = csv_names - set(match_kw.keys())
    if uncovered:
        issues.append({
            "type": "no_match_kw",
            "severity": "medium",
            "count": len(uncovered),
            "items": sorted(uncovered)[:20],
            "fix": "这些CSV模板没有match_keywords, 无法被P0关键词匹配到"
        })

    # 3. 按检查类型统计 tag 覆盖
    level2_counts = Counter()
    for cat in tags.get("categories", []):
        level2 = cat.get("level2", "")
        cnt = len(cat.get("templates", []))
        level2_counts[level2] = cnt

    print("\n=== 模板覆盖统计 ===")
    for l2, cnt in level2_counts.most_common():
        bar = "█" * min(cnt // 5, 20)
        print(f"  {l2:8s} [{bar:<20s}] {cnt:3d}")

    # 4. 检查 exam_type 关键词覆盖
    exam_kw = {"腹部": ["肝胆","胰腺","脾脏","肾脏","腹部","胆囊","胆总管"],
               "心脏": ["心脏","二尖瓣","三尖瓣","主动脉","心包","心室","心房","瓣膜","EF","反流"],
               "妇产": ["子宫","卵巢","宫颈","盆腔","胎儿","孕囊","胎盘","羊水","脐带","胚芽","胎心"],
               "甲状腺": ["甲状腺","峡部","结节","TI-RADS"],
               "乳腺": ["乳腺","腋窝","BI-RADS"],
               "血管": ["颈动脉","椎动脉","斑块","IMT","流速","基底动脉"],
               "泌尿": ["前列腺","膀胱","残余尿","精囊","睾丸"],
               "骨骼肌肉": ["关节","骨骼","肌腱","半月板"]}

    print("\n=== P0 match_keywords 按类型覆盖 ===")
    for exam, kws in exam_kw.items():
        covered = []
        for kw in kws:
            found = False
            for tpl, tpl_kws in match_kw.items():
                if kw in tpl_kws or kw in tpl:
                    found = True
                    break
            covered.append((kw, found))
        hits = sum(1 for _, f in covered if f)
        bar = "H" * hits + "-" * (len(kws) - hits)
        print(f"  {exam:6s} [{bar}] {hits}/{len(kws)}")

    return issues


def auto_fix(issues, tags, match_kw, csv_data):
    """自动修复发现的问题"""
    fixes = 0

    for issue in issues:
        if issue["type"] == "match_kw_only":
            # 把 match_kw中的模板名加到 tags
            for name in issue["items"]:
                # 推断 level2
                level2 = _infer_level2(name)
                for cat in tags.get("categories", []):
                    if cat.get("level2") == level2:
                        cat["templates"].append({
                            "name": name, "level1": cat["level1"],
                            "level2": level2, "level3": _infer_level3(name),
                            "template_id": f"auto_{name}", "fields_count": 0
                        })
                        fixes += 1
                        break
            print(f"  Fixed {fixes} missing tags from match_kw")

        if issue["type"] == "no_match_kw":
            # 为CSV中有但match_kw没有的模板生成关键词
            for name in issue["items"]:
                row = csv_data.get(name, {})
                info1 = (row.get('INFO1') or '')[:200]
                keywords = _extract_keywords(name, info1)
                match_kw[name] = keywords
                fixes += 1
            print(f"  Added {fixes} match_keywords from CSV templates")

    if fixes > 0:
        with open(TAG_FILE, 'w', encoding='utf-8') as f:
            json.dump(tags, f, ensure_ascii=False, indent=2)

        with open(RULE_FILE, encoding='utf-8') as f:
            rules = json.load(f)
        rules["templates"]["match_keywords"] = match_kw
        with open(RULE_FILE, 'w', encoding='utf-8') as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)

        print(f"\nAuto-fixed {fixes} issues. Tags and match_keywords updated.")
    else:
        print("No auto-fixes needed.")

    return fixes


def _infer_level2(name):
    keywords = {
        "心脏": ["心脏","心室","心房","瓣膜","二尖","三尖","主动脉","肺动脉","心包"],
        "腹部": ["肝脏","胆囊","胰腺","脾脏","肾脏","肝","胆","胰","脾","肾","腹部"],
        "妇产": ["子宫","卵巢","宫颈","盆腔","胎儿","孕囊","胎盘","产科"],
        "甲状腺乳腺": ["甲状腺","乳腺","峡部","结节","乳房"],
        "血管": ["颈动脉","椎动脉","斑块","IMT","动脉","静脉","血管"],
        "泌尿前列腺": ["前列腺","膀胱","精囊","睾丸","肾","泌尿"],
    }
    for l2, kws in keywords.items():
        if any(kw in name for kw in kws):
            return l2
    return "其他"


def _infer_level3(name):
    organs = ["肝脏","胆囊","胰腺","脾脏","肾脏","子宫","卵巢","前列腺","膀胱",
              "甲状腺","乳腺","二尖瓣","主动脉瓣","颈动脉","椎动脉","胎儿"]
    for o in organs:
        if o in name:
            return o
    return "其他"


def _extract_keywords(name, info1):
    kw = set()
    clean = re.sub(r'[\[\]\(\)（）\*\+\-\.]', '', name)
    kw.add(clean[:30])
    # 3-char chunks
    for i in range(len(clean)-2):
        chunk = clean[i:i+3]
        if re.match(r'^[一-鿿]{3}$', chunk):
            kw.add(chunk)
    # from info1
    info_clean = re.sub(r'[\[\]\(\)（）\*\+]', '', info1)[:50]
    for i in range(len(info_clean)-2):
        chunk = info_clean[i:i+3]
        if re.match(r'^[一-鿿]{3}$', chunk):
            kw.add(chunk)
    return sorted(kw, key=len, reverse=True)[:8]


# ── Benchmark ──

def benchmark_from_test_file():
    """从 test_sample_1000.csv 批量测试覆盖率"""
    if not TEST_FILE.exists():
        print(f"Test file not found: {TEST_FILE}")
        return

    from template_anchor import match_exact_template

    stats = defaultdict(lambda: {"total": 0, "high": 0, "low": 0, "none": 0})
    low_cases = []

    with open(TEST_FILE, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            text = (row.get('text', row.get('输入文本', row.get('JCBW', ''))) or '').strip()
            exam = (row.get('exam_type', row.get('检查类型', row.get('RIS_XMMC', ''))) or '腹部超声').strip()
            if len(text) < 10:
                continue

            results = match_exact_template(text, exam)
            stats[exam]["total"] += 1

            if not results:
                stats[exam]["none"] += 1
                low_cases.append((exam, text[:100], "无匹配"))
            elif results[0]["confidence_pct"] >= 90:
                stats[exam]["high"] += 1
            else:
                stats[exam]["low"] += 1
                if len(low_cases) < 10:
                    low_cases.append((exam, text[:100], results[0]["tpl_name"]))

            if (i + 1) % 200 == 0:
                print(f"  Processed {i+1}...")

    print(f"\n=== Benchmark Results ({sum(s['total'] for s in stats.values())} samples) ===")
    for exam, s in sorted(stats.items(), key=lambda x: -x[1]["total"]):
        high_pct = s["high"] / max(s["total"], 1) * 100
        print(f"  {exam:12s} total={s['total']:3d}  HIGH={s['high']:3d} ({high_pct:.0f}%)  LOW={s['low']:3d}  NONE={s['none']:3d}")

    if low_cases:
        print(f"\n=== Low confidence cases ({len(low_cases)} samples) ===")
        for exam, text, tpl in low_cases[:10]:
            print(f"  [{exam}] → {tpl}")
            print(f"    {text}...")


# ── Main ──

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Template Coverage Analyzer")
    parser.add_argument("--fix", action="store_true", help="Auto-fix discovered issues")
    parser.add_argument("--benchmark", action="store_true", help="Benchmark on test data")
    args = parser.parse_args()

    print("=" * 60)
    print("  Ultrasound Template Coverage Analyzer")
    print("=" * 60)

    tags, match_kw, csv_data = load_all()

    print(f"\nLoaded: {len(match_kw)} match_keywords | "
          f"{sum(len(c['templates']) for c in tags['categories'])} tags | "
          f"{len(csv_data)} CSV templates")

    issues = diagnose_template_coverage(tags, match_kw, csv_data)

    if issues:
        print(f"\n=== Issues Found ({len(issues)}) ===")
        for issue in issues:
            print(f"\n[{issue['severity'].upper()}] {issue['type']} ({issue['count']} items)")
            print(f"  Fix: {issue['fix']}")
            if issue['items']:
                print(f"  Samples: {', '.join(issue['items'][:5])}")

    if args.fix and issues:
        print("\n=== Auto-Fixing ===")
        auto_fix(issues, tags, match_kw, csv_data)

    if args.benchmark:
        print("\n=== Benchmark ===")
        benchmark_from_test_file()
