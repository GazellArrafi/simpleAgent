"""Kanal 'app': pesan disimpan lalu ditampilkan di Inbox Nasabah (Streamlit).
DATA_BACKEND=json → data/outbox.json | DATA_BACKEND=postgres → tabel bank.notifications."""

import json
import threading

import config

_lock = threading.Lock()
COLUMNS = ["message_id", "customer_id", "sim_date", "insight_id", "code", "agent", "severity", "category", "title",
           "body", "cta", "footer", "source", "channels", "status", "created_at", "send_at", "telegram"]


def _pg():
    return config.DATA_BACKEND == "postgres"


def _repo():
    from bank_data.repository import get_repo
    return get_repo()


# ---------------------------------------------------------------- json
def _read_json() -> list[dict]:
    if not config.OUTBOX_FILE.exists():
        return []
    return json.loads(config.OUTBOX_FILE.read_text(encoding="utf-8") or "[]")


def _write_json(rows):
    config.OUTBOX_FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- API
def read_all() -> list[dict]:
    if _pg():
        return _repo()._q("SELECT * FROM notifications ORDER BY created_at, message_id")
    return _read_json()


def append(record: dict):
    if _pg():
        cols = [c for c in COLUMNS if c in record]
        _repo()._q(f"INSERT INTO notifications ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
                   [record[c] for c in cols])
        return
    with _lock:
        rows = _read_json()
        rows.append(record)
        _write_json(rows)


def exists(customer_id: str, insight_id: str, sim_date: str) -> bool:
    if _pg():
        return bool(_repo()._q("SELECT 1 FROM notifications WHERE customer_id = %s AND insight_id = %s AND sim_date = %s",
                               (customer_id, insight_id, sim_date)))
    return any(r["customer_id"] == customer_id and r["insight_id"] == insight_id and r["sim_date"] == sim_date
               for r in _read_json())


def for_customer(customer_id: str) -> list[dict]:
    if _pg():
        return _repo()._q("SELECT * FROM notifications WHERE customer_id = %s ORDER BY created_at, message_id",
                          (customer_id,))
    return [r for r in _read_json() if r["customer_id"] == customer_id]


def clear(customer_id: str | None = None):
    if _pg():
        if customer_id:
            _repo()._q("DELETE FROM notifications WHERE customer_id = %s", (customer_id,))
        else:
            _repo()._q("DELETE FROM notifications")
        return
    with _lock:
        _write_json([r for r in _read_json() if customer_id and r["customer_id"] != customer_id])
