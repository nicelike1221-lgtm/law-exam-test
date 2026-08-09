# -*- coding: utf-8 -*-
"""把 build_xingzheng.py 产出的 feishu_records.json（482 条商经知）
按飞书字段类型格式化后 batch_create 写入多维表格（当前商经知已为 0 条，全新导入）。
读 D:\\测试\\.env 凭据。
流程:
  1) 拿 tenant_access_token
  2) GET /fields 取得「字段名 -> 类型」映射
  3) 逐条按类型格式化（multi_select 包 [{"text":v}]；single_select 包 {"text":v}；number 转数值）
  4) batch_create（每批 ≤500，本批 434 一次即可）
用法:
  python write_xingzheng_feishu.py        # DRY_RUN 只打印类型映射+样例
  DRY_RUN=0 python write_xingzheng_feishu.py   # 真正写入
"""
import json, os, sys, urllib.error, urllib.request

ROOT = r"D:\测试"
ENV_PATH = os.path.join(ROOT, ".env")
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

# 飞书 bitable 字段类型整数码 -> 规范类型名
TYPE_CODES = {
    1: "text", 2: "number", 3: "single_select", 4: "multi_select",
    5: "datetime", 7: "checkbox", 11: "user", 13: "phone",
    15: "url", 17: "email",
}
def code2type(ftype):
    if isinstance(ftype, str):
        return ftype.strip().lower()
    return TYPE_CODES.get(int(ftype), "text")

def fmt(value, ftype):
    """按飞书字段类型把 python 值格式化成 API 期望形态。空值返回 None（跳过该字段）。"""
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    t = code2type(ftype)
    if t in ("multiselect", "multi_select"):
        # 简化格式：multi_select 写成字符串数组 [{"text":v}] 已废弃，直接 ["v"]
        if isinstance(value, list):
            return [str(x).strip() for x in value if str(x).strip()]
        return [str(value).strip()]
    if t in ("single_select", "singleselect"):
        # 简化格式：single_select 写成纯字符串，而非 {"text":v}
        return str(value).strip()
    if t in ("number", "auto_number"):
        try:
            f = float(value)
            return int(f) if f.is_integer() else f
        except (TypeError, ValueError):
            return None
    if t in ("checkbox",):
        return bool(value)
    # text / url / email / phone / datetime / formula / user ... 一律转字符串
    return str(value)

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

    # 1) 字段类型映射
    r = http("GET", f"{base_url}/fields?page_size=200", token=token)
    if r.get("code") != 0:
        print("❌ 获取字段失败:", r)
        sys.exit(1)
    type_map = {}
    for f in r.get("data", {}).get("items", []):
        type_map[f["field_name"]] = f.get("type", "")
    print(f"字段类型映射（共 {len(type_map)} 个字段）:")
    for k, v in type_map.items():
        print(f"  {k} -> {v}")

    recs = json.load(open(SRC, encoding="utf-8"))
    print(f"\n待写入记录数: {len(recs)}")

    # 2) 格式化
    formatted = []
    for rec in recs:
        fields = {}
        for k, v in rec.items():
            ftype = type_map.get(k)
            if ftype is None:
                # 飞书表无此字段，跳过以免报错
                continue
            val = fmt(v, ftype)
            if val is not None:
                fields[k] = val
        formatted.append({"fields": fields})

    # 校验：所有记录是否都含 题目ID / 科目 / 状态
    miss_id = [i for i, fr in enumerate(formatted) if not fr["fields"].get("题目ID")]
    miss_sub = [i for i, fr in enumerate(formatted) if not fr["fields"].get("科目")]
    miss_st = [i for i, fr in enumerate(formatted) if not fr["fields"].get("状态")]
    print(f"缺题目ID: {len(miss_id)} | 缺科目: {len(miss_sub)} | 缺状态: {len(miss_st)}")

    if DRY_RUN:
        print("\n[DRY_RUN] 样例格式化后的首条记录:")
        print(json.dumps(formatted[0], ensure_ascii=False, indent=2)[:1200])
        print("\nDRY_RUN 结束。设 DRY_RUN=0 重新运行以真正写入飞书。")
        return

    ok = 0
    fail = 0
    failed_ids = []
    for i in range(0, len(formatted), PAGE):
        chunk = formatted[i:i+PAGE]
        r = http("POST", f"{base_url}/records/batch_create", token=token,
                 body={"records": chunk})
        if r.get("code") == 0:
            n = len(r.get("data", {}).get("records", []))
            ok += n
            print(f"  第 {i//PAGE+1} 批写入 {n} 条")
        else:
            fail += len(chunk)
            print(f"  ⚠️ 第 {i//PAGE+1} 批失败: {r}")
            # 记录该批题目ID便于排查
            for fr in chunk:
                failed_ids.append(fr["fields"].get("题目ID"))
    print(f"\n✅ 已写入 {ok} 条，失败 {fail} 条。")
    if failed_ids:
        print("失败题目ID:", failed_ids[:20])

if __name__ == "__main__":
    main()
