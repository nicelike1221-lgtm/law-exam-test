# -*- coding: utf-8 -*-
"""批量把行政法题目的「答案」字段更新为本地修复后的结论答案。
只更新 data/行政法_答案更新包.json 中列出的题目（以题目ID定位 record_id）。
读 D:\\测试\\.env 的飞书凭据。
用法：python update_feishu_answers.py   （默认 DRY_RUN 打印将更新项；设 DRY_RUN=0 真正写入）
"""
import json, os, sys, urllib.parse, urllib.error, urllib.request

ROOT = r"D:\测试"
ENV_PATH = os.path.join(ROOT, ".env")
PKG_PATH = os.path.join(ROOT, "data", "行政法_答案更新包.json")
DRY_RUN = os.environ.get("DRY_RUN", "1") != "0"

def load_env():
    env = {}
    for line in open(ENV_PATH, encoding="utf-8"):
        s = line.strip()
        if not s or s.startswith("#"): continue
        i = s.find("=")
        if i < 0: continue
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

def extract(val):
    if val is None: return ""
    if isinstance(val, list):
        for it in val:
            if isinstance(it, dict) and it.get("text"): return str(it["text"])
            elif it: return str(it)
        return ""
    return str(val)

def main():
    env = load_env()
    base = env["FEISHU_BASE_ID"]
    table = env["FEISHU_QUESTION_TABLE_ID"]
    base_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{base}/tables/{table}"

    pkg = json.load(open(PKG_PATH, encoding="utf-8"))
    updates = {u["题目ID"]: u["答案"] for u in pkg["updates"]}
    print(f"更新包题目数: {len(updates)}")

    # 拿 token
    t = http("POST", "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
             body={"app_id": env["FEISHU_APP_ID"], "app_secret": env["FEISHU_APP_SECRET"]})
    if not t.get("tenant_access_token"):
        print("❌ 获取飞书 token 失败:", t); sys.exit(1)
    token = t["tenant_access_token"]

    # 本地 json 拿题型，按 科目+题型 分块 search
    d = json.load(open(os.path.join(ROOT, "data", "questions.行政法.json"), encoding="utf-8"))
    qs = d if isinstance(d, list) else d.get("questions", [])
    type_of = {q["题目ID"]: q.get("题型", "") for q in qs}
    types = sorted({v for v in type_of.values() if v})

    id2rid = {}
    for ty in types:
        conds = [
            {"field_name": "科目", "operator": "is", "value": ["行政法"]},
            {"field_name": "题型", "operator": "is", "value": [ty]},
        ]
        body = {"filter": {"conjunction": "and", "conditions": conds}, "page_size": 500}
        r = http("POST", f"{base_url}/records/search", token=token, body=body)
        if r.get("code") != 0:
            print(f"  ⚠️ 题型[{ty}] search 失败:", r); continue
        for it in r.get("data", {}).get("items", []):
            tid = extract(it.get("fields", {}).get("题目ID"))
            rid = it.get("record_id") or it.get("id")
            if tid:
                id2rid[tid] = rid
    # 补一次纯科目搜索（兜底无题型记录）
    conds = [{"field_name": "科目", "operator": "is", "value": ["行政法"]}]
    r = http("POST", f"{base_url}/records/search", token=token,
             body={"filter": {"conjunction": "and", "conditions": conds}, "page_size": 500})
    if r.get("code") == 0:
        for it in r.get("data", {}).get("items", []):
            tid = extract(it.get("fields", {}).get("题目ID"))
            rid = it.get("record_id") or it.get("id")
            if tid and tid not in id2rid:
                id2rid[tid] = rid

    todo = [(tid, rid, updates[tid]) for tid in updates if tid in id2rid]
    missing = [tid for tid in updates if tid not in id2rid]
    print("DEBUG types=", types, "id2rid大小=", len(id2rid), "唯一rid数=", len(set(id2rid.values())))
    print(f"飞书匹配到 record_id: {len(todo)} / {len(updates)}")
    if missing:
        print(f"⚠️ 未匹配到 {len(missing)} 题(可能科目/题型不一致或已被删): {missing[:10]}")

    if DRY_RUN:
        print("\n[DRY_RUN] 将更新的样例:")
        for item in todo[:10]:
            print("  ", item)
        print("\nDRY_RUN 模式未写入。设 DRY_RUN=0 重新运行以真正更新飞书。")
        return

    # 真正写入：batch_update（每次最多 500）
    ok = 0; fail = 0
    for i in range(0, len(todo), 500):
        chunk = todo[i:i+500]
        records = [{"record_id": rid, "fields": {"答案": ans}} for _, rid, ans in chunk]
        r = http("POST", f"{base_url}/records/batch_update", token=token, body={"records": records})
        if r.get("code") == 0:
            ok += len(chunk)
        else:
            fail += len(chunk)
            print(f"  ⚠️ batch_update 失败: {r}")
    print(f"\n✅ 已更新 {ok} 题，失败 {fail} 题。")

if __name__ == "__main__":
    main()
