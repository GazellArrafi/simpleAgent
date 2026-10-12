"""Helper bersama untuk analitik: format Rupiah/tanggal & pembuat insight."""

from datetime import date, datetime

BULAN = ["", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
SEVERITY_RANK = {"critical": 3, "warning": 2, "info": 1}
CATEGORY_ID = {
    "groceries": "belanja bulanan", "dining": "makan & minum", "ecommerce": "belanja online",
    "transport": "transportasi", "travel": "travel", "entertainment": "hiburan", "bills": "tagihan",
    "health": "kesehatan", "electronics": "elektronik", "fashion": "fashion", "education": "pendidikan",
}


def rp(x) -> str:
    return "Rp" + f"{round(x):,}".replace(",", ".")


def tgl(d, with_day=False) -> str:
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    s = f"{d.day} {BULAN[d.month]} {d.year}"
    return f"{HARI[d.weekday()]}, {s}" if with_day else s


def pct(x) -> str:
    return f"{x * 100:.0f}%"


def to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def last4(card: dict) -> str:
    return card["card_number_masked"][-4:]


def card_label(card: dict) -> str:
    return f"{card['product']} **** {last4(card)}"


def make_insight(agent, code, ref, severity, category, priority, title, facts, recommendation, notify=True) -> dict:
    return {
        "insight_id": f"{code}:{ref}",
        "agent": agent,
        "code": code,
        "category": category,      # reminder | alert | education | offer
        "severity": severity,      # critical | warning | info
        "priority": priority,
        "title": title,
        "facts": facts,
        "recommendation": recommendation,
        "notify": notify,
    }


def purchases(txs, approved_only=True):
    return [t for t in txs if t["type"] == "purchase" and (t["status"] == "approved" or not approved_only)]
