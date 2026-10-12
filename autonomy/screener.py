"""Screener portofolio: 'radar' murah (tanpa LLM) untuk menemukan nasabah yang perlu perhatian.
Manager memilih sendiri kriteria mana yang dipakai sesuai misinya."""

from datetime import date, timedelta

from analytics.common import rp
from autonomy import store
from bank_data.repository import get_repo
from channels import outbox

CRITERIA = {
    "cc_overdue": "Tagihan kartu kredit lewat jatuh tempo & belum bayar minimum",
    "cc_due_within_3_days": "Tagihan kartu kredit jatuh tempo ≤3 hari & belum lunas",
    "cc_limit_above_80pct": "Pemakaian limit kartu kredit ≥80%",
    "cc_declined_last_3_days": "Ada transaksi ditolak karena limit dalam 3 hari terakhir",
    "large_transaction_last_3_days": "Ada transaksi ≥Rp5 juta dalam 3 hari terakhir",
    "min_payment_streak": "Bayar minimum/sebagian ≥3 bulan berturut-turut",
    "loan_overdue": "Cicilan pinjaman tertunggak",
    "loan_due_within_5_days": "Cicilan pinjaman jatuh tempo ≤5 hari tanpa autodebet",
    "healthy_offer_candidate": "Nasabah sehat (selalu lunas, limit <30%, consent marketing) — kandidat penawaran",
}
WEIGHT = {"cc_overdue": 100, "loan_overdue": 98, "cc_declined_last_3_days": 90, "large_transaction_last_3_days": 80,
          "cc_due_within_3_days": 85, "loan_due_within_5_days": 75, "cc_limit_above_80pct": 70,
          "min_payment_streak": 50, "healthy_offer_candidate": 10}


def _check(c, repo, d: date) -> dict[str, str]:
    cid = c["customer_id"]
    hits = {}
    for card in repo.get_credit_cards(cid):
        sts = [s for s in repo.get_cc_statements(cid) if s["card_id"] == card["card_id"]]
        util = card["current_balance"] / card["credit_limit"]
        if sts:
            last = sts[-1]
            remaining = last["total_due"] - last["paid_amount"]
            days = (date.fromisoformat(last["due_date"]) - d).days
            if last["days_past_due"] > 0:
                hits["cc_overdue"] = f"telat {last['days_past_due']} hari, sisa {rp(remaining)}"
            elif remaining > 0 and 0 <= days <= 3:
                hits["cc_due_within_3_days"] = f"jatuh tempo {days} hari lagi, sisa {rp(remaining)}"
            streak = 0
            for s in reversed([s for s in sts[-6:] if s["status"] != "open"]):
                if s["status"] not in ("paid_minimum", "paid_partial"):
                    break
                streak += 1
            if streak >= 3:
                hits["min_payment_streak"] = f"{streak} bulan"
            closed = [s for s in sts[-6:] if s["status"] != "open"]
            if c["marketing_consent"] and util < 0.3 and closed and all(s["status"] in ("paid_full", "no_bill") for s in closed):
                hits["healthy_offer_candidate"] = f"limit terpakai {util:.0%}"
        if util >= 0.8:
            hits["cc_limit_above_80pct"] = f"{util:.0%} terpakai"
        recent = repo.get_cc_transactions(cid, days=3, until=d)
        declined = [t for t in recent if t["status"] == "declined"]
        if declined:
            hits["cc_declined_last_3_days"] = f"{len(declined)} transaksi ditolak"
        large = [t for t in recent if t["type"] == "purchase" and t["status"] == "approved" and t["amount"] >= 5_000_000]
        if large:
            hits["large_transaction_last_3_days"] = ", ".join(f"{t['merchant']} {rp(t['amount'])}" for t in large[:2])
    for loan in repo.get_loans(cid):
        days = (date.fromisoformat(loan["next_due_date"]) - d).days
        if loan["days_past_due"] > 0:
            hits["loan_overdue"] = f"{loan['type']} telat {loan['days_past_due']} hari"
        elif 0 <= days <= 5 and not loan["autodebet"]:
            hits["loan_due_within_5_days"] = f"{loan['type']} {days} hari lagi, cicilan {rp(loan['monthly_installment'])}"
    return hits


def scan(criteria: list[str], limit: int = 10) -> list[dict]:
    repo = get_repo()
    d = repo.reference_date()
    wanted = [c for c in criteria if c in CRITERIA] or list(CRITERIA)
    week_ago = (d - timedelta(days=7)).isoformat()
    contacts = {}
    for r in outbox.read_all():
        if r.get("sim_date", "") >= week_ago:
            contacts.setdefault(r["customer_id"], []).append(r["sim_date"])
    open_fu = {f["customer_id"] for f in store.list_followups("open")}
    rows = []
    for c in repo.list_customers():
        hits = {k: v for k, v in _check(c, repo, d).items() if k in wanted}
        if hits:
            rows.append({"customer_id": c["customer_id"], "nickname": c["nickname"], "segment": c["segment"],
                         "matched": hits, "score": sum(WEIGHT[k] for k in hits),
                         "messages_last_7_days": len(contacts.get(c["customer_id"], [])),
                         "last_contact": max(contacts.get(c["customer_id"], [""])) or None,
                         "has_open_followup": c["customer_id"] in open_fu})
    rows.sort(key=lambda r: -r["score"])
    return rows[:limit]
