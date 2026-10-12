"""CLI simpleAgent.

  python main.py generate [--customers 200] [--seed 42] [--ref-date YYYY-MM-DD]
  python main.py run --customer C0001 [--objective "fokus pengingat tagihan CC"]
  python main.py batch [--limit 20]
  python main.py ask "berapa total belanja dining C0003 30 hari terakhir?"
  python main.py reset-outbox
  python main.py autopilot [--days 7] [--interval 3]     # mode otonom
  python main.py world-step                              # majukan dunia 1 hari tanpa agent
  python main.py autopilot-reset
  python main.py db-setup | db-load                      # PostgreSQL (markdown/database.md)
"""

import argparse
import sys
import time
from collections import Counter
from datetime import date

sys.stdout.reconfigure(encoding="utf-8")


def cmd_generate(args):
    from data_gen.generate_data import generate_and_save
    import config
    meta = generate_and_save(args.customers, args.seed, date.fromisoformat(args.ref_date) if args.ref_date else None)
    print(f"Data dummy dibuat (reference_date={meta['reference_date']}):")
    for k, v in meta["counts"].items():
        print(f"  {k:<22} {v:>8,}")
    if config.DATA_BACKEND == "postgres":
        print("DATA_BACKEND=postgres → memuat ke database...")
        cmd_db_load(args)


def cmd_db_setup(_):
    from bank_data.db_admin import setup
    setup()
    print("Selesai. Lanjut: python main.py db-load")


def cmd_db_load(_):
    from bank_data.db_admin import load_from_json
    t0 = time.perf_counter()
    load_from_json()
    print(f"Database terisi dalam {time.perf_counter() - t0:.1f} dtk.")


def print_result(state):
    print(f"\n=== {state['customer_id']}  |  sim_date {state['sim_date']} ===")
    print(f"Objective: {state['objective']}")
    print("\n--- Jejak agent ---")
    for t in state["trace"]:
        tag = " [LLM]" if t["llm"] else ""
        dur = f" ({t['duration_ms']} ms)" if "duration_ms" in t else ""
        print(f"[{t['ts']}] {t['agent']}{tag}: {t['action']}{dur}")
        for line in t["detail"].splitlines():
            print(f"      {line}")
    print("\n--- Analisa ---")
    for n in state.get("analyst_notes", []):
        print(f"* {n['title']}: {n['analysis']}")
    print("\n--- Pesan ke nasabah ---")
    for m in state.get("messages", []):
        print(f"\n[{m['severity'].upper()}] {m['title']}   ({m['source']})")
        print(m["body"])
        print(f"👉 {m['cta']}\n{m['footer']}")
    if not state.get("messages"):
        print("(tidak ada pesan)")
    print("\n--- Status pengiriman ---")
    for d in state.get("deliveries", []):
        print(f"  {d['insight_id']}: {d['status']} {d['channels']}")


def cmd_run(args):
    from graph.workflow import run_customer
    from llm import llm_status
    print(f"LLM: {llm_status()}")
    print_result(run_customer(args.customer, args.objective))


def cmd_batch(args):
    from bank_data.repository import get_repo
    from graph.workflow import run_customer
    from llm import llm_status
    print(f"LLM: {llm_status()}")
    customers = get_repo().list_customers()[: args.limit or None]
    codes, sent, t0 = Counter(), 0, time.perf_counter()
    for i, c in enumerate(customers, 1):
        st = run_customer(c["customer_id"], args.objective)
        codes.update(x["code"] for x in st.get("insights", []))
        sent += sum(1 for d in st.get("deliveries", []) if d["status"] in ("sent", "scheduled"))
        print(f"\r{i}/{len(customers)} nasabah diproses", end="", flush=True)
    print(f"\nSelesai dalam {time.perf_counter() - t0:.1f} dtk. Pesan baru: {sent}")
    print("Insight per kode:")
    for code, n in codes.most_common():
        print(f"  {code:<24} {n:>5}")


def cmd_ask(args):
    from agents.data_chat import ask
    answer, calls = ask(args.question)
    for c in calls:
        print(f"  🔧 {c}")
    print(answer)


def cmd_autopilot(args):
    from autonomy.autopilot import run
    from llm import llm_status
    print(f"LLM: {llm_status()} | {'terus-menerus' if args.days <= 0 else f'{args.days} hari'}, jeda {args.interval} dtk")
    print("Feed aktivitas: data/autopilot/activity.jsonl (atau tab Autopilot di UI). Ctrl+C / tombol Stop untuk berhenti.")
    run(args.days, args.interval)


def cmd_world_step(_):
    from autonomy.world import World
    from bank_data.repository import get_repo
    events = World(get_repo()).step()
    print(f"Tanggal simulasi sekarang {get_repo().reference_date()}, {len(events)} kejadian:")
    for e in events[:40]:
        print(f"  {e['customer_id']} {e['type']}: {e['detail']}")


def cmd_autopilot_reset(_):
    from autonomy import store
    store.reset_all()
    print("Jejak autopilot dihapus (misi tetap). Catatan: data nasabah tidak dikembalikan; jalankan 'generate' untuk reset dunia.")


def cmd_telegram_test(_):
    import config
    from channels import telegram
    if not config.TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN belum diisi di .env (ambil dari @BotFather).")
        return
    if not config.TELEGRAM_DEMO_CHAT_ID:
        chats = telegram.find_chat_ids()
        if not chats:
            print("Belum ada pesan ke bot. Buka bot kamu di Telegram, klik START / kirim 'halo', lalu jalankan lagi.")
            return
        print("Chat id ditemukan — salin ke .env sebagai TELEGRAM_DEMO_CHAT_ID:")
        for c in chats:
            print(f"  TELEGRAM_DEMO_CHAT_ID={c['chat_id']}   ({c['nama']} @{c['username']})")
        return
    ok, info = telegram.send("✅ simpleAgent terhubung! Notifikasi dari agent akan masuk ke chat ini.")
    print(f"Kirim pesan tes: {info}")


def cmd_reset(_):
    from channels import outbox
    outbox.clear()
    print("Outbox dikosongkan.")


def main():
    ap = argparse.ArgumentParser(description="simpleAgent — mockup multi-agent personalisasi nasabah")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="buat data dummy JSON")
    g.add_argument("--customers", type=int, default=200)
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--ref-date")
    r = sub.add_parser("run", help="jalankan agent untuk 1 nasabah")
    r.add_argument("--customer", required=True)
    r.add_argument("--objective")
    b = sub.add_parser("batch", help="jalankan agent untuk banyak nasabah")
    b.add_argument("--limit", type=int, default=0)
    b.add_argument("--objective")
    a = sub.add_parser("ask", help="tanya Data Agent (butuh LLM)")
    a.add_argument("question")
    sub.add_parser("reset-outbox", help="kosongkan outbox")
    ap_ = sub.add_parser("autopilot", help="mode otonom: dunia bergerak & agent bekerja sendiri")
    ap_.add_argument("--days", type=int, default=0, help="jumlah hari simulasi (0 = terus)")
    ap_.add_argument("--interval", type=float, default=3.0, help="jeda antar hari (detik)")
    sub.add_parser("world-step", help="majukan dunia 1 hari tanpa agent")
    sub.add_parser("autopilot-reset", help="hapus jejak autopilot")
    sub.add_parser("telegram-test", help="cari chat id / kirim pesan tes Telegram")
    sub.add_parser("db-setup", help="buat role, database, tabel & hak akses PostgreSQL")
    sub.add_parser("db-load", help="isi PostgreSQL dari data/*.json")
    args = ap.parse_args()
    {"generate": cmd_generate, "run": cmd_run, "batch": cmd_batch, "ask": cmd_ask,
     "reset-outbox": cmd_reset,
     "telegram-test": cmd_telegram_test, "db-setup": cmd_db_setup, "db-load": cmd_db_load,
     "autopilot": cmd_autopilot, "world-step": cmd_world_step, "autopilot-reset": cmd_autopilot_reset}[args.cmd](args)


if __name__ == "__main__":
    main()
