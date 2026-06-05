#!/usr/bin/env python3
"""
超声报告语音结构化 MCP Server — 接入小智ESP32机器人

用法:
  pip install mcp
  python ultrasound_mcp_server.py

xiaozhi.me 控制台配置:
  类型: stdio MCP Server
  命令: python3 /opt/ultrasound-report-mvp/ultrasound_mcp_server.py
"""

from mcp.server.fastmcp import FastMCP
import logging, json, base64, urllib.request, sys

logger = logging.getLogger("ultrasound_mcp")
logging.basicConfig(level=logging.INFO, stream=sys.stderr)

API_BASE = "http://47.109.151.238:8800"

# 创建 MCP 服务器
mcp = FastMCP("超声报告语音结构化", description="超声医生口述→结构化报告。支持方言(湘/川/渝)。")


@mcp.tool()
def ultrasound_transcribe(
    text: str,
    patient_id: str,
    gender: str = "",
    age: int = 0,
    exam_type: str = "腹部超声",
    name: str = "",
) -> dict:
    """超声医生口述→结构化报告。小智ASR转文字后调用此工具, 返回超声所见+提示+ICD10+建议。

    小智内部已做完ASR(语音→文字), 此工具接收的是文字口述, 不是音频。

    Args:
        text: ASR转写后的口述文字 (小智自动处理)
        patient_id: 患者病历号/唯一ID (必填, 一单一录)
        gender: 性别 (男/女)
        age: 年龄 (0-150)
        exam_type: 检查类型 (腹部超声/乳腺超声/甲状腺超声/产科超声/心脏超声/泌尿超声/妇科超声)
        name: 患者姓名 (可选, 建议脱敏)

    Returns:
        dict: {code, msg, study_see, study_hint, recommendation, elapsed_ms, template}
    """
    if not text or not text.strip():
        return {"code": 400, "msg": "text 不能为空 (小智应已做好ASR)", "study_see": ""}
    if not patient_id:
        return {"code": 400, "msg": "patient_id 不能为空 (一单一录)", "study_see": ""}

    logger.info(f"[MCP Tool] patient={patient_id} exam={exam_type} text_len={len(text)}")

    try:
        payload = json.dumps({
            "text": text.strip(),
            "patient_context": {
                "patient_id": patient_id,
                "gender": gender,
                "age": age,
                "exam_type": exam_type,
                "name": name,
            }
        }, ensure_ascii=False).encode()

        req = urllib.request.Request(
            f"{API_BASE}/v1/structure",
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"}
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())
            data = result.get("data", {})
            return {
                "code": result.get("code", 200),
                "msg": result.get("msg", "success"),
                "template": data.get("template_used", ""),
                "method": data.get("method", ""),
                "elapsed_ms": data.get("elapsed_ms", 0),
                "confidence": data.get("confidence", 0),
                "study_see": data.get("study_see", ""),
                "study_hint": data.get("study_hint", []),
                "recommendation": data.get("recommendation", ""),
            }
    except Exception as e:
        logger.error(f"[MCP Tool] error: {e}")
        return {"code": 500, "msg": f"API调用失败: {str(e)[:200]}", "study_see": ""}


@mcp.tool()
def ultrasound_quality_check(text: str, exam_type: str = "腹部超声") -> dict:
    """检查超声ASR文本质量, 评估置信度和方言纠正效果。

    Args:
        text: ASR识别后的中文文本
        exam_type: 检查类型

    Returns:
        dict: {confidence, route, signals, details}
    """
    if not text or len(text) < 5:
        return {"confidence": 0, "route": "full", "details": "文本过短"}

    try:
        payload = json.dumps({"text": text, "exam_type": exam_type}, ensure_ascii=False).encode()
        url = f"{API_BASE}/v1/asr-quality?text={urllib.parse.quote(text)}&exam_type={urllib.parse.quote(exam_type)}"
        req = urllib.request.Request(url, headers={"Authorization": "Bearer mcptool"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"confidence": 0, "route": "full", "details": f"评估失败: {e}"}


if __name__ == "__main__":
    logger.info("超声报告 MCP Server 启动 (stdio模式)")
    logger.info(f"API后端: {API_BASE}")
    mcp.run(transport="stdio")
