"""
超声语音报告系统 - 语音识别路由 (v3.0 全量数据存储版)
所有语音数据、ASR结果、意图、匹配全部存入数据库
"""
import os, json, uuid, asyncio
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
async def ali_asr(file: UploadFile = File(...), doctor: str = Form("")):
    if not file.filename: raise HTTPException(400, "文件名为空")
    content = await file.read()
    if len(content) == 0: raise HTTPException(400, "文件为空")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:8]
    safe_name = f"{ts}_{uid}.webm"
    filepath = AUDIO_DIR / safe_name
    file_size = len(content)

    # 1. 存本地
    with open(filepath, 'wb') as f: f.write(content)

    # 2. 记录录音
    conn = get_db()
    cur = conn.execute("""INSERT INTO audio_recordings(filename,filepath,file_size,doctor,status)
                          VALUES(?,?,?,?,'processed')""",
                       (safe_name, str(filepath), file_size, doctor))
    audio_id = cur.lastrowid
    conn.commit()

    text = ""
    source = "whisper"
    asr_elapsed = 0
    raw_text = ""
    corrected_text = ""
    quality_score = 0.5

    # 3. DashScope ASR
    if DASHSCOPE_API_KEY:
        try:
            start = datetime.now()
            text = await _call_dashscope_asr(str(filepath))
            asr_elapsed = (datetime.now() - start).total_seconds()
            if text: source = "dashscope"
        except:
            pass

    # 4. Whisper + 知识库修正
    if not text:
        import time
        result = asr.transcribe(content, language='zh')
        raw_text = result['text']
        quality_score = result.get('quality_score', 0.5)
        asr_elapsed = result.get('duration', 0)

        from knowledge_engine import knowledge
        if raw_text:
            corrected_text = knowledge.correct_asr_text(raw_text)
        else:
            corrected_text = raw_text

        # 自动管线
        if corrected_text:
            from pipeline import pipeline as pl
            if pl:
                pipe_result = pl.process_and_save(corrected_text, doctor)
                text = pipe_result['report']['description']

                # 记录ASR日志
                conn.execute("""INSERT INTO asr_logs(audio_file,raw_text,corrected_text,source,quality_score,
                                elapsed_seconds,doctor,report_id)
                                VALUES(?,?,?,?,?,?,?,?)""",
                             (safe_name, raw_text, corrected_text, source, quality_score,
                              asr_elapsed, doctor, pipe_result.get('report_id', '')))
                # 记录意图日志
                intent = pipe_result.get('intent', {})
                conn.execute("""INSERT INTO intent_logs(text,sites,findings,is_normal,keywords,elapsed_ms,report_id)
                                VALUES(?,?,?,?,?,?,?)""",
                             (corrected_text,
                              json.dumps(intent.get('sites', []), ensure_ascii=False),
                              json.dumps(intent.get('findings', []), ensure_ascii=False),
                              1 if intent.get('is_normal') else 0,
                              json.dumps(intent.get('keywords', []), ensure_ascii=False),
                              pipe_result.get('elapsed_ms', 0),
                              pipe_result.get('report_id', '')))

                # 更新匹配日志
                matches = pipe_result.get('matches', [])
                top3 = []
                for m in matches[:3]:
                    top3.append({'name': m.get('template_name',''), 'score': m.get('score',0)})
                conn.execute("""INSERT INTO match_log(voice_text,corrected_text,best_template_id,best_template_name,
                                best_score,matched_sites,result_count,top3_candidates,doctor,report_id)
                                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                             (raw_text, corrected_text,
                              pipe_result['report'].get('template_id',''),
                              pipe_result['report'].get('template_name',''),
                              pipe_result['report'].get('match_score',0),
                              pipe_result['report'].get('matched_sites',''),
                              len(matches),
                              json.dumps(top3, ensure_ascii=False),
                              doctor, pipe_result.get('report_id', '')))
                conn.commit()
            else:
                text = corrected_text
        else:
            text = corrected_text

    # 5. 写入报告完整链路
    # （report表已通过pipeline.process_and_save写入）

    conn.close()
    return {
        "text": text, "source": source, "audio_file": safe_name, "audio_path": str(filepath),
        "raw_text": raw_text, "corrected_text": corrected_text,
        "quality_score": quality_score, "elapsed_seconds": round(asr_elapsed, 2),
    }


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
    # 记录录音
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
    import dashscope
    from dashscope.audio.asr import Transcription
    dashscope.api_key = DASHSCOPE_API_KEY
    upload = dashscope.Files.upload(file_path=audio_path, purpose='file_trans')
    if upload.status_code != 200:
        raise Exception(f"上传失败: {upload.message}")
    file_id = upload.output['uploaded_files'][0]['file_id']
    task = Transcription.async_call(model='qwen3-asr-flash-filetrans', file_urls=[file_id])
    if task.status_code != 200:
        raise Exception(f"提交失败: {task.message}")
    task_id = task.output['task_id']
    import time
    for _ in range(60):
        r = Transcription.wait(task_id)
        s = r.output.get('task_status', '')
        if s == 'SUCCEEDED':
            sentences = r.output.get('sentences', [])
            return ''.join([s.get('text', '') for s in sentences])
        elif s == 'FAILED':
            raise Exception(f"转写失败: {r.output.get('message', '')}")
        time.sleep(1)
    raise Exception("转写超时")
