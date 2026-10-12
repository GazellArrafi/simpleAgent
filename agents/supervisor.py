"""Supervisor: (1) membuat rencana — analis mana yang ditugaskan, (2) mereview hasil analis —
prioritas, batas jumlah pesan, menahan penawaran bila ada tunggakan (rules.md B)."""

import time

from pydantic import BaseModel, Field

import config
from agents.analysts import ANALYSTS
from agents.base import to_json, trace
from analytics.common import SEVERITY_RANK
from bank_data.tools import get_customer_overview
from llm import structured

DEFAULT_OBJECTIVE = "Personalisasi menyeluruh: ingatkan hal penting soal tagihan, limit, cicilan, dan beri saran yang relevan."

PLAN_SYSTEM = """Kamu adalah Supervisor tim analis personalisasi nasabah di sebuah bank Indonesia.
Tugasmu memilih analis mana yang perlu ditugaskan untuk nasabah ini, berdasarkan ringkasan produk nasabah
dan OBJECTIVE dari operator. Pilih seminimal mungkin tapi jangan lewatkan analis yang relevan dengan objective.
Analis bertanda (TIDAK TERSEDIA) tidak boleh dipilih. Jelaskan alasanmu singkat (1-2 kalimat, Bahasa Indonesia)."""


class Plan(BaseModel):
    analysts: list[str] = Field(description="Nama analis yang ditugaskan, persis seperti di daftar")
    reason: str = Field(description="Alasan singkat pemilihan")


def plan_node(state: dict) -> dict:
    started = time.perf_counter()
    cid = state["customer_id"]
    objective = state.get("objective") or DEFAULT_OBJECTIVE
    overview = get_customer_overview.invoke({"customer_id": cid})
    eligible = [n for n, a in ANALYSTS.items() if a.eligible(overview)]
    catalog = "\n".join(f"- {n}: {a.description}" + ("" if n in eligible else " (TIDAK TERSEDIA)")
                        for n, a in ANALYSTS.items())
    user = f"OBJECTIVE: {objective}\n\nRINGKASAN NASABAH:\n{to_json(overview)}\n\nDAFTAR ANALIS:\n{catalog}"
    out, err = structured(Plan, PLAN_SYSTEM, user)

    used_llm = bool(out)
    chosen = [a for a in dict.fromkeys(out.analysts) if a in eligible] if out else []
    if chosen:
        reason = out.reason.strip()
        rejected = [a for a in out.analysts if a not in eligible]
        if rejected:
            reason += f" (diabaikan karena tidak relevan dengan produk nasabah: {', '.join(rejected)})"
    else:
        chosen, used_llm = eligible, False
        reason = "Mode aturan: semua analis yang relevan dengan produk nasabah ditugaskan."
        if err and err != "offline":
            reason += f" (LLM gagal: {err})"
    return {
        "objective": objective, "overview": overview, "plan": chosen, "plan_reason": reason,
        "trace": [
            trace("supervisor", "minta overview ke data_agent", f"get_customer_overview({cid})", tools=["get_customer_overview"]),
            trace("supervisor", f"menugaskan {len(chosen)} analis", f"{', '.join(chosen) or '-'}\nAlasan: {reason}",
                  llm=used_llm, started=started),
        ],
    }


def review_node(state: dict) -> dict:
    started = time.perf_counter()
    insights = state.get("insights", [])
    cap = config.RULES["max_messages_per_run"]
    delinquent = any(i["code"] in ("CC_OVERDUE", "LOAN_OVERDUE") for i in insights)
    held, candidates = [], []
    for i in insights:
        if not i["notify"]:
            held.append({**i, "hold_reason": "catatan internal (notify=false)"})
        elif i["category"] == "offer" and delinquent:
            held.append({**i, "hold_reason": "penawaran ditahan karena nasabah punya tunggakan"})
        else:
            candidates.append(i)
    candidates.sort(key=lambda i: (-SEVERITY_RANK[i["severity"]], -i["priority"]))
    selected = candidates[:cap]
    held += [{**i, "hold_reason": f"melebihi batas {cap} pesan per run"} for i in candidates[cap:]]
    detail = "Dikirim: " + (", ".join(i["code"] for i in selected) or "-")
    if held:
        detail += "\nDitahan: " + ", ".join(f"{i['code']} ({i['hold_reason']})" for i in held)
    return {"selected": selected, "held": held,
            "trace": [trace("supervisor", f"review {len(insights)} insight → {len(selected)} dikirim", detail,
                            started=started)]}
