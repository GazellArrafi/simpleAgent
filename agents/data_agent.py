"""Data Agent: satu-satunya agent yang membaca data nasabah (lewat tools). Hanya mengambil data yang
dibutuhkan analis yang ditugaskan supervisor (least data)."""

import time

import config
from agents.analysts import ANALYSTS
from agents.base import trace
from bank_data import tools as T
from bank_data.repository import get_repo

# kebutuhan data -> (tool, argumen tambahan)
NEED_TO_TOOL = {
    "profile": (T.get_customer_profile, {}),
    "cards": (T.get_credit_cards, {}),
    "statements": (T.get_cc_statements, {}),
    "cc_transactions": (T.get_cc_transactions, {"days": config.ANALYSIS_WINDOW_DAYS}),
    "savings": (T.get_savings_summary, {"days": 90}),
    "loans": (T.get_loans, {}),
    "offers": (T.get_offer_catalog, None),  # None = tool tanpa customer_id
}


def _size(value) -> str:
    if isinstance(value, list):
        return f"{len(value)} baris"
    if isinstance(value, dict) and "transactions" in value:
        return f"{len(value['accounts'])} rekening, {len(value['transactions'])} mutasi"
    return "1 record"


def build_context(customer_id: str, needs) -> tuple[dict, list[str]]:
    """Ambil data sesuai kebutuhan lewat tools. Return (context, daftar panggilan tool)."""
    repo = get_repo()
    pg = repo.backend == "postgres"
    context, calls = {}, []
    for need in needs:
        tool, extra = NEED_TO_TOOL[need]
        args = {} if extra is None else {"customer_id": customer_id, **extra}
        if pg:
            repo.start_query_log()
        context[need] = tool.invoke(args)
        calls.append(f"{tool.name}({', '.join(f'{k}={v}' for k, v in args.items())}) → {_size(context[need])}")
        if pg:  # tampilkan SQL yang benar-benar dieksekusi
            calls += [f"    SQL: {q[:220]}{'…' if len(q) > 220 else ''}" for q in repo.pop_query_log()]
    return context, calls


def node(state: dict) -> dict:
    started = time.perf_counter()
    needs = ["profile"]  # profil selalu dibutuhkan komunikator
    for name in state.get("plan", []):
        needs += [n for n in ANALYSTS[name].needs if n not in needs]
    context, calls = build_context(state["customer_id"], needs)
    return {"context": context,
            "trace": [trace("data_agent", f"ambil {len(needs)} jenis data", "\n".join(calls), started=started,
                            tools=[c.split("(")[0] for c in calls if not c.startswith(" ")])]}
