"""Analisa tagihan & riwayat pembayaran kartu kredit (rules.md A1)."""

from datetime import date

import config
from analytics.common import card_label, make_insight, rp, tgl

AGENT = "cc_billing_analyst"
R = config.RULES


def analyze(ctx: dict, sim: date):
    savings = sum(a["balance"] for a in ctx.get("savings", {}).get("accounts", []))
    metrics, insights = [], []
    for card in ctx.get("cards", []):
        sts = [s for s in ctx.get("statements", []) if s["card_id"] == card["card_id"]]
        if not sts:
            continue
        last = sts[-1]
        due = date.fromisoformat(last["due_date"])
        days_to_due = (due - sim).days
        remaining = max(0, last["total_due"] - last["paid_amount"])
        hist = sts[-6:]
        closed = [s for s in hist if s["status"] != "open"]
        streak = 0
        for s in reversed(closed):
            if s["status"] not in ("paid_minimum", "paid_partial"):
                break
            streak += 1
        late_count = sum(1 for s in hist if s["paid_late"])
        interest_6m = sum(s["interest"] for s in hist)
        fees_6m = sum(s["fees"] for s in hist)
        can_pay = savings >= remaining > 0
        m = {"card_id": card["card_id"], "statement_id": last["statement_id"], "status": last["status"],
             "due_date": last["due_date"], "days_to_due": days_to_due, "total_due": last["total_due"],
             "minimum_due": last["minimum_due"], "paid_amount": last["paid_amount"], "remaining": remaining,
             "days_past_due": last["days_past_due"], "min_payment_streak": streak, "late_count_6m": late_count,
             "interest_paid_6m": interest_6m, "fees_paid_6m": fees_6m, "autodebet": card["autodebet"],
             "savings_balance": savings, "savings_covers_bill": can_pay,
             "history": [s["status"] for s in hist]}
        metrics.append(m)

        base = {"kartu": card_label(card), "tanggal_jatuh_tempo": tgl(due, with_day=True),
                "total_tagihan": rp(last["total_due"]), "pembayaran_minimum": rp(last["minimum_due"]),
                "sisa_tagihan": rp(remaining)}
        if can_pay:
            base["saldo_tabungan_cukup"] = "ya, saldo tabungan cukup untuk melunasi"
        ref = last["statement_id"]

        if last["days_past_due"] > 0:
            fee = min(config.CC_LATE_FEE_CAP, round(last["total_due"] * config.CC_LATE_FEE_PCT, -2))
            insights.append(make_insight(
                AGENT, "CC_OVERDUE", ref, "critical", "alert", 100,
                f"Tagihan kartu kredit sudah lewat jatuh tempo {last['days_past_due']} hari",
                {**base, "hari_terlambat": f"{last['days_past_due']} hari", "denda_keterlambatan": rp(fee),
                 "bunga_per_bulan": "1,75%"},
                f"Segera bayar minimal {rp(max(0, last['minimum_due'] - last['paid_amount']))} hari ini "
                f"untuk menghentikan denda dan menjaga riwayat kredit (SLIK OJK)."))
        elif remaining > 0 and 0 <= days_to_due <= R["due_soon_days"]:
            critical = days_to_due <= R["due_critical_days"]
            when = "hari ini" if days_to_due == 0 else f"{days_to_due} hari lagi"
            insights.append(make_insight(
                AGENT, "CC_DUE_SOON", ref, "critical" if critical else "warning", "reminder",
                95 if critical else 85, f"Tagihan kartu kredit jatuh tempo {when}",
                {**base, "sisa_hari": when},
                f"Bayar penuh {rp(remaining)} sebelum {tgl(due)} agar bebas bunga 1,75%/bulan"
                + (", saldo tabungan Anda mencukupi." if can_pay else ".")))
        elif remaining > 0 and 0 <= days_to_due <= R["due_upcoming_days"]:
            insights.append(make_insight(
                AGENT, "CC_DUE_UPCOMING", ref, "info", "reminder", 45,
                f"Tagihan kartu kredit jatuh tempo {days_to_due} hari lagi",
                {**base, "sisa_hari": f"{days_to_due} hari lagi"},
                f"Siapkan pembayaran {rp(remaining)} sebelum {tgl(due)}."))

        if streak >= R["min_payment_streak"]:
            insights.append(make_insight(
                AGENT, "CC_MIN_PAYMENT_HABIT", card["card_id"], "warning", "education", 60,
                f"Pembayaran minimum {streak} bulan berturut-turut",
                {"kartu": card_label(card), "bulan_berturut_turut": f"{streak} bulan",
                 "bunga_dibayar_6_bulan": rp(interest_6m), "bunga_per_bulan": "1,75%",
                 "saldo_terpakai_sekarang": rp(card["current_balance"])},
                "Membayar minimum membuat sisa tagihan terus berbunga. Pertimbangkan bayar lebih dari minimum "
                "atau ubah sisa tagihan jadi cicilan tetap berbunga lebih rendah."))
        if late_count >= 1 and not card["autodebet"]:
            insights.append(make_insight(
                AGENT, "CC_AUTODEBET_SUGGEST", card["card_id"], "info", "education", 40,
                "Aktifkan autodebet agar tidak telat bayar",
                {"kartu": card_label(card), "telat_bayar_6_bulan": f"{late_count} kali",
                 "denda_dibayar_6_bulan": rp(fees_6m)},
                "Aktifkan autodebet dari rekening tabungan supaya tagihan terbayar otomatis tiap jatuh tempo."))
    return {"cards": metrics}, insights
