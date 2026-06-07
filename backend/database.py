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
    """)
    # template_categories表可能被旧的database.py创建了，尝试创建
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS template_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            parent_id INTEGER DEFAULT 0
        )""")
        conn.commit()
    except:
        pass
    conn.commit()
    conn.close()
