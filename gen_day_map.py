# -*- coding: utf-8 -*-
"""依据学习计划，把每道题(题目ID)分配到具体「天数」，产出：
   data/day_map.json  -> { "题目ID": day }
   data/day_meta.json -> [{day,date,weekday,label,total,spans:[{subject,count}]}]
与 gen_plan.py 使用完全一致的科目顺序与每日题量分配，确保一一对应。
"""
import json, os, datetime

DATA = r"D:\测试\data"
OUT_MAP = os.path.join(DATA, "day_map.json")
OUT_META = os.path.join(DATA, "day_meta.json")

# 与 gen_plan.py 完全一致的科目顺序（实体法优先）
SUBJECT_FILES = [
    ("行政法", "questions.行政法.json"),
    ("商经知", "questions.商经知.json"),
    ("理论法", "questions.理论法.json"),
    ("三国法", "questions.三国法.json"),
    ("刑事诉讼法", "questions.刑事诉讼法.json"),
    ("民诉", "questions.民诉.json"),
]

START = datetime.date(2026, 8, 9)
END = datetime.date(2026, 8, 30)
N_DAYS = (END - START).days + 1  # 22
WD = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# 预载各科目题目（保持文件内顺序），仅纳入「可刷题」集合：
# 与站点/接口一致 —— 有题目ID + 有题干 + (无状态 或 状态=已发布)
def serveable(arr):
    return [
        q for q in arr
        if q.get("题目ID") and q.get("题干")
        and (not q.get("状态") or q.get("状态") == "已发布")
    ]

qs_by_subj = {}
TOTAL = 0
for s, f in SUBJECT_FILES:
    path = os.path.join(DATA, f)
    data = json.load(open(path, encoding="utf-8"))
    if isinstance(data, dict):
        # 注意：空列表 [] 为假值，必须显式判断 None，不能让它 fallback 到 values()[0]
        arr = data.get("questions")
        if arr is None:
            arr = data.get("items") or []
        data = arr
    qs_by_subj[s] = serveable(data)
    TOTAL += len(qs_by_subj[s])

SUBJ_ORDER = [s for s, _ in SUBJECT_FILES]

# 每日题量：Day1=80 轻量上手，其余 21 天均摊剩余 -> ~94/天
caps = [80]
rem = TOTAL - 80
n = N_DAYS - 1
base, extra = divmod(rem, n)
for i in range(n):
    caps.append(base + (1 if i < extra else 0))
assert sum(caps) == TOTAL, (sum(caps), TOTAL)

day_map = {}
day_meta = []
subj_done = {s: 0 for s in SUBJ_ORDER}
subj_idx = 0

for di in range(N_DAYS):
    cap = caps[di]
    spans = []
    left = cap
    while left > 0:
        s = SUBJ_ORDER[subj_idx]
        qlist = qs_by_subj[s]
        done = subj_done[s]
        take = min(left, len(qlist) - done)
        if take <= 0:
            subj_done[s] = len(qlist)
            subj_idx += 1
            continue
        for k in range(done, done + take):
            q = qlist[k]
            qid = q.get("题目ID") or q.get("id") or q.get("题目id")
            if qid:
                day_map[str(qid)] = di + 1
        subj_done[s] += take
        spans.append({"subject": s, "count": take})
        left -= take
    d = START + datetime.timedelta(days=di)
    label = "Day%d · " % (di + 1) + " + ".join(f"{sp['subject']}{sp['count']}" for sp in spans)
    day_meta.append({
        "day": di + 1, "date": d.isoformat(), "weekday": WD[d.weekday()],
        "label": label, "total": cap, "spans": spans,
    })

# 校验
assigned = len(day_map)
assert assigned == TOTAL, f"分配题数 {assigned} != {TOTAL}"
per_day = {}
for v in day_map.values():
    per_day[v] = per_day.get(v, 0) + 1
for di in range(N_DAYS):
    assert per_day.get(di + 1, 0) == caps[di], (di + 1, per_day.get(di + 1), caps[di])

json.dump(day_map, open(OUT_MAP, "w", encoding="utf-8"), ensure_ascii=False)
json.dump(day_meta, open(OUT_META, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

print("OK ->", OUT_MAP, OUT_META)
print("分配题数:", assigned, "| 天数:", N_DAYS)
print("样例 day_meta[4]:", day_meta[4])
print("day_map 样本:", list(day_map.items())[:3])
