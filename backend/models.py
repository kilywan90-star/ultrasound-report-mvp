"""
超声语音报告系统 - Pydantic 模型 (v3.0)
"""
from pydantic import BaseModel
from typing import Optional

# ===== 医生 =====
class DoctorCreate(BaseModel):
    name: str; department: str = "超声科"; title: str = ""

# ===== 患者 =====
class PatientCreate(BaseModel):
    name: str; sex: str = ""; age: int = 0
    outpatient_no: str = ""; inpatient_no: str = ""; dept_name: str = ""

class PatientUpdate(BaseModel):
    name: str = ""; sex: str = ""; age: int = 0
    outpatient_no: str = ""; inpatient_no: str = ""; dept_name: str = ""

# ===== 匹配 =====
class MatchQuery(BaseModel):
    text: str; doctor: str = ""

# ===== 报告 =====
class ReportCreate(BaseModel):
    doctor: str; patient_id: int = 0; patient_name: str = ""
    patient_sex: str = ""; patient_age: int = 0
    voice_text: str = ""
    template_id: str = ""; template_name: str = ""
    description: str = ""; diagnosis: str = ""
    match_score: float = 0; matched_sites: str = ""; variables: str = "{}"
    asr_raw_text: str = ""; asr_corrected_text: str = ""; asr_source: str = ""; asr_quality: float = 0

class ReportUpdate(BaseModel):
    patient_name: str = ""; patient_sex: str = ""; patient_age: int = 0
    description: str = ""; diagnosis: str = ""; status: str = ""
    his_report_id: str = ""; external_ref: str = ""

# ===== 语音 =====
class TranscribeResult(BaseModel):
    text: str; duration: float = 0
