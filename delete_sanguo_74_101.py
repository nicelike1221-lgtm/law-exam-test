# -*- coding: utf-8 -*-
"""删除三国法 book 74/101 两道旧版题（题目ID sanguo-074 / sanguo-101）。
安全范式：GET /records 全表枚举 → 按 题目ID 精确过滤 → batch_delete（键 records）。
"""
import json, os, sys, urllib.error, urllib.request

ROOT = r"D:\测试"
ENV_PATH = ROOT + r"\.env"
DRY_RUN = os.environ.get("DRY_RUN", "1") != "0"
TARGET_IDS = {"sanguo-074", "sanguo-101"}

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

    # GET 全表枚举
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
    print(f"全表记录: {len(allrecs)}")

    # 题目ID 归一化（兼容 text 字段返回的 [{text,type}] 数组或纯字符串）
    def get_qid(f):
        v = f.get("题目ID")
        if isinstance(v, list):
            return "".join(x.get("text", "") for x in v).strip()
        return str(v).strip() if v else ""

    hits = [it for it in allrecs if get_qid(it["fields"]) in TARGET_IDS]
    print(f"命中目标题数: {len(hits)}")
    for it in hits:
        f = it["fields"]
        qid = get_qid(f)
        stem = str(f.get("题干", "")).replace("\n", " ")[:36]
        print(f"  - {qid} | record_id={it['record_id']} | 状态={f.get('状态')} | 题干: {stem}")

    if len(hits) != 2:
        print(f"⚠️ 命中数 != 2，终止（防止误删）。请检查 题目ID 是否为 sanguo-074/sanguo-101。")
        return

    if DRY_RUN:
        print("\n[DRY_RUN] 不执行删除。设 DRY_RUN=0 真正删除。")
        return

    ids = [it["record_id"] for it in hits]
    r = http("POST", f"{bu}/records/batch_delete", token=token, body={"records": ids})
    if r.get("code") == 0:
        print(f"✅ 已删除 {len(ids)} 条: {ids}")
    else:
        print(f"❌ 删除失败: {r}")

if __name__ == "__main__":
    main()
