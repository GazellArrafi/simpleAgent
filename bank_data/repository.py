"""Satu-satunya pintu akses data JSON. Data di-load sekali lalu diindeks per customer_id.

Kalau nanti pindah ke database, cukup ganti isi kelas ini.
"""

import contextlib
import json
import os
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import config

_PER_CUSTOMER = ["savings_accounts", "savings_transactions", "credit_cards", "cc_transactions",
                 "cc_statements", "loans"]


class BankRepository:
    def __init__(self, data_dir: Path = config.DATA_DIR):
        self.data_dir = Path(data_dir)
        if not (self.data_dir / "meta.json").exists():
            raise FileNotFoundError(f"Data belum ada di {self.data_dir}. Jalankan: python main.py generate")
        self.mtime = _meta_mtime(self.data_dir)
        self.meta = self._load("meta")
        self.offers = self._load("offers")
        self._customers = {c["customer_id"]: c for c in self._load("customers")}
        self._index = {}
        for name in _PER_CUSTOMER:
            idx = defaultdict(list)
            for row in self._load(name):
                idx[row["customer_id"]].append(row)
            self._index[name] = idx

    def _load(self, name):
        return json.loads((self.data_dir / f"{name}.json").read_text(encoding="utf-8"))

    # ---------------------------------------------------------------- tulis (dipakai world simulator)
    backend = "json"

    def add_row(self, name: str, row: dict):
        self._index[name][row["customer_id"]].append(row)

    # dict yang dikembalikan adalah objek yang sama di memori -> perubahan sudah tercatat, cukup save()
    def update_card(self, card): ...
    def update_account(self, acct): ...
    def update_statement(self, st): ...
    def update_loan(self, loan): ...

    def transaction(self):
        return contextlib.nullcontext()

    def set_reference_date(self, d: date):
        self.meta["reference_date"] = d.isoformat()

    def save(self):
        """Tulis semua tabel (atomic). meta.json ditulis terakhir supaya proses lain reload setelah data lengkap."""
        for name in _PER_CUSTOMER:
            _atomic_write(self.data_dir / f"{name}.json", [r for rows in self._index[name].values() for r in rows])
        _atomic_write(self.data_dir / "customers.json", list(self._customers.values()))
        _atomic_write(self.data_dir / "meta.json", self.meta)
        self.mtime = _meta_mtime(self.data_dir)

    # ---------------------------------------------------------------- dasar
    def reference_date(self) -> date:
        return date.fromisoformat(config.SIM_DATE or self.meta["reference_date"])

    def list_customers(self) -> list[dict]:
        return list(self._customers.values())

    def get_customer(self, customer_id: str) -> dict | None:
        return self._customers.get(customer_id)

    def _rows(self, name, customer_id):
        return self._index[name].get(customer_id, [])

    def get_savings_accounts(self, customer_id):
        return self._rows("savings_accounts", customer_id)

    def get_savings_transactions(self, customer_id, days: int | None = None, until: date | None = None):
        return _window(self._rows("savings_transactions", customer_id), days, until or self.reference_date())

    def get_credit_cards(self, customer_id):
        return self._rows("credit_cards", customer_id)

    def get_cc_transactions(self, customer_id, days: int | None = None, until: date | None = None,
                            category: str | None = None):
        rows = _window(self._rows("cc_transactions", customer_id), days, until or self.reference_date())
        return [r for r in rows if not category or r["category"] == category]

    def get_cc_statements(self, customer_id):
        return sorted(self._rows("cc_statements", customer_id), key=lambda s: s["statement_date"])

    def get_loans(self, customer_id):
        return self._rows("loans", customer_id)

    # ---------------------------------------------------------------- ringkasan
    def overview(self, customer_id) -> dict:
        c = self.get_customer(customer_id)
        if not c:
            raise KeyError(f"Nasabah {customer_id} tidak ditemukan")
        cards, loans = self.get_credit_cards(customer_id), self.get_loans(customer_id)
        savings = self.get_savings_accounts(customer_id)
        return {
            "customer_id": customer_id,
            "nickname": c["nickname"],
            "segment": c["segment"],
            "age": c["age"],
            "marketing_consent": c["marketing_consent"],
            "has_credit_card": bool(cards),
            "credit_card_count": len(cards),
            "cc_transactions_90d": len(self.get_cc_transactions(customer_id, days=90)),
            "has_loan": bool(loans),
            "loan_types": [l["type"] for l in loans],
            "has_savings": bool(savings),
            "savings_balance_total": sum(a["balance"] for a in savings),
        }


def _window(rows, days, until: date):
    end = datetime.combine(until, datetime.max.time())
    start = datetime.combine(until - timedelta(days=days), datetime.min.time()) if days else None
    out = []
    for r in rows:
        dt = datetime.fromisoformat(r["datetime"])
        if dt <= end and (start is None or dt >= start):
            out.append(r)
    return out


def _meta_mtime(data_dir: Path) -> int:
    return (data_dir / "meta.json").stat().st_mtime_ns


def _atomic_write(path: Path, obj):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for attempt in range(10):  # Windows: file tujuan bisa sedang dibaca proses lain
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.2 * (attempt + 1))
    raise PermissionError(f"Gagal menulis {path}")


_repo: BankRepository | None = None
_repo_lock = threading.Lock()


def get_repo() -> BankRepository:
    """Repository bersama per proses, sesuai DATA_BACKEND (json | postgres).
    JSON: reload otomatis kalau file diubah proses lain (mis. autopilot). Postgres: selalu data terkini."""
    global _repo
    with _repo_lock:
        if config.DATA_BACKEND == "postgres":
            if _repo is None:
                from bank_data.pg_repository import PostgresRepository
                _repo = PostgresRepository()
            return _repo
        if _repo is None or _meta_mtime(config.DATA_DIR) != _repo.mtime:
            _repo = BankRepository()
        return _repo


def reload_repo() -> BankRepository:
    global _repo
    _repo = None
    return get_repo()
