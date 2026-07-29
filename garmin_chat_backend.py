#!/usr/bin/env python3
"""
追风计划 AI 教练后端
- 直接导入 garmin_cn_mcp 的工具函数读取 Garmin 中国区数据
- 提供简单的中文关键词路由
- 被 Node 开发服务器代理到 /api/garmin/*
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

# ─── 路径与凭据 ───────────────────────────────────────────────────
GARMIN_MCP_DIR = Path("C:/Users/mushr/WorkBuddy/2026-07-29-08-59-10/garmin-cn-mcp")
sys.path.insert(0, str(GARMIN_MCP_DIR))


def _load_credentials():
    """从 ~/.workbuddy/mcp.json 读取 garmin-cn 凭据"""
    mcp_path = Path.home() / ".workbuddy" / "mcp.json"
    if mcp_path.exists():
        cfg = json.loads(mcp_path.read_text(encoding="utf-8"))
        svr = cfg.get("mcpServers", {}).get("garmin-cn", {})
        env = svr.get("env", {})
        for k in ["GARMIN_CN_EMAIL", "GARMIN_CN_PASSWORD", "GARMIN_EMAIL", "GARMIN_PASSWORD"]:
            v = env.get(k) or os.environ.get(k)
            if v and not os.environ.get(k):
                os.environ[k] = v


_load_credentials()

# 把 token 缓存改到临时目录，避免 WorkBuddy 沙箱对个人目录文件删除的限制
import tempfile
g_token_path = Path(tempfile.gettempdir()) / "garmin_cn_session.json"

# 这里导入会触发登录（如果缓存失效），所以放在凭据加载之后
import garmin_cn_mcp as g
g._token_file = g_token_path
g._token_dir = g_token_path.parent


# ─── 工具 ─────────────────────────────────────────────────────────
def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _days_ago(n):
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


def _parse_date(msg, default_offset=1):
    """从中文消息里解析日期，默认昨天"""
    msg = msg.lower()
    if "前天" in msg:
        return _days_ago(2)
    if "昨天" in msg or "昨晚" in msg:
        return _days_ago(1)
    if "今天" in msg:
        return _today()
    m = re.search(r"(\d+)\s*天[前以]?", msg)
    if m:
        return _days_ago(int(m.group(1)))
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", msg)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return _days_ago(default_offset)


def _parse_days(msg):
    """解析消息中的天数范围"""
    msg = msg.lower()
    if "一周" in msg or "7天" in msg or "七天" in msg or "最近7天" in msg:
        return 7
    if "3天" in msg or "三天" in msg:
        return 3
    if "30天" in msg or "一个月" in msg or "本月" in msg:
        return 30
    m = re.search(r"(\d+)\s*天", msg)
    if m:
        return int(m.group(1))
    return 7


# ─── 格式化器 ─────────────────────────────────────────────────────
def fmt_training_status(data):
    d = json.loads(data) if isinstance(data, str) else data
    if not isinstance(d, dict):
        return "📊 训练状态数据格式异常"
    status_data = d.get("mostRecentTrainingStatus", {})
    devices = status_data.get("latestTrainingStatusData", {}) if isinstance(status_data, dict) else {}
    # 取第一个设备
    device_status = next(iter(devices.values()), {}) if isinstance(devices, dict) else {}
    feedback = device_status.get("trainingStatusFeedbackPhrase", "")
    sport = device_status.get("sport", "")
    acute = device_status.get("acuteTrainingLoadDTO", {}) or {}

    vo2_data = d.get("mostRecentVO2Max", {})
    generic_vo2 = vo2_data.get("generic", {}) if isinstance(vo2_data, dict) else {}

    load_balance = d.get("mostRecentTrainingLoadBalance", {})
    balance_map = load_balance.get("metricsTrainingLoadBalanceDTOMap", {}) if isinstance(load_balance, dict) else {}
    balance = next(iter(balance_map.values()), {}) if isinstance(balance_map, dict) else {}

    lines = ["📊 训练状态"]
    if feedback:
        lines.append(f"- 当前状态：{feedback} ({sport})")
    if acute:
        lines.append(f"- 急性负荷：{acute.get('dailyTrainingLoadAcute', '未知')} / 慢性负荷：{acute.get('dailyTrainingLoadChronic', '未知')}")
        lines.append(f"- 急慢性比值：{acute.get('dailyAcuteChronicWorkloadRatio', '未知')} ({acute.get('acwrStatus', '')})")
    if generic_vo2:
        lines.append(f"- VO2 Max：{generic_vo2.get('vo2MaxValue', '未知')} ml/kg/min")
    if balance:
        lines.append(f"- 有氧低强度：{balance.get('monthlyLoadAerobicLow', 0):.0f} (目标 {balance.get('monthlyLoadAerobicLowTargetMin', 0)}-{balance.get('monthlyLoadAerobicLowTargetMax', 0)})")
        lines.append(f"- 有氧高强度：{balance.get('monthlyLoadAerobicHigh', 0):.0f} (目标 {balance.get('monthlyLoadAerobicHighTargetMin', 0)}-{balance.get('monthlyLoadAerobicHighTargetMax', 0)})")
    if len(lines) == 1:
        lines.append("- 暂无详细训练状态数据")
    return "\n".join(lines)


def fmt_training_readiness(data):
    d = json.loads(data) if isinstance(data, str) else data
    # 实际返回可能是列表或字典
    if isinstance(d, list) and d:
        readiness = d[0]
    elif isinstance(d, dict):
        readiness = d
    else:
        readiness = {}
    score = readiness.get("score", "未知")
    feedback = readiness.get("feedbackShort", "")
    level = readiness.get("level", "")
    lines = [f"🎯 训练准备度：{score}/100 {feedback} ({level})".replace("  ()", "").replace("()", "").strip()]
    rt = readiness.get("recoveryTime")
    if rt is not None:
        lines.append(f"- 恢复时间：约 {rt} 小时")
    sleep_score = readiness.get("sleepScore")
    if sleep_score is not None:
        lines.append(f"- 睡眠得分：{sleep_score}")
    acute = readiness.get("acuteLoad")
    if acute is not None:
        lines.append(f"- 急性负荷：{acute}")
    return "\n".join(lines)


def _mins(v):
    return (v or 0) // 60

def fmt_sleep(data, date):
    d = json.loads(data) if isinstance(data, str) else data
    sleep = d.get("dailySleepDTO", {}) or {}
    if not sleep or not sleep.get("sleepTimeInSeconds"):
        return f"😴 {date} 暂无睡眠数据（可能手表未同步或当天数据尚未生成）。"
    score = sleep.get("sleepScore", "未知")
    total = sleep.get("sleepTimeInSeconds", 0) or 0
    hours = total // 3600
    mins = (total % 3600) // 60
    deep = _mins(sleep.get("deepSleepSeconds"))
    light = _mins(sleep.get("lightSleepSeconds"))
    rem = _mins(sleep.get("remSleepSeconds"))
    awake = _mins(sleep.get("awakeSleepSeconds"))
    lines = [f"😴 {date} 睡眠数据"]
    lines.append(f"- 睡眠得分：{score}")
    lines.append(f"- 总时长：{hours}小时{mins}分")
    lines.append(f"- 深睡：{deep}分 / 浅睡：{light}分 / REM：{rem}分 / 清醒：{awake}分")
    hr = sleep.get("averageHR") or sleep.get("restingHeartRate")
    if hr:
        lines.append(f"- 平均心率：{hr} bpm")
    return "\n".join(lines)


def fmt_activities(data, days):
    d = json.loads(data) if isinstance(data, str) else data
    if not isinstance(d, list):
        d = []
    if not d:
        return f"🏃 最近 {days} 天没有检测到运动记录。"
    lines = [f"🏃 最近 {days} 天运动记录（共 {len(d)} 条）"]
    for act in d[:10]:
        name = act.get("activityName", "未知")
        t = (act.get("startTimeLocal") or "")[:10]
        dist = act.get("distance") or 0
        dist_km = round(dist / 1000, 2) if dist else 0
        dur = act.get("duration") or 0
        dur_min = round(dur / 60, 1) if dur else 0
        pace = ""
        if dist_km and dur_min:
            pace_sec = dur_min * 60 / dist_km
            pace = f" / 配速 {int(pace_sec//60)}'{int(pace_sec%60):02d}"
        lines.append(f"- {t} {name}：{dist_km} km / {dur_min} 分{pace}")
    return "\n".join(lines)


def fmt_last_activity(data):
    d = json.loads(data) if isinstance(data, str) else data
    if isinstance(d, list) and d:
        d = d[0]
    if not isinstance(d, dict) or "activityId" not in d:
        return "🏃 没有找到最近的运动记录。"
    name = d.get("activityName", "未知")
    t = (d.get("startTimeLocal") or "")[:16].replace("T", " ")
    dist = d.get("distance") or 0
    dist_km = round(dist / 1000, 2) if dist else 0
    dur = d.get("duration") or 0
    dur_min = round(dur / 60, 1) if dur else 0
    avg_hr = d.get("averageHR", "未知")
    lines = [f"🏃 最近一次运动：{name}"]
    lines.append(f"- 时间：{t}")
    lines.append(f"- 距离：{dist_km} km")
    lines.append(f"- 时长：{dur_min} 分")
    lines.append(f"- 平均心率：{avg_hr} bpm")
    return "\n".join(lines)


def fmt_hrv(data, date):
    d = json.loads(data) if isinstance(data, str) else data
    hrv = (d.get("hrvSummary") or {}) if isinstance(d, dict) else {}
    if not hrv:
        return f"💓 {date} 暂无 HRV 数据。"
    avg = hrv.get("avgHrv", "未知")
    last = hrv.get("lastNightAvg", "未知")
    status = hrv.get("status", "未知")
    return f"💓 {date} HRV\n- 平均 HRV：{avg} ms\n- 昨晚平均：{last} ms\n- 状态：{status}"


def fmt_stress(data, date):
    d = json.loads(data) if isinstance(data, str) else data
    stress = (d.get("stressSummary") or {}) if isinstance(d, dict) else {}
    avg = stress.get("avgStressLevel", "未知")
    maxv = stress.get("maxStressLevel", "未知")
    return f"🧘 {date} 压力\n- 平均压力：{avg}\n- 峰值压力：{maxv}"


# ═══════════════════════════════════════════════════════════════════
#  AI 跑步教练：训练计划生成与调整
# ═══════════════════════════════════════════════════════════════════
PLAN_FILE = Path(__file__).parent / "data" / "training_plan.json"


def _load_plan():
    if PLAN_FILE.exists():
        try:
            return json.loads(PLAN_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _save_plan(plan):
    PLAN_FILE.parent.mkdir(parents=True, exist_ok=True)
    PLAN_FILE.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")


def _extract_number(msg, default=None):
    """提取消息中的数字，用于周数、跑量、目标配速等"""
    m = re.search(r"(\d+(?:\.\d+)?)", msg)
    return float(m.group(1)) if m else default


def _parse_goal(msg):
    """识别目标赛事/距离"""
    msg = msg.lower()
    if any(k in msg for k in ["全马", "马拉松", "42", "42.195"]):
        return "全马", 42.195
    if any(k in msg for k in ["半马", "21", "21.0975"]):
        return "半马", 21.0975
    if any(k in msg for k in ["10公里", "10k", "10 km", "十公里"]):
        return "10K", 10
    if any(k in msg for k in ["5公里", "5k", "5 km", "五公里"]):
        return "5K", 5
    return "健康跑", None


def _parse_pace(msg):
    """解析目标配速，如 5:30、430"""
    m = re.search(r"(\d+)\s*[:'：]\s*(\d{2})", msg)
    if m:
        return f"{int(m.group(1))}:{m.group(2)}"
    m = re.search(r"(\d{3,4})", msg)
    if m:
        p = m.group(1)
        if len(p) == 3:
            return f"{p[0]}:{p[1:]}"
        if len(p) == 4:
            return f"{p[:2]}:{p[2:]}"
    return None


def _estimate_current_weekly_volume():
    """根据最近 7 天跑步记录估算当前周跑量"""
    try:
        data = g.get_activities_by_date(_days_ago(7), _today(), "running")
        acts = json.loads(data) if isinstance(data, str) else data
        if not isinstance(acts, list):
            return 0
        total_km = sum((a.get("distance") or 0) for a in acts) / 1000
        return round(total_km, 1)
    except Exception:
        return 0


def _athlete_snapshot():
    """获取运动员当前状态快照"""
    snapshot = {"date": _today(), "running_volume_7d": _estimate_current_weekly_volume()}
    try:
        readiness_data = g.get_training_readiness(_today())
        readiness = json.loads(readiness_data) if isinstance(readiness_data, str) else readiness_data
        if isinstance(readiness, list) and readiness:
            readiness = readiness[0]
        snapshot["readiness"] = readiness
    except Exception:
        snapshot["readiness"] = {}

    try:
        status_data = g.get_training_status(_today())
        status = json.loads(status_data) if isinstance(status_data, str) else status_data
        snapshot["training_status"] = status
    except Exception:
        snapshot["training_status"] = {}

    try:
        sleep_data = g.get_sleep(_days_ago(1))
        sleep = json.loads(sleep_data) if isinstance(sleep_data, str) else sleep_data
        snapshot["sleep"] = sleep
    except Exception:
        snapshot["sleep"] = {}

    try:
        hrv_data = g.get_hrv(_days_ago(1))
        hrv = json.loads(hrv_data) if isinstance(hrv_data, str) else hrv_data
        snapshot["hrv"] = hrv
    except Exception:
        snapshot["hrv"] = {}

    return snapshot


def _coach_status(snapshot):
    """基于快照给出训练可行性评分与建议"""
    readiness = snapshot.get("readiness") or {}
    sleep = (snapshot.get("sleep") or {}).get("dailySleepDTO", {})
    hrv_summary = (snapshot.get("hrv") or {}).get("hrvSummary", {})
    status = snapshot.get("training_status") or {}

    score = readiness.get("score") or 70
    sleep_score = sleep.get("sleepScore") or 70
    hrv_status = hrv_summary.get("status", "")
    acute = readiness.get("acuteLoad") or 0

    # 尝试从训练状态提取 ACWR
    acwr = None
    try:
        ts_data = status.get("mostRecentTrainingStatus", {})
        devices = ts_data.get("latestTrainingStatusData", {}) if isinstance(ts_data, dict) else {}
        device_status = next(iter(devices.values()), {}) if isinstance(devices, dict) else {}
        acute_dto = device_status.get("acuteTrainingLoadDTO", {}) or {}
        acwr = acute_dto.get("dailyAcuteChronicWorkloadRatio")
    except Exception:
        pass

    if score >= 80 and sleep_score >= 75 and hrv_status in ("BALANCED", "HIGH"):
        level = "green"
        advice = "状态良好，可以按计划执行训练，必要时可适度加量。"
    elif score >= 60 and sleep_score >= 60:
        level = "yellow"
        advice = "状态一般，建议维持原计划或轻度减量，避免高强度间歇。"
    else:
        level = "red"
        advice = "状态欠佳，建议今天休息、做低强度恢复跑或交叉训练。"

    if acwr and acwr > 1.5:
        level = "red"
        advice += " 注意：急慢性负荷比偏高，近期受伤风险增加，务必减量。"
    elif acwr and acwr < 0.7:
        advice += " 提示：训练刺激不足，可以考虑适当增加跑量。"

    return {
        "level": level,
        "readiness_score": score,
        "sleep_score": sleep_score,
        "hrv_status": hrv_status,
        "acwr": acwr,
        "advice": advice,
    }


def _session_type_for_day(day_index, phase, goal, week):
    """day_index: 0=周一, 6=周日"""
    if day_index in (0, 4):  # 周一、周五
        return "休息/交叉训练", 0, "休息或瑜伽/力量训练"
    if day_index == 2:  # 周三
        if phase in ("提升期", "巅峰期"):
            return "节奏跑", 8, "乳酸阈值节奏跑，体感约「舒适偏累」"
        return "轻松跑", 6, "放松慢跑，心率不超过最大心率的75%"
    if day_index == 5:  # 周六
        return "轻松跑", 5, "恢复性慢跑"
    if day_index == 1:  # 周二
        if phase in ("提升期", "巅峰期") and goal in ("5K", "10K", "半马"):
            return "间歇跑", 8, "如 8×400m 或 6×800m，组间慢跑恢复"
        return "轻松跑", 5, "慢跑"
    if day_index == 3:  # 周四
        if phase == "减量期":
            return "轻松跑", 5, "保持轻松"
        return "轻松跑", 6, "有氧慢跑"
    # 周日 LSD
    if goal == "全马":
        return "长距离慢跑", 12 + week, "LSD，心率一区到二区下限"
    if goal == "半马":
        return "长距离慢跑", 8 + week * 0.5, "LSD"
    if goal == "10K":
        return "长距离慢跑", 7 + week * 0.3, "LSD"
    return "长距离慢跑", 5 + week * 0.2, "LSD"


def _build_week_sessions(week, phase, weekly_km, goal, start_date):
    """生成一周课表"""
    sessions = []
    # 强度日占比：周二、周三、周日占主要跑量
    # 简单分配：周日 30%，周三 15%，周二/周四 各 15%，周六 10%
    if goal in ("全马", "半马"):
        weights = [0, 0.12, 0.15, 0.15, 0, 0.10, 0.30]  # 周一到周日
    elif goal in ("10K", "5K"):
        weights = [0, 0.18, 0.15, 0.12, 0, 0.10, 0.25]
    else:
        weights = [0, 0.10, 0.15, 0.10, 0, 0.15, 0.25]

    total_running = weekly_km * 0.95  # 留 5% 给浮动
    day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

    for i, w in enumerate(weights):
        date = (start_date + timedelta(days=(week - 1) * 7 + i)).strftime("%Y-%m-%d")
        if w == 0:
            sessions.append({
                "date": date,
                "week": week,
                "day": day_names[i],
                "phase": phase,
                "type": "休息",
                "distance": 0,
                "duration": 0,
                "intensity": "低",
                "note": "休息或做力量/拉伸/交叉训练",
                "completed": False,
                "adjusted": False,
            })
            continue
        session_type, intensity_score, note = _session_type_for_day(i, phase, goal, week)
        dist = round(total_running * w, 1)
        # 估算时长：轻松跑 6:30/km，节奏 5:30/km，间歇 5:00/km
        pace_map = {"轻松跑": 6.5, "长距离慢跑": 6.8, "节奏跑": 5.5, "间歇跑": 5.0}
        duration = int(dist * pace_map.get(session_type, 6.0))
        intensity = "高" if session_type in ("间歇跑", "节奏跑") else ("中" if session_type == "长距离慢跑" else "低")
        sessions.append({
            "date": date,
            "week": week,
            "day": day_names[i],
            "phase": phase,
            "type": session_type,
            "distance": dist,
            "duration": duration,
            "intensity": intensity,
            "note": note,
            "completed": False,
            "adjusted": False,
        })
    return sessions


def generate_training_plan(goal, target_distance, target_date=None, weekly_volume=None, weeks=None):
    """生成新的训练计划"""
    snapshot = _athlete_snapshot()
    current_vol = snapshot.get("running_volume_7d", 0)

    if not weekly_volume:
        if target_distance:
            # 基于目标距离给一个默认周跑量
            vol_map = {42.195: 50, 21.0975: 35, 10: 25, 5: 20}
            weekly_volume = vol_map.get(target_distance, 30)
        else:
            weekly_volume = max(20, current_vol * 1.2)

    if not weeks:
        if target_date:
            delta = (datetime.strptime(target_date, "%Y-%m-%d").date() - datetime.now().date()).days
            weeks = max(4, delta // 7)
        else:
            weeks = 12

    # 起步周跑量：取当前 7 天跑量和目标 60% 的较大值，但不超过目标
    start_volume = min(max(current_vol, weekly_volume * 0.5), weekly_volume * 0.8)
    if start_volume < 5:
        start_volume = weekly_volume * 0.5

    today = datetime.now().date()
    # 找到下周一作为计划开始日
    start_date = today + timedelta(days=(7 - today.weekday()) % 7)

    plan_days = []
    for week in range(1, weeks + 1):
        # 周期划分
        if week <= weeks * 0.55:
            phase = "基础期"
            vol = start_volume + (weekly_volume - start_volume) * (week / (weeks * 0.55))
        elif week <= weeks * 0.80:
            phase = "提升期"
            vol = weekly_volume * (1 + 0.08 * ((week - weeks * 0.55) / (weeks * 0.25)))
        elif week <= weeks * 0.92:
            phase = "巅峰期"
            vol = weekly_volume * 0.95
        else:
            phase = "减量期"
            vol = weekly_volume * (0.65 - 0.25 * ((week - weeks * 0.92) / (weeks * 0.08)))

        # 每 4 周一个恢复周
        if week % 4 == 0 and phase != "减量期":
            phase = "恢复周"
            vol *= 0.75

        plan_days.extend(_build_week_sessions(week, phase, round(vol, 1), goal, start_date))

    plan = {
        "id": f"plan-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "created_at": _today(),
        "updated_at": _today(),
        "goal": goal,
        "target_distance": target_distance,
        "target_date": target_date,
        "target_weekly_volume": weekly_volume,
        "weeks": weeks,
        "current_week": 1,
        "snapshot": snapshot,
        "days": plan_days,
    }
    _save_plan(plan)
    return plan


def adjust_training_plan():
    """基于最新数据调整当前计划未来未完成的训练"""
    plan = _load_plan()
    if not plan:
        return None

    snapshot = _athlete_snapshot()
    status = _coach_status(snapshot)

    today_str = _today()
    adjusted_count = 0
    for day in plan.get("days", []):
        if day.get("completed") or day.get("date") < today_str:
            continue
        # 如果状态红色，未来高强度日改为轻松跑或休息
        if status["level"] == "red":
            if day.get("type") in ("间歇跑", "节奏跑"):
                day["type"] = "轻松跑"
                day["intensity"] = "低"
                day["note"] = f"（已调整：{status['advice']}）原内容改为轻松跑"
                day["adjusted"] = True
                adjusted_count += 1
            elif day.get("type") == "长距离慢跑" and day.get("distance", 0) > 10:
                day["distance"] = round(day["distance"] * 0.6, 1)
                day["duration"] = int(day["duration"] * 0.6)
                day["note"] = f"（已调整：{status['advice']}）LSD 减量"
                day["adjusted"] = True
                adjusted_count += 1
        # 如果状态黄色，高强度日减量
        elif status["level"] == "yellow":
            if day.get("type") in ("间歇跑", "节奏跑"):
                day["distance"] = round(day["distance"] * 0.8, 1)
                day["duration"] = int(day["duration"] * 0.8)
                day["note"] = f"（已调整：{status['advice']}）强度课减量"
                day["adjusted"] = True
                adjusted_count += 1

    plan["updated_at"] = today_str
    plan["latest_status"] = status
    _save_plan(plan)
    return {"plan": plan, "status": status, "adjusted_count": adjusted_count}


def fmt_plan(plan):
    """把计划格式化为聊天回复"""
    if not plan:
        return "还没有训练计划。可以对我说「帮我制定一个 12 周全马计划」开始。"
    lines = [f"📋 训练计划：{plan.get('goal', '健康跑')}"]
    if plan.get("target_date"):
        lines.append(f"- 目标日期：{plan['target_date']}")
    lines.append(f"- 周期：{plan.get('weeks')} 周 / 当前第 {plan.get('current_week')} 周")
    lines.append(f"- 目标周跑量：{plan.get('target_weekly_volume')} km")

    today_str = _today()
    # 显示本周和未来一周课表
    future = [d for d in plan.get("days", []) if d.get("date") >= today_str][:14]
    if future:
        lines.append("\n🏃 接下来两周课表：")
        for d in future:
            mark = "✅" if d.get("completed") else ("✏️" if d.get("adjusted") else "•")
            if d.get("type") == "休息":
                lines.append(f"{mark} {d['date']} {d['day']}：休息")
            else:
                lines.append(f"{mark} {d['date']} {d['day']}：{d['type']} {d['distance']}km / {d['duration']}分 [{d['intensity']}]")
    return "\n".join(lines)


def coach_plan_advice():
    """生成一句针对当前计划的综合建议"""
    plan = _load_plan()
    snapshot = _athlete_snapshot()
    status = _coach_status(snapshot)

    lines = ["📊 当前状态评估"]
    lines.append(f"- 训练准备度：{status['readiness_score']}/100")
    lines.append(f"- 睡眠得分：{status['sleep_score']}")
    if status.get("acwr"):
        lines.append(f"- 急慢性负荷比：{status['acwr']:.2f}")
    lines.append(f"\n💡 教练建议：{status['advice']}")

    if plan:
        today_str = _today()
        today_session = next((d for d in plan.get("days", []) if d.get("date") == today_str), None)
        if today_session:
            if status["level"] == "red":
                lines.append(f"\n⚠️ 今天的课表是「{today_session['type']} {today_session['distance']}km」，建议改为休息或轻松恢复跑。")
            elif status["level"] == "yellow":
                lines.append(f"\n📅 今天的课表「{today_session['type']} {today_session['distance']}km」建议减量到 70% 执行。")
            else:
                lines.append(f"\n📅 今天的课表「{today_session['type']} {today_session['distance']}km」可以按计划完成。")

    return "\n".join(lines)


# ─── 路由 ─────────────────────────────────────────────────────────
def route(message):
    msg = message.lower()

    # ── 训练计划类意图 ──
    if (any(k in msg for k in ["制定计划", "生成计划", "做计划", "来一份计划", "新建计划"]) or
            ("制定" in msg and "计划" in msg) or ("生成" in msg and "训练" in msg)):
        goal, distance = _parse_goal(message)
        target_date = None
        m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", message)
        if m:
            target_date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        weeks = int(_extract_number(message)) if re.search(r"\d+\s*周", message) else None
        weekly_volume = _extract_number(message) if re.search(r"周跑量|每周|km", message) else None
        plan = generate_training_plan(goal, distance, target_date, weekly_volume, weeks)
        return {"tool": "generate_plan", "reply": fmt_plan(plan), "data": plan}

    if (any(k in msg for k in ["调整计划", "修改计划", "更新计划", "根据状态调整"]) or
            ("调整" in msg and "训练" in msg) or ("修改" in msg and "训练" in msg)):
        result = adjust_training_plan()
        if result is None:
            return {"tool": "adjust_plan", "reply": "还没有训练计划，先制定一个吧。", "data": None}
        reply = coach_plan_advice() + "\n\n" + fmt_plan(result["plan"])
        return {"tool": "adjust_plan", "reply": reply, "data": result}

    if any(k in msg for k in ["查看计划", "当前计划", "课表", "训练计划"]):
        plan = _load_plan()
        reply = coach_plan_advice() + "\n\n" + fmt_plan(plan)
        return {"tool": "get_plan", "reply": reply, "data": plan}

    if any(k in msg for k in ["今天怎么跑", "今天训练", "今天跑什么", "今天课表", "今天安排"]):
        plan = _load_plan()
        snapshot = _athlete_snapshot()
        status = _coach_status(snapshot)
        today_str = _today()
        today_session = next((d for d in plan.get("days", []) if d.get("date") == today_str), None) if plan else None
        lines = [f"💡 教练建议：{status['advice']}"]
        if today_session:
            if today_session.get("type") == "休息":
                lines.append(f"\n📅 今天（{today_str}）课表：休息。{status['advice']}")
            else:
                lines.append(f"\n📅 今天（{today_str}）课表：{today_session['type']} {today_session['distance']}km / {today_session['duration']}分")
                if status["level"] == "red":
                    lines.append("⚠️ 当前状态欠佳，建议改为休息或轻松恢复跑。")
                elif status["level"] == "yellow":
                    lines.append("🟡 状态一般，建议按课表 70% 左右执行。")
                else:
                    lines.append("✅ 状态良好，可以按计划完成。")
        else:
            lines.append(f"\n📅 今天没有安排课表。当前 7 天跑量约 {snapshot.get('running_volume_7d', 0)} km。")
        return {"tool": "today_plan", "reply": "\n".join(lines), "data": {"status": status, "session": today_session}}

    if any(k in msg for k in ["睡眠", "睡得", "昨晚"]):
        date = _parse_date(message, 1)
        data = g.get_sleep(date)
        return {"tool": "get_sleep", "reply": fmt_sleep(data, date), "data": json.loads(data)}

    if any(k in msg for k in ["准备度", "训练准备", "今天怎么跑", "今天该"]):
        date = _parse_date(message, 0)
        data = g.get_training_readiness(date)
        return {"tool": "get_training_readiness", "reply": fmt_training_readiness(data), "data": json.loads(data)}

    if any(k in msg for k in ["训练状态", "训练负荷", "恢复", "vo2", "最大摄氧量"]):
        date = _parse_date(message, 0)
        data = g.get_training_status(date)
        return {"tool": "get_training_status", "reply": fmt_training_status(data), "data": json.loads(data)}

    if any(k in msg for k in ["最近一次", "最近运动", "上次跑", "刚刚跑"]):
        data = g.get_last_activity()
        return {"tool": "get_last_activity", "reply": fmt_last_activity(data), "data": json.loads(data)}

    if any(k in msg for k in ["活动", "跑步", "骑行", "运动记录", "配速", "跑量"]):
        days = _parse_days(message)
        start = _days_ago(days)
        end = _today()
        data = g.get_activities_by_date(start, end, "running" if "跑步" in msg or "配速" in msg or "跑量" in msg else "")
        return {"tool": "get_activities_by_date", "reply": fmt_activities(data, days), "data": json.loads(data)}

    if any(k in msg for k in ["hrv", "心率变异"]):
        date = _parse_date(message, 1)
        data = g.get_hrv(date)
        return {"tool": "get_hrv", "reply": fmt_hrv(data, date), "data": json.loads(data)}

    if any(k in msg for k in ["压力"]):
        date = _parse_date(message, 0)
        data = g.get_stress(date)
        return {"tool": "get_stress", "reply": fmt_stress(data, date), "data": json.loads(data)}

    if any(k in msg for k in ["设备", "手表", "手环"]):
        data = g.get_devices()
        return {"tool": "get_devices", "reply": "⌚ 已绑定设备信息如下：", "data": json.loads(data)}

    if any(k in msg for k in ["徽章", "成就"]):
        data = g.get_earned_badges()
        return {"tool": "get_earned_badges", "reply": "🏅 徽章成就信息如下：", "data": json.loads(data)}

    if any(k in msg for k in ["装备", "跑鞋", "自行车"]):
        data = g.get_gear()
        return {"tool": "get_gear", "reply": "🎽 装备信息如下：", "data": json.loads(data)}

    if any(k in msg for k in ["资料", "profile", "个人"]):
        data = g.get_profile()
        return {"tool": "get_profile", "reply": "👤 用户资料如下：", "data": json.loads(data)}

    return {
        "tool": None,
        "reply": "我不太确定你想查什么。可以问我：\n- 我昨晚睡得怎么样？\n- 最近7天跑步记录\n- 今天训练准备度如何？\n- 最近训练负荷和恢复\n- 我的HRV/压力/血氧",
        "data": None,
    }


# ─── HTTP 服务 ────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # 保持简洁
        print(f"[garmin-backend] {format % args}")

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            return self._send_json({"ok": True, "service": "garmin-cn-ai-coach"})
        self._send_json({"error": "Not Found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/chat":
            return self._send_json({"error": "Not Found"}, 404)

        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return self._send_json({"error": "Empty body"}, 400)
        raw = self.rfile.read(length)
        # 兼容不同客户端编码（浏览器发 UTF-8，部分命令行可能发 GBK）
        for enc in ("utf-8", "gbk", "gb2312", "latin-1"):
            try:
                body = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            body = raw.decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return self._send_json({"error": "Invalid JSON"}, 400)

        message = payload.get("message", "").strip()
        if not message:
            return self._send_json({"error": "message required"}, 400)

        try:
            result = route(message)
            result["ok"] = True
            self._send_json(result)
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)}, 500)


def main():
    port = int(os.environ.get("GARMIN_BACKEND_PORT", "8787"))
    host = os.environ.get("GARMIN_BACKEND_HOST", "127.0.0.1")
    with ThreadingHTTPServer((host, port), Handler) as server:
        print(f"[garmin-backend] 已启动 http://{host}:{port}")
        server.serve_forever()


if __name__ == "__main__":
    main()
