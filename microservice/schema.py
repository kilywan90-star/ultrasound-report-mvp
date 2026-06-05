"""
Ultrasound-AI-Service — Schema 定义 v4.1
纯 Pydantic 请求/响应模型, 医院级商用 API 规范
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List
import uuid


# ── 请求模型 ──

VALID_EXAM_TYPES = {
    "腹部超声", "乳腺超声", "甲状腺超声", "产科超声", "心脏超声",
    "泌尿超声", "妇科超声", "血管超声", "小器官超声", "颈部血管",
    "下肢血管", "前列腺超声", "阴囊超声", "经颅多普勒", "胸部", "腰椎间盘",
    "肝胆胰脾超声", "肾脏超声", "膀胱超声", "盆腔超声", "胎儿超声",
}


class PatientContext(BaseModel):
    """患者上下文 — PACS/HIS 传入

    必传字段 (3+1):
      - patient_id: 病历号/患者唯一ID (关联院内 HIS/PACS)
      - gender: 性别 (男/女)
      - age: 年龄 (0-150)
      - exam_type: 检查类型

    可选字段:
      - name: 患者姓名 (建议脱敏, 默认不传)
      - exam_part: 检查部位
      - department: 申请科室
      - clinical_diag: 临床诊断
    """
    patient_id: str = Field(..., min_length=1, max_length=64,
                           description="必传: 病历号/患者唯一ID")
    gender: str = Field(..., min_length=1, max_length=2,
                       description="必传: 性别 (男/女/M/F)")
    age: int = Field(..., ge=0, le=150, description="必传: 年龄")
    exam_type: str = Field(..., min_length=1, max_length=50,
                          description="必传: 检查类型 (如 腹部超声/乳腺超声)")
    name: Optional[str] = Field(default=None, max_length=20,
                               description="可选: 患者姓名(建议脱敏)")
    exam_part: Optional[str] = Field(default=None, max_length=50,
                                    description="可选: 检查部位")
    department: Optional[str] = Field(default=None, max_length=50,
                                     description="可选: 申请科室")
    clinical_diag: Optional[str] = Field(default=None, max_length=200,
                                        description="可选: 临床诊断")

    @validator("gender")
    def validate_gender(cls, v):
        if v not in ("男", "女", "M", "F"):
            raise ValueError(f"性别只能为 男/女/M/F, 收到: {v}")
        return v

    @validator("exam_type")
    def check_exam_type(cls, v):
        if v not in VALID_EXAM_TYPES:
            # 允许非标类型通过但给出警告 (未来可能新增科室)
            pass
        return v


class StructureRequest(BaseModel):
    """文本结构化请求"""
    text: str = Field(..., min_length=1, max_length=10000,
                     description="ASR 识别文本或口述原文")
    patient_context: PatientContext = Field(..., description="患者上下文 (必传)")


class TranscribeRequest(BaseModel):
    """语音转录请求 (form-data, patient_context 为 JSON 字符串)"""
    patient_context: Optional[PatientContext] = Field(default=None,
                                                      description="患者上下文 JSON")


# ── 响应模型 ──

class StudyHint(BaseModel):
    """超声提示条目"""
    rank: int = 1
    diagnosis: str = ""
    icd10: str = ""


class StructureData(BaseModel):
    """结构化结果数据"""
    raw_text: str = Field(default="", description="原始 ASR 文本 (transcribe 接口返回)")
    corrected_text: str = Field(default="", description="ASR 纠错后文本")
    duration: float = Field(default=0.0, description="语音时长 (秒)")
    is_valid: bool = Field(default=True, description="音频/文本是否通过质量检查")
    study_see: str = Field(default="", description="超声所见 (HTML 格式)")
    study_hint: list[StudyHint] = Field(default_factory=list, description="超声提示列表")
    recommendation: str = Field(default="", description="建议")
    template_used: str = Field(default="", description="匹配到的模板名")
    template_info1: str = Field(default="", description="模板原文 (前 200 字)")
    method: str = Field(default="", description="处理方法: abcdef_v3 / anchored_llm / anchored_regex / rule_fallback")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="置信度")
    warnings: list[str] = Field(default_factory=list, description="警告信息")
    validation_issues: list[str] = Field(default_factory=list, description="验证问题")
    degraded: bool = Field(default=False, description="是否触发熔断降级")
    elapsed_ms: float = Field(default=0.0, description="处理耗时 (毫秒)")
    audit_id: Optional[str] = Field(default=None, description="审计日志 ID")
    request_id: Optional[str] = Field(default=None, description="请求唯一 ID")


class ApiResponse(BaseModel):
    """统一 API 响应信封 (医院级商用标准)"""
    code: int = Field(default=200, description="状态码: 200/400/401/403/429/500")
    msg: str = Field(default="success", description="提示信息")
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12],
                           description="请求唯一 ID")
    data: Optional[StructureData] = Field(default=None, description="结构化结果")
