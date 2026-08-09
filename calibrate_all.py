# -*- coding: utf-8 -*-
"""
校准所有科目：以解析结论为准，修正答案字段。
- 高置信（强结论句，如"本题答案为X/本题正确答案为选项X/本题选X/正确答案为X"）：带矛盾检测，直接以结论覆盖答案字段。
- 中低置信（逐项"X项正确/错误"推导，无强结论）：仅在推断答案与答案字段冲突时标记为"需人工复核"，不直接改。
负面题干（"哪一选项错误"）聚合推断自动反转（答案为被判"错误"的选项）。

用法：
  DRY_RUN=1 python calibrate_all.py            # 仅统计 + 出 CSV 报告，不写飞书（默认）
  python calibrate_all.py                      # 真正写入飞书（先确认 DRY_RUN 报告）
"""
import json, re, os, sys, csv, urllib.request, urllib.error

DRY_RUN = os.environ.get("DRY_RUN", "1") == "1"

LOCAL = {
    "行政法":   "data/questions.行政法.json",
    "刑事诉讼法": "data/questions.刑事诉讼法.json",
    "商经知":   "data/questions.商经知.json",
    "理论法":   "data/questions.理论法.json",
    "三国法":   "data/questions.三国法.json",
    "民诉":     "data/questions.民诉.json",
}

def norm(s):
    return "".join(sorted(set(re.sub(r"[^A-Ea-e]", "", str(s)).upper())))

def load_local(path):
    d = json.load(open(path, encoding="utf-8"))
    return d if isinstance(d, list) else d.get("questions", [])

# ---------- 高置信强结论 ----------
STRONG = [
    r"本题答案为\s*([A-Ea-e]{1,5})",
    r"本题正确答案为选项\s*([A-Ea-e]{1,5})",
    r"本题正确答案为\s*([A-Ea-e]{1,5})",
    r"本题选\s*([A-Ea-e]{1,5})",
    r"综上所述[，,。\s]*本题选\s*([A-Ea-e]{1,5})",
    r"总之[，,。\s]*本题答案为\s*([A-Ea-e]{1,5})",
    r"综上[，,。\s]*本题正确答案为选项\s*([A-Ea-e]{1,5})",
    r"综上[，,。\s]*正确答案为\s*([A-Ea-e]{1,5})",
    r"综上所述[，,。\s]*正确答案为\s*([A-Ea-e]{1,5})",
    r"正确答案为\s*([A-Ea-e]{1,5})",
]
def strong_conclusion(exp):
    for p in STRONG:
        m = re.search(p, exp)
        if m:
            return norm(m.group(1))
    return None

# ---------- 逐项推导（覆盖并列 X、Y项正确） ----------
AFF = [
    r"([A-Ea-e])\s*项正确",
    r"([A-Ea-e])\s*选项正确",
    r"选项\s*([A-Ea-e])\s*正确",
    r"([A-Ea-e])\s*项当选",
    r"([A-Ea-e])\s*当选",
    r"([A-Ea-e])\s*[、,，]\s*([A-Ea-e])\s*项正确",
    r"([A-Ea-e])\s*[、,，]\s*([A-Ea-e])\s*选项正确",
    r"选项\s*([A-Ea-e])\s*[、,，]\s*([A-Ea-e])\s*正确",
    r"([A-Ea-e])\s*[、,，]\s*([A-Ea-e])\s*项当选",
]
NEG = [
    r"([A-Ea-e])\s*项错误",
    r"([A-Ea-e])\s*选项错误",
    r"选项\s*([A-Ea-e])\s*错误",
    r"([A-Ea-e])\s*项不当选",
    r"([A-Ea-e])\s*不当选",
    r"([A-Ea-e])\s*[、,，]\s*([A-Ea-e])\s*项错误",
    r"([A-Ea-e])\s*[、,，]\s*([A-Ea-e])\s*选项错误",
]
def neg_stem(s):
    return bool(re.search(r"错误|不正确|不属于|不应|不能|不包括|没有", s or ""))

def _collect(patterns, exp):
    s = set()
    for p in patterns:
        for m in re.finditer(p, exp):
            for g in m.groups():
                if g: s.add(g.upper())
    return s

def aggregate_infer(exp, is_neg):
    aff = _collect(AFF, exp)
    neg = _collect(NEG, exp)
    if aff & neg:
        return None
    if is_neg:
        return norm("".join(neg)) if neg else None
    return norm("".join(aff)) if aff else None

def is_single(ans):
    return len(norm(ans)) == 1

def analyze(q):
    field = norm(q.get("答案", ""))
    if not field:
        return ("skip", "", "答案字段为空")
    exp = q.get("解析", "") or ""
    c = strong_conclusion(exp)
    if c:
        if is_single(field) and len(c) != 1:
            return ("skip", c, "单选但结论多字母(误提取)")
        nset = _collect(NEG, exp); aset = _collect(AFF, exp)
        if nset & set(c):
            return ("skip", c, "结论含被判错选项")
        if aset and not (aset <= set(c)):
            return ("skip", c, "明确当选选项不在结论")
        if neg_stem(q.get("题干", "")) and nset and nset != set(c):
            return ("skip", c, "负面题否定陈述与结论不符")
        if c != field:
            return ("modify", c, "强结论覆盖")
        return ("ok", c, "已一致")
    inf = aggregate_infer(exp, neg_stem(q.get("题干", "")))
    if inf is None:
        return ("skip", "", "无强结论且逐项推导不可信")
    if inf != field:
        return ("review", inf, "逐项推导与答案字段冲突")
    return ("ok", inf, "逐项推导已一致")

# ---------- 飞书 ----------
def load_env():
    env = {}
    for line in open(".env", encoding="utf-8"):
        s = line.strip()
        if not s or s.startswith("#"): continue
        i = s.find("=")
        if i < 0: continue
        env[s[:i].strip()] = s[i+1:].strip().strip('"').strip("'")
    return env

def feishu_http(method, url, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token: req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def feishu_client():
    env = load_env()
    token = feishu_http("POST", "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                        body={"app_id": env["FEISHU_APP_ID"], "app_secret": env["FEISHU_APP_SECRET"]})["tenant_access_token"]
    base = env["FEISHU_BASE_ID"]; table = env["FEISHU_QUESTION_TABLE_ID"]
    return token, f"https://open.feishu.cn/open-apis/bitable/v1/apps/{base}/tables/{table}"

def feishu_id2rid(token, base_url, subj):
    qs = load_local(LOCAL[subj])
    types = sorted({q.get("题型", "") for q in qs if q.get("题型")})
    id2rid = {}
    for ty in types:
        conds = [{"field_name": "科目", "operator": "is", "value": [subj]},
                 {"field_name": "题型", "operator": "is", "value": [ty]}]
        r = feishu_http("POST", f"{base_url}/records/search", token=token,
                        body={"filter": {"conjunction": "and", "conditions": conds}, "page_size": 500})
        for it in r.get("data", {}).get("items", []):
            f = it.get("fields", {})
            tid = f.get("题目ID")
            if isinstance(tid, list): tid = tid[0].get("text") if tid else None
            rid = it.get("record_id") or it.get("id")
            if tid: id2rid[tid] = rid
    return id2rid

def main():
    report = {}
    all_modify = {}  # subj -> [(tid, ans)]
    for subj, path in LOCAL.items():
        qs = load_local(path)
        modified, skipped, reviewed, ok = [], [], [], []
        local_map = {q.get("题目ID"): q for q in qs}
        for q in qs:
            tid = q.get("题目ID")
            act, ans, reason = analyze(q)
            if act == "modify":
                modified.append([tid, q.get("题型"), q.get("答案"), ans, "已修改", reason])
                all_modify.setdefault(subj, []).append((tid, ans))
            elif act == "skip":
                skipped.append([tid, q.get("题型"), q.get("答案"), ans, "跳过", reason])
            elif act == "review":
                reviewed.append([tid, q.get("题型"), q.get("答案"), ans, "需人工", reason])
            else:
                ok.append(tid)
        report[subj] = dict(total=len(qs), modified=modified, skipped=skipped,
                            reviewed=reviewed, ok=len(ok))
        out = f"data/{subj}_答案校准报告.csv"
        with open(out, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["题目ID", "题型", "原答案", "建议答案", "状态", "备注"])
            for r in modified: w.writerow(r)
            for r in reviewed: w.writerow(r)
            for r in skipped: w.writerow(r)
        print(f"{subj}: 总{len(qs)} 修改{len(modified)} 需人工{len(reviewed)} 跳过{len(skipped)} 已一致{len(ok)}")

    if DRY_RUN:
        print("\n[DRY_RUN] 未写入飞书。设 DRY_RUN=0 运行以真正更新。")
        return

    # 写入飞书 + 更新本地 JSON
    token, base_url = feishu_client()
    total_ok = total_fail = 0
    for subj, changes in all_modify.items():
        if not changes: continue
        id2rid = feishu_id2rid(token, base_url, subj)
        todo = [(tid, id2rid[tid], ans) for tid, ans in changes if tid in id2rid]
        missing = [tid for tid, _ in changes if tid not in id2rid]
        # 更新本地 JSON
        d = json.load(open(LOCAL[subj], encoding="utf-8"))
        arr = d if isinstance(d, list) else d.get("questions", [])
        lmap = {q.get("题目ID"): q for q in arr}
        for tid, ans in changes:
            if tid in lmap: lmap[tid]["答案"] = ans
        json.dump(d, open(LOCAL[subj], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        # 批量写飞书
        for i in range(0, len(todo), 500):
            chunk = todo[i:i+500]
            recs = [{"record_id": rid, "fields": {"答案": ans}} for _, rid, ans in chunk]
            r = feishu_http("POST", f"{base_url}/records/batch_update", token=token, body={"records": recs})
            if r.get("code") == 0:
                total_ok += len(chunk)
            else:
                total_fail += len(chunk)
                print(f"  {subj} 批次失败:", r)
        print(f"  {subj}: 写入飞书 {len(todo)} 题 (未匹配 {len(missing)})")
    print(f"\n完成 飞书写入成功{total_ok}题，失败{total_fail}题")

if __name__ == "__main__":
    main()
