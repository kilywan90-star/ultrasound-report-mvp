"""
超声语音报告系统 - 数据库层 (v3.0 完整版)
所有业务数据全量存储，供其他系统调阅和数据挖掘
"""
import sqlite3, json
from pathlib import Path

DB_PATH = Path(__file__).parent / "ultrasound.db"

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
        -- ===== 医生档案 =====
        CREATE TABLE IF NOT EXISTS doctors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            department TEXT DEFAULT '超声科',
            title TEXT DEFAULT '',
            employee_id TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- ===== 患者档案 =====
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sex TEXT DEFAULT '',
            age INTEGER DEFAULT 0,
            age_unit TEXT DEFAULT '岁',
            outpatient_no TEXT DEFAULT '',
            inpatient_no TEXT DEFAULT '',
            dept_name TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            id_card TEXT DEFAULT '',
            bed_no TEXT DEFAULT '',
            exam_no TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- ===== 录音原始数据 =====
        CREATE TABLE IF NOT EXISTS audio_recordings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            file_size INTEGER DEFAULT 0,
            duration_seconds REAL DEFAULT 0,
            audio_format TEXT DEFAULT 'webm',
            doctor TEXT DEFAULT '',
            patient_id INTEGER DEFAULT 0,
            report_id TEXT DEFAULT '',
            status TEXT DEFAULT 'saved',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- ===== ASR识别日志 =====
        CREATE TABLE IF NOT EXISTS asr_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            audio_file TEXT DEFAULT '',
            raw_text TEXT DEFAULT '',
            corrected_text TEXT DEFAULT '',
            source TEXT DEFAULT 'whisper',
            quality_score REAL DEFAULT 0,
            hotwords_count INTEGER DEFAULT 0,
            elapsed_seconds REAL DEFAULT 0,
            doctor TEXT DEFAULT '',
            report_id TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- ===== 意图识别日志 =====
        CREATE TABLE IF NOT EXISTS intent_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            sites TEXT DEFAULT '[]',
            findings TEXT DEFAULT '[]',
            is_normal INTEGER DEFAULT 0,
            keywords TEXT DEFAULT '[]',
            elapsed_ms INTEGER DEFAULT 0,
            report_id TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- ===== 模板匹配日志 =====
        CREATE TABLE IF NOT EXISTS match_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            voice_text TEXT NOT NULL,
            corrected_text TEXT DEFAULT '',
            best_template_id TEXT DEFAULT '',
            best_template_name TEXT DEFAULT '',
            best_score REAL DEFAULT 0,
            matched_sites TEXT DEFAULT '',
            result_count INTEGER DEFAULT 0,
            top3_candidates TEXT DEFAULT '[]',
            doctor TEXT DEFAULT '',
            report_id TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- ===== 报告主表 =====
        CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY,
            doctor TEXT NOT NULL,
            doctor_id INTEGER DEFAULT 0,
            patient_id INTEGER DEFAULT 0,
            patient_name TEXT DEFAULT '',
            patient_sex TEXT DEFAULT '',
            patient_age INTEGER DEFAULT 0,
            template_id TEXT DEFAULT '',
            template_name TEXT DEFAULT '',
            description TEXT DEFAULT '',
            diagnosis TEXT DEFAULT '',
            -- 业务路径记录
            audio_file TEXT DEFAULT '',
            asr_raw_text TEXT DEFAULT '',
            asr_corrected_text TEXT DEFAULT '',
            asr_source TEXT DEFAULT '',
            asr_quality REAL DEFAULT 0,
            intent_sites TEXT DEFAULT '',
            intent_findings TEXT DEFAULT '',
            intent_is_normal INTEGER DEFAULT 0,
            -- 匹配信息
            match_score REAL DEFAULT 0,
            matched_sites TEXT DEFAULT '',
            match_candidates TEXT DEFAULT '',
            variables TEXT DEFAULT '{}',
            -- 状态
            status TEXT DEFAULT 'draft',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            confirmed_at TEXT,
            -- 外部系统对接
            his_report_id TEXT DEFAULT '',
            external_ref TEXT DEFAULT ''
        );

        -- ===== 报告编辑历史 =====
        CREATE TABLE IF NOT EXISTS report_edits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id TEXT NOT NULL,
            field_name TEXT NOT NULL,
            old_value TEXT DEFAULT '',
            new_value TEXT DEFAULT '',
            doctor TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- ===== 操作审计日志 =====
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doctor TEXT NOT NULL,
            action TEXT NOT NULL,
            target_type TEXT DEFAULT '',
            target_id TEXT DEFAULT '',
            detail TEXT DEFAULT '',
            ip_address TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- ===== 知识库版本 =====
        CREATE TABLE IF NOT EXISTS kb_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            file_size INTEGER DEFAULT 0,
            checksum TEXT DEFAULT '',
            version TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- ===== 模板分类 =====
        CREATE TABLE IF NOT EXISTS template_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            parent_id INTEGER DEFAULT 0
        );

        -- ===== 初始化默认模板分类 =====
        INSERT OR IGNORE INTO template_categories(id,name,parent_id) VALUES
            (1,'腹部',0),(2,'心脏',0),(3,'甲状腺',0),(4,'乳腺',0),(5,'颈动脉',0),
            (6,'前列腺',0),(7,'子宫附件',0),(8,'双肾',0),(9,'其他',0);

        -- ===== 医生工作站：检查会话 =====
        CREATE TABLE IF NOT EXISTS exam_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_no TEXT UNIQUE NOT NULL,
            patient_id INTEGER NOT NULL,
            doctor TEXT DEFAULT '',
            exam_type TEXT DEFAULT '',
            exam_part TEXT DEFAULT '',
            session_date TEXT NOT NULL,
            status TEXT DEFAULT '待检',
            merged_text TEXT DEFAULT '',
            report_id TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- ===== 医生工作站：录音分段 =====
        CREATE TABLE IF NOT EXISTS audio_segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            patient_id INTEGER NOT NULL,
            segment_no INTEGER NOT NULL,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            normalized_path TEXT DEFAULT '',
            file_size INTEGER DEFAULT 0,
            duration_seconds REAL DEFAULT 0,
            asr_source TEXT DEFAULT '',
            raw_text TEXT DEFAULT '',
            corrected_text TEXT DEFAULT '',
            quality_score REAL DEFAULT 0,
            is_valid INTEGER DEFAULT 1,
            warnings TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- ===== API报告（对接外部系统）=====
        CREATE TABLE IF NOT EXISTS api_reports (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            examdate        TEXT,
            examtime        TEXT,
            machinetype     TEXT,
            VISCERAS        TEXT,
            NAME            TEXT,
            SEX             TEXT,
            age             INTEGER,
            AGEUNIT         TEXT DEFAULT '岁',
            FromDeptName    TEXT,
            OUTPATIENTNO    TEXT,
            INPATIENTNO     TEXT,
            DESCRIBES       TEXT,
            DIAGNOSIS       TEXT,
            ModuleName      TEXT,
            ClinicDiagnosis TEXT,
            audio_path      TEXT,
            tenant_id       INTEGER,
            request_id      TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        -- ===== API全链路追踪日志 =====
        CREATE TABLE IF NOT EXISTS api_trace_logs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id      TEXT UNIQUE,
            patient_id      TEXT NOT NULL,
            name            TEXT,
            gender          TEXT,
            age             INTEGER,
            exam_part       TEXT,
            raw_input       TEXT,
            raw_input_len   INTEGER,
            voice_cmd_hit   TEXT,
            dual_mixed_hit  TEXT,
            body_part_route TEXT,
            dialect_found   TEXT,
            erase_found     TEXT,
            template_matched TEXT,
            method          TEXT,
            hospital_name   TEXT,
            authorized_user TEXT,
            authorized_api  TEXT,
            elapsed_ms      INTEGER,
            confidence      REAL,
            study_see       TEXT,
            study_hint      TEXT,
            study_hint_icd10 TEXT,
            recommendation  TEXT,
            patient_note    TEXT,
            audio_status    TEXT DEFAULT 'valid',
            dual_mixed      INTEGER DEFAULT 0,
            llm_model       TEXT DEFAULT 'deepseek-chat/v4-flash',
            prompt_rules    TEXT,
            audio_path_1    TEXT,
            audio_path_2    TEXT,
            audio_path_3    TEXT,
            audio_path_4    TEXT,
            audio_path_5    TEXT,
            http_code       INTEGER DEFAULT 200,
            billing_amount  REAL DEFAULT 0,
            tenant_id       INTEGER,
            created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        -- ===== 全链路追踪（旧版兼容）=====
        CREATE TABLE IF NOT EXISTS abcdef_trace_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id TEXT UNIQUE NOT NULL,
            patient_id INTEGER, gender TEXT, age INTEGER,
            A_asr TEXT, B_free_llm TEXT, C_regex TEXT,
            D_enhanced TEXT, E_template TEXT, F_validated TEXT,
            study_see TEXT, study_hint TEXT, recommendation TEXT,
            created_at TEXT NOT NULL, error_msg TEXT,
            template_name TEXT, template_id TEXT
        );
    """)
    # 兼容旧库：CREATE TABLE IF NOT EXISTS 不会补列，这里统一补齐新旧 schema 需要的列
    def _ensure_column(table: str, column: str, definition: str) -> None:
        try:
            existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        except Exception:
            pass

    # patients: 兼容 database.py(sex/outpatient_no) 与 db.py(gender/exam_type/status)
    for col, definition in [
        ("sex", "TEXT DEFAULT ''"),
        ("gender", "TEXT DEFAULT ''"),
        ("age_unit", "TEXT DEFAULT '岁'"),
        ("outpatient_no", "TEXT DEFAULT ''"),
        ("outpatient_id", "TEXT DEFAULT ''"),
        ("inpatient_no", "TEXT DEFAULT ''"),
        ("inpatient_id", "TEXT DEFAULT ''"),
        ("dept_name", "TEXT DEFAULT ''"),
        ("department", "TEXT DEFAULT ''"),
        ("phone", "TEXT DEFAULT ''"),
        ("id_card", "TEXT DEFAULT ''"),
        ("bed_no", "TEXT DEFAULT ''"),
        ("exam_no", "TEXT DEFAULT ''"),
        ("exam_type", "TEXT DEFAULT '超声'"),
        ("exam_part", "TEXT DEFAULT ''"),
        ("clinical_diag", "TEXT DEFAULT ''"),
        ("source", "TEXT DEFAULT '手动'"),
        ("payment_status", "TEXT DEFAULT ''"),
        ("tenant_id", "INTEGER"),
        ("status", "TEXT DEFAULT '待检'"),
    ]:
        _ensure_column("patients", col, definition)

    # reports: 兼容 db.py 简表与 database.py 全量表
    for col, definition in [
        ("doctor", "TEXT DEFAULT ''"),
        ("doctor_id", "INTEGER DEFAULT 0"),
        ("patient_name", "TEXT DEFAULT ''"),
        ("patient_sex", "TEXT DEFAULT ''"),
        ("patient_age", "INTEGER DEFAULT 0"),
        ("template", "TEXT DEFAULT ''"),
        ("raw_text", "TEXT DEFAULT ''"),
        ("structured", "TEXT DEFAULT ''"),
        ("edited", "TEXT DEFAULT ''"),
        ("audio_path", "TEXT DEFAULT ''"),
        ("voice_text", "TEXT DEFAULT ''"),
        ("template_id", "TEXT DEFAULT ''"),
        ("template_name", "TEXT DEFAULT ''"),
        ("description", "TEXT DEFAULT ''"),
        ("diagnosis", "TEXT DEFAULT ''"),
        ("audio_file", "TEXT DEFAULT ''"),
        ("asr_raw_text", "TEXT DEFAULT ''"),
        ("asr_corrected_text", "TEXT DEFAULT ''"),
        ("asr_source", "TEXT DEFAULT ''"),
        ("asr_quality", "REAL DEFAULT 0"),
        ("intent_sites", "TEXT DEFAULT ''"),
        ("intent_findings", "TEXT DEFAULT ''"),
        ("intent_is_normal", "INTEGER DEFAULT 0"),
        ("match_score", "REAL DEFAULT 0"),
        ("matched_sites", "TEXT DEFAULT ''"),
        ("match_candidates", "TEXT DEFAULT ''"),
        ("variables", "TEXT DEFAULT '{}'"),
        ("confirmed_at", "TEXT"),
        ("his_report_id", "TEXT DEFAULT ''"),
        ("external_ref", "TEXT DEFAULT ''"),
    ]:
        _ensure_column("reports", col, definition)

    # audit_log: 兼容旧审计表与新审计表
    for col, definition in [
        ("doctor", "TEXT DEFAULT 'system'"),
        ("target_type", "TEXT DEFAULT ''"),
        ("target_id", "TEXT DEFAULT ''"),
        ("ip_address", "TEXT DEFAULT ''"),
        ("patient_id", "INTEGER"),
        ("input_text", "TEXT DEFAULT ''"),
        ("output_text", "TEXT DEFAULT ''"),
        ("operator", "TEXT DEFAULT 'system'"),
    ]:
        _ensure_column("audit_log", col, definition)

    conn.commit()
    conn.close()
