# 超声报告新旧代码对比报告
生成时间: 2026-06-07

## 文件结构对比

- 旧项目文件数: 256
- 新版文件数: 22

### 新版新增文件


### 旧版有但新版无的文件


## 相同路径文件差异

### backend/main.py
```diff
--- old/backend/main.py
+++ new/backend/main.py
@@ -1,1185 +1,87 @@
-"""超声报告语音结构化 MVP — FastAPI 后端 v0.3"""
+"""
+超声语音报告系统 - FastAPI 主入口
+"""
+import json
+from pathlib import Path
+from fastapi import FastAPI
+from fastapi.middleware.cors import CORSMiddleware
+from fastapi.staticfiles import StaticFiles
 
-from dotenv import load_dotenv
-from pathlib import Path
-# Try project root .env first, fall back to parent directory
-_root = Path(__file__).resolve().parents[1]
-_env = _root / ".env"
-if not _env.exists():
-    _env = Path(__file__).resolve().parents[2] / ".env"
-load_dotenv(_env)
+from database import init_db, get_db
+from engine import Matcher
 
+# ===== 配置 =====
 import os
-import re
-import uuid
-import hmac
-import asyncio
-import logging
-from datetime import datetime
+os.environ.setdefault("DASHSCOPE_API_KEY", os.environ.get("DASHSCOPE_API_KEY", "sk-6e6dfb5313964b2eb79bc72edf72b7db"))
 
-from fastapi import FastAPI, File, HTTPException, Request, UploadFile
-from fastapi.middleware.cors import CORSMiddleware
-from fastapi.responses import FileResponse, JSONResponse
-from pydantic import BaseModel, Field
+BASE_DIR = Path(__file__).parent
+FRONTEND_DIR = BASE_DIR.parent / "frontend"
+RULEBASE_PATH = r"C:\Users\Administrator\Desktop\超声规则库_rulebase.json"
+PORT = 18001
 
-try:
-    from asr_client import transcribe_audio
-    ASR_AVAILABLE = True
-except (ImportError, ModuleNotFoundError):
-    ASR_AVAILABLE = False
-    def _asr_unavailable(*a, **kw): raise RuntimeError("ASR不可用")
-    transcribe_audio = _asr_unavailable
+# ===== 数据库初始化 =====
+init_db()
 
-from templates import match_template, TEMPLATES
-from template_filler import match_and_fill
-from template_engine_v2 import match_and_fill_optimized, search_optimized as template_search_v2
-from fixed_template_engine import process_with_fixed_template, TEMPLATE_TAGS, DEFAULT_TEMPLATES
-from asr_correction import correct_ASR_text
-from template_fetal import fill_fetal_template
-from api_section_templates import router as section_templates_router
-from api_pacs import router as pacs_router
-from api_pacs_config import router as pacs_config_router
-from api_system_log import router as syslog_router
-from api_data_list import router as datalist_router
-import db
+# ===== 规则库加载 =====
+with open(RULEBASE_PATH, 'r', encoding='utf-8') as f:
+    rb = json.load(f)
 
-BUILD = "20260607-2103"
-VERSION = f"v3.3.{BUILD}"
+# ===== 匹配引擎 =====
+matcher = Matcher(rb)
 
-from api_exam_parts import router as exam_parts_router
-app = FastAPI(title="超声报告语音结构化", version=VERSION)
+# ===== 初始化自动管线 =====
+from pipeline import init_pipeline
+pipeline = init_pipeline(matcher)
 
... (truncated, 1256 lines total)
```

### backend/db.py
```diff
--- old/backend/db.py
+++ new/backend/database.py
@@ -1,473 +1,202 @@
-"""SQLite 数据库管理 — 患者队列 + 报告持久化"""
-
-import json
-import sqlite3
-import threading
-from datetime import datetime
+"""
+超声语音报告系统 - 数据库层 (v3.0 完整版)
+所有业务数据全量存储，供其他系统调阅和数据挖掘
+"""
+import sqlite3, json
 from pathlib import Path
 
 DB_PATH = Path(__file__).parent / "ultrasound.db"
 
-# 线程安全：每个线程拿自己的连接
-_local = threading.local()
-
-
-def _conn() -> sqlite3.Connection:
-    if not hasattr(_local, "conn") or _local.conn is None:
-        _local.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
-        _local.conn.row_factory = sqlite3.Row
-        _local.conn.execute("PRAGMA journal_mode=WAL")
-        _local.conn.execute("PRAGMA foreign_keys=ON")
-    return _local.conn
-
+def get_db():
+    conn = sqlite3.connect(str(DB_PATH))
+    conn.row_factory = sqlite3.Row
+    conn.execute("PRAGMA journal_mode=WAL")
+    conn.execute("PRAGMA foreign_keys=ON")
+    return conn
 
 def init_db():
-    """建表（幂等）"""
-    c = _conn()
+    conn = get_db()
+    c = conn.cursor()
     c.executescript("""
+        -- ===== 医生档案 =====
+        CREATE TABLE IF NOT EXISTS doctors (
+            id INTEGER PRIMARY KEY AUTOINCREMENT,
+            name TEXT UNIQUE NOT NULL,
+            department TEXT DEFAULT '超声科',
+            title TEXT DEFAULT '',
+            employee_id TEXT DEFAULT '',
+            created_at TEXT DEFAULT (datetime('now','localtime')),
+            updated_at TEXT DEFAULT (datetime('now','localtime'))
+        );
+
+        -- ===== 患者档案 =====
         CREATE TABLE IF NOT EXISTS patients (
-            id          INTEGER PRIMARY KEY AUTOINCREMENT,
-            name        TEXT    NOT NULL,
-            gender      TEXT    NOT NULL CHECK(gender IN ('男','女')),
-            age         INTEGER,
-            exam_type   TEXT    NOT NULL,
-            exam_part   TEXT,
-            outpatient_id TEXT,             -- 门诊号 (PACS)
-            inpatient_id  TEXT,             -- 住院号 (PACS)
-            department    TEXT,             -- 申请科室 (PACS)
-            clinical_diag TEXT,             -- 临床诊断 (PACS)
-            tenant_id     INTEGER,          -- 租户ID (api_platform)
-            status      TEXT    NOT NULL DEFAULT '待检' CHECK(status IN ('待检','检查中','已完成')),
-            created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
-            updated_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
-        );
-
-        CREATE INDEX IF NOT EXISTS idx_patients_outpatient ON patients(outpatient_id);
-        CREATE INDEX IF NOT EXISTS idx_patients_inpatient ON patients(inpatient_id);
-        CREATE INDEX IF NOT EXISTS idx_patients_status ON patients(status);
-
+            id INTEGER PRIMARY KEY AUTOINCREMENT,
+            name TEXT NOT NULL,
+            sex TEXT DEFAULT '',
+            age INTEGER DEFAULT 0,
... (truncated, 666 lines total)
```

### frontend/index.html
```diff
--- old/frontend/index.html
+++ new/frontend/index.html
@@ -2,7 +2,6 @@
 <html lang="zh-CN">
 <head>
 <meta charset="UTF-8">
-<meta http-equiv="Content-Security-Policy" content="upgrade-insecure-requests">
 <meta name="viewport" content="width=device-width, initial-scale=1.0">
 <title>超声语音报告系统 v3.0</title>
 <style>
@@ -11,6 +10,7 @@
 html,body{height:100%;font-family:var(--font);font-size:14px;color:var(--text);background:var(--bg)}
 ::-webkit-scrollbar{width:5px}::-webkit-scrollbar-thumb{background:#d1d5db;border-radius:3px}
 .app{display:flex;height:100vh}
+/* Sidebar */
 .sidebar{width:var(--sidebar-w);background:linear-gradient(180deg,#001529,#002140);color:#fff;display:flex;flex-direction:column;flex-shrink:0}
 .sidebar .logo{padding:18px 20px;font-size:16px;font-weight:700;border-bottom:1px solid rgba(255,255,255,.1);display:flex;align-items:center;gap:8px}
 .sidebar .logo .v{font-size:10px;background:var(--primary);padding:2px 8px;border-radius:10px}
@@ -20,6 +20,7 @@
 .sidebar .nav-item.on{color:#fff;background:var(--primary);border-left-color:#fff}
 .sidebar .nav-item .icon{font-size:16px;width:20px;text-align:center}
 .sidebar .ver{border-top:1px solid rgba(255,255,255,.1);padding:12px 20px;font-size:11px;color:rgba(255,255,255,.4)}
+/* Main */
 .main{flex:1;display:flex;flex-direction:column;min-width:0;overflow:hidden}
 .topbar{display:flex;align-items:center;justify-content:space-between;padding:0 24px;height:54px;background:var(--card);border-bottom:1px solid var(--border);flex-shrink:0}
 .topbar .title{font-size:16px;font-weight:600}
@@ -29,14 +30,17 @@
 .topbar .right .badge.online{background:#f0fdf4;color:#15803d}
 .content{flex:1;padding:16px 24px;overflow-y:auto}
 .page{display:none}.page.on{display:block}
+/* Card */
 .card{background:var(--card);border-radius:var(--radius);box-shadow:var(--shadow);margin-bottom:14px}
 .card-hd{padding:12px 20px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;font-size:15px;font-weight:600}
 .card-bd{padding:14px 20px}
+/* Stats */
 .stats-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:14px}
 .stat-card{padding:16px 20px;background:var(--card);border-radius:var(--radius);box-shadow:var(--shadow)}
 .stat-card .num{font-size:26px;font-weight:700;color:var(--primary)}
 .stat-card .label{font-size:13px;color:var(--text2);margin-top:2px}
 .stat-card.green .num{color:var(--success)}.stat-card.orange .num{color:var(--warning)}.stat-card.purple .num{color:#8b5cf6}
+/* Voice input */
 .voice-row{display:flex;align-items:center;gap:10px;padding:12px 20px;background:var(--card);border-radius:var(--radius);box-shadow:var(--shadow);margin-bottom:14px}
 .voice-row .mic-btn{width:42px;height:42px;border-radius:50%;border:2px solid var(--primary);background:var(--card);color:var(--primary);font-size:18px;cursor:pointer;flex-shrink:0;display:flex;align-items:center;justify-content:center}
 .voice-row .mic-btn:hover{background:var(--primary-bg)}
@@ -48,6 +52,7 @@
 .voice-row .btn:hover{background:var(--primary-hover)}
 .voice-row .btn.green{background:var(--success)}.voice-row .btn.green:hover{filter:brightness(1.1)}
 .voice-row .btn.gray{background:#f3f4f6;color:var(--text2)}.voice-row .btn.gray:hover{background:#e5e7eb}
+/* Match area */
 .match-area{display:flex;gap:14px;min-height:400px}
 .match-left{flex:1;min-width:0}.match-right{width:300px;flex-shrink:0}
 @media(max-width:900px){.match-right{display:none}}
@@ -56,6 +61,7 @@
 .st.warn{background:#fffbeb;color:#b45309;border-left:3px solid var(--warning)}
 .st.err{background:#fef2f2;color:#b91c1c;border-left:3px solid var(--danger)}
 .st.info{background:var(--primary-bg);color:var(--primary);border-left:3px solid var(--primary)}
+/* Edit area */
 .edit-area label{font-size:11px;font-weight:600;color:var(--text2);margin-top:10px;display:block}
 .edit-area label:first-child{margin-top:0}
 .edit-area textarea{width:100%;min-height:44px;padding:8px 12px;border:1px solid var(--border);border-radius:6px;font-size:13px;font-family:var(--font);resize:vertical;outline:none;background:#f9fafb;line-height:1.5;margin-top:4px}
@@ -65,6 +71,7 @@
 .patient-bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:8px 0}
 .patient-bar input{padding:6px 12px;border:1px solid var(--border);border-radius:6px;font-size:13px;outline:none;flex:1}
 .patient-bar input:focus{border-color:var(--primary)}
+/* Candidate list */
 .cl{display:flex;flex-direction:column;gap:4px;max-height:520px;overflow-y:auto}
 .c{padding:10px 14px;background:var(--card);border-radius:6px;box-shadow:var(--shadow);cursor:pointer;border:2px solid transparent}
 .c:hover{border-color:var(--primary)}.c.on{border-color:var(--primary);background:var(--primary-bg)}
@@ -74,6 +81,7 @@
 .c .meta .tag.high{background:#f0fdf4;color:#15803d}
 .c .meta .tag.med{background:#fffbeb;color:#b45309}
 .c .meta .tag.low{background:#fef2f2;color:#b91c1c}
+/* Table */
 table.data{width:100%;border-collapse:collapse;font-size:13px}
 table.data th{padding:9px 12px;text-align:left;font-weight:600;color:var(--text2);border-bottom:2px solid var(--border);background:#fafafa;position:sticky;top:0;font-size:12px}
 table.data td{padding:8px 12px;border-bottom:1px solid #f3f4f6}
@@ -81,10 +89,12 @@
 .badge{display:inline-block;padding:2px 10px;border-radius:10px;font-size:12px;font-weight:500}
 .badge.confirmed{background:#f0fdf4;color:#15803d}
 .badge.draft{background:#fffbeb;color:#b45309}
... (truncated, 343 lines total)
```

