# -*- coding: utf-8 -*-
"""修复 商经知 飞书数据：清掉全部旧记录(可能含重复/泄漏版)，重写干净 482 条。
关键修正：batch_delete 的 body 键是 records（非 record_ids）。
删除前用 GET /records 全表枚举（search 分页会死循环），客户端按 科目=商经知 过滤。
"""
import json, os, sys, urllib.error, urllib.request
from collections import Counter

ROOT = r"D:\测试"
ENV_PATH = ROOT + r"\.env"
SRC = os.path.join(ROOT, "quiz_output", "2026-08-10_商经知重导", "feishu_records.json")
DRY_RUN = os.environ.get("DRY_RUN", "1") != "0"
PAGE = 500

def load_env():
    env = {}
    for line in open(ENV_PATH, encoding="utf-8"):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        i = s.find("=")
        if i < 0:
            continue
        env[s[:i].strip()] = s[i+1:].strip().strip('"').strip("'")
    return env

def http(method, url, token=None, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"code": -1, "msg": str(e)}

def main():
    env = load_env()
    base = env["FEISHU_BASE_ID"]; table = env["FEISHU_QUESTION_TABLE_ID"]
    bu = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{base}/tables/{table}"

    t = http("POST", "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
             body={"app_id": env["FEISHU_APP_ID"], "app_secret": env["FEISHU_APP_SECRET"]})
    token = t.get("tenant_access_token")
    if not token:
        print("❌ token 失败:", t); sys.exit(1)

    # 1) 全表 GET 枚举
    allrecs = []; pt = None; pg = 0
    while True:
        u = f"{bu}/records?page_size=500"
        if pt:
            u += "&page_token=" + pt
        r = http("GET", u, token=token)
        if r.get("code") != 0:
            print("❌ list 失败:", r); break
        its = r.get("data", {}).get("items", [])
        allrecs += its
        pt = r.get("data", {}).get("page_token")
        pg += 1
        if not pt or not its or pg > 50:
            break
    print(f"全表记录总数: {len(allrecs)}")
    c = Counter(str(it["fields"].get("科目")) for it in allrecs)
    print("科目分布:", dict(c))

    sj_ids = [it["record_id"] for it in allrecs if str(it["fields"].get("科目")) == "商经知"]
    sj_ids = list(dict.fromkeys(sj_ids))  # 去重保序
    print(f"待删 商经知 record_id: {len(sj_ids)}")

    if DRY_RUN:
        print("\n[DRY_RUN] 不执行删除/写入。设 DRY_RUN=0 运行以真正执行。")
        return

    # 2) 批量删除（正确键 records）
    deleted = 0
    for i in range(0, len(sj_ids), PAGE):
        chunk = sj_ids[i:i+PAGE]
        r = http("POST", f"{bu}/records/batch_delete", token=token, body={"records": chunk})
        if r.get("code") == 0:
            n = len(r.get("data", {}).get("records", chunk))
            deleted += n
            print(f"  删除第 {i//PAGE+1} 批 {n} 条")
        else:
            print(f"  ⚠️ 删除第 {i//PAGE+1} 批失败: {r}")
    print(f"✅ 共删除 {deleted} 条商经知")

    # 3) 重写干净 482
    recs = json.load(open(SRC, encoding="utf-8"))
    print(f"待写入: {len(recs)}")
    ok = 0; fail = 0
    for i in range(0, len(recs), PAGE):
        chunk = recs[i:i+PAGE]
        r = http("POST", f"{bu}/records/batch_create", token=token, body={"records": chunk})
        if r.get("code") == 0:
            n = len(r.get("data", {}).get("records", []))
            ok += n
            print(f"  写入第 {i//PAGE+1} 批 {n} 条")
        else:
            fail += len(chunk)
            print(f"  ⚠️ 写入第 {i//PAGE+1} 批失败: {r}")
    print(f"✅ 已写入 {ok} 条，失败 {fail} 条")

    # 4) 校验：再全表枚举数 商经知
    final = []
    pt = None; pg = 0
    while True:
        u = f"{bu}/records?page_size=500"
        if pt:
            u += "&page_token=" + pt
        r = http("GET", u, token=token)
        if r.get("code") != 0:
            break
        its = r.get("data", {}).get("items", [])
        final += its
        pt = r.get("data", {}).get("page_token")
        pg += 1
        if not pt or not its or pg > 50:
            break
    fc = Counter(str(it["fields"].get("科目")) for it in final)
    print("最终科目分布:", dict(fc))

if __name__ == "__main__":
    main()
