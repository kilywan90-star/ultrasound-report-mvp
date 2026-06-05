"""
Ultrasound-AI-Service — Schema 定义
纯 Pydantic 请求/响应模型, 无业务逻辑依赖
"""

from pydantic import BaseModel, Field
from typing import Optional


# ── 请求模型 ──

class PatientContext(BaseModel):
    """患者上下文 — PACS/前端传入"""
    name: str = Field(default="", max_length=20)
    gender: str = Field(default="", max_length=2, description="男/女")
    age: Optional[int] = Field(default=None, ge=0, le=200)
    exam_type: str = Field(default="腹部超声", max_length=50, description="检查类型")
    exam_part: Optional[str] = Field(default=None, max_length=50, description="检查部位")
    department: Optional[str] = Field(default=None, max_length=50, description="申请科室")
    clinical_diag: Optional[str] = Field(default=None, max_length=200, description="临床诊断")
    inpatient_id: Optional[str] = Field(default=None, max_length=50)
    outpatient_id: Optional[str] = Field(default=None, max_length=50)


class TranscribeRequest(BaseModel):
    """语音转录请求"""
    patient_context: Optional[PatientContext] = Field(default=None, description="患者上下文JSON")


class StructureRequest(BaseModel):
    """文本结构化请求"""
    text: str = Field(..., min_length=1, max_length=10000)
    patient_context: Optional[PatientContext] = Field(default=None)


# ── 响应模型 ──

class ExtractedSlots(BaseModel):
    """结构化提取的槽位数据 (key-value)"""
    class Config:
        extra = "allow"


class StudyHint(BaseModel):
    """超声提示条目"""
    rank: int = 1
    diagnosis: str = ""
    icd10: str = ""


class StructureData(BaseModel):
    """结构化结果数据"""
    raw_text: str = Field(default="", description="原始ASR文本(transcribe接口返回)")
    corrected_text: str = Field(default="", description="ASR纠错后文本")
    duration: float = Field(default=0.0, description="语音时长(秒)")
    is_valid: bool = Field(default=True, description="音频/文本是否通过质量检查")
    study_see: str = Field(default="", description="超声所见(HTML格式)")
    study_hint: list[StudyHint] = Field(default_factory=list, description="超声提示列表")
    recommendation: str = Field(default="", description="建议")
    template_used: str = Field(default="", description="匹配到的模板名")
    template_info1: str = Field(default="", description="模板原文(前200字)")
    method: str = Field(default="", description="处理方法: abcdef_v3/anchored_llm/anchored_regex/rule_fallback")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="置信度")
    warnings: list[str] = Field(default_factory=list, description="警告信息")
    validation_issues: list[str] = Field(default_factory=list, description="验证问题")
    degraded: bool = Field(default=False, description="是否触发熔断降级")
    elapsed_ms: float = Field(default=0.0, description="处理耗时(毫秒)")
    audit_id: Optional[str] = Field(default=None, description="审计日志ID")


class ApiResponse(BaseModel):
    """标准API响应"""
    code: int = Field(default=200, description="状态码: 200/400/500")
    msg: str = Field(default="success", description="提示信息")
    data: Optional[StructureData] = Field(default=None, description="结构化结果")
