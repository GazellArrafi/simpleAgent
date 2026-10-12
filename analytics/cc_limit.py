"""Analisa pemakaian & proyeksi limit kartu kredit (rules.md A2)."""

from calendar import monthrange
from datetime import date, timedelta

import config
from analytics.common import card_label, make_insight, pct, purchases, rp, tgl, to_dt

AGENT = "cc_limit_analyst"
R = config.RULES


def _next_statement(statement_day: int, sim: date) -> date:
    after = sim + timedelta(days=1)
    for y, m in [(after.year, after.month), (after.year + (after.month == 12), after.month % 12 + 1)]:
        d = date(y, m, min(statement_day, monthrange(y, m)[1]))
        if d >= after:
            return d
    raise ValueError("tanggal cetak tagihan tidak valid")


def analyze(ctx: dict, sim: date):
    metrics, insights = [], []
    since = sim - timedelta(days=30)
    for card in ctx.get("cards", []):
        limit, bal = card["credit_limit"], card["current_balance"]
        util = bal / limit if limit else 0
        txs = [t for t in ctx.get("cc_transactions", []) if t["card_id"] == card["card_id"]]
        recent = [t for t in txs if to_dt(t["datetime"]).date() > since]
        spend_30 = sum(t["amount"] for t in purchases(recent))
        declined = [t for t in recent if t["status"] == "declined"]
        daily = spend_30 / 30
        next_stmt = _next_statement(card["statement_day"], sim)
        days_to_stmt = (next_stmt - sim).days
        projected = bal + daily * days_to_stmt
        days_until_full = (limit - bal) / daily if daily > 0 else None
        m = {"card_id": card["card_id"], "credit_limit": limit, "current_balance": bal,
             "available_limit": limit - bal, "utilization": round(util, 4), "spend_30d": spend_30,
             "avg_daily_spend": round(daily), "declined_30d": len(declined),
             "declined_amount_30d": sum(t["amount"] for t in declined), "next_statement_date": next_stmt.isoformat(),
             "projected_balance_at_statement": round(projected),
             "days_until_limit_full": round(days_until_full, 1) if days_until_full is not None else None}
        metrics.append(m)

        base = {"kartu": card_label(card), "limit_kartu": rp(limit), "limit_terpakai": rp(bal),
                "sisa_limit": rp(max(0, limit - bal)), "persentase_terpakai": pct(util)}
        if util >= R["util_critical"] or declined:
            facts = dict(base)
            if declined:
                facts["transaksi_ditolak_30_hari"] = f"{len(declined)} transaksi ({rp(m['declined_amount_30d'])})"
            insights.append(make_insight(
                AGENT, "CC_LIMIT_CRITICAL", f"{card['card_id']}-{sim:%Y%m%d}", "critical", "alert", 90,
                f"Limit kartu kredit {'sudah terlampaui' if util >= 1 else 'hampir habis'} ({pct(util)} terpakai)", facts,
                "Lakukan pembayaran sebagian untuk memulihkan limit, dan tunda transaksi besar sampai limit tersedia."))
        elif util >= R["util_high"]:
            insights.append(make_insight(
                AGENT, "CC_LIMIT_HIGH", f"{card['card_id']}-{sim:%Y%m%d}", "warning", "alert", 70,
                f"Pemakaian limit kartu kredit sudah {pct(util)}", base,
                "Pantau pengeluaran agar transaksi penting tidak tertolak; bayar sebagian lebih awal bila perlu."))
        elif projected > limit and days_until_full is not None:
            full_date = sim + timedelta(days=int(days_until_full))
            insights.append(make_insight(
                AGENT, "CC_LIMIT_PROJECTION", f"{card['card_id']}-{sim:%Y%m%d}", "warning", "alert", 65,
                "Dengan pola belanja sekarang, limit diperkirakan habis sebelum tagihan berikutnya",
                {**base, "rata_rata_belanja_harian": rp(daily),
                 "perkiraan_limit_habis": f"sekitar {tgl(full_date)} ({int(days_until_full)} hari lagi)",
                 "tanggal_cetak_tagihan_berikutnya": tgl(next_stmt)},
                "Atur ulang prioritas belanja beberapa minggu ke depan atau bayar sebagian tagihan lebih awal."))
    return {"cards": metrics}, insights
