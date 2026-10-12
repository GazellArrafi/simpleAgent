"""Heartbeat autopilot: tiap putaran = 1 hari simulasi.
world.step() → Manager bangun & bekerja sendiri (mode LLM) / screener + pipeline aturan (mode offline)."""

import os
import threading
import time
from datetime import datetime, timedelta

from autonomy import screener, store
from autonomy.world import World
from bank_data.repository import get_repo
from llm import is_online, llm_status

OFFLINE_CRITERIA = [c for c in screener.CRITERIA if c != "healthy_offer_candidate"]


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _heartbeat(stop: threading.Event):
    while not stop.wait(2):
        store.set_state(heartbeat=_now())


def _offline_day(sim_date: str):
    from graph.workflow import run_customer
    limit = int(store.load_mission().get("max_cases_per_day", 5))
    cooldown = (get_repo().reference_date() - timedelta(days=2)).isoformat()
    rows = [r for r in screener.scan(OFFLINE_CRITERIA, 200) if (r["last_contact"] or "") < cooldown][:limit]
    for row in rows:
        st = run_customer(row["customer_id"])
        sent = [m["code"] for m in st.get("messages", [])]
        store.log("pipeline", "done", f"{row['customer_id']} ({', '.join(row['matched'])}) → pesan: {', '.join(sent) or '-'}",
                  0, row["customer_id"], sim_date)
    store.add_report(sim_date, f"[offline] {limit} nasabah prioritas teratas diproses dengan pipeline aturan.")


def run(days: int = 0, interval: float = 3.0):
    """days=0 → jalan terus sampai diminta berhenti (tombol Stop / file STOP)."""
    store.clear_stop()
    mode = "llm" if is_online() else "offline"
    store.set_state(running=True, pid=os.getpid(), started_at=_now(), heartbeat=_now(), days_done=0, mode=mode,
                    llm=llm_status(), phase="mulai", error=None)
    stop_hb = threading.Event()
    threading.Thread(target=_heartbeat, args=(stop_hb,), daemon=True).start()
    n = 0
    try:
        while (days <= 0 or n < days) and not store.stop_requested():
            store.set_state(phase="dunia bergerak")
            events = World(get_repo()).step()
            d = get_repo().reference_date().isoformat()
            counts = {}
            for e in events:
                counts[e["type"]] = counts.get(e["type"], 0) + 1
            store.log("world", "tick", f"Hari baru {d}: {len(events)} kejadian "
                      + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())), 0, None, d)
            store.set_state(sim_date=d, phase="agent bekerja")
            if mode == "llm":
                from autonomy.agents import run_manager_day
                res = run_manager_day()
                if res["error"] and res["error"] != "recursion":  # LLM bermasalah → hari ini pakai jalur aturan
                    store.log("autopilot", "error", f"Manager gagal ({res['error']}), fallback ke pipeline aturan", 0, None, d)
                    _offline_day(d)
            else:
                _offline_day(d)
            n += 1
            store.set_state(days_done=n, phase="istirahat")
            end = time.time() + interval
            while time.time() < end and not store.stop_requested():
                time.sleep(0.3)
    except Exception as e:
        store.set_state(error=f"{type(e).__name__}: {e}")
        store.log("autopilot", "error", f"{type(e).__name__}: {e}")
        raise
    finally:
        stop_hb.set()
        store.clear_stop()
        store.set_state(running=False, phase="berhenti", heartbeat=_now())
