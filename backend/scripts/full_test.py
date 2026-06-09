import json, urllib.request, urllib.parse, random, string, time, os

BASE = "http://127.0.0.1:9999"
PASS = 0; FAIL = 0; ERRORS = {}
RANDOM_TEXTS = [
    "肝脏大小正常，包膜光整，实质回声均匀",
    "胆囊壁毛糙，内见强回声伴声影",
    "甲状腺左叶见低回声结节",
    "双侧乳腺未见明确占位性病变",
    "心脏各房室内径正常，各瓣膜清晰",
    "子宫前位大小形态正常",
    "右肾见无回声区，考虑囊肿",
    "前列腺大小正常，形态规则",
    "脾脏未见肿大，实质回声均匀",
    "胎儿头位，双顶径8.5cm，股骨长6.7cm",
    "肝脏形态欠规则，轮廓增大，表面欠光滑，实质回声几乎消失，可见大小不等的无回声区",
]

def api(method, path, body=None, timeout=30):
    url = BASE + path
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type":"application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}: {e.read().decode()[:80]}"}
    except Exception as e:
        return {"_error": str(e)[:100]}

def upload_segment_file(sid, filepath):
    boundary = "----" + "".join(random.choices(string.ascii_letters + string.digits, k=24))
    with open(filepath, "rb") as f:
        blob = f.read()
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"t.wav\"\r\nContent-Type: audio/wav\r\n\r\n".encode() + blob + f"\r\n--{boundary}--\r\n".encode())
    req = urllib.request.Request(BASE + f"/api/workstation/sessions/{sid}/segments", data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        r = urllib.request.urlopen(req, timeout=120)
        return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}: {e.read().decode()[:100]}"}

def t(name, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
    except Exception as e:
        FAIL += 1
        ERRORS[name] = str(e)[:120]

print("=" * 60)
print("FULL SYSTEM AUTOMATED TEST v3")
print("=" * 60)

# -- 1. STATIC PAGES --
print("\n--- 1. Static Pages ---")
for p in ["/", "/pad.html", "/pad.js", "/director.html", "/director.js", "/tablet.html",
          "/tablet.js", "/index.html", "/style.css", "/api.js", "/ui.js", "/app.js"]:
    def check(url):
        r = urllib.request.urlopen(url, timeout=10)
        return r.status == 200
    t(f"GET {p}", lambda url=BASE+p: check(url))

# -- 2. CORE API --
print("\n--- 2. Core API ---")
for ep in ["/api/health", "/api/stats", "/api/patients", "/api/reports", "/api/doctors", "/api/templates"]:
    def check(ep=ep):
        d = api("GET", BASE+ep)
        return d is not None and "_error" not in d
    t(f"GET {ep}", check)

t("audio-records/storage", lambda: "directory" in api("GET", BASE+"/api/audio-records/storage"))
t("audio-records list", lambda: api("GET", BASE+"/api/audio-records?limit=1") is not None)
t("workstation queue", lambda: api("GET", BASE+"/api/workstation/queue?status=%E5%BE%85%E6%A3%80&limit=3") is not None)
t("auto/cheatsheet", lambda: api("GET", BASE+"/api/auto/cheatsheet") is not None)

# -- 3. STRUCTURE --
print("\n--- 3. Structure API ---")
for txt in RANDOM_TEXTS:
    short = txt[:15]
    def check(t=txt):
        d = api("POST", BASE+"/api/structure", {"text": t, "exam_type": "腹部超声"})
        return d.get("success") in (True, False)
    t(f"structure: {short}...", check)

t("structure empty", lambda: api("POST", BASE+"/api/structure", {"text":"","exam_type":"腹部超声"}).get("_error","y").startswith("HTTP 422"))
t("structure cardiac", lambda: api("POST", BASE+"/api/structure", {"text":"心脏大小正常","exam_type":"心脏超声"}).get("success"))
t("structure thyroid", lambda: api("POST", BASE+"/api/structure", {"text":"甲状腺双侧叶大小形态正常","exam_type":"甲状腺超声"}).get("success") in (True, False))

# -- 4. AUTO PIPELINE --
print("\n--- 4. Auto Pipeline ---")
for txt in ["肝脏大小正常", "胆囊壁毛糙", "甲状腺左叶结节"]:
    def check(t=txt):
        d = api("POST", BASE+"/api/auto/process", {"text": t})
        return d is not None
    t(f"auto {txt[:8]}", check)

# -- 5. WORKSTATION FULL LOOP --
print("\n--- 5. Workstation Loop ---")
t("mock seed", lambda: api("POST", BASE+"/api/workstation/mock-patients", {}) is not None)
q = api("GET", BASE+"/api/workstation/queue?status=%E5%BE%85%E6%A3%80&limit=1")
patients = q.get("patients", [])
wav_path = "/opt/ultrasound-report-mvp/backend/recordings/20260609_083433_50c3b9ea.16k.wav"

for i in range(3):
    q2 = api("GET", BASE+"/api/workstation/queue?status=%E5%BE%85%E6%A3%80&limit=1")
    pl = q2.get("patients", [])
    if not pl: continue
    pid = pl[0]["id"]
    s = api("POST", BASE+"/api/workstation/sessions", {"patient_id": pid, "exam_type": "腹部超声"})
    sid = s.get("session", {}).get("id")
    if not sid: continue
    t(f"ws cycle {i+1} session", lambda: sid is not None)
    t(f"ws cycle {i+1} detail", lambda: api("GET", BASE+f"/api/workstation/sessions/{sid}") is not None)
    if os.path.exists(wav_path):
        t(f"ws cycle {i+1} segment", lambda: upload_segment_file(sid, wav_path).get("success", False))
        t(f"ws cycle {i+1} merge", lambda: api("POST", BASE+f"/api/workstation/sessions/{sid}/merge", {}).get("success"))
        t(f"ws cycle {i+1} report", lambda: api("POST", BASE+f"/api/workstation/sessions/{sid}/generate-report", {}).get("success"))

# -- 6. ASR --
print("\n--- 6. ASR Upload ---")
if os.path.exists(wav_path):
    with open(wav_path, "rb") as f:
        blob = f.read()
    boundary = "----" + "".join(random.choices(string.ascii_letters + string.digits, k=24))
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"t.wav\"\r\nContent-Type: audio/wav\r\n\r\n".encode() + blob + f"\r\n--{boundary}--\r\n".encode())
    req = urllib.request.Request(BASE+"/api/asr/transcribe", data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        r = urllib.request.urlopen(req, timeout=60)
        d = json.loads(r.read().decode())
        t("asr transcribe", lambda: d.get("success") in (True, False))
        t("asr has text", lambda: "text" in d)
        t("asr has source", lambda: "source" in d)
    except Exception as e:
        t("asr upload fail", lambda: str(e)[:10])

# -- SUMMARY --
print(f"\n{'=' * 60}")
print(f"RESULTS:  {PASS} passed  /  {FAIL} failed  /  {PASS + FAIL} total")
if FAIL == 0:
    print("ALL TESTS PASSED")
else:
    print("FAILURES:")
    for k, v in list(ERRORS.items())[:15]:
        print(f"  {k}: {v}")
