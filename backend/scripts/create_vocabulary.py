"""用 DashScope SDK 创建超声热词表，输出 vocabulary_id"""
import json
import os

from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from dashscope.audio.asr import VocabularyService

# 加载热词
with open(Path(__file__).parent / "vocabulary_ultrasound_120.json", encoding="utf-8") as f:
    vocabulary = json.load(f)

print(f"热词总数: {len(vocabulary)}")

service = VocabularyService()

try:
    vocabulary_id = service.create_vocabulary(
        prefix="ultrasound",
        target_model="paraformer-v2",
        vocabulary=vocabulary,
    )
    print(f"\n=== 创建成功 ===")
    print(f"vocabulary_id: {vocabulary_id}")
    print(f"\n请将此 ID 填入 .env 文件的 DASHSCOPE_VOCABULARY_ID={vocabulary_id}")
except Exception as e:
    print(f"\n创建失败: {e}")
    print("请确认 DASHSCOPE_API_KEY 环境变量已正确设置，且账户已开通语音识别服务")
