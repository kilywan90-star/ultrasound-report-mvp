"""
40万真实报告 Benchmark — 模拟语音输入测试

流程：
1. 从 40W CSV 取 StudySee（模拟 ASR 文本）
2. 送入 structure API
3. 对比模板匹配结果 vs 原始 StudyHint
4. 按部位/疾病统计准确率
5. 输出报告
"""
import json, re, csv, io, os, sys, time, random
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── 配置 ──
BASE = os.getenv("API_BASE", "http://127.0.0.1:9999")
SAMPLE_SIZE = int(os.getenv("SAMPLE_SIZE", "500"))      # 每次测 500 条
CSV_PATH = os.getenv("40W_CSV", "").strip()
if not CSV_PATH:
    CSV_PATH = "C:/Users/Administrator/Desktop/超声结构化报告/长沙报告40W.csv"

BODY_PARTS = {
    '腹部': ['肝脏','胆囊','脾脏','胰腺','双肾','肝','胆','肾'],
    '心脏': ['心脏','左心室','左心房','二尖瓣','室间隔'],
    '甲状腺': ['甲状腺','甲状旁腺','峡部'],
    '乳腺': ['乳腺','乳房','腋窝'],
    '妇科': ['子宫','卵巢','附件','宫颈','盆腔'],
    '泌尿': ['前列腺','精囊','睾丸','附睾'],
    '血管': ['颈动脉','椎动脉','下肢静脉'],
}


class BenchmarkStats:
    def __init__(self):
        self.total = 0
        self.matched = 0
        self.partial = 0
        self.failed = 0
        self.by_bodypart = defaultdict(lambda: {"total": 0, "matched": 0, "partial": 0, "failed": 0})
        self.errors = []

    def add(self, body_part, hit, partial_match=False):
        self.total += 1
        self.by_bodypart[body_part]["total"] += 1
        if hit:
            self.matched += 1
            self.by_bodypart[body_part]["matched"] += 1
        elif partial_match:
            self.partial += 1
            self.by_bodypart[body_part]["partial"] += 1
        else:
            self.failed += 1
            self.by_bodypart[body_part]["failed"] += 1

    def report(self):
        print(f"{'='*60}")
        print(f" BENCHMARK REPORT")
        print(f"{'='*60}")
        print(f"  Total tested:     {self.total}")
        print(f"  Template matched: {self.matched} ({self.matched/max(self.total,1)*100:.1f}%)")
        print(f"  Partial match:    {self.partial} ({self.partial/max(self.total,1)*100:.1f}%)")
        print(f"  Failed:           {self.failed} ({self.failed/max(self.total,1)*100:.1f}%)")
        print()
        print(f"  {'Body Part':<12} {'Total':>6} {'Match':>6} {'Partial':>8} {'Fail':>6} {'Rate':>6}")
        print(f"  {'-'*12} {'-'*6} {'-'*6} {'-'*8} {'-'*6} {'-'*6}")
        for bp, stats in sorted(self.by_bodypart.items()):
            rate = stats["matched"] / max(stats["total"], 1) * 100
            print(f"  {bp:<12} {stats['total']:>6} {stats['matched']:>6} {stats['partial']:>8} {stats['failed']:>6} {rate:>5.0f}%")
        print()


def match_bodypart(see_text: str) -> str:
    for bp, kws in BODY_PARTS.items():
        if any(kw in see_text for kw in kws):
            return bp
    return "其他"


def main():
    if not os.path.exists(CSV_PATH):
        print(f"CSV not found: {CSV_PATH}")
        return

    import urllib.request
    import urllib.error

    stats = BenchmarkStats()
    records_loaded = 0

    # Parse CSV
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        raw = f.read()
    raw = raw.lstrip('﻿').lstrip('﻿')

    lines = raw.split('\n')
    records_raw = []
    current = None
    for line in lines[1:]:
        l = line.rstrip('\r')
        if l.startswith('}'):
            if current:
                records_raw.append('\n'.join(current))
                current = None
            continue
        if re.match(r'^\d+,', l):
            if current:
                records_raw.append('\n'.join(current))
            current = [l]
        elif current:
            current.append(l)
    if current:
        records_raw.append('\n'.join(current))

    print(f"Parsed {len(records_raw)} records. Sampling {SAMPLE_SIZE}...\n")

    sampled = random.sample(records_raw, min(SAMPLE_SIZE, len(records_raw)))

    for idx, rec in enumerate(sampled):
        parts = rec.split(',')
        see = parts[7].strip() if len(parts) > 7 else ''
        hint = parts[8].strip() if len(parts) > 8 else ''
        if see.startswith('"') and see.endswith('"'): see = see[1:-1]
        if hint.startswith('"') and hint.endswith('"'): hint = hint[1:-1]
        see_clean = re.sub(r'\s+', '', see)
        hint_clean = re.sub(r'\s+', '', hint)
        if len(see_clean) < 10 or len(hint_clean) < 4:
            continue

        body_part = match_bodypart(see_clean)

        # Determine exam_type from body_part
        exam_type_map = {
            '腹部': '腹部超声', '心脏': '心脏超声', '甲状腺': '甲状腺超声',
            '乳腺': '乳腺超声', '妇科': '妇科超声', '泌尿': '泌尿超声', '血管': '血管超声',
        }
        exam_type = exam_type_map.get(body_part, '腹部超声')

        # Call structure API
        data = json.dumps({"text": see_clean[:2000], "exam_type": exam_type}).encode()
        req = urllib.request.Request(f"{BASE}/api/structure", data=data,
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            result = json.loads(resp.read().decode())
        except Exception as e:
            stats.add(body_part, False)
            continue

        if not result.get("success"):
            stats.add(body_part, False)
            continue

        # Extract template diagnosis from result
        report = result.get("report", {}) or {}
        hints = report.get("study_hint", []) or []
        template_diag = "".join([h.get("diagnosis", "") if isinstance(h, dict) else str(h) for h in hints])
        template_diag_clean = re.sub(r'\s+', '', template_diag)

        # 比较诊断内容
        hit = False
        partial = False
        if template_diag_clean and hint_clean:
            # 提取关键词
            t_kw = set(re.findall(r'[一-鿿]{2,}', template_diag_clean))
            h_kw = set(re.findall(r'[一-鿿]{2,}', hint_clean))
            # 判断匹配类型
            common = t_kw & h_kw
            if len(common) >= 3 or (template_diag_clean in hint_clean or hint_clean in template_diag_clean):
                hit = True
            elif len(common) >= 1 and max(len(t_kw), len(h_kw)) >= 2:
                # 模板诊断至少有一个关键词命中原始诊断
                partial = True
                print(f"  PARTIAL: see={see_clean[:50]} template_diag={template_diag_clean[:40]} hint={hint_clean[:40]} common={common}")

        stats.add(body_part, hit, partial)

        if (idx + 1) % 100 == 0:
            print(f"  Progress: {idx+1}/{len(sampled)} ({stats.matched} matched, {stats.failed} failed)")

    stats.report()


if __name__ == "__main__":
    import random
    main()
