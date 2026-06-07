#!/usr/bin/env python3
"""
每日自动知识库迭代任务 (cron: 0 2 * * *)
从 audit_log 提取前一天的修改记录, 自动生成候选规则
"""
import sqlite3, json, re, sys
from pathlib import Path
from collections import Counter
from datetime import datetime, timedelta

DB_PATH = Path(__file__).resolve().parent / "ultrasound.db"
KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"

def today_str():
    return datetime.now().strftime("%Y-%m-%d")

def yesterday_str():
    return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

def get_yesterday_audit():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    yesterday = yesterday_str()

    # ① 医生修改记录
    rows = conn.execute(
        "SELECT * FROM audit_log WHERE created_at >= ? AND action IN ('doctor_save','pacs_send')",
        (yesterday,)
    ).fetchall()

    conn.close()
    return rows

def extract_candidate_rules(rows):
    """
    TODO: 从 audit_log.detail JSON字段中提取 is_manual_edit 标记
    当前 audit_log 无此字段, 需先在 db.py 的 doctor_save 中增加标记
    占位逻辑: 检查 edited vs structured 的差异
    """
    candidates = []
    for row in rows:
        detail = row["detail"]
        if not detail: continue
        try:
            d = json.loads(detail) if isinstance(detail, str) else detail
        except:
            continue

        # 如果有 edited 和 structured 的对比, 找出医生改了哪些字段
        edited = d.get("edited", {})
        if edited:
            for key, val in edited.items():
                candidates.append({
                    "source": "doctor_edit",
                    "field": key,
                    "edited_value": str(val)[:100],
                    "patient_id": row["patient_id"],
                    "date": row["created_at"][:10]
                })

    return candidates

def save_candidates(candidates):
    if not candidates: return

    # 加载现有候选
    cand_file = KNOWLEDGE_DIR / "confusion_candidates.json"
    existing = {}
    if cand_file.exists():
        with open(cand_file, encoding="utf-8") as f:
            existing = json.load(f)

    # 追加新候选
    for c in candidates:
        word = c["edited_value"][:20]
        if word not in existing:
            existing[word] = {"count": 1, "sample_context": c["edited_value"][:80], "source": "auto"}
        else:
            existing[word]["count"] = existing[word].get("count", 0) + 1

    with open(cand_file, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print(f"[auto-learn] {today_str()}: added {len(candidates)} candidates to confusion_candidates.json")

def main():
    print(f"[auto-learn] Starting daily iteration: {today_str()}")
    rows = get_yesterday_audit()
    print(f"[auto-learn] Yesterday audit records: {len(rows)}")

    candidates = extract_candidate_rules(rows)
    save_candidates(candidates)
    print(f"[auto-learn] Done. {len(candidates)} candidates extracted.")

if __name__ == "__main__":
    main()
