#!/usr/bin/env python3
"""
质控看板 — 每日生成统计报告, 更新 operational_stats.json
"""
import sqlite3, json, re
from pathlib import Path
from collections import Counter
from datetime import datetime

DB_PATH = Path(__file__).resolve().parent / "ultrasound.db"
KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"

def compute_stats():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # 总报告数
    total_reports = conn.execute("SELECT COUNT(*) as c FROM reports").fetchone()["c"]

    # 按模板分布
    template_dist = Counter()
    for row in conn.execute("SELECT template, COUNT(*) as c FROM reports GROUP BY template"):
        template_dist[row["template"]] = row["c"]

    # 按方法分布
    method_dist = {}
    for row in conn.execute("SELECT action, COUNT(*) as c FROM audit_log GROUP BY action"):
        method_dist[row["action"]] = row["c"]

    conn.close()

    return {
        "_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_reports": total_reports,
        "top_templates": template_dist.most_common(20),
        "action_counts": method_dist,
    }

def main():
    stats = compute_stats()
    out = KNOWLEDGE_DIR / "dashboard_stats.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"[dashboard] saved to {out}")

if __name__ == "__main__":
    main()
