"""阿里云百炼 DashScope 语音识别 — 支持流式输出 v2"""

import os, asyncio, tempfile, dashscope, time, logging, json
from asr_correction import correct_ASR_text

_log = logging.getLogger(__name__)

# 加载超声热词表（670个医学术语），提升ASR识别准确率
_HOTWORDS_CACHE = None
def _load_hotwords() -> list[str]:
    global _HOTWORDS_CACHE
    if _HOTWORDS_CACHE is not None:
        return _HOTWORDS_CACHE
    hw_path = os.path.join(os.path.dirname(__file__), "knowledge", "asr_hotwords_auto.json")
    try:
        with open(hw_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        words = [item["word"] for item in data.get("hotwords", []) if "word" in item]
        _HOTWORDS_CACHE = words
        print(f"[ASR热词] 已加载 {len(words)} 个超声术语")
        _log.info(f"ASR热词已加载: {len(words)}个")

        # 验证: 打印一些热词的注入格式
        sample = words[:5]
        print(f"[ASR热词] 即将注入到qwen3-asr-flash: {sample}")
        print(f"[ASR热词] 总计 {len(words)} 个词, 来源: {data.get('_source','unknown')}")
    except Exception as e:
        _log.warning(f"ASR热词加载失败: {e}")
        _HOTWORDS_CACHE = []
    return _HOTWORDS_CACHE


async def transcribe_audio(audio_data: bytes, sample_rate: int = 16000) -> dict:
    """返回 {"raw": 原始ASR文本, "text": 纠错后文本} (非流式, 保持兼容)"""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY 环境变量未设置")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_data)
        tmp_path = tmp.name

    # 加载热词
    hot_words = _load_hotwords()
    _log.info(f"ASR请求: 热词{len(hot_words)}个, 音频{len(audio_data)}字节")

    last_error = None
    for attempt in range(3):
        try:
            def _call():
                try:
                    return dashscope.MultiModalConversation.call(
                        model="qwen3-asr-flash",
                        messages=[{"role":"user","content":[{"audio":tmp_path}]}],
                        api_key=api_key,
                        hot_words=hot_words,
                    )
                finally:
                    pass

            response = await asyncio.wait_for(asyncio.to_thread(_call), timeout=45)

            if response.status_code == 200:
                content = response.output.choices[0].message.content
                if isinstance(content, list):
                    raw_text = "".join(c.get("text","") if isinstance(c,dict) else str(c) for c in content)
                else:
                    raw_text = str(content) if content else ""
                if raw_text.strip():
                    try: os.unlink(tmp_path)
                    except OSError: pass
                    corrected = correct_ASR_text(raw_text.strip())
                    return {"raw": raw_text.strip(), "text": corrected}
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
    except OSError: pass
    raise RuntimeError(f"语音识别失败({len(str(last_error))}): {last_error}")


async def transcribe_audio_stream(audio_data: bytes, sample_rate: int = 16000):
    """
    流式语音识别 — 返回 async generator, 逐段 yield 识别结果

    用法:
        async for chunk in transcribe_audio_stream(audio_data):
            print(chunk["text"])  # 增量文本
            # chunk["text"] 是增量文本, 前端逐字追加
    """
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY 环境变量未设置")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_data)
        tmp_path = tmp.name

    try:
        def _call():
            return dashscope.MultiModalConversation.call(
                model="qwen3-asr-flash",
                messages=[{"role":"user","content":[{"audio":tmp_path}]}],
                api_key=api_key,
                stream=True,
                incremental_output=True,
                hot_words=_load_hotwords(),
            )

        response = await asyncio.to_thread(_call)

        accumulated_text = ""
        for chunk in response:
            if chunk.status_code == 200:
                try:
                    content = chunk.output.choices[0].message.content
                    if isinstance(content, list):
                        delta = "".join(c.get("text","") if isinstance(c,dict) else str(c) for c in content)
                    else:
                        delta = str(content) if content else ""
                    if delta:
                        accumulated_text += delta
                        yield {"text": delta, "accumulated": accumulated_text, "is_final": False}
                except (AttributeError, IndexError):
                    pass

        # Final yield with corrected full text
        if accumulated_text.strip():
            corrected = correct_ASR_text(accumulated_text.strip())
            yield {"text": "", "accumulated": accumulated_text.strip(), "corrected": corrected, "is_final": True}
        else:
            yield {"text": "", "accumulated": "", "corrected": "", "is_final": True, "error": "ASR未返回识别文本"}

    except Exception as e:
        _log.error(f"流式ASR失败: {e}")
        yield {"text": "", "accumulated": "", "corrected": "", "is_final": True, "error": str(e)}
    finally:
        try: os.unlink(tmp_path)
        except OSError: pass
