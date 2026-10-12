"""Web UI simpleAgent (HTML/CSS/JS + API JSON, tanpa dependency tambahan).

  python web\\server.py [--port 8000] [--host 127.0.0.1]

Detail rancangan: markdown/webui.md
"""

import argparse
import json
import mimetypes
import re
import subprocess
import sys
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import config  # noqa: E402
from agents.analysts import ANALYSTS  # noqa: E402
from agents.supervisor import DEFAULT_OBJECTIVE  # noqa: E402
from llm import is_online, llm_status  # noqa: E402

NODES = [{"id": "supervisor_plan", "label": "Supervisor · rencana", "group": "core"},
         {"id": "data_agent", "label": "Data Agent", "group": "core"},
         *[{"id": n, "label": a.title, "group": "analyst"} for n, a in ANALYSTS.items()],
         {"id": "supervisor_review", "label": "Supervisor · review", "group": "core"},
         {"id": "communicator", "label": "Communicator", "group": "core"},
         {"id": "delivery", "label": "Delivery", "group": "core"}]


# ---------------------------------------------------------------- helpers
def repo():
    from bank_data.repository import get_repo
    return get_repo()


def data_ready() -> bool:
    if config.DATA_BACKEND == "postgres":
        try:
            repo()
            return True
        except Exception:
            return False
    return (config.DATA_DIR / "meta.json").exists()


def _default(o):
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if isinstance(o, Decimal):
        return int(o) if o == o.to_integral_value() else float(o)
    if isinstance(o, set):
        return list(o)
    return str(o)


def autopilot_alive(state: dict) -> bool:
    hb = state.get("heartbeat")
    return bool(state.get("running") and hb and (datetime.now() - datetime.fromisoformat(hb)).total_seconds() < 15)


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------- jobs (proses lama di thread latar)
JOBS: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_job_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="job")


def start_job(kind: str, fn) -> str:
    job_id = uuid.uuid4().hex[:10]
    job = {"id": job_id, "kind": kind, "status": "running", "steps": [], "plan": None, "progress": None,
           "result": None, "error": None, "started_at": datetime.now().isoformat(timespec="seconds")}
    with _jobs_lock:
        JOBS[job_id] = job
        for old in sorted(JOBS.values(), key=lambda j: j["started_at"])[:-30]:  # simpan 30 job terakhir saja
            JOBS.pop(old["id"], None)

    def wrapper():
        try:
            job["result"] = fn(job)
            job["status"] = "done"
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            job["error"] = f"{type(e).__name__}: {e}"
            job["status"] = "error"

    _job_pool.submit(wrapper)
    return job_id


def job_run(customer_id: str, objective: str):
    from graph.workflow import run_customer

    def fn(job):
        def on_update(node, update):
            if isinstance(update, dict) and "plan" in update:
                job["plan"] = update["plan"]
            job["steps"].append(node)
        return run_customer(customer_id, objective, on_update=on_update)
    return fn


def job_batch(limit: int, objective: str):
    from graph.workflow import run_customer

    def fn(job):
        targets = repo().list_customers()[:limit]
        sent = 0
        for i, c in enumerate(targets, 1):
            res = run_customer(c["customer_id"], objective)
            sent += sum(1 for d in res.get("deliveries", []) if d["status"] != "duplicate_skipped")
            job["progress"] = {"done": i, "total": len(targets), "label": c["full_name"]}
        return {"processed": len(targets), "sent": sent}
    return fn


def job_generate(n: int, seed: int):
    def fn(job):
        from bank_data.repository import reload_repo
        from data_gen.generate_data import generate_and_save
        job["steps"].append("generate")
        meta = generate_and_save(n, seed)
        if config.DATA_BACKEND == "postgres":
            from bank_data.db_admin import load_from_json
            job["steps"].append("db_load")
            load_from_json(log=lambda *_: None)
        reload_repo()
        return meta
    return fn


# ---------------------------------------------------------------- handlers API
def api_status(_q, _b):
    out = {"llm": llm_status(), "online": is_online(), "backend": config.DATA_BACKEND, "ready": data_ready(),
           "default_objective": DEFAULT_OBJECTIVE, "nodes": NODES}
    if out["ready"]:
        R = repo()
        out["sim_date"] = R.reference_date()
        out["counts"] = R.meta["counts"]
    return out


def api_customers(_q, _b):
    keys = ("customer_id", "full_name", "segment", "city", "occupation", "demo_persona")
    return [{k: c.get(k) for k in keys} for c in repo().list_customers()]


def _customer_or_404(cid):
    cust = repo().get_customer(cid)
    if not cust:
        raise ApiError(404, f"Nasabah {cid} tidak ditemukan")
    return cust


def api_customer(_q, _b, cid):
    R = repo()
    cust = _customer_or_404(cid)
    return {"profile": cust, "credit_cards": R.get_credit_cards(cid), "statements": R.get_cc_statements(cid),
            "savings": R.get_savings_accounts(cid), "loans": R.get_loans(cid)}


def _days(q, default):
    try:
        return max(1, min(int(q.get("days", [default])[0]), 400))
    except ValueError:
        raise ApiError(400, "days harus angka") from None


def api_cc_tx(q, _b, cid):
    _customer_or_404(cid)
    return repo().get_cc_transactions(cid, days=_days(q, 30))


def api_sav_tx(q, _b, cid):
    _customer_or_404(cid)
    return repo().get_savings_transactions(cid, days=_days(q, 60))


def api_inbox(_q, _b, cid):
    from channels import outbox
    return sorted(outbox.for_customer(cid), key=lambda r: str(r["created_at"]), reverse=True)


def api_run(_q, b):
    cid = str(b.get("customer_id", "")).strip().upper()
    _customer_or_404(cid)
    objective = (b.get("objective") or "").strip() or DEFAULT_OBJECTIVE
    return {"job_id": start_job("run", job_run(cid, objective))}


def api_batch(_q, b):
    total = len(repo().list_customers())
    limit = max(1, min(int(b.get("limit") or 20), total))
    objective = (b.get("objective") or "").strip() or DEFAULT_OBJECTIVE
    return {"job_id": start_job("batch", job_batch(limit, objective))}


def api_generate(_q, b):
    n = max(8, min(int(b.get("customers") or 200), 5000))
    seed = max(0, min(int(b.get("seed") or 42), 99999))
    return {"job_id": start_job("generate", job_generate(n, seed))}


def api_job(_q, _b, job_id):
    job = JOBS.get(job_id)
    if not job:
        raise ApiError(404, "Job tidak ditemukan (server mungkin di-restart)")
    return job


def api_ask(_q, b):
    if not is_online():
        raise ApiError(400, "Fitur ini butuh LLM. Isi MODEL_NAME dan API key di .env.")
    question = (b.get("question") or "").strip()
    if not question:
        raise ApiError(400, "Pertanyaan kosong")
    from agents.data_chat import ask
    history = [{"role": m["role"], "content": m["content"]} for m in (b.get("history") or [])
               if m.get("role") in ("user", "assistant")][-6:]
    answer, calls = ask(question, history)
    return {"answer": answer, "calls": calls}


def api_outbox(_q, _b):
    from channels import outbox
    rows = sorted(outbox.read_all(), key=lambda r: str(r["created_at"]), reverse=True)
    return {"rows": rows, "summary": {"total": len(rows), "customers": len({r["customer_id"] for r in rows}),
                                      "llm": sum(1 for r in rows if r.get("source") == "llm")}}


def api_outbox_clear(_q, b):
    from channels import outbox
    outbox.clear(b.get("customer_id") or None)
    return {"ok": True}


def api_autopilot(_q, _b):
    from autonomy import store as ap
    state = ap.get_state()
    return {"state": state, "alive": autopilot_alive(state), "mission": ap.load_mission(),
            "activity": ap.read_activity(200)[::-1], "reports": ap.read_reports()[-7:][::-1],
            "followups": ap.list_followups("open"), "events": ap.read_events(60)[::-1],
            "sim_date": state.get("sim_date") or (repo().reference_date() if data_ready() else None)}


def api_autopilot_start(_q, b):
    from autonomy import store as ap
    if autopilot_alive(ap.get_state()):
        raise ApiError(409, "Autopilot sudah berjalan")
    days = max(0, min(int(b.get("days", 7)), 365))
    interval = max(0.0, min(float(b.get("interval", 5)), 300.0))
    ap.DIR.mkdir(parents=True, exist_ok=True)
    log = (ap.DIR / "autopilot.log").open("a", encoding="utf-8")
    subprocess.Popen([sys.executable, "main.py", "autopilot", "--days", str(days), "--interval", str(interval)],
                     cwd=config.BASE_DIR, stdout=log, stderr=subprocess.STDOUT,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return {"ok": True}


def api_autopilot_stop(_q, _b):
    from autonomy import store as ap
    ap.request_stop()
    return {"ok": True}


def api_autopilot_reset(_q, _b):
    from autonomy import store as ap
    if autopilot_alive(ap.get_state()):
        raise ApiError(409, "Hentikan autopilot dulu sebelum reset")
    ap.reset_all()
    return {"ok": True}


def api_autopilot_mission(_q, b):
    from autonomy import store as ap
    ap.save_mission({"goal": str(b.get("goal", "")).strip(), "constraints": str(b.get("constraints", "")).strip(),
                     "max_cases_per_day": max(1, min(int(b.get("max_cases_per_day", 5)), 30))})
    return {"ok": True}


CID = r"([A-Za-z0-9_-]+)"
ROUTES = [
    ("GET", r"/api/status", api_status),
    ("GET", r"/api/customers", api_customers),
    ("GET", rf"/api/customers/{CID}", api_customer),
    ("GET", rf"/api/customers/{CID}/cc-transactions", api_cc_tx),
    ("GET", rf"/api/customers/{CID}/savings-transactions", api_sav_tx),
    ("GET", rf"/api/customers/{CID}/inbox", api_inbox),
    ("POST", r"/api/run", api_run),
    ("POST", r"/api/batch", api_batch),
    ("POST", r"/api/generate", api_generate),
    ("GET", r"/api/jobs/([0-9a-f]+)", api_job),
    ("POST", r"/api/ask", api_ask),
    ("GET", r"/api/outbox", api_outbox),
    ("POST", r"/api/outbox/clear", api_outbox_clear),
    ("GET", r"/api/autopilot", api_autopilot),
    ("POST", r"/api/autopilot/start", api_autopilot_start),
    ("POST", r"/api/autopilot/stop", api_autopilot_stop),
    ("POST", r"/api/autopilot/reset", api_autopilot_reset),
    ("POST", r"/api/autopilot/mission", api_autopilot_mission),
]
ROUTES = [(m, re.compile(p + r"/?$"), fn) for m, p, fn in ROUTES]


# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "simpleAgentWeb/1.0"

    def log_message(self, fmt, *args):
        if "/api/jobs/" not in self.path and "/api/autopilot" != self.path:  # polling tidak perlu di-log
            sys.stderr.write(f"{self.log_date_time_string()}  {fmt % args}\n")

    def _send(self, status: int, body: bytes, ctype: str, cache=False):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=60" if cache else "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj):
        self._send(status, json.dumps(obj, default=_default, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _api(self, method: str):
        url = urlparse(self.path)
        for m, pattern, fn in ROUTES:
            match = pattern.match(url.path)
            if match and m == method:
                break
        else:
            return self._json(404, {"error": "Endpoint tidak ada"})
        try:
            body = {}
            if method == "POST":
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                body = json.loads(raw or b"{}")
            self._json(200, fn(parse_qs(url.query), body, *match.groups()))
        except ApiError as e:
            self._json(e.status, {"error": str(e)})
        except (ValueError, TypeError) as e:
            self._json(400, {"error": f"Input tidak valid: {e}"})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._json(500, {"error": f"{type(e).__name__}: {e}"})

    def _static(self):
        path = urlparse(self.path).path
        target = (STATIC / (path.lstrip("/") or "index.html")).resolve()
        if not target.is_relative_to(STATIC) or not target.is_file():
            target = STATIC / "index.html"
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)

    def do_GET(self):
        if self.path.startswith("/api/"):
            self._api("GET")
        else:
            self._static()

    def do_POST(self):
        if self.path.startswith("/api/"):
            self._api("POST")
        else:
            self._json(405, {"error": "Method tidak didukung"})


class PooledServer(ThreadingHTTPServer):
    """Request ditangani thread pool tetap → koneksi Postgres per-thread tidak bertambah terus."""
    daemon_threads = True
    pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="http")

    def process_request(self, request, client_address):
        self.pool.submit(self.process_request_thread, request, client_address)


def main():
    p = argparse.ArgumentParser(description="Web UI simpleAgent")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    args = p.parse_args()
    srv = PooledServer((args.host, args.port), Handler)
    print(f"simpleAgent web UI → http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}")
    print(f"LLM: {llm_status()} · data: {config.DATA_BACKEND}  (Ctrl+C untuk berhenti)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nBerhenti.")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
