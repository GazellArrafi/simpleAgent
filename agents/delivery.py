"""Delivery: kirim pesan ke kanal (inbox web/outbox JSON + Telegram opsional) dengan aturan
dedup & jam tenang (rules.md C6-C7)."""

import time
import uuid
from datetime import datetime, timedelta

import config
from agents.base import trace
from channels import outbox, telegram


def _quiet(now: datetime) -> bool:
    start, end = config.RULES["quiet_hours"]
    return now.hour >= start or now.hour < end


def _next_morning(now: datetime) -> datetime:
    target = now.replace(hour=config.RULES["quiet_hours"][1], minute=0, second=0, microsecond=0)
    return target if target > now else target + timedelta(days=1)


def node(state: dict) -> dict:
    started = time.perf_counter()
    cid, sim = state["customer_id"], state["sim_date"]
    profile = state["context"]["profile"]
    now = datetime.now()
    deliveries, lines = [], []
    for m in state.get("messages", []):
        if outbox.exists(cid, m["insight_id"], sim):
            deliveries.append({"insight_id": m["insight_id"], "status": "duplicate_skipped", "channels": []})
            lines.append(f"⏭ {m['code']}: sudah pernah dikirim hari ini (dedup)")
            continue
        hold = m["severity"] == "info" and _quiet(now)
        record = {"message_id": uuid.uuid4().hex[:10], "customer_id": cid, "sim_date": sim, **m,
                  "channels": ["app"], "status": "scheduled" if hold else "sent",
                  "created_at": now.isoformat(timespec="seconds"),
                  "send_at": (_next_morning(now) if hold else now).isoformat(timespec="seconds")}
        if telegram.enabled() and not hold:
            ok, info = telegram.send(telegram.format_message(record), profile.get("telegram_chat_id"))
            record["telegram"] = info
            if ok:
                record["channels"].append("telegram")
        outbox.append(record)
        deliveries.append({"insight_id": m["insight_id"], "status": record["status"], "channels": record["channels"],
                           "send_at": record["send_at"]})
        lines.append(f"{'🕗' if hold else '✅'} {m['code']} → {', '.join(record['channels'])} ({record['status']})")
    return {"deliveries": deliveries,
            "trace": [trace("delivery", f"memproses {len(deliveries)} pesan", "\n".join(lines) or "-", started=started)]}
