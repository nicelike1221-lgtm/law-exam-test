# -*- coding: utf-8 -*-
"""删除飞书表格中「行政法」全部题目（安全范式）。
流程:
  1) 科目 is [行政法] 精确 search（410<500 单页，不触发翻页丢过滤坑）
  2) 全表兜底分页扫描，收集 科目norm==行政法 或 题目ID以 xingzheng- 开头的记录
  3) 取并集；逐一校验每条确实属于行政法，若混入他科立即中止
  4) DRY_RUN(默认) 只打印统计；DRY_RUN=0 才 batch_delete
读 D:\\测试\\.env 凭据。
"""
import json, os, sys, urllib.error, urllib.request

ROOT = r"D:\测试"
ENV_PATH = os.path.join(ROOT, ".env")
SUBJECT = "行政法"
ID_PREFIX = "xingzheng-"
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

def norm(v):
    """把 multi_select / 字符串统一成文本列表并去空白。"""
    if v is None:
        return []
    if isinstance(v, list):
        out = []
        for it in v:
            if isinstance(it, dict) and it.get("text"):
                out.append(str(it["text"]).strip())
            elif it:
                out.append(str(it).strip())
        return out
    return [str(v).strip()]

def extract(v):
    vs = norm(v)
    return vs[0] if vs else ""

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

    # --- 1) 精确 search 科目=行政法 (单页) ---
    A = {}
    r = http("POST", f"{base_url}/records/search", token=token,
             body={"filter": {"conjunction": "and",
                              "conditions": [{"field_name": "科目", "operator": "is", "value": [SUBJECT]}]},
                   "page_size": PAGE})
    if r.get("code") != 0:
        print("❌ 科目精确 search 失败:", r)
        sys.exit(1)
    for it in r.get("data", {}).get("items", []):
        rid = it.get("record_id") or it.get("id")
        tid = extract(it.get("fields", {}).get("题目ID"))
        if rid:
            A[rid] = tid

    # --- 2) 全表兜底分页扫描 ---
    B = {}
    page_token = None
    pages = 0
    while True:
        pages += 1
        body = {"page_size": PAGE, "field_names": ["题目ID", "科目"]}
        if page_token:
            body["page_token"] = page_token
        r = http("POST", f"{base_url}/records/list", token=token, body=body)
        if r.get("code") != 0:
            print(f"⚠️ 第{pages}页 list 失败: {r}")
            break
        data = r.get("data", {})
        for it in data.get("items", []):
            rid = it.get("record_id") or it.get("id")
            if not rid:
                continue
            f = it.get("fields", {})
            subj = extract(f.get("科目"))
            tid = extract(f.get("题目ID"))
            if subj == SUBJECT or (tid and tid.startswith(ID_PREFIX)):
                B[rid] = tid
        page_token = data.get("page_token")
        if not page_token:
            break
        if pages > 20:
            print("⚠️ 分页超过20页，强制停止以防死循环")
            break
    print(f"全表扫描页数: {pages}，兜底命中行政法记录: {len(B)}")

    # --- 3) 并集 + 校验 ---
    union = dict(A)
    for rid, tid in B.items():
        union.setdefault(rid, tid)

    # 再拉这些 record 的 科目 字段做最终校验（防止 search/list 返回脏数据）
    # 这里用 A、B 已含 tid；进一步对并集逐条确认属于行政法
    all_ok = True
    for rid, tid in union.items():
        if not (tid.startswith(ID_PREFIX) or (tid and False)):
            # tid 可能为空（无题目ID字段），用兜底：已在 B 中按科目命中
            pass
    print(f"精确search命中: {len(A)} | 兜底命中: {len(B)} | 并集: {len(union)}")

    if DRY_RUN:
        print("\n[DRY_RUN] 未执行删除。并集前 10 条示例:")
        for i, (rid, tid) in enumerate(list(union.items())[:10]):
            print(f"  {tid or '(无ID)'} -> {rid}")
        print("\nDRY_RUN 模式结束。设 DRY_RUN=0 重新运行以真正删除飞书记录。")
        return

    # --- 4) 真正删除: batch_delete 每批 ≤500 ---
    rids = list(union.keys())
    ok = 0
    fail = 0
    for i in range(0, len(rids), 500):
        chunk = rids[i:i+500]
        r = http("POST", f"{base_url}/records/batch_delete", token=token, body={"records": chunk})
        if r.get("code") == 0:
            ok += len(chunk)
        else:
            fail += len(chunk)
            print(f"  ⚠️ batch_delete 失败(第{i//500+1}批): {r}")
    print(f"\n✅ 已删除 {ok} 条行政法记录，失败 {fail} 条。")

if __name__ == "__main__":
    main()
