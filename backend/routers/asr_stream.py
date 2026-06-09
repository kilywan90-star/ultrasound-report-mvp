"""
WebSocket 实时 ASR 流 v6 — 采用 paraformer-realtime-v2 call 模式

浏览器蓄积 PCM 后一次性识别，增量传回结果
"""
import asyncio
import json
import logging
import os
import tempfile
import struct
import wave

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import dashscope
from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult

router = APIRouter()
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
CHUNK_SECONDS = 3

audio_buffers = {}


class BufferASRCallback(RecognitionCallback):
    def __init__(self, ws, ws_id):
        self.ws = ws
        self.ws_id = ws_id

    def _send(self, data):
        try:
            import asyncio
            asyncio.run_coroutine_threadsafe(
                self.ws.send_json(data), asyncio.get_event_loop()
            )
        except:
            pass

    def on_event(self, result):
        import dashscope.audio.asr as r
        try:
            sentences = []
            if isinstance(result, r.RecognitionResult):
                sentences = result.get_sentence() or []
            elif isinstance(result, dict):
                sentences = result.get("payload", result).get("sentence", []) if isinstance(result.get("payload", result), dict) else []
            text = "".join([s.get("text", "") for s in sentences if isinstance(s, dict)])
            if text:
                self._send({"type": "partial", "text": text})
        except Exception as e:
            logging.warning("on_event: %s", e)

    def on_error(self, result):
        msg = result.get("message", "") if hasattr(result, "get") else str(result)
        logging.warning("dashscope error: %s", msg)
        self._send({"type": "error", "message": msg})


@router.websocket("/ws/asr/stream")
async def asr_stream(ws: WebSocket):
    await ws.accept()
    ws_id = id(ws)
    audio_buffers[ws_id] = bytearray()
    logging.info("WS connected")

    if not DASHSCOPE_API_KEY:
        await ws.send_json({"type": "error", "message": "DASHSCOPE_API_KEY 未配置"})
        await ws.close()
        return

    await ws.send_json({"type": "status", "status": "ready"})

    try:
        while True:
            data = await ws.receive_bytes()
            audio_buffers[ws_id].extend(data)

            buf = audio_buffers[ws_id]
            # Process every ~3 seconds (16000*3*2 = 96000 bytes)
            while len(buf) >= 96000:
                chunk = bytes(buf[:96000])
                buf = buf[96000:]
                audio_buffers[ws_id] = buf
                asyncio.create_task(transcribe_chunk(ws, ws_id, chunk))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logging.warning("WS error: %s", e)
    finally:
        audio_buffers.pop(ws_id, None)
        await ws.send_json({"type": "status", "status": "closed"})
        try:
            await ws.close()
        except Exception:
            pass


async def transcribe_chunk(ws, ws_id, pcm_data):
    try:
        dashscope.api_key = DASHSCOPE_API_KEY

        # Write PCM to temp WAV
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name
        with wave.open(wav_path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(pcm_data)

        callback = BufferASRCallback(ws, ws_id)
        recognizer = Recognition(
            model="paraformer-realtime-v2",
            callback=callback,
            format="wav",
            sample_rate=16000,
        )
        result = recognizer.call(file=wav_path)

        if hasattr(result, "get_sentence"):
            sentences = result.get_sentence() or []
            text = "".join([s.get("text", "") for s in sentences if isinstance(s, dict)])
            if text:
                await ws.send_json({"type": "partial", "text": text})

        os.unlink(wav_path)

    except Exception as e:
        logging.warning("transcribe_chunk error: %s", e)
