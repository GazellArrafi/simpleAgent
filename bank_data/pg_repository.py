"""Repository PostgreSQL — kontrak sama persis dengan BankRepository (JSON), jadi agent & analitik tidak berubah.

Semua akses memakai query terparameter. SQL yang dijalankan dicatat per thread (query log) supaya
jejak Data Agent bisa menampilkan query apa saja yang dieksekusi.
"""

import threading
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

import config

SAV_TXN_COLS = ("txn_id, account_id, customer_id, txn_time AS datetime, direction, category, description, "
                "amount, balance_after")
CC_TXN_COLS = ("txn_id, card_id, customer_id, txn_time AS datetime, type, merchant, category, amount, currency, "
               "original_amount, channel, location, is_recurring, status, decline_reason")
INT_TYPES = {"bigint", "integer", "smallint"}


def _plain(v):
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


def _row(r: dict) -> dict:
    return {k: _plain(v) for k, v in r.items()}


class PostgresRepository:
    backend = "postgres"

    def __init__(self, dsn: str = config.DATABASE_URL):
        if not dsn:
            raise RuntimeError("DATABASE_URL belum diisi di .env (lihat markdown/database.md)")
        self.dsn = dsn
        self._local = threading.local()
        self._columns: dict[str, dict[str, str]] = {}
        if not self._q("SELECT 1 AS ok FROM app_meta WHERE key = 'reference_date'"):
            raise FileNotFoundError("Database masih kosong. Jalankan: python main.py db-setup && python main.py db-load")
        self.offers = self._q("SELECT offer_id, name, type, is_credit_product, description, target, cta FROM offers ORDER BY offer_id")

    # ---------------------------------------------------------------- koneksi & eksekusi
    def conn(self) -> psycopg.Connection:
        c = getattr(self._local, "conn", None)
        if c is None or c.closed:
            c = psycopg.connect(self.dsn, autocommit=True, row_factory=dict_row,
                                options="-c search_path=bank")
            self._local.conn = c
        return c

    def _q(self, sql: str, params=(), one=False):
        log = getattr(self._local, "qlog", None)
        if log is not None:
            log.append(" ".join(sql.split()))
        with self.conn().cursor() as cur:
            cur.execute(sql, params)
            rows = [_row(r) for r in cur.fetchall()] if cur.description else []
        if one:
            return rows[0] if rows else None
        return rows

    def start_query_log(self):
        self._local.qlog = []

    def pop_query_log(self) -> list[str]:
        log, self._local.qlog = getattr(self._local, "qlog", None) or [], None
        return log

    @contextmanager
    def transaction(self):
        with self.conn().transaction():
            yield

    # ---------------------------------------------------------------- meta
    def reference_date(self) -> date:
        if config.SIM_DATE:
            return date.fromisoformat(config.SIM_DATE)
        return date.fromisoformat(self._q("SELECT value FROM app_meta WHERE key = 'reference_date'", one=True)["value"])

    @property
    def meta(self) -> dict:
        m = {r["key"]: r["value"] for r in self._q("SELECT key, value FROM app_meta")}
        m["counts"] = self._q("""
            SELECT (SELECT count(*) FROM customers) AS customers,
                   (SELECT count(*) FROM savings_accounts) AS savings_accounts,
                   (SELECT count(*) FROM savings_transactions) AS savings_transactions,
                   (SELECT count(*) FROM credit_cards) AS credit_cards,
                   (SELECT count(*) FROM cc_transactions) AS cc_transactions,
                   (SELECT count(*) FROM cc_statements) AS cc_statements,
                   (SELECT count(*) FROM loans) AS loans,
                   (SELECT count(*) FROM offers) AS offers""", one=True)
        return m

    # ---------------------------------------------------------------- baca
    def list_customers(self) -> list[dict]:
        return self._q("SELECT * FROM customers ORDER BY customer_id")

    def get_customer(self, customer_id):
        return self._q("SELECT * FROM customers WHERE customer_id = %s", (customer_id,), one=True)

    def get_savings_accounts(self, customer_id):
        return self._q("SELECT * FROM savings_accounts WHERE customer_id = %s ORDER BY account_id", (customer_id,))

    def _window(self, until: date | None, days: int | None):
        end = datetime.combine(until or self.reference_date(), datetime.max.time())
        start = datetime.combine(end.date() - timedelta(days=days), datetime.min.time()) if days else datetime.min
        return start, end

    def get_savings_transactions(self, customer_id, days=None, until=None):
        start, end = self._window(until, days)
        return self._q(f"SELECT {SAV_TXN_COLS} FROM savings_transactions "
                       "WHERE customer_id = %s AND txn_time BETWEEN %s AND %s ORDER BY txn_time, txn_id",
                       (customer_id, start, end))

    def get_credit_cards(self, customer_id):
        return self._q("SELECT * FROM credit_cards WHERE customer_id = %s ORDER BY card_id", (customer_id,))

    def get_cc_transactions(self, customer_id, days=None, until=None, category=None):
        start, end = self._window(until, days)
        sql = (f"SELECT {CC_TXN_COLS} FROM cc_transactions "
               "WHERE customer_id = %s AND txn_time BETWEEN %s AND %s")
        params = [customer_id, start, end]
        if category:
            sql += " AND category = %s"
            params.append(category)
        return self._q(sql + " ORDER BY txn_time, txn_id", params)

    def get_cc_statements(self, customer_id):
        return self._q("SELECT * FROM cc_statements WHERE customer_id = %s ORDER BY statement_date", (customer_id,))

    def get_loans(self, customer_id):
        return self._q("SELECT * FROM loans WHERE customer_id = %s ORDER BY loan_id", (customer_id,))

    def overview(self, customer_id) -> dict:
        since = datetime.combine(self.reference_date() - timedelta(days=90), datetime.min.time())
        r = self._q("""
            SELECT c.customer_id, c.nickname, c.segment, c.age, c.marketing_consent,
                   (SELECT count(*) FROM credit_cards k WHERE k.customer_id = c.customer_id) AS credit_card_count,
                   (SELECT count(*) FROM cc_transactions t
                     WHERE t.customer_id = c.customer_id AND t.txn_time >= %s) AS cc_transactions_90d,
                   (SELECT coalesce(array_agg(l.type ORDER BY l.loan_id), '{}') FROM loans l
                     WHERE l.customer_id = c.customer_id) AS loan_types,
                   (SELECT count(*) FROM savings_accounts a WHERE a.customer_id = c.customer_id) AS savings_count,
                   (SELECT coalesce(sum(a.balance), 0) FROM savings_accounts a
                     WHERE a.customer_id = c.customer_id) AS savings_balance_total
            FROM customers c WHERE c.customer_id = %s""", (since, customer_id), one=True)
        if not r:
            raise KeyError(f"Nasabah {customer_id} tidak ditemukan")
        return {"customer_id": r["customer_id"], "nickname": r["nickname"], "segment": r["segment"], "age": r["age"],
                "marketing_consent": r["marketing_consent"], "has_credit_card": r["credit_card_count"] > 0,
                "credit_card_count": r["credit_card_count"], "cc_transactions_90d": r["cc_transactions_90d"],
                "has_loan": bool(r["loan_types"]), "loan_types": r["loan_types"], "has_savings": r["savings_count"] > 0,
                "savings_balance_total": int(r["savings_balance_total"])}

    # ---------------------------------------------------------------- tulis (world simulator)
    def _table_columns(self, table: str) -> dict[str, str]:
        if table not in self._columns:
            rows = self._q("SELECT column_name, data_type FROM information_schema.columns "
                           "WHERE table_schema = 'bank' AND table_name = %s", (table,))
            self._columns[table] = {r["column_name"]: r["data_type"] for r in rows}
        return self._columns[table]

    def add_row(self, table: str, row: dict):
        cols = self._table_columns(table)
        data = {("txn_time" if k == "datetime" else k): v for k, v in row.items()}
        data = {k: v for k, v in data.items() if k in cols}
        self._q(f"INSERT INTO {table} ({', '.join(data)}) VALUES ({', '.join(['%s'] * len(data))})",
                [_to_db(v, cols[k]) for k, v in data.items()])

    def _update(self, table: str, key: str, row: dict, fields: tuple[str, ...]):
        cols = self._table_columns(table)
        self._q(f"UPDATE {table} SET {', '.join(f'{f} = %s' for f in fields)} WHERE {key} = %s",
                [_to_db(row[f], cols[f]) for f in fields] + [row[key]])

    def update_card(self, card):
        self._update("credit_cards", "card_id", card, ("current_balance", "available_limit"))

    def update_account(self, acct):
        self._update("savings_accounts", "account_id", acct, ("balance",))

    def update_statement(self, st):
        self._update("cc_statements", "statement_id", st, ("paid_amount", "paid_date", "status", "paid_late", "days_past_due"))

    def update_loan(self, loan):
        self._update("loans", "loan_id", loan, ("days_past_due", "status", "remaining_months", "outstanding", "next_due_date"))

    def set_reference_date(self, d: date):
        self._q("INSERT INTO app_meta (key, value) VALUES ('reference_date', %s) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (d.isoformat(),))

    def save(self):
        """Tidak perlu: setiap tulis langsung ke DB (dibungkus transaction() oleh world simulator)."""


def _to_db(v, data_type: str):
    if v is None:
        return None
    if data_type in INT_TYPES:
        return int(round(v))
    if data_type == "jsonb":
        return Jsonb(v)
    return v
