"""
超声语音报告系统 - FastAPI 主入口
"""
import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import init_db, get_db
from engine import Matcher

# ===== 配置 =====
import os
os.environ.setdefault("DASHSCOPE_API_KEY", os.environ.get("DASHSCOPE_API_KEY", "sk-6e6dfb5313964b2eb79bc72edf72b7db"))

BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
RULEBASE_PATH = r"C:\Users\Administrator\Desktop\超声规则库_rulebase.json"
PORT = 18001

# ===== 数据库初始化 =====
init_db()

# ===== 规则库加载 =====
with open(RULEBASE_PATH, 'r', encoding='utf-8') as f:
    rb = json.load(f)

# ===== 匹配引擎 =====
matcher = Matcher(rb)

# ===== 初始化自动管线 =====
from pipeline import init_pipeline
pipeline = init_pipeline(matcher)

# ===== FastAPI =====
app = FastAPI(title="超声语音报告系统", version="3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ===== 注册路由 =====
from routers import doctors, patients, reports, templates, stats, match, voice, auto

# 注入依赖
templates.init(matcher)
match.init(matcher)

app.include_router(doctors.router)
app.include_router(patients.router)
app.include_router(reports.router)
app.include_router(templates.router)
app.include_router(stats.router)
app.include_router(match.router)
app.include_router(voice.router)
app.include_router(auto.router)

# ===== 初始化默认数据 =====
@app.on_event("startup")
def startup():
    conn = get_db()
    # 默认医生
    default_docs = ['陈慧','曾宁花','毛媛媛','刘丹','陈莺语','尹定国','任欢','唐娟']
    for name in default_docs:
        try:
            conn.execute("INSERT INTO doctors(name,department) VALUES(?,'超声科')", (name,))
        except: pass
    conn.commit()
    conn.close()
    print(f"启动完成: http://localhost:{PORT}")
    print(f"规则库: {len(rb['templates'])}模板, 医生: {len(default_docs)}默认")

# ===== 前端静态文件 =====
# 用普通路由替代StaticFiles挂载，避免覆盖API路由
from fastapi.responses import FileResponse, HTMLResponse
import os as _os

FRONTEND_INDEX = FRONTEND_DIR / "index.html"

@app.get("/", include_in_schema=False)
def serve_frontend():
    if FRONTEND_INDEX.exists():
        return HTMLResponse(content=open(str(FRONTEND_INDEX), 'r', encoding='utf-8').read())
    return HTMLResponse("<h1>超声语音报告系统</h1><p>前端文件未找到</p>")

# ===== 启动 =====
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
