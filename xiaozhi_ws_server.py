#!/usr/bin/env python3
"""
小智ESP32 WebSocket音频接收器 — 端口 8801

接收: 小智直连 ws://47.109.151.238:8801/asr
协议: JSON控制消息 + 二进制音频数据
格式: OPUS/WebM, 16kHz (小智默认)
处理: 接收→临时文件→调阿里百炼ASR→调结构化→返回JSON报告
"""

import asyncio, websockets, json, sys, os, tempfile, logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("ws_asr")

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
os.environ.setdefault("DASHSCOPE_API_KEY", "sk-8d3e69bd0fd842ddb996ca263328d1a2")
os.environ.setdefault("DEEPSEEK_API_KEY", "sk-707a90a4206b45e9962d606d7a6434f3")

PORT = 8801


async def process_audio(audio_bytes: bytes, patient_id: str, exam_type: str, gender: str, age: int, name: str) -> dict:
    """调后端流水线: ASR→结构化"""
    import subprocess
    # 写入临时文件
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        # 调后端ASR
        from backend.asr_client import transcribe_audio
        asr_result = await transcribe_audio(audio_bytes)
        raw_text = asr_result.get("raw", "")
        corrected = asr_result.get("text", raw_text)
        logger.info(f"ASR: {corrected[:100]}...")

        # 调后端结构化 (直接用HTTP调8800端口)
        import urllib.request
        payload = json.dumps({
            "text": corrected,
            "patient_context": {
                "patient_id": patient_id,
                "gender": gender,
                "age": age,
                "exam_type": exam_type,
                "name": name,
            }
        }, ensure_ascii=False).encode()
        req = urllib.request.Request(
            "http://localhost:8800/v1/structure",
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8", "Authorization": "Bearer ws-internal"}
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())
            data = result.get("data", {})
            return {
                "code": result.get("code", 200),
                "msg": result.get("msg", "success"),
                "asr_text": corrected[:300],
                "template": data.get("template_used", ""),
                "method": data.get("method", ""),
                "elapsed_ms": data.get("elapsed_ms", 0),
                "confidence": data.get("confidence", 0),
                "study_see": data.get("study_see", ""),
                "study_hint": data.get("study_hint", []),
                "recommendation": data.get("recommendation", ""),
            }
    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        return {"code": 500, "msg": str(e)[:200], "study_see": ""}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


async def handler(websocket):
    """WebSocket连接处理"""
    client = str(websocket.remote_address)
    logger.info(f"WS connected: {client}")

    audio_bytes = bytearray()
    patient_id = f"XZ-{id(websocket):08x}"
    exam_type = "腹部超声"
    gender = ""
    age = 0
    name = ""

    try:
        async for message in websocket:
            if isinstance(message, str):
                # JSON控制消息
                msg = json.loads(message)
                msg_type = msg.get("type", "")
                if msg_type == "config":
                    patient_id = msg.get("patient_id", patient_id)
                    exam_type = msg.get("exam_type", exam_type)
                    gender = msg.get("gender", "")
                    age = msg.get("age", 0)
                    name = msg.get("name", "")
                    await websocket.send(json.dumps({"type": "config_ack", "status": "ok"}, ensure_ascii=False))
                    logger.info(f"Config: pid={patient_id} exam={exam_type}")
                elif msg_type == "done":
                    break
                elif msg_type == "ping":
                    await websocket.send(json.dumps({"type": "pong"}))
            elif isinstance(message, bytes):
                audio_bytes.extend(message)

        if len(audio_bytes) < 400:
            await websocket.send(json.dumps({"code": 400, "msg": "音频数据过小 (<400 bytes)"}, ensure_ascii=False))
            return

        logger.info(f"Processing {len(audio_bytes)} bytes audio for {patient_id}")
        result = await process_audio(bytes(audio_bytes), patient_id, exam_type, gender, age, name)
        await websocket.send(json.dumps(result, ensure_ascii=False))
        logger.info(f"Result: code={result.get('code')} tpl={result.get('template','')}")

    except websockets.exceptions.ConnectionClosed:
        logger.info(f"WS disconnected: {client}")
    except Exception as e:
        logger.error(f"WS error: {e}")
        try:
            await websocket.send(json.dumps({"code": 500, "msg": str(e)[:200]}, ensure_ascii=False))
        except:
            pass


async def main():
    logger.info(f"小智WebSocket音频接收器启动 — ws://0.0.0.0:{PORT}/asr")
    async with websockets.serve(handler, "0.0.0.0", PORT):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
