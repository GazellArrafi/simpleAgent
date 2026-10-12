"""Penyimpanan kecil untuk mode autopilot (data/autopilot/): misi, state, memori, follow-up,
kejadian, log aktivitas agent, laporan harian. Dibaca juga oleh UI Streamlit (proses lain)."""

import json
import threading
import uuid
from datetime import date, datetime

import config

DIR = config.DATA_DIR / "autopilot"
_lock = threading.Lock()

DEFAULT_MISSION = {
    "goal": ("Jaga kesehatan finansial nasabah: pastikan tidak ada yang telat bayar kartu kredit maupun cicilan, "
             "cegah limit kartu habis, waspadai transaksi mencurigakan, dan beri penawaran yang relevan hanya "
             "kepada nasabah yang kondisinya sehat."),
    "constraints": ("Jangan spam: hubungi nasabah hanya bila ada alasan kuat. Utamakan yang paling mendesak. "
                    "Setelah mengingatkan, pantau hasilnya lewat follow-up."),
    "max_cases_per_day": 5,
}


def _path(name):
    DIR.mkdir(parents=True, exist_ok=True)
    return DIR / name


def _read(name, default):
    p = _path(name)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8") or "null") or default
    except json.JSONDecodeError:
        return default


def _write(name, obj):
    p = _path(name)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    tmp.replace(p)


def _append_jsonl(name, row):
    with _lock, _path(name).open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _read_jsonl(name, last: int | None = None):
    p = _path(name)
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()
    rows = []
    for line in lines[-last:] if last else lines:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


# ---------------------------------------------------------------- misi & state
def load_mission() -> dict:
    return {**DEFAULT_MISSION, **_read("mission.json", {})}


def save_mission(mission: dict):
    _write("mission.json", mission)


def get_state() -> dict:
    return _read("state.json", {})


def set_state(**kw):
    with _lock:
        _write("state.json", {**get_state(), **kw})


def request_stop():
    _path("STOP").write_text("stop")


def stop_requested() -> bool:
    return _path("STOP").exists()


def clear_stop():
    _path("STOP").unlink(missing_ok=True)


# ---------------------------------------------------------------- log aktivitas
def log(agent: str, kind: str, text: str, depth: int = 0, customer_id: str | None = None, sim_date: str | None = None):
    """kind: tick | start | think | tool | result | done | error | report"""
    _append_jsonl("activity.jsonl", {"ts": datetime.now().strftime("%H:%M:%S"), "sim_date": sim_date,
                                     "agent": agent, "kind": kind, "depth": depth, "customer_id": customer_id,
                                     "text": text})


def read_activity(last=200):
    return _read_jsonl("activity.jsonl", last)


# ---------------------------------------------------------------- kejadian dunia
def add_events(events: list[dict]):
    for e in events:
        _append_jsonl("events.jsonl", e)


def events_on(sim_date: str) -> list[dict]:
    return [e for e in _read_jsonl("events.jsonl", 5000) if e["date"] == sim_date]


def read_events(last=300):
    return _read_jsonl("events.jsonl", last)


# ---------------------------------------------------------------- memori per nasabah
def add_memory(customer_id: str, agent: str, note: str, sim_date: str):
    with _lock:
        mem = _read("memory.json", {})
        mem.setdefault(customer_id, []).append({"date": sim_date, "agent": agent, "note": note})
        _write("memory.json", mem)


def get_memory(customer_id: str, last=15) -> list[dict]:
    return _read("memory.json", {}).get(customer_id, [])[-last:]


def all_memory() -> dict:
    return _read("memory.json", {})


# ---------------------------------------------------------------- follow-up
def add_followup(customer_id: str, due: date, reason: str, created_by: str, sim_date: str) -> dict:
    with _lock:
        rows = _read("followups.json", [])
        fu = {"followup_id": "FU-" + uuid.uuid4().hex[:6], "customer_id": customer_id, "due_date": due.isoformat(),
              "reason": reason, "created_by": created_by, "created_on": sim_date, "status": "open", "outcome": None}
        rows.append(fu)
        _write("followups.json", rows)
    return fu


def list_followups(status: str | None = None, customer_id: str | None = None) -> list[dict]:
    return [f for f in _read("followups.json", [])
            if (not status or f["status"] == status) and (not customer_id or f["customer_id"] == customer_id)]


def due_followups(sim_date: str) -> list[dict]:
    return [f for f in list_followups("open") if f["due_date"] <= sim_date]


def close_followup(followup_id: str, outcome: str, sim_date: str) -> bool:
    with _lock:
        rows = _read("followups.json", [])
        for f in rows:
            if f["followup_id"] == followup_id and f["status"] == "open":
                f.update(status="closed", outcome=outcome, closed_on=sim_date)
                _write("followups.json", rows)
                return True
    return False


# ---------------------------------------------------------------- laporan harian
def add_report(sim_date: str, text: str):
    with _lock:
        rows = _read("reports.json", [])
        rows.append({"sim_date": sim_date, "report": text})
        _write("reports.json", rows)


def read_reports() -> list[dict]:
    return _read("reports.json", [])


def reset_all():
    """Hapus semua jejak autopilot (kecuali misi)."""
    for name in ["state.json", "activity.jsonl", "events.jsonl", "memory.json", "followups.json", "reports.json", "STOP"]:
        _path(name).unlink(missing_ok=True)
