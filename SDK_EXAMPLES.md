# 超声报告语音 API — SDK 示例

## Python

```python
import requests

API_BASE = "http://47.109.151.238"

class UltrasoundClient:
    def __init__(self, api_key: str):
        self.key = api_key

    def structure(self, text: str, patient_id: str, gender: str, age: int, exam_type: str) -> dict:
        """文本 → 结构化报告"""
        r = requests.post(f"{API_BASE}/v1/structure", json={
            "text": text,
            "patient_context": {
                "patient_id": patient_id,
                "gender": gender,
                "age": age,
                "exam_type": exam_type,
            }
        }, headers={"Authorization": f"Bearer {self.key}"})
        r.raise_for_status()
        return r.json()

    def transcribe(self, audio_path: str, patient_id: str, gender: str, age: int, exam_type: str) -> dict:
        """语音文件 → 结构化报告"""
        with open(audio_path, "rb") as f:
            r = requests.post(f"{API_BASE}/v1/transcribe",
                files={"audio_file": f},
                data={"patient_context": json.dumps({
                    "patient_id": patient_id, "gender": gender, "age": age, "exam_type": exam_type
                })},
                headers={"Authorization": f"Bearer {self.key}"})
        r.raise_for_status()
        return r.json()

    def usage(self) -> dict:
        r = requests.get(f"{API_BASE}/v1/usage",
            headers={"Authorization": f"Bearer {self.key}"})
        r.raise_for_status()
        return r.json()

# 用法
import json
client = UltrasoundClient(api_key="sk-xxx")
report = client.structure(
    text="肝脏大小形态正常胆囊壁光滑胰腺未见异常",
    patient_id="MRN-001", gender="男", age=45, exam_type="腹部超声"
)
print(report["data"]["study_see"])
```

## JavaScript

```javascript
const BASE = "http://47.109.151.238";

async function structureReport(apiKey, text, patientId, gender, age, examType) {
  const r = await fetch(`${BASE}/v1/structure`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      text,
      patient_context: { patient_id: patientId, gender, age, exam_type: examType }
    }),
  });
  return r.json();
}

// 用法
const report = await structureReport(
  "sk-xxx",
  "肝脏大小正常胆囊壁光滑",
  "MRN-001", "男", 45, "腹部超声"
);
console.log(report.data.study_see);
```

## cURL

```bash
# 注册
curl -X POST http://47.109.151.238/v1/signup \
  -H "Content-Type: application/json" \
  -d '{"name":"XX医院","email":"xx@hospital.cn"}'

# 文本结构化 (保存返回的 api_key)
curl -X POST http://47.109.151.238/v1/structure \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <API_KEY>" \
  -d '{"text":"肝脏大小正常胆囊壁光滑","patient_context":{"patient_id":"P001","gender":"男","age":45,"exam_type":"腹部超声"}}'

# 语音转录
curl -X POST http://47.109.151.238/v1/transcribe \
  -H "Authorization: Bearer <API_KEY>" \
  -F "audio_file=@recording.webm" \
  -F 'patient_context={"patient_id":"P001","gender":"女","age":38,"exam_type":"乳腺超声"}'

# 查询用量
curl -H "Authorization: Bearer <API_KEY>" http://47.109.151.238/v1/usage
```
