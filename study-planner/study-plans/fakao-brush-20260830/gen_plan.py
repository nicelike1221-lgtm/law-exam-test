# -*- coding: utf-8 -*-
"""生成「法考题库 8/30 前刷一遍」逐时学习计划 (plan.json + plan.md)"""
import json, datetime, os

OUT = os.path.dirname(os.path.abspath(__file__))
PLAN_ID = "fakao-brush-20260830"

# ---- 题库可刷题题量（来自本地 JSON, 仅含「已发布」=站点实际可刷，2026-08-09 校准后）----
# 草稿 159 道（行政法76/三国法77/商经知6）题干或选项残缺，保持草稿不计入
SUBJECTS = [  # 实体法优先：先实体法后程序法
    ("行政法", 334),    # 410 - 76草稿
    ("商经知", 458),    # 464 - 6草稿
    ("理论法", 516),
    ("三国法", 272),    # 349 - 77草稿
    ("刑事诉讼法", 370),
    ("民诉", 113),
]
TOTAL = sum(c for _, c in SUBJECTS)  # 2063

START = datetime.date(2026, 8, 9)
END = datetime.date(2026, 8, 30)
N_DAYS = (END - START).days + 1  # 22

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# ---- 每天题量分配 ----
# Day1(8/9) 上手 80 题；其余 21 天均摊（与 day_map.json 下拉框口径一致）
caps = [80]
rem = TOTAL - 80  # 1983
n = N_DAYS - 1
base, extra = divmod(rem, n)  # base=94, extra=9
for i in range(n):
    caps.append(base + (1 if i < extra else 0))
assert sum(caps) == TOTAL, (sum(caps), TOTAL)

# ---- 顺序把题量映射到每天，标注科目区间 ----
def build_day_spans(cap):
    spans = []
    left = cap
    while left > 0:
        s, cnt = SUBJECTS[build_day_spans.idx]
        take = min(left, cnt - build_day_spans.done[s])
        build_day_spans.done[s] += take
        if build_day_spans.done[s] >= cnt:
            build_day_spans.idx += 1
        spans.append((s, take))
        left -= take
    return spans

build_day_spans.idx = 0
build_day_spans.done = {s: 0 for s, _ in SUBJECTS}

dates = [START + datetime.timedelta(days=i) for i in range(N_DAYS)]
daily = []
for i, d in enumerate(dates):
    cap = caps[i]
    spans = build_day_spans(cap)
    daily.append({
        "day_index": i + 1,
        "date": d.isoformat(),
        "weekday": WEEKDAY_CN[d.weekday()],
        "is_sunday": d.weekday() == 6,
        "capacity": cap,
        "spans": spans,
    })

# ---- 阶段划分（按科目组）----
# 阶段一 实体法：行政法+商经知+理论法
# 阶段二 程序法：三国法+刑诉+民诉
# 计算每科结束日
done2 = {s: 0 for s, _ in SUBJECTS}
subj_end_day = {}
for day in daily:
    for s, take in day["spans"]:
        done2[s] += take
        if done2[s] >= dict(SUBJECTS)[s] and s not in subj_end_day:
            subj_end_day[s] = day["day_index"]

ent_end = subj_end_day["理论法"]
stages = [
    {
        "name": "阶段一 · 实体法（理解型，优先突破）",
        "subjects": "行政法 → 商经知 → 理论法",
        "range": f"Day1(8/9) – Day{ent_end}({dates[ent_end-1].isoformat()})",
        "pace": "正常",
        "milestone": "实体法 1308 题全部过完一遍，标记出易错点",
    },
    {
        "name": "阶段二 · 程序法（记忆型，集中刷）",
        "subjects": "三国法 → 刑事诉讼法 → 民诉",
        "range": f"Day{ent_end+1} – Day{subj_end_day['民诉']}({dates[subj_end_day['民诉']-1].isoformat()})",
        "pace": "正常",
        "milestone": "程序法 755 题过完，全库 2063 题覆盖完成（8/30 达成一遍）",
    },
]
closing_note = (
    "**收尾说明**：全库 2063 题（已发布）在 Day22（8/30）刚好刷完一遍，无独立复盘窗口。另有 159 道草稿题因题干/选项残缺保持草稿、不计入本轮。"
    "二刷安排在「每日 15min 复盘」中持续进行（复看前日★题）；"
    "若某天提前完成，用余量二刷当日★题。8/30 后可导出★题清单做专项突破。"
)

# ---- 生成每日 hourly 任务 ----
def fmt_spans(spans):
    parts = []
    for s, take in spans:
        parts.append(f"{s} {take}题")
    return " + ".join(parts)

daily_tasks = []
for day in daily:
    d = day["date"]
    wd = day["weekday"]
    cap = day["capacity"]
    sunday = day["is_sunday"]
    tasks = []
    half = cap // 2
    a_cnt = half
    b_cnt = cap - half
    span_txt = fmt_spans(day["spans"])
    # 模块A 09:00–11:00
    tasks.append({
        "title": f"模块A · 刷题 ({a_cnt}题) ｜ {span_txt}",
        "start": "09:00", "end": "11:00", "duration_min": 120,
        "type": "刷题", "checkable": True,
        "methodology_tip": "番茄法：2h = 4 个 25+5；每题先自己选，再对答案，错题立即标★",
    })
    # 午休提示
    # 模块B 14:00 起（所有天统一 4h 预算：A 120 + B 105 + 复盘 15）
    b_dur = 105
    rev_dur = 15
    if sunday:
        rev_tip = "费曼输出：挑本周 3 个易错考点讲给自己听，并艾宾浩斯复看昨日★题（15min 内完成）"
    else:
        rev_tip = "艾宾浩斯 D-1：复看昨日标记的★题，没懂的回看解析/考点"
    tasks.append({
        "title": f"模块B · 刷题 ({b_cnt}题) ｜ {span_txt}",
        "start": "14:00", "end": "15:45", "duration_min": b_dur,
        "type": "刷题", "checkable": True,
        "methodology_tip": "多选/任选题慢一点：先排除明显错误项，再核对答案逻辑",
    })
    tasks.append({
        "title": "当日复盘",
        "start": "15:45", "end": "16:00", "duration_min": rev_dur,
        "type": "复盘", "checkable": True,
        "methodology_tip": rev_tip,
    })
    daily_tasks.append({
        "day_index": day["day_index"], "date": d, "weekday": wd,
        "is_sunday": sunday,
        "capacity": cap, "subject_spans": span_txt, "tasks": tasks,
    })

# ---- 写入 plan.json ----
plan = {
    "plan_id": PLAN_ID,
    "goal": "2026-08-30 前把题库核心 6 科可刷题（2063 题，已发布）完整刷一遍",
    "deadline": END.isoformat(),
    "start": START.isoformat(),
    "time_granularity": "hourly",
    "daily_budget_min": 240,
    "total_questions": TOTAL,
    "subjects": {s: c for s, c in SUBJECTS},
    "subject_order": [s for s, _ in SUBJECTS],
    "stages": stages,
    "subj_end_day": subj_end_day,
    "daily_tasks": daily_tasks,
}
with open(os.path.join(OUT, "plan.json"), "w", encoding="utf-8") as f:
    json.dump(plan, f, ensure_ascii=False, indent=2)

# ---- 生成 plan.md ----
def week_of(day):
    # 以周日开头分组（8/9 为周日）
    return (day["day_index"] - 1) // 7 + 1

lines = []
lines.append(f"# 📘 法考题库刷题计划 · 8/30 前刷完一遍\n")
lines.append(f"> 生成于 2026-08-09 ｜ 计划窗口：**2026-08-09 ~ 2026-08-30（{N_DAYS} 天）** ｜ 精度：按小时")
lines.append(f"> 数据源：本地题库 JSON（校准后）。核心 6 科共 **{TOTAL} 题**（民法仅 2 道样例，未全量入库，本轮不计入）。\n")

lines.append("## 一、目标与可行性")
lines.append(f"- **目标**：{plan['goal']}")
lines.append(f"- **每日预算**：4h/天（模块A 2h + 模块B 1h45m + 复盘 15min）")
lines.append(f"- **总量/天数**：{TOTAL} 题 ÷ {N_DAYS} 天 ≈ **{TOTAL//N_DAYS} 题/天**（Day1 轻量 80 题上手，其余日均 ~{base} 题）")
lines.append(f"- **节奏档**：正常（按 4h/天刚好在 8/30 刷完一遍，无额外缓冲；每日余量用于二刷当日★题）")
tot_min = sum(t["duration_min"] for d in daily_tasks for t in d["tasks"])
lines.append(f"- **总投入**：约 {tot_min//60}h（刷题 {tot_min//60}h，含每日复盘）\n")

lines.append("## 二、阶段划分（两阶段）")
for i, st in enumerate(stages, 1):
    lines.append(f"### {st['name']}")
    lines.append(f"- 科目顺序：**{st['subjects']}**")
    lines.append(f"- 时间：**{st['range']}** ｜ 节奏：{st['pace']}")
    lines.append(f"- 里程碑：{st['milestone']}")
lines.append("")
lines.append(closing_note)
lines.append("")

lines.append("## 三、每周目标")
week_goals = {
    1: "实体法启动：行政法为主，建立刷题节奏与错题标记习惯",
    2: "实体法收尾 + 程序法启动：商经知/理论法过半，三国法开刷",
    3: "程序法主力：刑诉 + 民诉，全库覆盖接近完成",
    4: "收尾日：民诉收尾，全库 2063 题一遍达成；二刷转入日常复盘与 8/30 后专项",
}
for w in range(1, 4):
    lines.append(f"- **第{w}周**：{week_goals[w]}")
lines.append(f"- **第4周（收尾）**：{week_goals[4]}")
lines.append("")

lines.append("## 四、每日逐时任务表\n")
cur_week = 0
for d in daily_tasks:
    w = week_of(d)
    if w != cur_week:
        cur_week = w
        lines.append(f"### 🗓 第{w}周（{week_goals.get(w,'')}）")
        lines.append("")
    sun_tag = " · 周日费曼复盘" if d["is_sunday"] else ""
    lines.append(f"**Day{d['day_index']} ｜ {d['date']} {d['weekday']} ｜ {d['capacity']}题{sun_tag}**")
    lines.append(f"- 今日科目：{d['subject_spans']}")
    for t in d["tasks"]:
        lines.append(f"  - `{t['start']}–{t['end']}` **{t['title']}** （{t['duration_min']}min）")
        lines.append(f"    - 💡 {t['methodology_tip']}")
    lines.append("")

lines.append("## 五、学习方法论（贯穿全程）")
lines.append("- **番茄工作法**：每个 2h 模块拆成 4 个 25+5，避免走神。")
lines.append("- **艾宾浩斯间隔复看**：每天复盘 15min 复看「昨日★题」（D-1），周日在复盘中加 费曼输出（讲本周易错考点）。")
lines.append("- **错题标记**：刷完即对答案，错题标★；日常复盘持续二刷★题，8/30 后再做专项突破。")
lines.append("- **二八法则**：先按题量均匀覆盖（保证一遍），阶段三再把时间压到标★的薄弱点。")
lines.append("")
lines.append("## 六、打卡与提醒")
lines.append("- 已设置**每日 08:00 提醒**，早上推送当日任务；连续 2 天未打卡会收到鼓励提醒。")
lines.append("- 打卡方式：告诉我「打卡 / 今天搞定了」，我更新记录并算连续天数。")
lines.append("- 周报：每周日可说「周报」看本周完成率与薄弱项。")
lines.append("")
lines.append("## 七、对照：自己排 vs 用本计划")
lines.append("❌ 大多数人自己排会踩的坑：平均分时间、只排输入不排复盘、计划一出就不再看。")
lines.append("✅ 本计划做了：实体法优先加权、每天嵌入错题复盘、配每日提醒 + 打卡，偏了能及时看见。")

md = "\n".join(lines)
with open(os.path.join(OUT, "plan.md"), "w", encoding="utf-8") as f:
    f.write(md)

print("OK")
print("TOTAL=", TOTAL, "DAYS=", N_DAYS, "caps sum=", sum(caps))
print("subj_end_day=", subj_end_day)
print("milestones:", stages[0]["range"], "|", stages[1]["range"])
print("plan.md bytes=", len(md))
