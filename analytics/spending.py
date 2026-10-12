"""Analisa pola belanja kartu kredit (rules.md A3)."""

from collections import defaultdict
from datetime import date, timedelta
from statistics import median

import config
from analytics.common import CATEGORY_ID, make_insight, pct, purchases, rp, tgl, to_dt

AGENT = "spending_analyst"
R = config.RULES


def _by_cat(txs):
    out = defaultdict(int)
    for t in txs:
        out[t["category"]] += t["amount"]
    return out


def analyze(ctx: dict, sim: date):
    income = ctx.get("profile", {}).get("monthly_income", 0)
    buys = purchases(ctx.get("cc_transactions", []))
    if not buys:
        return {"note": "tidak ada transaksi belanja"}, []
    cut30, cut120 = sim - timedelta(days=30), sim - timedelta(days=120)
    last30 = [t for t in buys if to_dt(t["datetime"]).date() > cut30]
    base = [t for t in buys if cut120 < to_dt(t["datetime"]).date() <= cut30]
    total30 = sum(t["amount"] for t in last30)
    base_monthly = sum(t["amount"] for t in base) / 3
    cat30, cat_base = _by_cat(last30), {k: v / 3 for k, v in _by_cat(base).items()}
    deltas = sorted(((c, v - cat_base.get(c, 0)) for c, v in cat30.items()), key=lambda x: -x[1])
    merchants = defaultdict(int)
    for t in last30:
        merchants[t["merchant"]] += t["amount"]
    top_merchants = sorted(merchants.items(), key=lambda x: -x[1])[:5]
    foreign = [t for t in last30 if t.get("currency", "IDR") != "IDR"]

    subs = defaultdict(list)
    for t in buys:
        if t["is_recurring"] and to_dt(t["datetime"]).date() > sim - timedelta(days=90):
            subs[t["merchant"]].append(t["amount"])
    subscriptions = {m: a[-1] for m, a in subs.items() if len(a) >= 2}

    med = median(t["amount"] for t in buys)
    known = {t["merchant"] for t in buys if to_dt(t["datetime"]).date() <= cut30}
    big = max(R["unusual_multiplier"] * med, R["unusual_min_amount"])
    unusual = [t for t in last30 if not t["is_recurring"] and (
        (t["amount"] >= big and t["merchant"] not in known)  # nominal besar di merchant yang belum pernah dipakai
        or (t.get("currency", "IDR") != "IDR" and to_dt(t["datetime"]).hour < 5 and t["channel"] == "online"))]

    metrics = {"spend_30d": total30, "baseline_monthly": round(base_monthly),
               "change_pct": round(total30 / base_monthly - 1, 3) if base_monthly else None,
               "by_category_30d": dict(sorted(cat30.items(), key=lambda x: -x[1])),
               "top_merchants_30d": top_merchants, "foreign_tx_30d": len(foreign),
               "subscriptions": subscriptions, "median_tx": med,
               "unusual": [{k: t[k] for k in ("txn_id", "datetime", "merchant", "amount", "location")} for t in unusual],
               "spend_to_income": round(total30 / income, 3) if income else None}

    insights = []
    if base_monthly and total30 >= base_monthly * (1 + R["spike_pct"]) and total30 - base_monthly >= R["spike_min_delta"]:
        change = total30 / base_monthly - 1
        tops = [f"{CATEGORY_ID.get(c, c)} (+{rp(d)})" for c, d in deltas[:2] if d > 0]
        insights.append(make_insight(
            AGENT, "SPENDING_SPIKE", f"{sim:%Y%m%d}", "warning" if change >= R["spike_warning_pct"] else "info",
            "education", 58, f"Belanja 30 hari terakhir naik {pct(change)}",
            {"belanja_30_hari": rp(total30), "rata_rata_bulanan_sebelumnya": rp(base_monthly),
             "kenaikan": pct(change), "kategori_naik_terbesar": ", ".join(tops)},
            "Cek kembali pengeluaran terbesar bulan ini dan sesuaikan anggaran agar tagihan berikutnya tetap terkendali."))
    if income and total30 >= R["spend_income_ratio"] * income:
        insights.append(make_insight(
            AGENT, "SPENDING_VS_INCOME", f"{sim:%Y%m%d}", "warning", "education", 55,
            "Belanja kartu kredit bulan ini sudah tinggi dibanding penghasilan",
            {"belanja_30_hari": rp(total30), "porsi_dari_penghasilan": pct(total30 / income)},
            "Idealnya cicilan & belanja kredit di bawah 30-40% penghasilan. Prioritaskan kebutuhan pokok."))
    if unusual:
        u = unusual[:2]
        insights.append(make_insight(
            AGENT, "UNUSUAL_TRANSACTION", u[0]["txn_id"], "warning", "alert", 75,
            "Ada transaksi kartu kredit yang tidak biasa",
            {"transaksi": "; ".join(f"{t['merchant']} {rp(t['amount'])} pada {tgl(t['datetime'])} "
                                     f"pukul {to_dt(t['datetime']):%H:%M}" for t in u)},
            "Jika Anda tidak merasa melakukan transaksi ini, blokir kartu sementara lewat app dan hubungi call center resmi."))
    if len(subscriptions) >= 2:
        insights.append(make_insight(
            AGENT, "SUBSCRIPTION_SUMMARY", f"{sim:%Y%m}", "info", "education", 20,
            f"Anda punya {len(subscriptions)} langganan bulanan di kartu kredit",
            {"langganan": ", ".join(f"{m} {rp(a)}" for m, a in subscriptions.items()),
             "total_per_bulan": rp(sum(subscriptions.values()))},
            "Tinjau langganan yang jarang dipakai supaya pengeluaran rutin lebih hemat."))
    return metrics, insights
