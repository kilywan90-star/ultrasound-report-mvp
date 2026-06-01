"""阿里云百炼 DashScope 语音识别 — qwen3-asr-flash 本地文件"""

import os
import asyncio
import tempfile
import dashscope


async def transcribe_audio(audio_data: bytes, sample_rate: int = 16000) -> str:
    """通过 qwen3-asr-flash 转写本地音频文件"""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY 环境变量未设置")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_data)
        tmp_path = tmp.name

    def _sync_call():
        try:
            response = dashscope.MultiModalConversation.call(
                model="qwen3-asr-flash",
                messages=[{
                    "role": "user",
                    "content": [{"audio": tmp_path}],
                }],
                api_key=api_key,
            )
            return response
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    response = await asyncio.to_thread(_sync_call)

    if response.status_code != 200:
        raise RuntimeError(f"ASR 失败 HTTP {response.status_code}: {response.message}")

    content = response.output.choices[0].message.content

    # qwen3-asr-flash 返回 format 可能是 list[dict] 或 str
    if isinstance(content, list):
        text = "".join(
            c.get("text", "") if isinstance(c, dict) else str(c)
            for c in content
        )
    else:
        text = str(content) if content else ""

    if not text or not text.strip():
        raise RuntimeError("ASR 未返回识别文本")

    return text.strip()
