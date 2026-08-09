# -*- coding: utf-8 -*-
import json, re, urllib.error, urllib.request
from collections import Counter
ROOT = r"D:\测试"; ENV = ROOT + r"\.env"
env = {}
for line in open(ENV, encoding="utf-8"):
    s = line.strip()
    if not s or s.startswith("#"):
        continue
    i = s.find("=")
    if i < 0:
        continue
    env[s[:i].strip()] = s[i+1:].strip().strip('"').strip("'")
base = env["FEISHU_BASE_ID"]; table = env["FEISHU_QUESTION_TABLE_ID"]
bu = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{base}/tables/{table}"

def get(u, t):
    req = urllib.request.Request(u, method="GET")
    req.add_header("Authorization", "Bearer " + t)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

tok_req = urllib.request.Request(
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
    data=json.dumps({"app_id": env["FEISHU_APP_ID"], "app_secret": env["FEISHU_APP_SECRET"]}).encode(),
    method="POST", headers={"Content-Type": "application/json"})
token = json.loads(urllib.request.urlopen(tok_req, timeout=30).read().decode())["tenant_access_token"]

allrecs = []; pt = None; pg = 0
while True:
    u = f"{bu}/records?page_size=500"
    if pt:
        u += "&page_token=" + pt
    r = get(u, token)
    its = r.get("data", {}).get("items", [])
    allrecs += its
    pt = r.get("data", {}).get("page_token")
    pg += 1
    if not pt or not its or pg > 50:
        break

c = Counter(str(it["fields"].get("科目")) for it in allrecs)
print("全表总数:", len(allrecs))
print("科目分布:", dict(c))
sj = [it for it in allrecs if str(it["fields"].get("科目")) == "商经知"]
leak = sum(1 for it in sj if re.search(r"(核心考点|一般考点)\s", str(it["fields"].get("解析", ""))))
hashp = sum(1 for it in sj if any(ln.strip().startswith("##") for ln in str(it["fields"].get("解析", "")).split("\n")))
empty_bz = sum(1 for it in sj if not str(it["fields"].get("编章", "")).strip())
empty_opt = sum(1 for it in sj if not str(it["fields"].get("选项A", "")).strip())
st = Counter(str(it["fields"].get("状态")) for it in sj)
print("商经知数量:", len(sj))
print("状态分布:", dict(st))
print("解析含核心考点泄漏:", leak, "| 含##前缀:", hashp, "| 空编章:", empty_bz, "| 空选项A:", empty_opt)
f0 = sj[0]["fields"]
print("样本 题目ID:", f0.get("题目ID"), "| 编章:", f0.get("编章"))
print("样本 解析首行:", str(f0.get("解析", ""))[:40].replace("\n", " "))
print("样本 解析末30字:", repr(str(f0.get("解析", ""))[-30:]))
