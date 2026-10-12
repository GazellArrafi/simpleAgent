"""Tools text-to-SQL untuk agent LLM: lihat skema → tulis SELECT sendiri → jalankan.

Pengaman berlapis (markdown/database.md bagian 2):
  1. koneksi memakai role agent_reader (read-only, statement_timeout 5 dtk, tanpa kolom sensitif)
  2. validasi: satu statement SELECT/WITH, kata kunci tulis/DDL ditolak
  3. hasil dibungkus LIMIT, yang dikirim ke LLM maks 50 baris
Error SQL dikembalikan sebagai teks supaya agent bisa memperbaiki query-nya sendiri.
"""

import json
import re
import threading
from functools import lru_cache

import psycopg
from langchain_core.tools import tool

import config
from bank_data.pg_repository import _plain

MAX_ROWS_DB = 200
MAX_ROWS_LLM = 50
WRITE_WORDS = re.compile(r"\b(insert|update|delete|merge|drop|alter|create|grant|revoke|truncate|copy|call|vacuum|"
                         r"lock|set|reset|refresh|comment|execute|prepare|listen|notify)\b"
                         r"|pg_sleep|pg_read|pg_ls|lo_import|lo_export|dblink|pg_terminate|set_config", re.I)
_local = threading.local()


def _conn() -> psycopg.Connection:
    c = getattr(_local, "conn", None)
    if c is None or c.closed:
        if not config.DATABASE_READONLY_URL:
            raise RuntimeError("DATABASE_READONLY_URL belum diisi di .env")
        c = psycopg.connect(config.DATABASE_READONLY_URL, autocommit=True,
                            options="-c search_path=bank -c default_transaction_read_only=on -c statement_timeout=5000")
        _local.conn = c
    return c


def validate_sql(query: str) -> tuple[str | None, str]:
    """Return (pesan_error | None, query_bersih)."""
    q = query.strip().rstrip(";").strip()
    q = re.sub(r"^```(sql)?|```$", "", q, flags=re.I).strip()
    if not q:
        return "query kosong", q
    if ";" in q:
        return "hanya boleh SATU statement (tanpa ';' di tengah)", q
    if not re.match(r"^(select|with)\b", q, re.I):
        return "hanya query SELECT / WITH yang diizinkan", q
    if m := WRITE_WORDS.search(q):
        return f"kata kunci '{m.group(0)}' tidak diizinkan (akses hanya baca)", q
    return None, q


def execute_readonly(query: str) -> dict:
    err, q = validate_sql(query)
    if err:
        return {"error": err}
    try:
        with _conn().cursor() as cur:
            cur.execute(f"SELECT * FROM ({q}) AS _q LIMIT {MAX_ROWS_DB}")
            cols = [d.name for d in cur.description]
            rows = [[_plain(v) for v in r] for r in cur.fetchall()]
    except psycopg.Error as e:
        msg = (e.diag.message_primary or str(e)).strip()
        if "permission denied for table customers" in msg:
            msg += (" (kolom phone, email, telegram_chat_id, demo_persona tidak boleh diakses — "
                    "sebutkan kolom customers secara eksplisit, jangan SELECT *)")
        return {"error": msg + (f" (petunjuk: {e.diag.message_hint})" if e.diag.message_hint else "")}
    return {"columns": cols, "row_count": len(rows), "rows": rows[:MAX_ROWS_LLM],
            "truncated": len(rows) > MAX_ROWS_LLM or len(rows) == MAX_ROWS_DB}


@lru_cache(maxsize=1)
def schema_text() -> str:
    with _conn().cursor() as cur:
        cur.execute("""
            SELECT c.table_name, obj_description(('bank.' || c.table_name)::regclass) AS table_comment,
                   c.column_name, c.data_type,
                   col_description(('bank.' || c.table_name)::regclass, c.ordinal_position) AS col_comment
            FROM information_schema.columns c
            WHERE c.table_schema = 'bank'
              AND has_column_privilege(current_user, 'bank.' || c.table_name, c.column_name, 'SELECT')
            ORDER BY c.table_name, c.ordinal_position""")
        out, current = [], None
        for table, tcomment, col, dtype, ccomment in cur.fetchall():
            if table != current:
                out.append(f"\nTABLE {table} -- {tcomment or ''}")
                current = table
            out.append(f"  {col} {dtype}" + (f" -- {ccomment}" if ccomment else ""))
    return ("Schema `bank` (PostgreSQL). Relasi: semua tabel transaksi punya customer_id → customers; "
            "cc_transactions & cc_statements punya card_id → credit_cards.\n" + "\n".join(out))


@tool
def describe_database() -> str:
    """Lihat struktur database bank (tabel, kolom, tipe, arti kolom). Panggil ini sebelum menulis SQL."""
    return schema_text()


@tool
def run_sql(query: str) -> str:
    """Jalankan SATU query SELECT (PostgreSQL) ke database bank, akses hanya-baca. Kembalikan kolom & baris
    (maks 50 baris). Kalau error, baca pesannya lalu perbaiki query. Tips: gunakan agregasi (SUM, COUNT,
    GROUP BY) daripada menarik banyak baris; tanggal 'hari ini' ada di app_meta (key='reference_date')."""
    res = execute_readonly(query)
    if "error" in res:
        return f"ERROR: {res['error']}. Perbaiki query lalu coba lagi."
    return json.dumps(res, ensure_ascii=False, default=str)


SQL_TOOLS = [describe_database, run_sql]
