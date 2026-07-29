#!/usr/bin/env python3
"""
追风计划训练计划 MCP 服务

职责：
- 保存和读取训练计划
- 根据运动员目标生成周期化课表
- 记录实际训练结果
- 读取 Garmin 中国区最新状态并动态调整未来课表

本服务通过 stdio 运行，供 WorkBuddy 的 MCP 连接器调用。
计划文件与网站共用：D:/测试/data/training_plan.json
"""

import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "training-plan",
    instructions=(
        "追风计划训练计划服务。负责创建、查看、记录和动态调整跑步训练计划。"
        "需要动态调整时，优先调用 adjust_plan_from_garmin。"
    ),
)

PLAN_FILE = Path(os.environ.get(
    "TRAINING_PLAN_FILE",
    "D:/测试/data/training_plan.json",
))
GARMIN_MCP_DIR = Path(os.environ.get(
    "GARMIN_MCP_DIR",
    "C:/Users/mushr/WorkBuddy/2026-07-29-08-59-10/garmin-cn-mcp",
))

DAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _today() -> date:
    return date.today()


def _date_text(value: date | str | None) -> str:
    if value is None or value == "":
        return _today().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    value = str(value).strip()
    if value in {"今天", "今日"}:
        return _today().isoformat()
    if value in {"明天", "明日"}:
        return (_today() + timedelta(days=1)).isoformat()
    m = re.fullmatch(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", value)
    if not m:
        raise ValueError("日期格式应为 YYYY-MM-DD")
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def _load_plan() -> dict[str, Any] | None:
    if not PLAN_FILE.exists():
        return None
    try:
        value = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _save_plan(plan: dict[str, Any]) -> None:
    PLAN_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = PLAN_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(PLAN_FILE)


def _goal_distance(goal: str) -> float | None:
    text = (goal or "").lower()
    if any(k in text for k in ("全马", "马拉松", "42k", "42.195")):
        return 42.195
    if any(k in text for k in ("半马", "21k", "21.0975")):
        return 21.0975
    if any(k in text for k in ("10k", "10公里", "十公里")):
        return 10.0
    if any(k in text for k in ("5k", "5公里", "五公里")):
        return 5.0
    return None


def _normal_goal(goal: str, target_distance: float | None) -> str:
    text = (goal or "健康跑").strip()
    distance = target_distance or _goal_distance(text)
    if distance == 42.195:
        return "全马"
    if distance == 21.0975:
        return "半马"
    if distance == 10:
        return "10K"
    if distance == 5:
        return "5K"
    return text or "健康跑"


def _phase(week: int, weeks: int) -> str:
    ratio = week / max(weeks, 1)
    if ratio >= 0.9:
        return "减量期"
    if ratio >= 0.75:
        return "巅峰期"
    if week % 4 == 0:
        return "恢复周"
    if ratio >= 0.45:
        return "提升期"
    return "基础期"


def _session(day_index: int, phase: str, goal: str, week: int, weekly_km: float) -> tuple[str, float, str, str]:
    if day_index in (0, 4):
        return "休息", 0, "低", "休息，或进行轻量拉伸/力量训练"
    if day_index == 1:
        kind = "间歇跑" if phase in ("提升期", "巅峰期") and goal in ("5K", "10K", "半马") else "轻松跑"
        return kind, (weekly_km * (0.16 if kind == "间歇跑" else 0.12)), ("高" if kind == "间歇跑" else "低"), "间歇组间充分慢跑恢复" if kind == "间歇跑" else "轻松慢跑，保持可以交谈"
    if day_index == 2:
        kind = "节奏跑" if phase in ("提升期", "巅峰期") else "轻松跑"
        return kind, weekly_km * (0.14 if kind == "节奏跑" else 0.12), ("高" if kind == "节奏跑" else "低"), "热身后完成节奏段，结束后充分放松" if kind == "节奏跑" else "轻松有氧跑"
    if day_index == 3:
        return "轻松跑", weekly_km * 0.12, "低", "恢复性慢跑，不追求配速"
    if day_index == 5:
        return "轻松跑", weekly_km * 0.10, "低", "短距离轻松跑或休息"
    long_factor = {"全马": 0.30, "半马": 0.27, "10K": 0.25, "5K": 0.22}.get(goal, 0.22)
    return "长距离慢跑", weekly_km * long_factor, "中", "全程控制在轻松有氧强度，结束后补水和进食"


def _build_days(start: date, weeks: int, goal: str, start_km: float, target_km: float) -> list[dict[str, Any]]:
    days: list[dict[str, Any]] = []
    for week in range(1, weeks + 1):
        phase = _phase(week, weeks)
        if week % 4 == 0 and phase not in ("减量期", "恢复周"):
            phase = "恢复周"
        progress = min(1.0, week / max(weeks * 0.55, 1))
        weekly = start_km + (target_km - start_km) * progress
        if phase == "恢复周":
            weekly *= 0.75
        if phase == "减量期":
            weekly *= max(0.45, 0.75 - (week / max(weeks, 1) - 0.9) * 2)
        weekly = round(max(8, weekly), 1)
        for day_index, day_name in enumerate(DAY_NAMES):
            session_type, distance, intensity, note = _session(day_index, phase, goal, week, weekly)
            distance = round(distance, 1)
            pace = 6.5 if session_type == "轻松跑" else 6.8 if session_type == "长距离慢跑" else 5.3
            days.append({
                "date": (start + timedelta(days=(week - 1) * 7 + day_index)).isoformat(),
                "week": week,
                "day": day_name,
                "phase": phase,
                "type": session_type,
                "distance": distance,
                "duration": int(distance * pace),
                "intensity": intensity,
                "note": note,
                "completed": False,
                "adjusted": False,
            })
    return days


def _json_arg(value: str | dict | list | None) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _readiness(snapshot: dict[str, Any]) -> tuple[float, float, str, float | None]:
    readiness = snapshot.get("readiness") or snapshot.get("training_readiness") or {}
    if isinstance(readiness, list):
        readiness = readiness[0] if readiness else {}
    score = float(readiness.get("score") or 70)
    sleep = snapshot.get("sleep") or {}
    sleep_dto = sleep.get("dailySleepDTO", sleep) if isinstance(sleep, dict) else {}
    sleep_score = float(sleep_dto.get("sleepScore") or snapshot.get("sleep_score") or 70)
    hrv = snapshot.get("hrv") or {}
    hrv_summary = hrv.get("hrvSummary", hrv) if isinstance(hrv, dict) else {}
    hrv_status = str(hrv_summary.get("status") or snapshot.get("hrv_status") or "")
    acwr = snapshot.get("acwr")
    if acwr is None:
        status = snapshot.get("training_status") or {}
        try:
            recent = status.get("mostRecentTrainingStatus", {})
            device_map = recent.get("latestTrainingStatusData", {})
            device = next(iter(device_map.values()), {})
            acwr = (device.get("acuteTrainingLoadDTO") or {}).get("dailyAcuteChronicWorkloadRatio")
        except (AttributeError, StopIteration):
            acwr = None
    try:
        acwr = float(acwr) if acwr is not None else None
    except (TypeError, ValueError):
        acwr = None
    return score, sleep_score, hrv_status, acwr


def _adjust_days(plan: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    score, sleep_score, hrv_status, acwr = _readiness(snapshot)
    if score < 60 or sleep_score < 60 or hrv_status.upper() in {"LOW", "UNBALANCED", "POOR"} or (acwr is not None and acwr > 1.5):
        level, reason = "red", "恢复指标偏低或急慢性负荷比偏高"
    elif score < 80 or sleep_score < 75 or (acwr is not None and acwr > 1.3):
        level, reason = "yellow", "恢复状态一般"
    else:
        level, reason = "green", "恢复状态良好"

    changed: list[dict[str, Any]] = []
    today = _today().isoformat()
    for item in plan.get("days", []):
        if item.get("completed") or item.get("date", "") < today:
            continue
        old = item.get("type")
        if level == "red" and old in {"间歇跑", "节奏跑"}:
            item["type"] = "轻松跑"
            item["intensity"] = "低"
            item["distance"] = round(float(item.get("distance") or 0) * 0.65, 1)
            item["duration"] = int(float(item.get("duration") or 0) * 0.65)
            item["note"] = f"动态调整：{reason}，改为轻松恢复跑"
        elif level == "red" and old == "长距离慢跑" and float(item.get("distance") or 0) > 10:
            item["distance"] = round(float(item["distance"]) * 0.7, 1)
            item["duration"] = int(float(item.get("duration") or 0) * 0.7)
            item["note"] = f"动态调整：{reason}，长距离减量"
        elif level == "yellow" and old in {"间歇跑", "节奏跑", "长距离慢跑"}:
            item["distance"] = round(float(item.get("distance") or 0) * 0.8, 1)
            item["duration"] = int(float(item.get("duration") or 0) * 0.8)
            item["note"] = f"动态调整：{reason}，训练量减少 20%"
        else:
            continue
        item["adjusted"] = True
        changed.append({"date": item.get("date"), "from": old, "to": item.get("type"), "distance": item.get("distance"), "note": item.get("note")})

    plan["updated_at"] = _today().isoformat()
    plan["latest_adjustment"] = {"level": level, "reason": reason, "readiness": score, "sleep_score": sleep_score, "hrv_status": hrv_status, "acwr": acwr, "changed_count": len(changed), "at": datetime.now().isoformat(timespec="seconds")}
    return {"level": level, "reason": reason, "readiness": score, "sleep_score": sleep_score, "hrv_status": hrv_status, "acwr": acwr, "changed": changed}


@mcp.tool()
def create_training_plan(goal: str, weeks: int = 12, weekly_km: float = 30, target_date: str = "") -> str:
    """创建跑步训练计划。goal 可填 5K、10K、半马、全马或健康跑；weekly_km 为目标周跑量。"""
    goal = _normal_goal(goal, _goal_distance(goal))
    weeks = max(1, min(int(weeks), 52))
    weekly_km = max(8.0, min(float(weekly_km), 200.0))
    target = _date_text(target_date) if target_date else ""
    today = _today()
    start = today + timedelta(days=(7 - today.weekday()) % 7)
    current = _load_plan()
    current_km = 0.0
    if current:
        current_km = float(current.get("snapshot", {}).get("running_volume_7d") or 0)
    start_km = min(max(current_km, weekly_km * 0.5), weekly_km * 0.8)
    plan = {
        "id": f"plan-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "goal": goal,
        "target_distance": _goal_distance(goal),
        "target_date": target or None,
        "weeks": weeks,
        "target_weekly_volume": weekly_km,
        "current_week": 1,
        "snapshot": {"running_volume_7d": current_km},
        "days": _build_days(start, weeks, goal, start_km, weekly_km),
    }
    _save_plan(plan)
    return json.dumps({"ok": True, "plan": plan}, ensure_ascii=False, indent=2)


@mcp.tool()
def get_training_plan(include_past: bool = False) -> str:
    """读取当前训练计划。默认只返回未过期课程和计划摘要。"""
    plan = _load_plan()
    if not plan:
        return json.dumps({"ok": False, "message": "当前没有训练计划"}, ensure_ascii=False)
    if not include_past:
        today = _today().isoformat()
        plan = {**plan, "days": [d for d in plan.get("days", []) if d.get("date", "") >= today]}
    return json.dumps({"ok": True, "plan": plan}, ensure_ascii=False, indent=2)


@mcp.tool()
def get_today_training(date_text: str = "") -> str:
    """获取指定日期的训练安排，默认获取今天。"""
    date_value = _date_text(date_text)
    plan = _load_plan()
    if not plan:
        return json.dumps({"ok": False, "message": "当前没有训练计划"}, ensure_ascii=False)
    session = next((d for d in plan.get("days", []) if d.get("date") == date_value), None)
    return json.dumps({"ok": True, "date": date_value, "session": session}, ensure_ascii=False, indent=2)


@mcp.tool()
def record_training_result(date_text: str, distance_km: float, duration_min: float, effort: int = 0, notes: str = "") -> str:
    """记录实际训练结果，并标记计划中的对应课程为已完成。effort 为 1-10 的主观用力程度。"""
    date_value = _date_text(date_text)
    plan = _load_plan()
    if not plan:
        return json.dumps({"ok": False, "message": "当前没有训练计划"}, ensure_ascii=False)
    session = next((d for d in plan.get("days", []) if d.get("date") == date_value), None)
    result = {"date": date_value, "distance_km": float(distance_km), "duration_min": float(duration_min), "effort": int(effort or 0), "notes": notes, "recorded_at": datetime.now().isoformat(timespec="seconds")}
    plan.setdefault("results", []).append(result)
    if session:
        session["completed"] = True
        session["actual"] = result
    plan["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _save_plan(plan)
    return json.dumps({"ok": True, "result": result, "matched_session": session}, ensure_ascii=False, indent=2)


@mcp.tool()
def adjust_plan_from_garmin(snapshot_json: str = "") -> str:
    """根据 Garmin 最新训练准备度、睡眠、HRV 和急慢性负荷比动态调整未来课表。

    snapshot_json 可传 Garmin 数据快照 JSON；留空时本工具会直接读取 garmin-cn MCP 同源函数。
    """
    plan = _load_plan()
    if not plan:
        return json.dumps({"ok": False, "message": "当前没有训练计划，请先调用 create_training_plan"}, ensure_ascii=False)
    snapshot = _json_arg(snapshot_json) if snapshot_json else None
    if not isinstance(snapshot, dict):
        sys.path.insert(0, str(GARMIN_MCP_DIR))
        _load_credentials_from_mcp()
        import garmin_cn_mcp as garmin
        snapshot = {}
        try:
            raw = garmin.get_training_readiness(_today().isoformat())
            snapshot["readiness"] = json.loads(raw) if isinstance(raw, str) else raw
        except Exception as exc:
            snapshot["readiness_error"] = str(exc)
        try:
            raw = garmin.get_sleep((_today() - timedelta(days=1)).isoformat())
            snapshot["sleep"] = json.loads(raw) if isinstance(raw, str) else raw
        except Exception as exc:
            snapshot["sleep_error"] = str(exc)
        try:
            raw = garmin.get_hrv((_today() - timedelta(days=1)).isoformat())
            snapshot["hrv"] = json.loads(raw) if isinstance(raw, str) else raw
        except Exception as exc:
            snapshot["hrv_error"] = str(exc)
        try:
            raw = garmin.get_training_status(_today().isoformat())
            snapshot["training_status"] = json.loads(raw) if isinstance(raw, str) else raw
        except Exception as exc:
            snapshot["training_status_error"] = str(exc)
    assessment = _adjust_days(plan, snapshot)
    plan["snapshot"] = snapshot
    _save_plan(plan)
    return json.dumps({"ok": True, "assessment": assessment, "plan": plan}, ensure_ascii=False, indent=2)


def _load_credentials_from_mcp() -> None:
    """从 WorkBuddy MCP 配置读取 Garmin 凭据，仅用于动态调整时读取数据。"""
    path = Path.home() / ".workbuddy" / "mcp.json"
    if not path.exists():
        return
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
        env = cfg.get("mcpServers", {}).get("garmin-cn", {}).get("env", {})
        for key in ("GARMIN_CN_EMAIL", "GARMIN_CN_PASSWORD", "GARMIN_EMAIL", "GARMIN_PASSWORD"):
            if env.get(key) and not os.environ.get(key):
                os.environ[key] = env[key]
    except Exception:
        return


if __name__ == "__main__":
    mcp.run(transport="stdio")
