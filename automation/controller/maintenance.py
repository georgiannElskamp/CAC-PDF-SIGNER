"""Calendar and durable limits for monthly maintenance."""
import calendar
from datetime import datetime, timezone
import os
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("America/Chicago")


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
    value = window(at)
    return value["day"] if closing else value["active"]


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
        output.write("cycle=" + window()["id"] + "\n")
