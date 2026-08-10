# -*- coding: utf-8 -*-
"""删除飞书表格中「理论法」全部题目。

关键坑（本表实测）:
  - records/search 带 page_token 分页会死循环, 每页都返回同一批 500 条
    => 改用「轮次策略」: search 取 <=500 条 -> batch_delete 删掉 -> 再 search
       -> 循环直到 search 返回 0 条。
  - records/list 是 GET 接口 (POST 会 404)，作为最终兜底全表枚举。
  - batch_delete 的 body 键必须是 records（不是 record_ids），否则静默删 0 条。

读 D:\\测试\\.env 凭据。DRY_RUN=0 才真正删除。
"""
import json, os, sys, time, urllib.error, urllib.parse, urllib.request

ROOT = r"D:\测试"
ENV_PATH = os.path.join(ROOT, ".env")
SUBJECT = "理论法"
ID_PREFIX = "lilun-"
DRY_RUN = os.environ.get("DRY_RUN", "1") != "0"
PAGE = 500
MAX_ROUNDS = 20


def load_env():
    env = {}
    for line in open(ENV_PATH, encoding="utf-8"):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        i = s.find("=")
        if i < 0:
            continue
        env[s[:i].strip()] = s[i + 1:].strip().strip('"').strip("'")
    return env


def http(method, url, token=None, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"code": -1, "msg": str(e)}
    except Exception as e:
        return {"code": -1, "msg": str(e)}


def norm(v):
    if v is None:
        return []
    if isinstance(v, list):
        out = []
        for it in v:
            if isinstance(it, dict) and it.get("text"):
                out.append(str(it["text"]).strip())
            elif isinstance(it, str) and it.strip():
                out.append(it.strip())
        return out
    if isinstance(v, dict):
        return [str(v.get("text", "")).strip()]
    return [str(v).strip()]


def extract(v):
    vs = norm(v)
    return vs[0] if vs else ""


def search_batch(base_url, token):
    """单次 search（不分页），返回 {record_id: 题目ID}"""
    body = {
        "filter": {"conjunction": "and",
                   "conditions": [{"field_name": "科目", "operator": "is", "value": [SUBJECT]}]},
        "page_size": PAGE,
    }
    r = http("POST", f"{base_url}/records/search", token=token, body=body)
    if r.get("code") != 0:
        return None, r
    out = {}
    for it in r.get("data", {}).get("items", []):
        rid = it.get("record_id") or it.get("id")
        if rid:
            out[rid] = extract(it.get("fields", {}).get("题目ID"))
    return out, r


def list_all(base_url, token):
    """GET /records 全表枚举，客户端过滤理论法。返回 {record_id: 题目ID}"""
    out = {}
    page_token = None
    pages = 0
    while True:
        pages += 1
        q = {"page_size": PAGE}
        if page_token:
            q["page_token"] = page_token
        url = f"{base_url}/records?" + urllib.parse.urlencode(q)
        r = http("GET", url, token=token)
        if r.get("code") != 0:
            print(f"  ⚠️ 第{pages}页 GET list 失败: {r}")
            break
        data = r.get("data", {})
        items = data.get("items", [])
        for it in items:
            rid = it.get("record_id") or it.get("id")
            if not rid:
                continue
            f = it.get("fields", {})
            subj = extract(f.get("科目")).replace(" ", "")
            tid = extract(f.get("题目ID")).strip()
            if subj == SUBJECT or (tid and tid.startswith(ID_PREFIX)):
                out[rid] = tid
        page_token = data.get("page_token")
        if not data.get("has_more") or not page_token:
            break
        if pages > 40:
            print("  ⚠️ list 分页超过40页，强制停止")
            break
    print(f"  全表枚举 {pages} 页，命中理论法 {len(out)} 条")
    return out


def batch_delete(base_url, token, rids):
    ok = fail = 0
    for i in range(0, len(rids), 500):
        chunk = rids[i:i + 500]
        r = http("POST", f"{base_url}/records/batch_delete", token=token, body={"records": chunk})
        if r.get("code") == 0:
            ok += len(chunk)
        else:
            fail += len(chunk)
            print(f"    ⚠️ batch_delete 失败(第{i//500+1}批): {r}")
        time.sleep(0.3)
    return ok, fail


def main():
    env = load_env()
    base = env["FEISHU_BASE_ID"]
    table = env["FEISHU_QUESTION_TABLE_ID"]
    base_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{base}/tables/{table}"

    t = http("POST", "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
             body={"app_id": env["FEISHU_APP_ID"], "app_secret": env["FEISHU_APP_SECRET"]})
    if not t.get("tenant_access_token"):
        print("❌ 获取飞书 token 失败:", t)
        sys.exit(1)
    token = t["tenant_access_token"]

    if DRY_RUN:
        got, _ = search_batch(base_url, token)
        if got is None:
            print("❌ search 失败")
            sys.exit(1)
        print(f"[DRY_RUN] 本轮 search 命中 {len(got)} 条（可能被单页 500 截断）")
        allrec = list_all(base_url, token)
        print(f"[DRY_RUN] 全表枚举命中理论法 {len(allrec)} 条 —— 这是真实总数")
        for i, (rid, tid) in enumerate(list(allrec.items())[:5]):
            print(f"    {tid or '(无ID)'} -> {rid}")
        print("\nDRY_RUN 结束。设 DRY_RUN=0 真正删除。")
        return

    total_ok = 0
    for rnd in range(1, MAX_ROUNDS + 1):
        got, raw = search_batch(base_url, token)
        if got is None:
            print(f"⚠️ 第{rnd}轮 search 失败: {raw}，转全表枚举兜底")
            break
        if not got:
            print(f"第{rnd}轮 search 命中 0 条 —— search 侧已清空")
            break
        print(f"第{rnd}轮 search 命中 {len(got)} 条，开始删除...")
        ok, fail = batch_delete(base_url, token, list(got.keys()))
        total_ok += ok
        print(f"  已删 {ok} 条（累计 {total_ok}），失败 {fail}")
        if ok == 0:
            print("  ⚠️ 本轮删除 0 条，停止以防死循环")
            break

    # 最终兜底：全表枚举，清掉 search 漏掉的残留
    print("\n最终兜底：全表枚举核查残留...")
    left = list_all(base_url, token)
    if left:
        print(f"发现残留 {len(left)} 条，执行删除...")
        ok, fail = batch_delete(base_url, token, list(left.keys()))
        total_ok += ok
        print(f"  残留已删 {ok} 条，失败 {fail}")
        left2 = list_all(base_url, token)
        print(f"  复核剩余: {len(left2)} 条")
    else:
        print("✅ 无残留")

    print(f"\n✅ 理论法共删除 {total_ok} 条记录。")


if __name__ == "__main__":
    main()
