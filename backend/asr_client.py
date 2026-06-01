"""阿里云百炼 DashScope 语音识别 — 带重试和容错"""

import os, asyncio, tempfile, dashscope, time
from asr_correction import correct_ASR_text


async def transcribe_audio(audio_data: bytes, sample_rate: int = 16000) -> str:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY 环境变量未设置")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_data)
        tmp_path = tmp.name

    last_error = None
    for attempt in range(3):
        try:
            def _call():
                try:
                    return dashscope.MultiModalConversation.call(
                        model="qwen3-asr-flash",
                        messages=[{"role":"user","content":[{"audio":tmp_path}]}],
                        api_key=api_key,
                    )
                finally:
                    pass

            response = await asyncio.wait_for(asyncio.to_thread(_call), timeout=45)

            if response.status_code == 200:
                content = response.output.choices[0].message.content
                if isinstance(content, list):
                    text = "".join(c.get("text","") if isinstance(c,dict) else str(c) for c in content)
                else:
                    text = str(content) if content else ""
                if text.strip():
                    try: os.unlink(tmp_path)
                    except: pass
                    return correct_ASR_text(text.strip())
                else:
                    last_error = "ASR 未返回识别文本"
            else:
                last_error = f"ASR API {response.status_code}: {response.message}"

        except asyncio.TimeoutError:
            last_error = "ASR 请求超时"
        except Exception as e:
            last_error = str(e)

        if attempt < 2:
            time.sleep(1.5)

    try: os.unlink(tmp_path)
    except: pass
    raise RuntimeError(f"语音识别失败({len(str(last_error))}): {last_error}")
