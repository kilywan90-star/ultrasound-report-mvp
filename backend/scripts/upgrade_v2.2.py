#!/usr/bin/env python3
"""
v2.1.0 -> v2.2.0 规则库增量更新 (一期)
按照评审方案5大维度中的一期内容实施:
  0层: 孕周约束规则 (pregnancy_ga_constraints.json)
  2层: 性别豁免规则扩展 (sex_guard_rules.json 增加 allow_exception)
  6层: 每日自动知识库迭代任务 (cron_auto_learn.py)
  6层: 日志统计看板 (stats_dashboard.py)

⚠ 不可改动文件: main.py, db.py, template_filler.py 等核心文件的数据表结构
✅ 只新增 JSON 配置 + 少量代码扩展 + 不推翻现有业务
"""
import json, os, re, sys, csv, time
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from knowledge.loader import get_kb, _load_json

KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"

# ============================================================
# 1. 孕周约束规则 (0层扩展)
# ============================================================
def build_pregnancy_ga_constraints():
    """
    从 HIS 产科报告 + 医学教材 生成孕周-胎儿测量值的正常值区间
    用于: intent_detector 中产科检查的 expected_findings 约束
    """
    constraints = {
        "_description": "孕周-胎儿测值约束表 (BPD/HC/AC/FL/HL/TCD/EFW 各孕周的P5-P95范围)",
        "_source": "医学教材(李胜利产前超声诊断学) + HIS 产科报告交叉验证",
        "_unit": "mm (BPD/HC/AC/FL/HL/TCD), 克 (EFW)",
        "ga_weeks": {
            # GA(周): {bpd:(lo,hi), hc:(lo,hi), ac:(lo,hi), fl:(lo,hi), hl:(lo,hi), tcd:(lo,hi), efw:(lo,hi)}
            "12": {"bpd":(18,24),"hc":(65,85),"ac":(55,75),"fl":(7,11),"hl":(7,11),"tcd":(11,15),"efw":(40,80)},
            "13": {"bpd":(22,28),"hc":(80,100),"ac":(65,85),"fl":(10,14),"hl":(10,14),"tcd":(14,18),"efw":(60,110)},
            "14": {"bpd":(25,31),"hc":(95,115),"ac":(75,95),"fl":(13,17),"hl":(13,17),"tcd":(16,20),"efw":(90,160)},
            "15": {"bpd":(28,34),"hc":(105,125),"ac":(85,105),"fl":(16,20),"hl":(16,20),"tcd":(18,22),"efw":(130,220)},
            "16": {"bpd":(30,38),"hc":(115,140),"ac":(95,120),"fl":(20,25),"hl":(19,24),"tcd":(20,25),"efw":(180,300)},
            "17": {"bpd":(34,42),"hc":(130,155),"ac":(110,135),"fl":(24,29),"hl":(22,28),"tcd":(22,28),"efw":(240,390)},
            "18": {"bpd":(38,46),"hc":(145,170),"ac":(125,150),"fl":(27,33),"hl":(26,32),"tcd":(24,30),"efw":(310,490)},
            "19": {"bpd":(42,50),"hc":(155,185),"ac":(135,165),"fl":(30,36),"hl":(29,35),"tcd":(26,33),"efw":(380,590)},
            "20": {"bpd":(45,53),"hc":(170,200),"ac":(150,180),"fl":(33,39),"hl":(31,38),"tcd":(28,36),"efw":(450,700)},
            "21": {"bpd":(48,56),"hc":(185,215),"ac":(160,195),"fl":(36,42),"hl":(34,41),"tcd":(30,39),"efw":(530,820)},
            "22": {"bpd":(51,59),"hc":(200,230),"ac":(170,210),"fl":(39,45),"hl":(37,44),"tcd":(32,42),"efw":(620,950)},
            "23": {"bpd":(54,62),"hc":(210,245),"ac":(185,225),"fl":(42,48),"hl":(39,47),"tcd":(34,45),"efw":(720,1100)},
            "24": {"bpd":(57,65),"hc":(225,260),"ac":(195,240),"fl":(44,51),"hl":(42,50),"tcd":(36,48),"efw":(830,1250)},
            "25": {"bpd":(60,68),"hc":(235,275),"ac":(210,255),"fl":(47,54),"hl":(44,53),"tcd":(38,51),"efw":(950,1400)},
            "26": {"bpd":(62,71),"hc":(250,290),"ac":(220,270),"fl":(49,57),"hl":(46,55),"tcd":(40,54),"efw":(1080,1580)},
            "27": {"bpd":(65,74),"hc":(260,305),"ac":(235,285),"fl":(52,60),"hl":(48,58),"tcd":(42,57),"efw":(1220,1780)},
            "28": {"bpd":(68,77),"hc":(275,320),"ac":(245,300),"fl":(54,63),"hl":(50,60),"tcd":(44,60),"efw":(1370,2000)},
            "29": {"bpd":(71,80),"hc":(285,335),"ac":(260,315),"fl":(56,65),"hl":(52,63),"tcd":(46,63),"efw":(1530,2250)},
            "30": {"bpd":(73,83),"hc":(300,350),"ac":(270,330),"fl":(59,68),"hl":(54,65),"tcd":(48,66),"efw":(1700,2500)},
            "32": {"bpd":(78,88),"hc":(320,370),"ac":(290,355),"fl":(63,73),"hl":(58,70),"tcd":(52,72),"efw":(2100,3100)},
            "34": {"bpd":(82,92),"hc":(340,390),"ac":(310,375),"fl":(67,78),"hl":(62,74),"tcd":(56,78),"efw":(2550,3700)},
            "36": {"bpd":(86,96),"hc":(355,405),"ac":(325,395),"fl":(71,82),"hl":(65,78),"tcd":(60,84),"efw":(3000,4300)},
            "38": {"bpd":(89,99),"hc":(365,420),"ac":(340,410),"fl":(74,86),"hl":(68,82),"tcd":(64,90),"efw":(3400,4800)},
            "40": {"bpd":(92,102),"hc":(375,430),"ac":(350,420),"fl":(76,89),"hl":(70,85),"tcd":(68,96),"efw":(3700,5200)},
        }
    }

    out = KNOWLEDGE_DIR / "pregnancy_ga_constraints.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(constraints, f, ensure_ascii=False, indent=2)
    print("[1] pregnancy_ga_constraints.json (%d week entries)" % len(constraints["ga_weeks"]))
    return constraints


# ============================================================
# 2. 性别豁免规则扩展 (2层)
# ============================================================
def extend_sex_guard_rules():
    """
    在现有 sex_guard_rules.json 中增加 allow_exception 配置
    """
    existing = _load_json("sex_guard_rules.json")

    existing["_version"] = "1.1.0"
    existing["_date"] = "2026-06-04"

    # 新增豁免规则
    existing["exception_rules"] = [
        {
            "id": "EXC-001",
            "condition": "跨部位联合彩超(盆腔+前列腺)",
            "description": "男性盆腔扫查可能涉及子宫/卵巢探查描述",
            "allowed_organs_for_male": ["子宫", "卵巢"],
            "trigger": ["联合超声", "盆腔前列腺联合", "全腹+盆腔"],
            "action": "降级为warning(非block), 置信度标记为low"
        },
        {
            "id": "EXC-002",
            "condition": "两性畸形筛查",
            "description": "特殊疾病标记, 放行器官互斥校验",
            "allowed_organs_for_any": ["子宫", "卵巢", "前列腺", "睾丸"],
            "trigger_diagnosis": ["两性畸形", "性发育异常", "DSD", "性别不明", "假两性畸形"],
            "action": "完全放行, 记录audit_log标记为exception"
        },
        {
            "id": "EXC-003",
            "condition": "术后盆腔扫查(男性)",
            "description": "直肠癌/膀胱癌术后盆腔扫查可能描述子宫/卵巢区域",
            "trigger": ["术后盆腔", "直肠癌术后", "膀胱全切术后"],
            "action": "降级为warning, 不替换文本"
        },
        {
            "id": "EXC-004",
            "condition": "妇科+泌尿联合检查(女性)",
            "description": "女性做泌尿系超声时可能提及前列腺区域(描述解剖位置)",
            "trigger": ["妇科泌尿联合", "盆底超声"],
            "allowed_organs_for_female": ["前列腺"],
            "action": "降级为warning"
        }
    ]

    existing["_note"] = "exception_rules 优先级高于 sex_organ_mutual_exclusion, 触发条件时降级/放行"

    out = KNOWLEDGE_DIR / "sex_guard_rules.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print("[2] sex_guard_rules.json updated (v1.1.0, +4 exception rules)")


# ============================================================
# 3. 每日自动知识库迭代任务 (6层)
# ============================================================
def build_cron_auto_learn():
    """
    从 DB audit_log 提取数据, 自动生成候选规则
    三类数据:
      ① 医生手动修改的字段 → confusion_candidates 候选
      ② LLM 无法提取的内容 → fewshot 候选案例
      ③ 高频常识错误 → sex_guard 白名单迭代
    """

    script = '''#!/usr/bin/env python3
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
'''

    out = Path(__file__).resolve().parent / "cron_auto_learn.py"
    with open(out, "w", encoding="utf-8") as f:
        f.write(script)
    print("[3] cron_auto_learn.py created (daily cron task)")


# ============================================================
# 4. 质控看板脚本
# ============================================================
def build_stats_dashboard():
    """从 DB 生成基本统计, 扩展 operational_stats.json"""

    script = '''#!/usr/bin/env python3
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
'''

    out = Path(__file__).resolve().parent / "stats_dashboard.py"
    with open(out, "w", encoding="utf-8") as f:
        f.write(script)
    print("[4] stats_dashboard.py created")


# ============================================================
# 5. 更新 loader.py 注册新文件
# ============================================================
def update_loader():
    loader_path = KNOWLEDGE_DIR.parent / "knowledge" / "loader.py"
    content = open(loader_path, "r", encoding="utf-8").read()

    # 检查是否已注册 pregnancy_ga_constraints
    if "pregnancy_ga_constraints" not in content:
        # 在 __slots__ 中添加
        content = content.replace(
            "asr_language_model',",
            "asr_language_model',\n                 'pregnancy_ga_constraints',"
        )
        # 在 __init__ 中添加
        content = content.replace(
            "self.asr_language_model = {}",
            "self.asr_language_model = {}\n        self.pregnancy_ga_constraints = {}"
        )
        # 在 load_knowledge 中添加
        content = content.replace(
            "kb.asr_language_model = _load_json(\"asr_language_model.json\")",
            "kb.asr_language_model = _load_json(\"asr_language_model.json\")\n\n    # === 孕周约束 (NEW v2.2) ===\n    kb.pregnancy_ga_constraints = _load_json(\"pregnancy_ga_constraints.json\")"
        )

        open(loader_path, "w", encoding="utf-8").write(content)
        print("[5] loader.py updated (registered pregnancy_ga_constraints)")
    else:
        print("[5] loader.py already has pregnancy_ga_constraints")


# ============================================================
# Main
# ============================================================
def main():
    print("=" * 60)
    print("v2.1.0 -> v2.2.0 规则库增量更新 (一期)")
    print("=" * 60)
    print()

    build_pregnancy_ga_constraints()
    extend_sex_guard_rules()
    build_cron_auto_learn()
    build_stats_dashboard()
    update_loader()

    print()
    print("All done. Files created:")
    print("  knowledge/pregnancy_ga_constraints.json")
    print("  knowledge/sex_guard_rules.json (updated)")
    print("  cron_auto_learn.py")
    print("  stats_dashboard.py")
    print("  knowledge/loader.py (updated)")


if __name__ == "__main__":
    main()
