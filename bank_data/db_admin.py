"""Setup & loader PostgreSQL: buat role + database + tabel + hak akses, lalu isi dari data/*.json (COPY)."""

import json

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb

import config

SCHEMA_SQL = config.BASE_DIR / "db" / "schema.sql"
GRANTS_SQL = config.BASE_DIR / "db" / "grants.sql"
# urutan sesuai foreign key
TABLES = ["customers", "savings_accounts", "savings_transactions", "credit_cards", "cc_transactions",
          "cc_statements", "loans", "offers"]


def _require_urls():
    missing = [k for k in ("DATABASE_ADMIN_URL", "DATABASE_URL", "DATABASE_READONLY_URL") if not getattr(config, k)]
    if missing:
        raise RuntimeError(f"Isi dulu di .env: {', '.join(missing)} (lihat markdown/database.md)")


def setup(log=print):
    """Idempotent: buat/ubah role bank_app & agent_reader, database, tabel (DROP + CREATE), hak akses."""
    _require_urls()
    app, reader = conninfo_to_dict(config.DATABASE_URL), conninfo_to_dict(config.DATABASE_READONLY_URL)
    dbname = app["dbname"]
    with psycopg.connect(config.DATABASE_ADMIN_URL, autocommit=True) as admin:
        for info in (app, reader):
            exists = admin.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (info["user"],)).fetchone()
            verb = "ALTER" if exists else "CREATE"
            admin.execute(sql.SQL(verb + " ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(info["user"]), sql.Literal(info["password"])))
            log(f"role {info['user']}: {'diperbarui' if exists else 'dibuat'}")
        if not admin.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)).fetchone():
            admin.execute(sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8'").format(
                sql.Identifier(dbname), sql.Identifier(app["user"])))
            log(f"database {dbname}: dibuat")
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        log("tabel, index & komentar: dibuat")
    admin_db = conninfo_to_dict(config.DATABASE_ADMIN_URL) | {"dbname": dbname}
    with psycopg.connect(**admin_db, autocommit=True) as conn:
        conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(dbname)))
        conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}").format(
            sql.Identifier(dbname), sql.Identifier(app["user"]), sql.Identifier(reader["user"])))
        conn.execute("SET search_path TO bank")
        conn.execute(GRANTS_SQL.read_text(encoding="utf-8"))
        log("hak akses agent_reader (read-only, tanpa kolom sensitif): diterapkan")


def _convert(value, data_type):
    if value is None:
        return None
    if data_type in ("bigint", "integer", "smallint"):
        return int(round(value))
    if data_type == "jsonb":
        return Jsonb(value)
    return value


def load_from_json(log=print) -> dict:
    """Kosongkan tabel lalu isi dari data/*.json. Return jumlah baris per tabel."""
    _require_urls()
    counts = {}
    with psycopg.connect(config.DATABASE_URL, options="-c search_path=bank") as conn:
        conn.execute("TRUNCATE notifications, app_meta, " + ", ".join(TABLES) + " CASCADE")
        for table in TABLES:
            rows = json.loads((config.DATA_DIR / f"{table}.json").read_text(encoding="utf-8"))
            cols = conn.execute("SELECT column_name, data_type FROM information_schema.columns "
                                "WHERE table_schema = 'bank' AND table_name = %s ORDER BY ordinal_position",
                                (table,)).fetchall()
            names = [c for c, _ in cols]
            with conn.cursor().copy(sql.SQL("COPY {} ({}) FROM STDIN").format(
                    sql.Identifier(table), sql.SQL(", ").join(map(sql.Identifier, names)))) as cp:
                for r in rows:
                    src = {("txn_time" if k == "datetime" else k): v for k, v in r.items()}
                    cp.write_row([_convert(src.get(c), t) for c, t in cols])
            counts[table] = len(rows)
            log(f"  {table:<22} {len(rows):>8,} baris")
        meta = json.loads((config.DATA_DIR / "meta.json").read_text(encoding="utf-8"))
        for key in ("reference_date", "history_start", "seed", "generated_at"):
            conn.execute("INSERT INTO app_meta (key, value) VALUES (%s, %s)", (key, str(meta[key])))
        conn.execute("ANALYZE")
    return counts
