#!/usr/bin/env python3
"""意图识别准确度测试 — 从HIS 500条随机超声报告验证 detect_template_category"""
import csv, re, sys, time, json, random
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixed_template_engine import detect_template_category

# 预期映射: HIS RIS_XMMC → 意图类别
EXAM_TO_CATEGORY = {
    "腹部彩超": "腹部",
    "前列腺膀胱彩超": "泌尿前列腺",
    "甲状腺彩超": "甲状腺乳腺",
    "妇科彩超": "妇产",
    "乳腺彩超": "甲状腺乳腺",
    "心脏彩超": "心脏",
    "双侧颈部动脉彩超": "血管",
    "阴道彩超": "妇产",
    "脑血管彩超": "血管",
}

def map_exam(exam):
    for key, cat in EXAM_TO_CATEGORY.items():
        if key in exam:
            return cat
    return "未知"

def run_test():
    sample_file = Path(__file__).resolve().parent / "test_sample_500.csv"
    if not sample_file.exists():
        print("ERROR: test_sample_500.csv not found")
        return

    with open(sample_file, encoding='utf-8-sig') as f:
        samples = list(csv.DictReader(f))

    correct = 0
    wrong = 0
    detail = []
    confusion = Counter()

    for i, row in enumerate(samples):
        text = row.get("JCSJ", "")
        exam = row.get("RIS_XMMC", "").strip()
        if not text or len(text) < 20:
            continue
        text = re.sub(r'[-]', '', text).strip()

        expected = map_exam(exam)
        result = detect_template_category(text)
        predicted = result["category"]
        conf = result["confidence"]

        if predicted == expected:
            correct += 1
            detail.append(("OK", exam[:15], predicted, conf))
        else:
            wrong += 1
            confusion[(expected, predicted)] += 1
            detail.append(("MIS", exam[:15], predicted, conf, expected))

    n = correct + wrong
    print("=" * 70)
    print("Intent Detection Accuracy Test — %d samples" % n)
    print("=" * 70)
    print("Correct: %d / %d = %.1f%%" % (correct, n, correct / n * 100))
    print("Wrong:   %d / %d = %.1f%%" % (wrong, n, wrong / n * 100))
    print()

    # 混淆矩阵
    print("=== Confusion Matrix (expected -> predicted) ===")
    for (exp, pred), cnt in confusion.most_common():
        print("  %-15s -> %-15s  %d times" % (exp, pred, cnt))

    # 每类准确率
    print()
    print("=== Per-category Accuracy ===")
    cat_stats = {}
    for status, exam, predicted, conf, *rest in detail:
        exp = rest[0] if rest else predicted
        cat = exp
        if cat not in cat_stats:
            cat_stats[cat] = [0, 0]
        cat_stats[cat][1] += 1
        if status == "OK":
            cat_stats[cat][0] += 1

    for cat in sorted(cat_stats):
        ok, total = cat_stats[cat]
        print("  %-15s  %d/%d = %.1f%%" % (cat, ok, total, ok / total * 100))

    # 置信度分布
    confs_ok = [c for s, _, _, c, *_ in detail if s == "OK"]
    confs_mis = [c for s, _, _, c, *_ in detail if s == "MIS"]
    print()
    print("=== Confidence Distribution ===")
    if confs_ok:
        print("  Correct:   mean=%.2f  min=%.2f  max=%.2f" % (
            sum(confs_ok) / len(confs_ok), min(confs_ok), max(confs_ok)))
    if confs_mis:
        print("  Wrong:     mean=%.2f  min=%.2f  max=%.2f" % (
            sum(confs_mis) / len(confs_mis), min(confs_mis), max(confs_mis)))

    # 误分类详情 (top 10)
    print()
    print("=== Top 10 Misclassifications ===")
    shown = 0
    for item in detail:
        if item[0] == "MIS" and shown < 10:
            status, exam, predicted, conf = item[:4]
            expected = item[4] if len(item) > 4 else "?"
            print("  [%s] exam=%s  expected=%s  got=%s  conf=%.2f" % (
                status, exam[:15], expected, predicted, conf))
            shown += 1

    return correct / n if n else 0


if __name__ == "__main__":
    acc = run_test()
    print()
    print("Accuracy: %.1f%%" % (acc * 100))
