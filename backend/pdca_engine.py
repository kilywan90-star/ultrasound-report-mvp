"""PDCA 持续改进引擎 — 反馈驱动的规则库自动优化

闭环流程:
  1. Collect: 从 feedback 表读取医生修改数据
  2. Analyze: 计算每个模板/诊断的准确率、编辑率、采纳率
  3. Recommend: 生成改进建议 (新增关键词/调整阈值/补充Few-Shot)
  4. Auto-Learn: 高置信度模式自动更新 match_keywords
  5. Report: 生成 PDCA 改进报告

用法:
  python pdca_engine.py           # 生成报告
  python pdca_engine.py --apply   # 自动应用高置信度改进
"""

import json, sqlite3, os, sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "api_platform.db"
FEEDBACK_DB = ROOT / "ultrasound.db"  # 原有 SQLite

# 最小反馈数阈值: 至少 N 条反馈才触发自动学习
MIN_FEEDBACK_FOR_AUTO_LEARN = 5
# 采纳率阈值: 医生采纳率 >= 此值视为"高置信度正确"
HIGH_CONFIDENCE_THRESHOLD = 0.80


def load_feedback(days: int = 30) -> list[dict]:
    """加载最近 N 天的反馈数据"""
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        rows = conn.execute(
            "SELECT * FROM feedback WHERE created_at >= ? ORDER BY created_at DESC",
            (cutoff,)
        ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return []
    conn.close()
    results = []
    for row in rows:
        try:
            results.append(json.loads(row["data"]))
        except (json.JSONDecodeError, KeyError):
            pass
    return results


def analyze_feedback(feedbacks: list[dict]) -> dict:
    """分析反馈数据, 计算多维度指标"""
    if not feedbacks:
        return {
            "total": 0, "avg_rating": 0, "rating_distribution": {},
            "templates": {}, "hints": {}, "missing_keywords_top10": [],
            "period": "尚无反馈数据",
        }

    total = len(feedbacks)
    ratings = [f.get("rating", 0) for f in feedbacks if f.get("rating", 0) > 0]
    avg_rating = sum(ratings) / len(ratings) if ratings else 0

    # 按模板统计编辑率
    template_stats = defaultdict(lambda: {"count": 0, "edits": 0, "avg_rating": 0, "ratings": []})
    # 诊断采纳率
    hint_acceptance = defaultdict(lambda: {"accepted": 0, "rejected": 0, "added": 0})
    # 关键词高频缺失
    missing_keywords = Counter()

    for fb in feedbacks:
        # 模板维度
        original = fb.get("original_text", "")
        study_see_ai = fb.get("study_see_ai", "")
        study_see_edited = fb.get("study_see_edited", "")
        tpl = fb.get("report_id", "unknown")

        # 简化: 用 report_id 前部分作为模板标识
        ts = template_stats[tpl[:20]]
        ts["count"] += 1
        if study_see_edited and study_see_ai != study_see_edited:
            ts["edits"] += 1
        if fb.get("rating", 0) > 0:
            ts["ratings"].append(fb["rating"])

        # 诊断维度
        for h in fb.get("accepted_hints", []):
            hint_acceptance[h]["accepted"] += 1
        for h in fb.get("rejected_hints", []):
            hint_acceptance[h]["rejected"] += 1
        for h in fb.get("added_hints", []):
            hint_acceptance[h]["added"] += 1
            # 医生新增的诊断 → 可能是规则库缺失
            missing_keywords[h] += 1

    # 计算每个模板的编辑率
    template_edit_rates = {}
    for tpl_id, ts in template_stats.items():
        ts["edit_rate"] = ts["edits"] / ts["count"] if ts["count"] > 0 else 0
        ts["avg_rating"] = sum(ts["ratings"]) / len(ts["ratings"]) if ts["ratings"] else 0
        template_edit_rates[tpl_id] = dict(ts)

    # 诊断采纳率
    hint_stats = {}
    for hint, stats in hint_acceptance.items():
        total_hints = stats["accepted"] + stats["rejected"]
        acceptance_rate = stats["accepted"] / total_hints if total_hints > 0 else 0
        hint_stats[hint] = {
            **stats,
            "acceptance_rate": round(acceptance_rate, 3),
            "needs_improvement": acceptance_rate < 0.6 and total_hints >= MIN_FEEDBACK_FOR_AUTO_LEARN,
        }

    return {
        "total": total,
        "avg_rating": round(avg_rating, 2),
        "rating_distribution": dict(Counter(ratings)),
        "templates": template_edit_rates,
        "hints": hint_stats,
        "missing_keywords_top10": missing_keywords.most_common(10),
        "period": f"最近 {len(feedbacks)} 条反馈",
    }


def generate_recommendations(analysis: dict) -> list[dict]:
    """基于分析结果生成 PDCA 改进建议"""
    recommendations = []

    if analysis["total"] < MIN_FEEDBACK_FOR_AUTO_LEARN:
        recommendations.append({
            "priority": "P2",
            "action": "等待更多反馈",
            "detail": f'当前 {analysis["total"]} 条, 需要 ≥{MIN_FEEDBACK_FOR_AUTO_LEARN} 条才能触发自动学习',
            "auto_apply": False,
        })
        return recommendations

    # 模板编辑率 > 30% → 需补充关键词
    for tpl_id, stats in analysis.get("templates", {}).items():
        if stats["edit_rate"] > 0.3 and stats["count"] >= MIN_FEEDBACK_FOR_AUTO_LEARN:
            recommendations.append({
                "priority": "P1",
                "action": "补充模板匹配关键词",
                "target": tpl_id,
                "detail": f'编辑率 {stats["edit_rate"]:.0%} ({stats["count"]}条反馈), 建议检查并补充 match_keywords',
                "auto_apply": stats["edit_rate"] > 0.5,
            })

    # 诊断采纳率 < 60% → 需补充 Few-Shot
    for hint, stats in analysis.get("hints", {}).items():
        if stats.get("needs_improvement"):
            recommendations.append({
                "priority": "P1",
                "action": "补充 Few-Shot 案例",
                "target": hint,
                "detail": f'采纳率仅 {stats["acceptance_rate"]:.0%}, 建议增加相关 Few-Shot 示例',
                "auto_apply": False,  # Few-Shot 人工审核
            })

    # 高频缺失诊断 → 自动添加到 match_keywords
    missing = analysis.get("missing_keywords_top10", [])
    for kw, count in missing:
        if count >= MIN_FEEDBACK_FOR_AUTO_LEARN:
            recommendations.append({
                "priority": "P0",
                "action": "新增 match_keywords",
                "target": kw,
                "detail": f'医生新增诊断 "{kw}" {count} 次, 可自动添加到规则库',
                "auto_apply": True,
            })

    if analysis["avg_rating"] < 3.0:
        recommendations.append({
            "priority": "P0",
            "action": "检查流水线配置",
            "detail": f'医生平均评分仅 {analysis["avg_rating"]}/5, 需排查 LLM/模板/ASR 问题',
            "auto_apply": False,
        })

    return recommendations


def auto_apply_recommendations(recommendations: list[dict], dry_run: bool = True) -> dict:
    """自动应用高置信度改进建议"""
    applied = []
    skipped = []

    for rec in recommendations:
        if not rec.get("auto_apply"):
            skipped.append(rec["action"])
            continue

        action = rec["action"]
        target = rec["target"]

        if action == "新增 match_keywords":
            try:
                # 加载现有规则
                rule_file = ROOT / "knowledge" / "master_rules.json"
                with open(rule_file, encoding="utf-8") as f:
                    rules = json.load(f)

                mk = rules.setdefault("templates", {}).setdefault("match_keywords", {})

                # 自动提取关键词
                new_kws = [target, target[:2], target[-2:]]  # 简化: 用诊断名+前后2字
                existing = mk.get(target, [])

                if not dry_run:
                    mk[target] = list(set(existing + new_kws))
                    # 备份
                    bak = rule_file.with_suffix(".json.bak")
                    import shutil
                    shutil.copy2(rule_file, bak)
                    # 保存
                    with open(rule_file, "w", encoding="utf-8") as f:
                        json.dump(rules, f, ensure_ascii=False, indent=2)

                applied.append({
                    "action": action,
                    "target": target,
                    "keywords_added": new_kws,
                    "dry_run": dry_run,
                })
            except Exception as e:
                skipped.append(f"{action}({target}): {e}")

        elif action == "补充模板匹配关键词":
            applied.append({
                "action": action,
                "target": target,
                "dry_run": True,
                "note": "需人工审核模板内容后补充关键词",
            })

    if dry_run:
        return {"mode": "dry_run", "applied": applied, "skipped": skipped,
                "note": "使用 --apply 参数执行实际修改"}
    return {"mode": "applied", "applied": applied, "skipped": skipped,
            "note": "已备份原始文件为 .json.bak"}


def generate_pdca_report(days: int = 30) -> dict:
    """生成完整 PDCA 报告"""
    feedbacks = load_feedback(days)
    analysis = analyze_feedback(feedbacks)
    recommendations = generate_recommendations(analysis)

    return {
        "generated_at": datetime.now().isoformat(),
        "period": f"最近 {days} 天",
        "plan": {
            "target_accuracy": "≥95%",
            "current_accuracy": f'{analysis.get("avg_rating", 0) * 20:.0f}% (基于医生评分)',
            "knowledge_base_size": {
                "templates": "4871条 (CSV)",
                "match_keywords": "968个",
                "few_shot": "19个案例",
                "icd10": "270个编码",
            },
        },
        "do": {
            "total_calls": analysis["total"],
            "feedback_received": len(feedbacks),
            "feedback_rate": f'{len(feedbacks)/max(analysis["total"],1)*100:.1f}%',
        },
        "check": {
            "avg_doctor_rating": analysis["avg_rating"],
            "rating_distribution": analysis.get("rating_distribution", {}),
            "high_edit_rate_templates": [
                {"id": tid, "edit_rate": f'{ts["edit_rate"]:.0%}', "count": ts["count"]}
                for tid, ts in analysis.get("templates", {}).items()
                if ts["edit_rate"] > 0.3
            ],
            "low_acceptance_hints": [
                {"hint": h, "rate": f'{s["acceptance_rate"]:.0%}'}
                for h, s in analysis.get("hints", {}).items()
                if s.get("needs_improvement")
            ],
            "top_missing_diagnoses": analysis.get("missing_keywords_top10", []),
        },
        "act": {
            "recommendations": recommendations,
            "auto_apply_count": len([r for r in recommendations if r.get("auto_apply")]),
            "manual_review_count": len([r for r in recommendations if not r.get("auto_apply")]),
        },
    }


# ── CLI ──
if __name__ == "__main__":
    dry_run = "--apply" not in sys.argv
    days = 30
    for i, arg in enumerate(sys.argv):
        if arg.startswith("--days="):
            days = int(arg.split("=")[1])

    print("=" * 60)
    print("  PDCA 持续改进引擎")
    print("=" * 60)

    report = generate_pdca_report(days)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if report["act"]["auto_apply_count"] > 0:
        print("\n" + "=" * 60)
        mode = "DRY RUN (预览)" if dry_run else "APPLYING (实际修改)"
        print(f"  {mode}")
        print("=" * 60)
        result = auto_apply_recommendations(
            report["act"]["recommendations"], dry_run=dry_run
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
