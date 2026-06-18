"""
医生工作站 API

流程：患者队列 → 检查会话 → 多段录音 → 合并文本 → 生成报告
"""
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import BaseModel

from database import get_db
from routers.asr import transcribe_unified
from routers.structure import StructureRequest, structure

router = APIRouter(prefix="/api/workstation", tags=["医生工作站"])

MOCK_PATIENTS = [
    ("张建国", "男", 56, "腹部超声", "肝胆胰脾双肾", "消化内科", "陈慧"),
    ("李秀兰", "女", 42, "甲状腺超声", "甲状腺", "内分泌科", "曾宁花"),
    ("王芳", "女", 35, "乳腺超声", "双侧乳腺", "乳腺外科", "刘丹"),
    ("刘强", "男", 61, "泌尿超声", "膀胱前列腺", "泌尿外科", "陈莺语"),
    ("陈丽", "女", 29, "产科超声", "中孕四维", "产科", "毛媛媛"),
    ("赵明", "男", 48, "心脏超声", "心脏", "心内科", "尹定国"),
    ("孙桂英", "女", 67, "血管超声", "颈动脉", "神经内科", "唐娟"),
    ("周伟", "男", 39, "腹部超声", "肝胆胰脾", "体检科", "任欢"),
    ("吴敏", "女", 52, "甲状腺超声", "甲状腺及颈部淋巴结", "内分泌科", "陈慧"),
    ("郑磊", "男", 45, "泌尿超声", "双肾输尿管膀胱", "泌尿外科", "刘丹"),
    ("冯艳", "女", 33, "妇科超声", "子宫附件", "妇科", "曾宁花"),
    ("马军", "男", 58, "腹部超声", "肝胆胰脾双肾", "普外科", "陈莺语"),
    ("朱梅", "女", 46, "乳腺超声", "双乳腺及腋窝", "乳腺外科", "毛媛媛"),
    ("胡强", "男", 72, "心脏超声", "心脏彩超", "心内科", "尹定国"),
    ("林娜", "女", 25, "产科超声", "早孕", "产科", "唐娟"),
    ("高峰", "男", 50, "血管超声", "下肢静脉", "血管外科", "任欢"),
    ("罗娟", "女", 40, "腹部超声", "胆囊", "消化内科", "陈慧"),
    ("黄伟", "男", 63, "泌尿超声", "前列腺", "泌尿外科", "刘丹"),
    ("唐芳", "女", 54, "甲状腺超声", "甲状腺", "体检科", "曾宁花"),
    ("谢勇", "男", 37, "腹部超声", "肝胆胰脾", "急诊科", "陈慧"),
    ("李强", "男", 44, "腹部超声", "肝脏", "消化内科", "陈莺语"),
    ("王丽", "女", 38, "甲状腺超声", "甲状腺", "内分泌科", "毛媛媛"),
    ("张伟", "男", 55, "乳腺超声", "双侧乳腺", "乳腺外科", "尹定国"),
    ("刘芳", "女", 31, "心脏超声", "心脏", "心内科", "唐娟"),
    ("陈强", "男", 62, "泌尿超声", "膀胱前列腺", "泌尿外科", "任欢"),
    ("杨丽", "女", 27, "产科超声", "早孕", "产科", "陈慧"),
    ("赵强", "男", 48, "腹部超声", "肝胆胰脾", "体检科", "刘丹"),
    ("黄丽", "女", 53, "甲状腺超声", "甲状腺", "内分泌科", "曾宁花"),
    ("周强", "男", 41, "腹部超声", "胆囊", "消化内科", "陈莺语"),
    ("吴丽", "女", 36, "乳腺超声", "双侧乳腺", "乳腺外科", "毛媛媛"),
    ("徐强", "男", 59, "泌尿超声", "双肾输尿管膀胱", "泌尿外科", "尹定国"),
    ("孙丽", "女", 24, "产科超声", "中孕四维", "产科", "唐娟"),
    ("马强", "男", 66, "心脏超声", "心脏彩超", "心内科", "任欢"),
    ("朱丽", "女", 47, "甲状腺超声", "甲状腺及颈部淋巴结", "内分泌科", "陈慧"),
    ("胡强", "男", 33, "腹部超声", "肝胆胰脾双肾", "普外科", "刘丹"),
    ("林丽", "女", 52, "乳腺超声", "双乳腺及腋窝", "乳腺外科", "曾宁花"),
    ("郭强", "男", 60, "血管超声", "颈动脉", "神经内科", "陈莺语"),
    ("唐丽", "女", 45, "妇科超声", "子宫附件", "妇科", "毛媛媛"),
    ("谢丽", "女", 39, "腹部超声", "肝脏", "体检科", "尹定国"),
    ("宋强", "男", 68, "泌尿超声", "前列腺", "泌尿外科", "唐娟"),
    ("董丽", "女", 37, "乳腺超声", "双侧乳腺", "乳腺外科", "任欢"),
    ("蒋强", "男", 50, "腹部超声", "肝胆胰脾", "消化内科", "陈慧"),
    ("彭丽", "女", 43, "甲状腺超声", "甲状腺", "内分泌科", "刘丹"),
    ("余强", "男", 57, "心脏超声", "心脏", "心内科", "曾宁花"),
    ("潘丽", "女", 29, "产科超声", "中孕四维", "产科", "陈莺语"),
    ("龚强", "男", 63, "腹部超声", "胆囊", "消化内科", "毛媛媛"),
    ("曹丽", "女", 49, "腹部超声", "肝胆胰脾双肾", "普外科", "尹定国"),
    ("薛丽", "女", 35, "乳腺超声", "双侧乳腺", "乳腺外科", "唐娟"),
    ("肖强", "男", 56, "泌尿超声", "膀胱前列腺", "泌尿外科", "任欢"),
    ("贾丽", "女", 42, "妇科超声", "子宫附件", "妇科", "陈慧"),
    ("韩博", "男", 47, "腹部超声", "肝脏", "消化内科", "陈慧"),
    ("沈丹", "女", 31, "甲状腺超声", "甲状腺", "内分泌科", "刘丹"),
    ("曹平", "男", 55, "心脏超声", "心脏", "心内科", "曾宁花"),
    ("邱洁", "女", 28, "产科超声", "早孕", "产科", "陈莺语"),
    ("廖俊", "男", 42, "泌尿超声", "双肾输尿管膀胱", "泌尿外科", "毛媛媛"),
    ("金燕", "女", 53, "乳腺超声", "双侧乳腺", "乳腺外科", "尹定国"),
    ("谭明", "男", 61, "血管超声", "下肢动脉", "血管外科", "唐娟"),
    ("夏琳", "女", 39, "妇科超声", "子宫附件", "妇科", "任欢"),
    ("范强", "男", 66, "腹部超声", "肝胆胰脾", "体检科", "陈慧"),
    ("方静", "女", 44, "甲状腺超声", "甲状腺及颈部淋巴结", "内分泌科", "刘丹"),
    ("石磊", "男", 37, "腹部超声", "胆囊", "消化内科", "曾宁花"),
    ("钟萍", "女", 51, "乳腺超声", "双乳腺及腋窝", "乳腺外科", "陈莺语"),
    ("田凯", "男", 59, "泌尿超声", "前列腺", "泌尿外科", "毛媛媛"),
    ("白洁", "女", 26, "产科超声", "中孕四维", "产科", "尹定国"),
    ("康华", "男", 48, "心脏超声", "心脏彩超", "心内科", "唐娟"),
    ("孟瑶", "女", 42, "腹部超声", "肝胆胰脾双肾", "普外科", "任欢"),
    ("贺斌", "男", 34, "腹部超声", "肝脏", "急诊科", "陈慧"),
    ("屈婷", "女", 57, "血管超声", "颈动脉", "神经内科", "刘丹"),
    ("毛杰", "男", 50, "腹部超声", "肝胆胰脾", "消化内科", "曾宁花"),
    ("文蓉", "女", 36, "甲状腺超声", "甲状腺", "内分泌科", "陈莺语"),
    ("阮鹏", "男", 63, "泌尿超声", "双肾输尿管膀胱", "泌尿外科", "毛媛媛"),
    ("樊红", "女", 47, "乳腺超声", "双侧乳腺", "乳腺外科", "尹定国"),
    ("骆涛", "男", 41, "腹部超声", "胆囊", "消化内科", "唐娟"),
    ("温玲", "女", 33, "妇科超声", "子宫附件", "妇科", "任欢"),
    ("聂坤", "男", 58, "心脏超声", "心脏", "心内科", "陈慧"),
    ("段丽", "女", 49, "腹部超声", "肝胆胰脾双肾", "体检科", "刘丹"),
    ("顾飞", "男", 44, "泌尿超声", "膀胱前列腺", "泌尿外科", "曾宁花"),
    ("时颖", "女", 30, "产科超声", "早孕", "产科", "陈莺语"),
    ("焦勇", "男", 67, "血管超声", "下肢静脉", "血管外科", "毛媛媛"),
    ("褚艳", "女", 54, "甲状腺超声", "甲状腺", "内分泌科", "尹定国"),
    ("单波", "男", 52, "腹部超声", "肝脏", "消化内科", "唐娟"),
    ("吉莉", "女", 38, "乳腺超声", "双侧乳腺", "乳腺外科", "任欢"),
    ("池强", "男", 46, "腹部超声", "肝胆胰脾", "普外科", "陈慧"),
    ("胥倩", "女", 29, "产科超声", "中孕四维", "产科", "刘丹"),
    ("舒磊", "男", 60, "泌尿超声", "双肾输尿管膀胱", "泌尿外科", "曾宁花"),
    ("乔慧", "女", 50, "心脏超声", "心脏", "心内科", "陈莺语"),
    ("万超", "男", 43, "腹部超声", "胆囊", "消化内科", "毛媛媛"),
    ("穆琳", "女", 35, "甲状腺超声", "甲状腺及颈部淋巴结", "内分泌科", "尹定国"),
    ("植华", "男", 57, "血管超声", "颈动脉", "神经内科", "唐娟"),
    ("乐婷", "女", 41, "妇科超声", "子宫附件", "妇科", "任欢"),
    ("全飞", "男", 65, "腹部超声", "肝胆胰脾双肾", "体检科", "陈慧"),
    ("盛芸", "女", 32, "乳腺超声", "双乳腺及腋窝", "乳腺外科", "刘丹"),
    ("岑林", "男", 49, "泌尿超声", "前列腺", "泌尿外科", "曾宁花"),
    ("宗敏", "女", 56, "腹部超声", "肝脏", "消化内科", "陈莺语"),
    ("葛阳", "男", 38, "心脏超声", "心脏彩超", "心内科", "毛媛媛"),
    ("楚芳", "女", 45, "甲状腺超声", "甲状腺", "内分泌科", "尹定国"),
    ("隋涛", "男", 64, "腹部超声", "肝胆胰脾", "普外科", "唐娟"),
    ("茅娟", "女", 27, "产科超声", "早孕", "产科", "任欢"),
    ("涂波", "男", 51, "泌尿超声", "双肾输尿管膀胱", "泌尿外科", "陈慧"),
    ("宰霞", "女", 40, "乳腺超声", "双侧乳腺", "乳腺外科", "刘丹"),
    ("上官云", "男", 62, "血管超声", "下肢动脉", "血管外科", "曾宁花"),
    ("尉迟英", "女", 48, "腹部超声", "胆囊", "消化内科", "陈莺语"),
    ("慕容枫", "男", 36, "腹部超声", "肝胆胰脾双肾", "急诊科", "毛媛媛"),
    ("令狐晓", "女", 59, "心脏超声", "心脏", "心内科", "尹定国"),
    ("司徒康", "男", 53, "泌尿超声", "膀胱前列腺", "泌尿外科", "唐娟"),
    ("司空洁", "女", 34, "妇科超声", "子宫附件", "妇科", "任欢"),
    ("诸葛睿", "男", 47, "腹部超声", "肝胆胰脾", "体检科", "陈慧"),
    ("欧阳敏", "女", 52, "甲状腺超声", "甲状腺", "内分泌科", "刘丹"),
    ("太叔明", "男", 58, "血管超声", "下肢静脉", "血管外科", "曾宁花"),
    ("梁秋月", "女", 33, "乳腺超声", "双侧乳腺", "乳腺外科", "陈莺语"),
    ("沈新辉", "男", 55, "腹部超声", "肝脏", "消化内科", "毛媛媛"),
    ("韩雪梅", "女", 46, "产科超声", "中孕四维", "产科", "尹定国"),
    ("叶国荣", "男", 61, "心脏超声", "心脏彩超", "心内科", "唐娟"),
    ("卢美玲", "女", 39, "甲状腺超声", "甲状腺及颈部淋巴结", "内分泌科", "任欢"),
    ("钱家豪", "男", 44, "泌尿超声", "双肾输尿管膀胱", "泌尿外科", "陈慧"),
    ("陈思远", "男", 50, "腹部超声", "肝胆胰脾双肾", "普外科", "刘丹"),
    ("江雨桐", "女", 37, "腹部超声", "胆囊", "消化内科", "曾宁花"),
    ("方伟杰", "男", 42, "乳腺超声", "双侧乳腺", "乳腺外科", "陈莺语"),
    ("顾婷婷", "女", 28, "妇科超声", "子宫附件", "妇科", "毛媛媛"),
    ("周志鹏", "男", 63, "血管超声", "颈动脉", "神经内科", "尹定国"),
    ("郑欣怡", "女", 55, "心脏超声", "心脏", "心内科", "唐娟"),
    ("蔡明远", "男", 48, "腹部超声", "肝胆胰脾", "消化内科", "任欢"),
    ("魏小雅", "女", 31, "甲状腺超声", "甲状腺", "内分泌科", "陈慧"),
    ("何浩然", "男", 59, "泌尿超声", "前列腺", "泌尿外科", "刘丹"),
    ("汤丽萍", "女", 43, "产科超声", "中孕四维", "产科", "曾宁花"),
    ("丁俊杰", "男", 36, "腹部超声", "肝脏", "急诊科", "陈莺语"),
]


class SessionCreate(BaseModel):
    patient_id: int
    doctor: str = ""
    exam_type: str = ""
    exam_part: str = ""


@router.post("/mock-patients")
def seed_mock_patients():
    conn = get_db()
    created = 0
    for i, (name, gender, age, exam_type, exam_part, department, doctor_name) in enumerate(MOCK_PATIENTS, start=1):
        exists = conn.execute(
            "SELECT id FROM patients WHERE name=? AND exam_type=? AND source='模拟'",
            (name, exam_type),
        ).fetchone()
        if exists:
            continue
        conn.execute(
            """INSERT INTO patients(name, gender, sex, age, exam_type, exam_part, department,
               dept_name, status, source, payment_status, outpatient_id, exam_no, referring_doctor)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (name, gender, gender, age, exam_type, exam_part, department,
             department, "待检", "模拟", "已缴费",
             f"P{i:04d}",
             f"EX{datetime.now().strftime('%Y%m%d')}{i:04d}",
             doctor_name),
        )
        created += 1
    conn.commit()
    conn.close()
    return {"success": True, "created": created, "total": len(MOCK_PATIENTS)}


@router.get("/queue")
def patient_queue(status: str = "待检", limit: int = 200, days: int = 0):
    conn = get_db()
    params = []
    where_clauses = []

    if status and status != "全部":
        if status == "待检":
            where_clauses.append("(status=? OR status='待检')")
        else:
            where_clauses.append("status=?")
        params.append(status)
    if days and days > 0:
        where_clauses.append("created_at >= date('now', 'localtime', ?)")
        params.append(f"-{days} days")

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    rows = conn.execute(
        f"""SELECT * FROM patients
           WHERE {where_sql}
           ORDER BY created_at DESC LIMIT ?""",
        (*params, limit),
    ).fetchall()
    conn.close()
    return {"patients": [dict(r) for r in rows], "total": len(rows)}


@router.post("/sessions")
def create_or_get_session(req: SessionCreate):
    conn = get_db()
    patient = conn.execute("SELECT * FROM patients WHERE id=?", (req.patient_id,)).fetchone()
    if not patient:
        conn.close()
        raise HTTPException(404, "患者不存在")
    p = dict(patient)
    session_date = datetime.now().strftime("%Y-%m-%d")
    exam_type = req.exam_type or p.get("exam_type") or "超声"
    exam_part = req.exam_part or p.get("exam_part") or ""
    row = conn.execute(
        """SELECT * FROM exam_sessions
           WHERE patient_id=? AND session_date=? AND exam_type=?
           ORDER BY id DESC LIMIT 1""",
        (req.patient_id, session_date, exam_type),
    ).fetchone()
    if not row:
        session_no = f"EX{datetime.now().strftime('%Y%m%d%H%M%S')}{req.patient_id:04d}"
        cur = conn.execute(
            """INSERT INTO exam_sessions(session_no,patient_id,doctor,exam_type,exam_part,session_date,status)
               VALUES(?,?,?,?,?,?,'检查中')""",
            (session_no, req.patient_id, req.doctor, exam_type, exam_part, session_date),
        )
        conn.execute("UPDATE patients SET status='检查中', updated_at=datetime('now','localtime') WHERE id=?", (req.patient_id,))
        conn.commit()
        row = conn.execute("SELECT * FROM exam_sessions WHERE id=?", (cur.lastrowid,)).fetchone()
    conn.close()
    return {"success": True, "session": dict(row), "patient": p}


@router.get("/sessions/{session_id}")
def get_session(session_id: int):
    conn = get_db()
    session = conn.execute("SELECT * FROM exam_sessions WHERE id=?", (session_id,)).fetchone()
    if not session:
        conn.close()
        raise HTTPException(404, "会话不存在")
    segments = conn.execute(
        "SELECT * FROM audio_segments WHERE session_id=? ORDER BY segment_no",
        (session_id,),
    ).fetchall()
    patient = conn.execute("SELECT * FROM patients WHERE id=?", (dict(session)["patient_id"],)).fetchone()
    conn.close()
    return {"session": dict(session), "patient": dict(patient) if patient else None, "segments": [dict(s) for s in segments]}


@router.post("/sessions/{session_id}/segments")
async def upload_segment(
    session_id: int,
    file: UploadFile = File(...),
    doctor: str = Form(""),
):
    conn = get_db()
    session = conn.execute("SELECT * FROM exam_sessions WHERE id=?", (session_id,)).fetchone()
    if not session:
        conn.close()
        raise HTTPException(404, "会话不存在")
    s = dict(session)
    max_seg = conn.execute("SELECT COALESCE(MAX(segment_no),0) AS n FROM audio_segments WHERE session_id=?", (session_id,)).fetchone()["n"]
    conn.close()

    asr_result = await transcribe_unified(
        file=file,
        doctor=doctor or s.get("doctor") or "",
        exam_type=s.get("exam_type") or "超声",
        run_structure=False,
    )

    conn = get_db()
    segment_no = int(max_seg or 0) + 1
    warnings = asr_result.get("warnings") or []
    is_valid = 1 if asr_result.get("success") else 0
    conn.execute(
        """INSERT INTO audio_segments(session_id,patient_id,segment_no,filename,filepath,normalized_path,
           file_size,duration_seconds,asr_source,raw_text,corrected_text,quality_score,is_valid,warnings)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            session_id,
            s["patient_id"],
            segment_no,
            asr_result.get("audio_file") or "",
            asr_result.get("audio_path") or "",
            asr_result.get("normalized_audio") or "",
            0,
            asr_result.get("duration_seconds") or 0,
            asr_result.get("source") or "",
            asr_result.get("raw_text") or "",
            asr_result.get("corrected_text") or "",
            asr_result.get("quality_score") or 0,
            is_valid,
            json.dumps(warnings, ensure_ascii=False),
        ),
    )
    conn.execute("UPDATE exam_sessions SET status='已暂停', updated_at=datetime('now','localtime') WHERE id=?", (session_id,))
    conn.commit()
    row = conn.execute("SELECT * FROM audio_segments WHERE session_id=? AND segment_no=?", (session_id, segment_no)).fetchone()
    conn.close()
    return {"success": True, "segment": dict(row), "asr": asr_result}


@router.get("/segments/{segment_id}/play")
def play_segment(segment_id: int, kind: str = "original"):
    conn = get_db()
    row = conn.execute("SELECT * FROM audio_segments WHERE id=?", (segment_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "录音段不存在")
    s = dict(row)
    path = Path(s.get("normalized_path") or "") if kind == "normalized" else Path(s.get("filepath") or "")
    if not path.exists() or not path.is_file():
        raise HTTPException(404, "音频文件不存在")
    media_type = "audio/wav" if path.suffix.lower() == ".wav" else "audio/webm"
    return FileResponse(path, media_type=media_type, filename=path.name)


def _merge_texts(texts: list[str]) -> str:
    seen = set()
    merged = []
    for text in texts:
        clean = (text or "").strip()
        if not clean:
            continue
        if clean in seen:
            continue
        seen.add(clean)
        merged.append(clean)
    return "\n".join(merged)


@router.post("/sessions/{session_id}/merge")
def merge_session(session_id: int):
    conn = get_db()
    rows = conn.execute(
        """SELECT * FROM audio_segments
           WHERE session_id=? AND is_valid=1 AND corrected_text!=''
           ORDER BY segment_no""",
        (session_id,),
    ).fetchall()
    merged = _merge_texts([dict(r).get("corrected_text", "") for r in rows])
    conn.execute(
        "UPDATE exam_sessions SET merged_text=?, status='已识别', updated_at=datetime('now','localtime') WHERE id=?",
        (merged, session_id),
    )
    conn.commit()
    session = conn.execute("SELECT * FROM exam_sessions WHERE id=?", (session_id,)).fetchone()
    conn.close()
    return {"success": True, "merged_text": merged, "session": dict(session)}


@router.post("/sessions/{session_id}/generate-report")
async def generate_report(session_id: int):
    conn = get_db()
    session = conn.execute("SELECT * FROM exam_sessions WHERE id=?", (session_id,)).fetchone()
    if not session:
        conn.close()
        raise HTTPException(404, "会话不存在")
    s = dict(session)
    patient = conn.execute("SELECT * FROM patients WHERE id=?", (s["patient_id"],)).fetchone()
    p = dict(patient) if patient else {}
    merged_text = s.get("merged_text") or ""
    if not merged_text:
        rows = conn.execute(
            """SELECT corrected_text FROM audio_segments
               WHERE session_id=? AND is_valid=1 AND corrected_text!=''
               ORDER BY segment_no""",
            (session_id,),
        ).fetchall()
        merged_text = _merge_texts([dict(r).get("corrected_text", "") for r in rows])
    conn.close()
    if not merged_text.strip():
        raise HTTPException(400, "没有可用于生成报告的有效录音文本")

    req = StructureRequest(
        text=merged_text,
        exam_type=s.get("exam_type") or p.get("exam_type") or "腹部超声",
        patient_id=str(p.get("id") or ""),
        patient_name=p.get("name") or "",
        patient_gender=p.get("gender") or p.get("sex") or "",
        patient_age=p.get("age") or 0,
        clinical_diag=p.get("clinical_diag") or "",
        doctor=s.get("doctor") or "",
    )
    result = await structure(req)
    report_id = result.get("report_id") or ""
    conn = get_db()
    conn.execute(
        "UPDATE exam_sessions SET merged_text=?, report_id=?, status='已生成报告', updated_at=datetime('now','localtime') WHERE id=?",
        (merged_text, str(report_id), session_id),
    )
    conn.execute("UPDATE patients SET status='已完成', updated_at=datetime('now','localtime') WHERE id=?", (s["patient_id"],))
    conn.commit()
    conn.close()
    return {"success": True, "merged_text": merged_text, "report": result}
