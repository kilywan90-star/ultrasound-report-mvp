# 超声报告新旧代码对比报告
生成时间: 2026-06-07

## 文件结构对比

- 旧项目文件数: 204
- 新版文件数: 22

### 新版新增文件

- `backend\asr_service.py`
- `backend\database.py`
- `backend\engine.py`
- `backend\knowledge_engine.py`
- `backend\llm_engine.py`
- `backend\medical_hotwords.json`
- `backend\models.py`
- `backend\pipeline.py`
- `backend\routers\auto.py`
- `backend\routers\doctors.py`
- `backend\routers\match.py`
- `backend\routers\patients.py`
- `backend\routers\reports.py`
- `backend\routers\stats.py`
- `backend\routers\templates.py`
- `backend\routers\voice.py`
- `backend\routing_rules.py`
- `start.bat`

### 旧版有但新版无的文件


## 相同路径文件差异

### backend/main.py
```diff
--- old/backend/main.py
+++ new/backend/main.py
@@ -1,1059 +1,87 @@
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
 
-BUILD = "20260607-1452"
-VERSION = f"v3.2.{BUILD}"
+# ===== 匹配引擎 =====
+matcher = Matcher(rb)
 
-from api_exam_parts import router as exam_parts_router
-app = FastAPI(title="超声报告语音结构化", version=VERSION)
+# ===== 初始化自动管线 =====
+from pipeline import init_pipeline
+pipeline = init_pipeline(matcher)
 
... (truncated, 1130 lines total)
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
@@ -3,1107 +3,714 @@
 <head>
 <meta charset="UTF-8">
 <meta name="viewport" content="width=device-width, initial-scale=1.0">
-<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
-<meta http-equiv="Pragma" content="no-cache">
-<meta http-equiv="Expires" content="0">
-<title>超声报告语音结构化</title>
+<title>超声语音报告系统 v3.0</title>
 <style>
-/* === Design Tokens === */
-:root{
-  --primary:#2563eb;--primary-light:#eff6ff;--primary-dark:#1d4ed8;
-  --danger:#dc2626;--danger-light:#fef2f2;
-  --success:#16a34a;--success-light:#f0fdf4;
-  --warn:#f59e0b;--purple:#7c3aed;--purple-light:#ede9fe;
-  --bg:#f1f5f9;--surface:#fff;--surface-alt:#f8fafc;
-  --border:#e2e8f0;--text:#0f172a;--text-secondary:#64748b;--text-muted:#94a3b8;
-  --sp-xs:4px;--sp-sm:6px;--sp-md:10px;--sp-lg:16px;
-  --shadow-sm:0 1px 3px rgba(0,0,0,.06),0 1px 2px rgba(0,0,0,.04);
-  --shadow-md:0 4px 6px rgba(0,0,0,.05),0 2px 4px rgba(0,0,0,.04);
-  --shadow-lg:0 10px 15px rgba(0,0,0,.06),0 4px 6px rgba(0,0,0,.04);
-  --radius-sm:4px;--radius-md:6px;--radius-lg:8px;
-  --font-sans:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;
-  --font-mono:'Courier New','Consolas',monospace;
-}
-
-/* === Reset & Base === */
-*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
-body{font-family:var(--font-sans);background:var(--bg);color:var(--text);height:100vh;display:flex;flex-direction:column}
-
-/* === Top Bar === */
-.bar{background:linear-gradient(135deg,#1e3a5f 0%,var(--primary) 100%);color:white;padding:10px 20px;font-size:14px;display:flex;justify-content:space-between;align-items:center;flex-shrink:0;box-shadow:var(--shadow-md);position:relative;z-index:10}
-.bar kbd{background:rgba(255,255,255,.15);border-radius:3px;padding:1px 6px;font-size:10px;margin:0 2px;font-family:var(--font-sans)}
-.bar .ver{font-size:10px;color:rgba(255,255,255,.6);font-weight:400;margin-left:8px}
-
-/* === App Layout === */
-.app{display:flex;flex:1;overflow:hidden}
-
-/* === Sidebar === */
-.side{width:240px;background:var(--surface);border-right:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0;box-shadow:2px 0 8px rgba(0,0,0,.04)}
-.side h3{padding:10px 12px;font-size:13px;border-bottom:1px solid var(--border);background:var(--surface-alt);font-weight:600;letter-spacing:.3px}
-.qa{padding:8px;border-bottom:1px solid var(--border)}
-.qa input,.qa select{padding:5px 7px;border:1px solid var(--border);border-radius:var(--radius-sm);font-size:12px;width:100%;margin-bottom:4px;font-family:var(--font-sans);transition:border-color .15s}
-.qa input:focus,.qa select:focus{outline:none;border-color:var(--primary);box-shadow:0 0 0 2px rgba(37,99,235,.1)}
-.qa .row{display:flex;gap:4px;margin-bottom:4px}
-.qa .row:last-child{margin-bottom:0}
-.qa button{padding:5px 12px;border:none;border-radius:var(--radius-sm);background:var(--primary);color:white;font-size:11px;cursor:pointer;white-space:nowrap;font-weight:500;transition:background .15s}
-.qa button:hover{background:var(--primary-dark)}
-.plist{flex:1;overflow-y:auto}
-.pi{padding:8px 10px;border-bottom:1px solid var(--border);cursor:pointer;font-size:12px;border-left:3px solid transparent;transition:background .1s}
-.pi:hover{background:var(--surface-alt)}
-.pi.on{background:var(--primary-light);border-left-color:var(--primary)}
-.pi .n{font-weight:600}
-.pi .e{color:var(--primary);font-size:11px}
-.pi .s{font-size:9px;color:var(--text-secondary)}
-
-/* === Main Content === */
-.main{flex:1;overflow-y:auto;padding:10px;display:flex;flex-direction:column;gap:8px}
-.main-cols{flex-direction:row;gap:10px;padding:10px}
-
-/* === Column Layout === */
-.col-input{flex:1.5;min-width:360px}
-.col-report{flex:1.2;min-width:360px}
-.col-preview{flex:1;min-width:280px;max-width:400px}
-
-/* === Panel Card === */
-.pn{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-md);overflow:hidden;box-shadow:var(--shadow-sm);transition:box-shadow .2s}
-.pn h4{padding:9px 14px;background:var(--surface-alt);font-size:12px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);font-weight:600;user-select:none}
-.pn h4:hover{background:#f1f5f9}
-.pn .b{padding:12px;display:block}
-.pn.coll .b{display:none}
-.pn-num{display:inline-flex;width:20px;height:20px;border-radius:50%;background:var(--primary);color:white;align-items:center;justify-content:center;font-size:10px;font-weight:600;margin-right:8px;flex-shrink:0}
-
-
-/* === Recording === */
-.rec-row{display:flex;align-items:center;gap:10px;margin-bottom:8px}
-.rec-btn{width:52px;height:52px;border-radius:50%;border:3px solid var(--danger);background:white;cursor:pointer;flex-shrink:0;display:flex;align-items:center;justify-content:center;transition:transform .2s,box-shadow .2s}
... (truncated, 1789 lines total)
```

