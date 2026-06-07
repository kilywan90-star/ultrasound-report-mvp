import json, urllib.request

# Test 1: no patient
data1 = json.dumps({"text": "肝脏大小正常 胆囊未见异常 胰腺正常 脾脏正常 双肾正常 未见异常血流信号", "exam_type": "腹部超声"}).encode()
req1 = urllib.request.Request("http://localhost:8700/api/structure", data=data1, headers={"Content-Type": "application/json"})
r1 = json.loads(urllib.request.urlopen(req1).read())
print("Test1 method:", r1.get("method"), "template:", r1.get("report",{}).get("_template_matched","")[:50])

# Test 2: with gender/age
data2 = json.dumps({"text": "肝脏大小正常 胆囊未见异常 胰腺正常 脾脏正常 双肾正常 未见异常血流信号", "exam_type": "腹部超声", "patient_gender": "男", "patient_age": 52}).encode()
req2 = urllib.request.Request("http://localhost:8700/api/structure", data=data2, headers={"Content-Type": "application/json"})
r2 = json.loads(urllib.request.urlopen(req2).read())
print("Test2 method:", r2.get("method"), "template:", r2.get("report",{}).get("_template_matched","")[:50])

# Test 3: obstetric
data3 = json.dumps({"text": "双顶径约5.8cm 股骨长约4.2cm 胎心率145次每分 胎盘后壁 羊水指数12.8", "exam_type": "妇产超声"}).encode()
req3 = urllib.request.Request("http://localhost:8700/api/structure", data=data3, headers={"Content-Type": "application/json"})
r3 = json.loads(urllib.request.urlopen(req3).read())
print("Test3 method:", r3.get("method"))
