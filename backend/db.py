"""SQLite 数据库管理 — 患者队列 + 报告持久化"""

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "ultrasound.db"

# 线程安全：每个线程拿自己的连接
_local = threading.local()


def _conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


def init_db():
    """建表（幂等）"""
    c = _conn()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS patients (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            gender      TEXT    NOT NULL CHECK(gender IN ('男','女')),
            age         INTEGER,
            exam_type   TEXT    NOT NULL,
            exam_part   TEXT,
            status      TEXT    NOT NULL DEFAULT '已缴费' CHECK(status IN ('已缴费','检查中','已完成')),
            created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS reports (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id  INTEGER NOT NULL REFERENCES patients(id),
            template    TEXT    NOT NULL,
            raw_text    TEXT,
            structured  TEXT,
            edited      TEXT,
            audio_path  TEXT,
            status      TEXT    NOT NULL DEFAULT '草稿' CHECK(status IN ('草稿','已确认')),
            created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        );

        -- 标准化报告存档表 (匹配 2报告内容.csv 格式 + audio_path)
        CREATE TABLE IF NOT EXISTS api_reports (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            examdate        TEXT,                   -- 检查日期 YYYY-MM-DD
            examtime        TEXT,                   -- 检查时间 HH:MM:SS
            machinetype     TEXT,                   -- 设备类型 (默认 "彩超")
            VISCERAS        TEXT,                   -- 检查脏器/部位
            NAME            TEXT,                   -- 患者姓名
            SEX             TEXT,                   -- 性别
            age             INTEGER,                -- 年龄
            AGEUNIT         TEXT DEFAULT '岁',       -- 年龄单位
            FromDeptName    TEXT,                   -- 申请科室
            OUTPATIENTNO    TEXT,                   -- 门诊号 (patient_id)
            INPATIENTNO     TEXT,                   -- 住院号
            DESCRIBES       TEXT,                   -- 超声所见 → study_see
            DIAGNOSIS       TEXT,                   -- 超声提示 → study_hint 拼接
            ModuleName      TEXT,                   -- 模板名称 → template_used
            ClinicDiagnosis TEXT,                   -- 临床诊断
            audio_path      TEXT,                   -- 语音文件路径
            tenant_id       INTEGER,                -- 租户ID
            request_id      TEXT,                   -- API请求ID
            created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id  INTEGER,
            action      TEXT    NOT NULL,
            input_text  TEXT,
            output_text TEXT,
            detail      TEXT,
            operator    TEXT    NOT NULL DEFAULT 'system',
            created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE INDEX IF NOT EXISTS idx_api_reports_date ON api_reports(examdate);
        CREATE INDEX IF NOT EXISTS idx_api_reports_tenant ON api_reports(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_api_reports_patient ON api_reports(OUTPATIENTNO);
    """)
    c.commit()


# ==================== 患者操作 ====================

def patient_add(name: str, gender: str, age: int, exam_type: str, exam_part: str = None) -> dict:
    """快捷录入患者"""
    c = _conn()
    cur = c.execute(
        "INSERT INTO patients (name, gender, age, exam_type, exam_part) VALUES (?,?,?,?,?)",
        (name, gender, age, exam_type, exam_part),
    )
    c.commit()
    return patient_get(cur.lastrowid)


def patient_get(patient_id: int) -> dict | None:
    c = _conn()
    row = c.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
    return dict(row) if row else None


def patient_queue(status: str = None) -> list[dict]:
    """获取患者队列，默认返回已缴费+检查中"""
    c = _conn()
    if status:
        rows = c.execute(
            "SELECT * FROM patients WHERE status=? ORDER BY created_at DESC", (status,)
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT * FROM patients WHERE status IN ('已缴费','检查中') ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def patient_update_status(patient_id: int, status: str) -> dict | None:
    c = _conn()
    c.execute(
        "UPDATE patients SET status=?, updated_at=datetime('now','localtime') WHERE id=?",
        (status, patient_id),
    )
    c.commit()
    return patient_get(patient_id)


# ==================== 报告操作 ====================

def report_create(patient_id: int, template: str, raw_text: str = None,
                  structured: dict = None, audio_path: str = None) -> dict:
    c = _conn()
    cur = c.execute(
        "INSERT INTO reports (patient_id, template, raw_text, structured, audio_path) VALUES (?,?,?,?,?)",
        (patient_id, template, raw_text, json.dumps(structured, ensure_ascii=False) if structured else None, audio_path),
    )
    c.commit()
    # 更新患者状态
    patient_update_status(patient_id, "检查中")
    return report_get(cur.lastrowid)


def report_get(report_id: int) -> dict | None:
    c = _conn()
    row = c.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    if d.get("structured"):
        d["structured"] = json.loads(d["structured"])
    if d.get("edited"):
        d["edited"] = json.loads(d["edited"])
    return d


def report_update(report_id: int, raw_text: str = None, structured: dict = None,
                  edited: dict = None, status: str = None) -> dict | None:
    c = _conn()
    # 构建动态 UPDATE
    sets = ["updated_at = datetime('now','localtime')"]
    params = []
    if raw_text is not None:
        sets.append("raw_text = ?")
        params.append(raw_text)
    if structured is not None:
        sets.append("structured = ?")
        params.append(json.dumps(structured, ensure_ascii=False))
    if edited is not None:
        sets.append("edited = ?")
        params.append(json.dumps(edited, ensure_ascii=False))
    if status is not None:
        sets.append("status = ?")
        params.append(status)
    params.append(report_id)
    c.execute(f"UPDATE reports SET {', '.join(sets)} WHERE id=?", params)
    c.commit()
    return report_get(report_id)


def report_confirm(report_id: int, edited: dict) -> dict | None:
    """确认报告：保存编辑版本 + 标记已确认 + 患者状态置已完成"""
    c = _conn()
    c.execute(
        "UPDATE reports SET edited=?, status='已确认', updated_at=datetime('now','localtime') WHERE id=?",
        (json.dumps(edited, ensure_ascii=False), report_id),
    )
    r = c.execute("SELECT patient_id FROM reports WHERE id=?", (report_id,)).fetchone()
    if r:
        patient_update_status(r["patient_id"], "已完成")
    c.commit()
    return report_get(report_id)


# ==================== 操作留痕 ====================

def audit_log(action: str, patient_id: int = None, input_text: str = None,
              output_text: str = None, detail: dict = None, operator: str = "system"):
    c = _conn()
    c.execute(
        "INSERT INTO audit_log (patient_id, action, input_text, output_text, detail, operator) VALUES (?,?,?,?,?,?)",
        (patient_id, action, input_text[:500] if input_text else None,
         output_text[:500] if output_text else None,
         json.dumps(detail, ensure_ascii=False) if detail else None, operator),
    )
    c.commit()


# ==================== 标准化报告存档 (匹配CSV格式) ====================

def api_report_save(
    patient_id: str, name: str, gender: str, age: int,
    exam_type: str, department: str, clinical_diag: str,
    study_see: str, study_hint: list[dict], template_used: str,
    audio_path: str = None, tenant_id: int = None, request_id: str = None,
) -> int:
    """将API调用结果按2报告内容.csv格式存入api_reports表"""
    from datetime import datetime as dt
    now = dt.now()

    # 拼接超声提示
    diagnosis_text = "; ".join(
        f"{h['rank']}. {h['diagnosis']} [{h.get('icd10', '')}]"
        for h in (study_hint or [])
    ) or ""

    # 提取纯文本超声所见
    import re as _re2
    describes_clean = _re2.sub(r'<[^>]+>', '', study_see or "")

    c = _conn()
    cur = c.execute(
        """INSERT INTO api_reports (
            examdate, examtime, machinetype, VISCERAS, NAME, SEX, age, AGEUNIT,
            FromDeptName, OUTPATIENTNO, DESCRIBES, DIAGNOSIS, ModuleName,
            ClinicDiagnosis, audio_path, tenant_id, request_id
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), "彩超",
            exam_type or "", name or "", gender or "", age or 0, "岁",
            department or "", patient_id or "",
            describes_clean[:5000], diagnosis_text[:2000], template_used or "",
            clinical_diag or "", audio_path or "", tenant_id, request_id,
        ),
    )
    c.commit()
    return cur.lastrowid


def api_report_list(days: int = 30, limit: int = 100) -> list[dict]:
    c = _conn()
    rows = c.execute(
        """SELECT * FROM api_reports
           WHERE created_at >= datetime('now','localtime','-'||?||' days')
           ORDER BY created_at DESC LIMIT ?""",
        (days, limit),
    ).fetchall()
    return [dict(r) for r in rows]


# 启动时建表
init_db()
