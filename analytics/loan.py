"""Analisa cicilan pinjaman (rules.md A4)."""

from datetime import date

import config
from analytics.common import make_insight, rp, tgl

AGENT = "loan_analyst"


def analyze(ctx: dict, sim: date):
    savings = sum(a["balance"] for a in ctx.get("savings", {}).get("accounts", []))
    metrics, insights = [], []
    for loan in ctx.get("loans", []):
        due = date.fromisoformat(loan["next_due_date"])
        days = (due - sim).days
        enough = savings >= loan["monthly_installment"]
        metrics.append({"loan_id": loan["loan_id"], "type": loan["type"], "next_due_date": loan["next_due_date"],
                        "days_to_due": days, "installment": loan["monthly_installment"],
                        "autodebet": loan["autodebet"], "days_past_due": loan["days_past_due"],
                        "savings_balance": savings, "savings_covers_installment": enough,
                        "outstanding": loan["outstanding"], "remaining_months": loan["remaining_months"]})
        facts = {"pinjaman": f"{loan['product']} ({loan['type']})", "cicilan_bulanan": rp(loan["monthly_installment"]),
                 "tanggal_jatuh_tempo": tgl(due, with_day=True),
                 "autodebet": "aktif" if loan["autodebet"] else "tidak aktif"}
        if loan["days_past_due"] > 0:
            insights.append(make_insight(
                AGENT, "LOAN_OVERDUE", f"{loan['loan_id']}-{due:%Y%m}", "critical", "alert", 98,
                f"Cicilan {loan['type']} tertunggak {loan['days_past_due']} hari",
                {**facts, "hari_tunggakan": f"{loan['days_past_due']} hari"},
                "Segera lakukan pembayaran cicilan untuk menghindari denda dan menjaga riwayat kredit."))
        elif 0 <= days <= config.RULES["loan_due_days"] and (not loan["autodebet"] or not enough):
            facts["saldo_tabungan"] = "cukup" if enough else "kurang dari nominal cicilan"
            when = "hari ini" if days == 0 else f"{days} hari lagi"
            insights.append(make_insight(
                AGENT, "LOAN_DUE_SOON", f"{loan['loan_id']}-{due:%Y%m}", "warning", "reminder", 80,
                f"Cicilan {loan['type']} jatuh tempo {when}", {**facts, "sisa_hari": when},
                ("Pastikan saldo tabungan mencukupi sebelum tanggal jatuh tempo." if not enough else
                 "Bayar cicilan lewat app sebelum jatuh tempo, atau aktifkan autodebet agar otomatis.")))
    return {"loans": metrics}, insights
