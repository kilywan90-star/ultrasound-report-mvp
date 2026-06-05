#!/usr/bin/env python3
"""
小智MCP WebSocket客户端 — 超声报告工具注册 + 音频处理

连接 wss://api.xiaozhi.me/mcp/ → 注册 ultrasound_transcribe 工具
→ 监听音频调用 → ASR+结构化 → 返回报告

用法:
  pip install websocket-client
  python xiaozhi_mcp_client.py

MCP协议格式 (xiaozhi-esp32):
  注册工具: {"type":"tools/register","tools":[...]}
  工具调用: {"type":"tools/call","id":"...","name":"...","arguments":{...}}
  返回结果: {"type":"tools/result","id":"...","name":"...","content":[{"type":"text","text":"..."}]}
"""

import json, base64, time, threading, sys, os
import urllib.request

try:
    import websocket
except ImportError:
    print("pip install websocket-client")
    sys.exit(1)

# ── 配置 ──
MCP_URL = "wss://api.xiaozhi.me/mcp/?token=eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOjQ4MTQ4MiwiYWdlbnRJZCI6NjYyNTg0LCJlbmRwb2ludElkIjoiYWdlbnRfNjYyNTg0IiwicHVycG9zZSI6Im1jcC1lbmRwb2ludCIsImlhdCI6MTc4MDY5OTkyMCwiZXhwIjoxODEyMjU3NTIwfQ.Rx1XdL9Mu4MSSXaygBzCjPX-dN9DgkmJfal45EDtTiCqJu7CIdI0RaLkKLvRpkhV_y4lQxVBe9cOnxS5rgvNEA"
API_BASE = "http://47.109.151.238:8800"

# ── 工具定义 ──
ULTRASOUND_TOOL = {
    "name": "ultrasound_transcribe",
    "description": "超声医生口述→结构化报告。发送base64编码的音频,返回完整的超声所见+提示+建议+ICD-10编码。支持方言(湘/川/渝)。",
    "inputSchema": {
        "type": "object",
        "properties": {
            "audio_base64": {"type": "string", "description": "base64编码的音频数据 (webm/wav/mp3, 16kHz)"},
            "patient_id": {"type": "string", "description": "患者病历号/唯一ID (必填)"},
            "gender": {"type": "string", "enum": ["男", "女"], "description": "性别"},
            "age": {"type": "integer", "minimum": 0, "maximum": 150, "description": "年龄"},
            "exam_type": {"type": "string", "description": "检查类型: 腹部超声/乳腺超声/甲状腺超声/产科超声/心脏超声/泌尿超声/妇科超声"},
            "name": {"type": "string", "description": "患者姓名(可选,建议脱敏)"},
        },
        "required": ["audio_base64", "patient_id"]
    }
}


def on_message(ws, message):
    """处理MCP消息"""
    try:
        data = json.loads(message)
        msg_type = data.get("type", "")
        print(f"\n[收到] type={msg_type}")

        if msg_type == "tools/call":
            # 工具调用 → 处理音频 → 返回报告
            tool_id = data.get("id", "")
            tool_name = data.get("name", "")
            args = data.get("arguments", {})
            print(f"  调用工具: {tool_name}")
            print(f"  参数: patient_id={args.get('patient_id','?')} audio_len={len(args.get('audio_base64',''))}")

            result = process_audio(args)

            # 返回结果
            response = {
                "type": "tools/result",
                "id": tool_id,
                "name": tool_name,
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]
            }
            ws.send(json.dumps(response, ensure_ascii=False))
            print(f"  已返回: code={result.get('code')} template={result.get('template','')}")

        elif msg_type == "tools/registered":
            print(f"  ✅ 工具注册成功: {data.get('tools',[])}")

        elif msg_type == "error":
            print(f"  ❌ 错误: {data}")

        else:
            print(f"  📨 {msg_type}: {str(data)[:200]}")

    except Exception as e:
        print(f"  ❌ on_message异常: {e}")


def on_open(ws):
    """连接成功后注册工具"""
    print(f"[连接成功] 注册 ultrasound_transcribe 工具...")
    register_msg = {
        "type": "tools/register",
        "tools": [ULTRASOUND_TOOL]
    }
    ws.send(json.dumps(register_msg, ensure_ascii=False))
    print("  已发送注册请求, 等待确认...")


def on_error(ws, error):
    print(f"[错误] {error}")


def on_close(ws, status, msg):
    print(f"[断开] status={status} msg={msg}")


def process_audio(args: dict) -> dict:
    """处理音频: base64→调API→返回报告"""
    audio_b64 = args.get("audio_base64", "")
    patient_id = args.get("patient_id", "MCP-UNKNOWN")
    gender = args.get("gender", "")
    age = args.get("age", 0)
    exam_type = args.get("exam_type", "腹部超声")
    name = args.get("name", "")

    if not audio_b64:
        return {"code": 400, "msg": "audio_base64为空", "study_see": ""}

    try:
        # 调用MCP专用端点
        payload = json.dumps({
            "audio_base64": audio_b64,
            "patient_id": patient_id,
            "gender": gender,
            "age": age,
            "exam_type": exam_type,
            "name": name,
        }, ensure_ascii=False).encode()

        req = urllib.request.Request(
            f"{API_BASE}/v1/mcp/transcribe",
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"}
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())
            return result
    except Exception as e:
        return {"code": 500, "msg": f"API调用失败: {str(e)[:200]}", "study_see": ""}


# ── 主循环 ──
if __name__ == "__main__":
    print("=" * 60)
    print("  小智MCP客户端 — 超声报告工具")
    print("=" * 60)
    print(f"  MCP: {MCP_URL[:60]}...")
    print(f"  API: {API_BASE}")
    print(f"  Tool: ultrasound_transcribe")
    print("=" * 60)

    ws = websocket.WebSocketApp(
        MCP_URL,
        on_message=on_message,
        on_open=on_open,
        on_error=on_error,
        on_close=on_close,
    )

    # 带自动重连
    while True:
        try:
            ws.run_forever(ping_interval=30, ping_timeout=10)
        except KeyboardInterrupt:
            print("\n[退出]")
            break
        except Exception as e:
            print(f"[重连中...] {e}")
            time.sleep(5)
