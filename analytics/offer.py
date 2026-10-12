"""Next-best-offer: cocokkan katalog penawaran dengan profil & perilaku nasabah (rules.md A5)."""

from collections import defaultdict
from datetime import date, timedelta

from analytics.common import make_insight, pct, purchases, to_dt

AGENT = "offer_analyst"
MIN_SCORE = 40


def _features(ctx, sim):
    profile = ctx.get("profile", {})
    cards, sts, loans = ctx.get("cards", []), ctx.get("statements", []), ctx.get("loans", [])
    buys = [t for t in purchases(ctx.get("cc_transactions", [])) if to_dt(t["datetime"]).date() > sim - timedelta(days=90)]
    total = sum(t["amount"] for t in buys) or 1
    share = defaultdict(float)
    for t in buys:
        share[t["category"]] += t["amount"] / total
    recent_sts = sts[-6:]
    closed = [s for s in recent_sts if s["status"] != "open"]
    util = max((c["current_balance"] / c["credit_limit"] for c in cards), default=0)
    return {
        "has_card": bool(cards),
        "category_share_90d": dict(share),
        "foreign_tx_90d": sum(1 for t in buys if t.get("currency", "IDR") != "IDR"),
        "max_utilization": util,
        "min_payments_6m": sum(1 for s in closed if s["status"] in ("paid_minimum", "paid_partial")),
        "late_6m": sum(1 for s in recent_sts if s["paid_late"]),
        "all_paid_full": bool(closed) and all(s["status"] in ("paid_full", "no_bill") for s in closed),
        "any_no_autodebet": any(not c["autodebet"] for c in cards),
        "delinquent": any(s["days_past_due"] > 0 for s in sts[-1:]) or any(l["days_past_due"] > 0 for l in loans),
        "savings": sum(a["balance"] for a in ctx.get("savings", {}).get("accounts", [])),
        "income": profile.get("monthly_income", 0),
        "segment": profile.get("segment"),
    }


def _score(offer, f):
    t = offer["target"]
    if offer["is_credit_product"] and f["delinquent"]:
        return 0, "ditahan: nasabah punya tunggakan (responsible lending)"
    if "segments" in t and f["segment"] not in t["segments"]:
        return 0, "segmen tidak cocok"
    score, why = 0.0, []
    if "categories" in t:
        s = sum(f["category_share_90d"].get(c, 0) for c in t["categories"])
        if s >= 0.15:
            score += s * 150
            why.append(f"porsi belanja {'/'.join(t['categories'])} {pct(s)}")
    if t.get("foreign") and f["foreign_tx_90d"] >= 3:
        score += 40
        why.append(f"{f['foreign_tx_90d']} transaksi luar negeri")
    if t.get("revolver") and f["has_card"] and (f["min_payments_6m"] >= 2 or f["max_utilization"] >= 0.7):
        score += 80
        why.append("sering bayar minimum / limit tinggi")
    if t.get("no_autodebet") and f["any_no_autodebet"]:
        score += 60 if f["late_6m"] else 25
        why.append("autodebet belum aktif")
    if t.get("healthy") and f["all_paid_full"] and f["max_utilization"] < 0.3 and f["income"] >= t.get("min_income", 0):
        score += 70
        why.append("selalu bayar lunas & pemakaian limit rendah")
    if "min_savings" in t:
        if f["savings"] >= t["min_savings"]:
            score += 50
            why.append("saldo tabungan besar")
        else:
            return 0, "saldo belum memenuhi"
    return round(score), ", ".join(why)


def analyze(ctx: dict, sim: date):
    profile = ctx.get("profile", {})
    if not profile.get("marketing_consent"):
        return {"skipped": "nasabah tidak memberi consent marketing"}, []
    f = _features(ctx, sim)
    scored = sorted(((o, *_score(o, f)) for o in ctx.get("offers", [])), key=lambda x: -x[1])
    metrics = {"features": {k: v for k, v in f.items() if k != "category_share_90d"},
               "top_categories_90d": dict(sorted(f["category_share_90d"].items(), key=lambda x: -x[1])[:4]),
               "scores": [{"offer_id": o["offer_id"], "name": o["name"], "score": s, "reason": r} for o, s, r in scored]}
    best, score, reason = scored[0] if scored else (None, 0, "")
    if not best or score < MIN_SCORE:
        return metrics, []
    return metrics, [make_insight(
        AGENT, "OFFER", f"{best['offer_id']}-{sim:%Y%m}", "info", "offer", 30, best["name"],
        {"penawaran": best["name"], "deskripsi": best["description"], "alasan_cocok": reason, "cara": best["cta"]},
        best["description"])]
