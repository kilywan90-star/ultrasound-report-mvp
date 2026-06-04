#!/usr/bin/env python3
"""
超声报告系统 全覆盖自动化测试 — 20个场景
"""
import json, urllib.request, urllib.error, time, sys, ssl

# Bypass self-signed cert
ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

BASE = "https://47.109.151.238"
RESULTS = []
PASS = FAIL = 0

def test(label, method, path, body=None, headers=None, expect_status=200, expect_field=None):
    global PASS, FAIL
    url = BASE + path
    if headers is None:
        headers = {}
    if "Content-Type" not in headers and body is not None:
        headers["Content-Type"] = "application/json"

    t0 = time.time()
    try:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        resp = urllib.request.urlopen(req, timeout=15, context=ssl_ctx)
        status = resp.status
        result = json.loads(resp.read().decode()) if status == 200 else None
        latency = (time.time() - t0) * 1000
    except urllib.error.HTTPError as e:
        status = e.code
        result = None
        latency = (time.time() - t0) * 1000
        try: result = json.loads(e.read().decode())
        except: pass
    except Exception as e:
        status = 0
        result = str(e)[:60]
        latency = (time.time() - t0) * 1000

    ok = True
    check = ""
    if status != expect_status:
        ok = False
        check = f"status={status}(expect {expect_status})"
    elif expect_field and result:
        val = result
        for k in expect_field.split("."):
            val = val.get(k, {}) if isinstance(val, dict) else val
        if not val:
            ok = False
            check = f"missing field={expect_field}"

    marker = "PASS" if ok else "FAIL"
    if ok: PASS += 1
    else: FAIL += 1
    RESULTS.append(f"  {marker} [{label}] {latency:.0f}ms" + (f"  {check}" if check else ""))

def run():
    global PASS, FAIL
    PASS = FAIL = 0
    RESULTS.clear()
    print("=" * 80)
    print("Ultrasound Report System - 20 Scenario Auto Test")
    print("=" * 80)

    # === Group 1: Infrastructure ===
    print("\n[Infrastructure]")
    test("health", "GET", "/api/health")
    test("templates", "GET", "/api/templates", expect_field="abdomen")
    test("patient-queue", "GET", "/api/patients/queue", expect_field="success")

    # === Group 2: Normal Flow ===
    print("\n[Normal Flow]")
    test("add-patient-male", "POST", "/api/patients/quick-add",
         body={"name":"TEST-Z3","gender":"男","age":52,"exam_type":"腹部超声"}, expect_field="patient")
    test("add-patient-female", "POST", "/api/patients/quick-add",
         body={"name":"TEST-LF","gender":"女","age":35,"exam_type":"妇产超声"}, expect_field="patient")
    test("add-patient-thyroid", "POST", "/api/patients/quick-add",
         body={"name":"TEST-W5","gender":"男","age":45,"exam_type":"甲状腺超声"}, expect_field="patient")

    test("struct-abdomen-no-patient", "POST", "/api/structure",
         body={"text":"肝脏大小形态正常，包膜光滑。胆囊大小正常，囊壁光滑。胰腺正常。脾脏正常。双肾正常。未见异常血流信号。","exam_type":"腹部超声"}, expect_field="success")
    test("struct-abdomen-with-gender", "POST", "/api/structure",
         body={"text":"肝脏大小形态正常，包膜光滑。胆囊大小正常，囊壁光滑。胰腺正常。脾脏正常。双肾正常。未见异常血流信号。","exam_type":"腹部超声","patient_gender":"男","patient_age":52}, expect_field="success")
    test("struct-obstetric", "POST", "/api/structure",
         body={"text":"双顶径5.8cm，头围22.1cm，腹围19.8cm，股骨长4.2cm，胎心率145，羊水指数12.8。胎盘后壁I级。","exam_type":"妇产超声","patient_gender":"女","patient_age":28}, expect_field="success")
    test("struct-thyroid", "POST", "/api/structure",
         body={"text":"甲状腺左叶4.5乘1.6乘1.5厘米，右叶4.8乘1.8乘1.7厘米。双侧叶内均可见多个低回声结节。","exam_type":"甲状腺超声","patient_gender":"男","patient_age":45}, expect_field="success")
    test("struct-prostate", "POST", "/api/structure",
         body={"text":"前列腺大小5.2乘4.5乘4.2厘米，形态饱满，突入膀胱1.5厘米。实质回声欠均匀，可见多个钙化灶。残余尿量80毫升。","exam_type":"腹部超声","patient_gender":"男","patient_age":65}, expect_field="success")

    # === Group 3: Edge/Error Cases ===
    print("\n[Edge/Error Cases]")
    test("empty-text", "POST", "/api/structure",
         body={"text":"","exam_type":"腹部超声"}, expect_status=422)
    test("overlong-text", "POST", "/api/structure",
         body={"text":"肝"*10001,"exam_type":"腹部超声"}, expect_status=422)
    test("missing-name", "POST", "/api/patients/quick-add",
         body={"name":"","gender":"男","age":50,"exam_type":"腹部超声"}, expect_status=422)
    test("invalid-gender", "POST", "/api/patients/quick-add",
         body={"name":"TEST","gender":"X","age":30,"exam_type":"腹部超声"}, expect_status=422)

    test("male-uterus", "POST", "/api/structure",
         body={"text":"子宫大小正常，卵巢未见异常，宫颈光滑","exam_type":"腹部超声","patient_gender":"男","patient_age":52}, expect_field="success")
    test("wrong-exam-type", "POST", "/api/structure",
         body={"text":"双顶径5.8cm 胎心率145 羊水12.8","exam_type":"心脏超声"}, expect_field="success")
    test("no-exam-type", "POST", "/api/structure",
         body={"text":"肝脏大小正常 胆囊正常"}, expect_field="success")
    test("numbers-only", "POST", "/api/structure",
         body={"text":"123 456 78.9 mm cm 3.2x5.8"}, expect_field="success")
    test("sql-injection", "POST", "/api/structure",
         body={"text":"肝脏; DROP TABLE patients;--","exam_type":"腹部超声"}, expect_field="success")
    test("xss-attempt", "POST", "/api/structure",
         body={"text":"<script>alert('xss')</script> 肝脏正常","exam_type":"腹部超声"}, expect_field="success")

    # === Report ===
    print()
    for r in RESULTS:
        print(r)
    total = PASS + FAIL
    print(f"\n{'='*80}")
    print(f"  Total: {total}  Pass: {PASS}  Fail: {FAIL}  Rate: {PASS/total*100:.0f}%")
    print(f"{'='*80}")
    return FAIL == 0

if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
