"""Calendar and durable limits for monthly maintenance."""
import calendar
from datetime import datetime, timedelta, timezone
import os
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("America/Chicago")


class DeadlinePassed(Exception):
    """Stop without treating an expired window as a rejected PR repair."""


def clock():
    return datetime.now(timezone.utc)


def window(at=None):
    local = (at or clock()).astimezone(ZONE)
    day = min(30, calendar.monthrange(local.year, local.month)[1])
    start = local.replace(day=day, hour=1, minute=17, second=0, microsecond=0)
    end = start.replace(hour=21, minute=0)
    return {"id": start.strftime("%Y-%m"), "start": start, "end": end,
            "active": start <= local < end, "day": local.date() == start.date()}


def scheduled_allowed(event, at=None, closing=False):
    if event != "schedule":
        return True
    if closing:
        local = (at or clock()).astimezone(ZONE)
        value = report_window(local)
        return value["start"] <= local < value["end"] + timedelta(hours=24)
    return window(at)["active"]


def report_window(at=None):
    """Report the most recent batch, including a delayed month-end run."""
    local = (at or clock()).astimezone(ZONE)
    value = window(local)
    if local < value["start"]:
        value = window(local.replace(day=1) - timedelta(days=1))
    return value


def require_window():
    if not scheduled_allowed(os.environ.get("GITHUB_EVENT_NAME")):
        raise DeadlinePassed("Monthly maintenance deadline passed; no further writes")


def claim(state, key, limit=1):
    """Persist an intent before work; an uncertain result never spends twice."""
    cycle = window()
    if not cycle["active"]:
        return False
    record = state.data.setdefault("cycles", {}).setdefault(cycle["id"], {"claims": {}})
    count = record["claims"].get(key, 0)
    if count >= limit:
        return False
    record["claims"][key] = count + 1
    record["deadline"] = cycle["end"].isoformat()
    if os.environ.get("GITHUB_RUN_ID", "").isdigit():
        record.setdefault("runs", {})[key] = os.environ["GITHUB_RUN_ID"]
    state.save()
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--closing", action="store_true")
    args = parser.parse_args()
    allowed = scheduled_allowed(os.environ["GITHUB_EVENT_NAME"], closing=args.closing)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write("allowed=" + str(allowed).lower() + "\n")
        output.write("cycle=" + (report_window() if args.closing else window())["id"] + "\n")
