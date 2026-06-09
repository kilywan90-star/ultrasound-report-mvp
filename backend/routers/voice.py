"""
超声语音报告系统 - 语音识别路由 (v3.0 全量数据存储版)
所有语音数据、ASR结果、意图、匹配全部存入数据库
"""
import os, json, uuid, asyncio, logging, time
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from asr_service import asr
from database import get_db

router = APIRouter(prefix="/api/voice", tags=["语音"])

AUDIO_DIR = Path(__file__).parent.parent / "recordings"
AUDIO_DIR.mkdir(exist_ok=True)

DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "") or "sk-6e6dfb5313964b2eb79bc72edf72b7db"


@router.post("/ali-asr")
async def ali_asr(file: UploadFile = File(...), doctor: str = Form(""), exam_type: str = Form("腹部超声")):
    """兼容旧接口：统一转发到 /api/asr/transcribe 的实现，避免新旧ASR逻辑不一致。"""
    from routers.asr import transcribe_unified
    return await transcribe_unified(file=file, doctor=doctor, exam_type=exam_type, run_structure=False)


@router.post("/save-local")
async def save_local(file: UploadFile = File(...)):
    if not file.filename: raise HTTPException(400, "文件名为空")
    content = await file.read()
    if len(content) == 0: raise HTTPException(400, "文件为空")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:8]
    safe_name = f"{ts}_{uid}.webm"
    filepath = AUDIO_DIR / safe_name
    with open(filepath, 'wb') as f: f.write(content)
    conn = get_db()
    conn.execute("INSERT INTO audio_recordings(filename,filepath,file_size,status) VALUES(?,?,?,'saved')",
                 (safe_name, str(filepath), len(content)))
    conn.commit()
    conn.close()
    return {"status": "ok", "path": str(filepath), "filename": safe_name, "size_bytes": len(content), "created_at": datetime.now().isoformat()}


@router.get("/recordings")
def list_recordings(limit: int = 100, doctor: str = ""):
    conn = get_db()
    if doctor:
        rows = conn.execute("SELECT * FROM audio_recordings WHERE doctor=? ORDER BY created_at DESC LIMIT ?",
                           (doctor, limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM audio_recordings ORDER BY created_at DESC LIMIT ?",
                           (limit,)).fetchall()
    conn.close()
    return {"recordings": [dict(r) for r in rows], "total": len(rows)}


@router.get("/logs/asr")
def get_asr_logs(limit: int = 100):
    conn = get_db()
    rows = conn.execute("SELECT * FROM asr_logs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return {"logs": [dict(r) for r in rows]}


@router.get("/logs/intent")
def get_intent_logs(limit: int = 100):
    conn = get_db()
    rows = conn.execute("SELECT * FROM intent_logs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return {"logs": [dict(r) for r in rows]}


@router.get("/logs/match")
def get_match_logs(limit: int = 100):
    conn = get_db()
    rows = conn.execute("SELECT * FROM match_log ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return {"logs": [dict(r) for r in rows]}


@router.get("/health")
def voice_health():
    try:
        model = asr.load_model()
        return {"status": "ok", "model": "whisper-small", "dashscope_configured": bool(DASHSCOPE_API_KEY),
                "recordings_dir": str(AUDIO_DIR), "ready": model is not None}
    except:
        return {"status": "error"}


async def _call_dashscope_asr(audio_path: str) -> str:
    """使用阿里云百炼文件转写ASR"""
    import dashscope
    from dashscope.audio.asr import Transcription
    dashscope.api_key = DASHSCOPE_API_KEY

    if not os.path.exists(audio_path):
        return ""

    try:
        upload = dashscope.Files.upload(file_path=audio_path, purpose='file_trans')
        if upload.status_code != 200:
            return ""
        file_id = upload.output['uploaded_files'][0]['file_id']
        file_info = dashscope.Files.get(file_id)
        file_url = file_info.output.get('url', '')
        if not file_url:
            return ""

        # 转写
        task = Transcription.async_call(model='qwen3-asr-flash-filetrans', file_urls=[file_url])
        if task.status_code != 200:
            return ""
        task_id = task.output['task_id']
        for _ in range(120):
            r = Transcription.wait(task_id)
            s = r.output.get('task_status', '')
            if s == 'SUCCEEDED':
                sentences = r.output.get('sentences', [])
                txt = ''.join([s.get('text', '') for s in sentences])
                if txt:
                    return txt
                break
            elif s == 'FAILED':
                break
            time.sleep(1)
    except Exception as e:
        logging.warning(f"DashScope ASR异常: {e}")

    return ""
