import json, urllib.request, ssl
ctx = ssl._create_unverified_context()

# Test fixed-template API
data = json.dumps({"text": "肝脏大小正常 胆囊正常 胰腺正常 脾脏正常 双肾正常 未见异常血流信号"}).encode()
req = urllib.request.Request("https://localhost:8700/api/fixed-template/structure", data=data, headers={"Content-Type": "application/json"})
r = urllib.request.urlopen(req, context=ctx)
d = json.loads(r.read())
print("1. Abdomen:", d.get("category"), "conf=", round(d.get("confidence",0),2), "tags:", len(d.get("tags",[])))

# Test with obstetrics
data2 = json.dumps({"text": "子宫呈前位，宫腔内可见一孕囊约2.8x1.8cm，可见胎心搏动"}).encode()
req2 = urllib.request.Request("https://localhost:8700/api/fixed-template/structure", data=data2, headers={"Content-Type": "application/json"})
r2 = urllib.request.urlopen(req2, context=ctx)
d2 = json.loads(r2.read())
print("2. Obstetric:", d2.get("category"), "is_fetal=", d2.get("is_fetal"), "conf=", round(d2.get("confidence",0),2))

# Test with custom template
data3 = json.dumps({"text": "肝脏大小正常 胆囊正常 胰腺正常", "fixed_template": "我的模板: 肝={liver_size} 胆={gall_size}"}).encode()
req3 = urllib.request.Request("https://localhost:8700/api/fixed-template/structure", data=data3, headers={"Content-Type": "application/json"})
r3 = urllib.request.urlopen(req3, context=ctx)
d3 = json.loads(r3.read())
print("3. Custom:", d3.get("category"), "filled:", d3.get("filled_template","")[:80])

print("ALL OK")
