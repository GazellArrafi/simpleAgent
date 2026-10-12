"""Generator data dummy perbankan (JSON) untuk mockup simpleAgent.

Mensimulasikan 6 bulan aktivitas per nasabah, HARI DEMI HARI:
  - tabungan: gaji masuk, QRIS, top up e-wallet, transfer, bayar tagihan, autodebet cicilan & kartu kredit
  - kartu kredit: belanja (bisa DITOLAK kalau melebihi limit), langganan bulanan, transaksi luar negeri,
    cetak tagihan bulanan, bunga 1,75%, denda telat, pembayaran (lunas / minimum / telat)
  - pinjaman: KPR / KKB / KTA

Tiap nasabah diberi `demo_persona` supaya hasil analisa bervariasi. Nasabah C0001..C0008 dijamin
punya persona tertentu (lihat DEMO_PERSONAS) untuk demo.

Pakai:  python data_gen/generate_data.py [--customers 200] [--seed 42] [--ref-date 2026-10-12]
"""

import argparse
import json
import math
import random
import sys
from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

HISTORY_DAYS = 182

FIRST_M = ["Budi", "Andi", "Rizky", "Dimas", "Fajar", "Agus", "Hendra", "Yoga", "Bayu", "Arif", "Reza", "Teguh",
           "Ilham", "Fikri", "Galih", "Joko", "Wahyu", "Rudi", "Dedi", "Gilang", "Aditya", "Kevin", "Rangga", "Hafiz"]
FIRST_F = ["Rina", "Sari", "Dewi", "Putri", "Ayu", "Nadia", "Intan", "Fitri", "Lestari", "Maya", "Citra", "Anisa",
           "Wulan", "Indah", "Tiara", "Nabila", "Siti", "Dinda", "Melati", "Kartika", "Aulia", "Salsabila", "Vina", "Laras"]
LAST = ["Pratama", "Saputra", "Wijaya", "Santoso", "Hidayat", "Kusuma", "Siregar", "Nasution", "Simanjuntak", "Halim",
        "Gunawan", "Setiawan", "Wibowo", "Lubis", "Hakim", "Rahman", "Nugroho", "Susanto", "Tanjung", "Firmansyah",
        "Putra", "Maharani", "Permata", "Utami"]
CITIES = ["Jakarta Selatan", "Jakarta Barat", "Jakarta Pusat", "Tangerang Selatan", "Bekasi", "Depok", "Bogor",
          "Bandung", "Surabaya", "Semarang", "Yogyakarta", "Medan", "Makassar", "Denpasar", "Malang", "Palembang"]
OCCUPATIONS = [  # (pekerjaan, rentang penghasilan bulanan dalam juta)
    ("Karyawan Swasta", (6, 25)), ("PNS", (5, 15)), ("Wiraswasta", (8, 60)), ("Dokter", (25, 90)),
    ("Manajer", (20, 60)), ("Freelancer", (5, 20)), ("Pegawai BUMN", (8, 30)), ("Pengusaha", (30, 150)),
    ("Software Engineer", (12, 40)), ("Guru", (5, 12)),
]

# kategori belanja kartu kredit: bobot frekuensi, rentang nominal (Rp), merchant
CATEGORIES = {
    "groceries": (18, (60_000, 1_200_000), ["Superindo", "Hypermart", "Ranch Market", "Transmart", "Lotte Mart", "Alfamart", "Indomaret"]),
    "dining": (24, (35_000, 650_000), ["Starbucks", "Kopi Kenangan", "McDonald's", "Hokben", "Sate Khas Senayan", "Solaria", "GrabFood", "GoFood", "Sushi Tei", "Bakmi GM"]),
    "ecommerce": (15, (50_000, 2_500_000), ["Tokopedia", "Shopee", "Lazada", "Blibli", "Zalora"]),
    "transport": (14, (20_000, 550_000), ["Grab", "Gojek", "Pertamina", "Shell", "Blue Bird", "KAI Access"]),
    "travel": (3, (450_000, 6_500_000), ["Traveloka", "tiket.com", "Garuda Indonesia", "AirAsia", "Agoda"]),
    "entertainment": (5, (50_000, 550_000), ["CGV", "Cinema XXI", "Steam", "Timezone"]),
    "bills": (6, (100_000, 1_500_000), ["PLN", "Telkomsel", "IndiHome", "BPJS Kesehatan", "First Media"]),
    "health": (4, (50_000, 1_800_000), ["Kimia Farma", "Guardian", "Siloam Hospitals", "Halodoc", "Century"]),
    "electronics": (2, (350_000, 14_000_000), ["Erafone", "iBox", "Electronic City", "Samsung Store", "Digimap"]),
    "fashion": (6, (150_000, 2_500_000), ["Uniqlo", "H&M", "Zara", "Matahari", "Sogo"]),
    "education": (3, (100_000, 1_500_000), ["Ruangguru", "Gramedia", "Coursera", "Periplus"]),
}
SUBSCRIPTIONS = [  # (merchant, kategori, nominal Rp, mata uang asli, nominal asli)
    ("Netflix", "entertainment", 186_000, "IDR", None), ("Spotify Premium", "entertainment", 54_990, "IDR", None),
    ("Disney+ Hotstar", "entertainment", 39_000, "IDR", None), ("YouTube Premium", "entertainment", 59_000, "IDR", None),
    ("iCloud+", "bills", 15_000, "IDR", None), ("ChatGPT Plus", "education", 327_000, "USD", 20.0),
    ("Vidio Platinum", "entertainment", 39_000, "IDR", None), ("Fitness First", "health", 450_000, "IDR", None),
]
FOREIGN = {  # mata uang: (negara, kurs, merchant)
    "SGD": ("Singapura", 12_150, ["Marina Bay Sands", "Din Tai Fung SG", "ION Orchard", "Grab SG", "Changi Duty Free"]),
    "JPY": ("Jepang", 106, ["Don Quijote Shibuya", "Uniqlo Ginza", "Ichiran Ramen", "JR East", "Lawson Tokyo"]),
    "THB": ("Thailand", 455, ["Siam Paragon", "Chatuchak Market", "Grab TH", "After You Dessert", "King Power"]),
    "USD": ("Amerika Serikat", 16_350, ["Macy's NYC", "Shake Shack", "Uber US", "Apple Fifth Ave", "Walgreens"]),
}
FOREIGN_CATS = ["dining", "fashion", "transport", "groceries", "entertainment"]

PERSONAS = {
    # w: bobot acak, spend: belanja bulanan (fraksi limit), init: saldo awal (fraksi limit), pay: pola bayar
    "healthy": dict(w=22, spend=(0.10, 0.22), init=(0.0, 0.05), pay="full"),
    "traveler": dict(w=8, spend=(0.25, 0.40), init=(0.0, 0.10), pay="full"),
    "revolver_near_limit": dict(w=12, spend=(0.10, 0.14), init=(0.55, 0.65), pay="min"),
    "minimum_payer": dict(w=10, spend=(0.07, 0.10), init=(0.20, 0.30), pay="min"),
    "due_soon": dict(w=12, spend=(0.18, 0.30), init=(0.0, 0.05), pay="full"),
    "overdue": dict(w=8, spend=(0.20, 0.30), init=(0.10, 0.30), pay="erratic"),
    "dormant": dict(w=6, spend=(0.01, 0.03), init=(0.0, 0.0), pay="full"),
    "spending_spike": dict(w=8, spend=(0.08, 0.12), init=(0.0, 0.05), pay="full"),
    "no_cc": dict(w=14),
}
DEMO_PERSONAS = ["due_soon", "overdue", "revolver_near_limit", "minimum_payer",
                 "spending_spike", "traveler", "healthy", "no_cc"]

OFFERS = [
    {"offer_id": "OF01", "name": "Cicilan 0% Elektronik 12 Bulan", "type": "installment", "is_credit_product": True,
     "description": "Ubah belanja elektronik/gadget min. Rp1 juta jadi cicilan 0% hingga 12 bulan di merchant partner.",
     "target": {"categories": ["electronics", "ecommerce"]}, "cta": "Aktifkan di app: Kartu Kredit > Cicilan"},
    {"offer_id": "OF02", "name": "Cashback Dining 20% Akhir Pekan", "type": "cashback", "is_credit_product": False,
     "description": "Cashback 20% (maks Rp50.000) tiap Sabtu-Minggu di restoran & aplikasi pesan antar partner.",
     "target": {"categories": ["dining"]}, "cta": "Lihat daftar merchant di menu Promo"},
    {"offer_id": "OF03", "name": "Bonus Miles & Asuransi Perjalanan Gratis", "type": "travel", "is_credit_product": False,
     "description": "Bonus 2x miles untuk transaksi luar negeri + asuransi perjalanan gratis saat beli tiket pakai kartu.",
     "target": {"categories": ["travel"], "foreign": True}, "cta": "Daftarkan perjalanan di menu Travel"},
    {"offer_id": "OF04", "name": "Cicilan Tagihan Bunga 0,99%", "type": "bill_installment", "is_credit_product": True,
     "description": "Ubah sisa tagihan kartu kredit jadi cicilan tetap bunga 0,99%/bulan, lebih ringan dari bunga revolving 1,75%.",
     "target": {"revolver": True}, "cta": "Ajukan di app: Kartu Kredit > Cicilan Tagihan"},
    {"offer_id": "OF05", "name": "Aktivasi Autodebet Kartu Kredit (Bonus 50.000 Poin)", "type": "service", "is_credit_product": False,
     "description": "Bayar tagihan otomatis dari tabungan, tidak perlu khawatir telat. Bonus 50.000 poin untuk aktivasi.",
     "target": {"no_autodebet": True}, "cta": "Aktifkan di app: Kartu Kredit > Autodebet"},
    {"offer_id": "OF06", "name": "Deposito Online Bunga 5,25%", "type": "deposit", "is_credit_product": False,
     "description": "Tempatkan dana mengendap mulai Rp10 juta dengan bunga 5,25% p.a., bisa dibuka 24 jam di app.",
     "target": {"min_savings": 50_000_000}, "cta": "Buka di app: Investasi > Deposito"},
    {"offer_id": "OF07", "name": "Upgrade Kartu & Kenaikan Limit", "type": "limit_increase", "is_credit_product": True,
     "description": "Riwayat pembayaran Anda sangat baik. Anda memenuhi syarat upgrade kartu dengan limit lebih besar.",
     "target": {"healthy": True, "min_income": 15_000_000}, "cta": "Ajukan di app: Kartu Kredit > Upgrade"},
    {"offer_id": "OF08", "name": "Diskon Belanja Bulanan 15%", "type": "cashback", "is_credit_product": False,
     "description": "Diskon 15% (maks Rp75.000) belanja kebutuhan bulanan di supermarket partner setiap Jumat.",
     "target": {"categories": ["groceries"]}, "cta": "Lihat merchant di menu Promo"},
    {"offer_id": "OF09", "name": "Reksa Dana Pasar Uang", "type": "investment", "is_credit_product": False,
     "description": "Mulai investasi dari Rp100.000 di reksa dana pasar uang, cocok untuk dana darurat.",
     "target": {"segments": ["Prioritas", "Emerald"], "min_savings": 20_000_000}, "cta": "Buka di app: Investasi"},
]


# ---------------------------------------------------------------- helpers
def log_uniform(rng, lo, hi, step=500):
    return max(step, round(math.exp(rng.uniform(math.log(lo), math.log(hi))) / step) * step)


def poisson(rng, lam):
    if lam <= 0:
        return 0
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1


def rand_time(rng, d, hours=(7, 23)):
    return datetime(d.year, d.month, d.day, rng.randint(*hours), rng.randint(0, 59), rng.randint(0, 59))


def month_day(y, m, day):
    return date(y, m, min(day, monthrange(y, m)[1]))


def monthly_dates(day, start, end):
    """Semua tanggal `day` tiap bulan yang jatuh di (start, end]."""
    out, y, m = [], start.year, start.month
    while date(y, m, 1) <= end:
        d = month_day(y, m, day)
        if start < d <= end:
            out.append(d)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def next_monthly(day, after):
    """Tanggal `day` pertama yang >= after."""
    d = month_day(after.year, after.month, day)
    if d >= after:
        return d
    y, m = (after.year + 1, 1) if after.month == 12 else (after.year, after.month + 1)
    return month_day(y, m, day)


def weighted_choice(rng, weights: dict):
    keys = list(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys])[0]


def mean_amount(weights):
    total = sum(weights.values())
    return sum(w / total * (hi - lo) / math.log(hi / lo) for c, w in weights.items()
               for lo, hi in [CATEGORIES[c][1]])


class Ids:
    def __init__(self):
        self.n = {}

    def __call__(self, prefix, width=8):
        self.n[prefix] = self.n.get(prefix, 0) + 1
        return f"{prefix}{self.n[prefix]:0{width}d}"


# ---------------------------------------------------------------- customers
def make_customer(rng, idx, persona, ref):
    gender = rng.choice("MF")
    first = rng.choice(FIRST_M if gender == "M" else FIRST_F)
    last = rng.choice(LAST)
    occupation, (lo, hi) = rng.choice(OCCUPATIONS)
    if persona == "traveler":
        lo, hi = max(lo, 25), max(hi, 80)
    income = round(rng.uniform(lo, hi) * 1_000_000, -5)
    age = rng.randint(23, 62)
    birth = ref - timedelta(days=age * 365 + rng.randint(0, 364))
    segment = "Prioritas" if income >= 50_000_000 else "Emerald" if income >= 20_000_000 else "Reguler"
    return {
        "customer_id": f"C{idx:04d}",
        "full_name": f"{first} {last}",
        "nickname": first,
        "gender": gender,
        "birth_date": birth.isoformat(),
        "age": age,
        "city": rng.choice(CITIES),
        "occupation": occupation,
        "monthly_income": income,
        "segment": segment,
        "joined_date": (ref - timedelta(days=rng.randint(400, 4000))).isoformat(),
        "phone": f"+62 8{rng.randint(11, 59)}-{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}",
        "email": f"{first.lower()}.{last.lower()}{rng.randint(1, 99)}@example.com",
        "preferred_channel": rng.choices(["app", "telegram", "email"], weights=[70, 20, 10])[0],
        "telegram_chat_id": None,
        "language": "id",
        "marketing_consent": rng.random() < 0.75,
        "demo_persona": persona,
    }


# ---------------------------------------------------------------- credit card
def make_card(rng, ids, cust, persona, ref):
    limit = max(5_000_000, round(cust["monthly_income"] * rng.uniform(1.5, 3.0), -6))
    product = ("Silver" if limit < 10_000_000 else "Gold" if limit < 30_000_000
               else "Platinum" if limit < 75_000_000 else "Signature")
    network = rng.choice(["Visa", "Mastercard", "JCB"])
    prefix = {"Visa": "4", "Mastercard": "5", "JCB": "3"}[network]
    if persona == "due_soon":
        last_stmt = ref + timedelta(days=rng.randint(1, 3)) - timedelta(days=config.CC_DUE_DAYS)
        stmt_day = last_stmt.day
    elif persona == "overdue":
        last_stmt = ref - timedelta(days=rng.randint(2, 7)) - timedelta(days=config.CC_DUE_DAYS)
        stmt_day = last_stmt.day
    else:
        stmt_day = rng.randint(1, 28)
    return {
        "card_id": ids("CC", 5),
        "customer_id": cust["customer_id"],
        "card_number_masked": f"{prefix}{rng.randint(100, 999)} **** **** {rng.randint(1000, 9999)}",
        "product": f"Kartu Kredit {product}",
        "network": network,
        "issued_date": (ref - timedelta(days=rng.randint(300, 2500))).isoformat(),
        "credit_limit": limit,
        "current_balance": 0,
        "available_limit": limit,
        "statement_day": stmt_day,
        "due_days_after_statement": config.CC_DUE_DAYS,
        "autodebet": persona in ("healthy", "traveler", "dormant") and rng.random() < 0.6,
        "reward_points": rng.randint(0, 250_000),
        "status": "active",
    }


def simulate_card(rng, ids, card, cust, persona, start, ref):
    cfg = PERSONAS[persona]
    limit = card["credit_limit"]
    weights = {c: v[0] for c, v in CATEGORIES.items()}
    if persona == "traveler":
        weights["travel"] *= 4
    spike_weights = dict(weights, electronics=weights["electronics"] * 8, ecommerce=weights["ecommerce"] * 2.5,
                         fashion=weights["fashion"] * 2)
    rate = min(4.0, rng.uniform(*cfg["spend"]) * limit / 30 / mean_amount(weights))
    bal = round(rng.uniform(*cfg["init"]) * limit, -3)

    subs = rng.sample(SUBSCRIPTIONS, k=0 if persona == "dormant" else rng.randint(1, 4))
    subs = [(s, rng.randint(1, 28)) for s in subs]
    trips = []
    if persona == "traveler":
        for _ in range(2):
            t0 = start + timedelta(days=rng.randint(10, HISTORY_DAYS - 20))
            trips.append((t0, t0 + timedelta(days=rng.randint(4, 7)), rng.choice(list(FOREIGN))))
    unusual_day = None
    if persona == "spending_spike" or rng.random() < 0.10:
        unusual_day = ref - timedelta(days=rng.randint(2, 20))

    stmt_dates = set(monthly_dates(card["statement_day"], start, ref - timedelta(days=1)))
    last_stmt_date = max(stmt_dates)
    txs, statements, cc_payments = [], [], []
    pay_queue = {}
    prev = None
    period = {"start": start + timedelta(days=1), "prev_balance": bal, "purchases": 0, "payments": 0,
              "interest": 0, "fees": 0}

    def add_tx(dt, typ, amount, merchant, category, status="approved", **extra):
        tx = {"txn_id": ids("CT"), "card_id": card["card_id"], "customer_id": cust["customer_id"],
              "datetime": dt.isoformat(), "type": typ, "merchant": merchant, "category": category,
              "amount": amount, "currency": "IDR", "original_amount": amount, "channel": extra.pop("channel", "system"),
              "location": extra.pop("location", "Indonesia"), "is_recurring": extra.pop("is_recurring", False),
              "status": status, "decline_reason": extra.pop("decline_reason", None)}
        tx.update(extra)
        txs.append(tx)

    def purchase(dt, merchant, category, amount, **extra):
        nonlocal bal
        if bal + amount > limit:
            add_tx(dt, "purchase", amount, merchant, category, status="declined",
                   decline_reason="Melebihi limit kartu", **extra)
            return
        bal += amount
        period["purchases"] += amount
        add_tx(dt, "purchase", amount, merchant, category, **extra)

    d = start + timedelta(days=1)
    while d <= ref:
        # 1) pembayaran terjadwal hari ini
        for st, amt in pay_queue.pop(d, []):
            bal -= amt
            period["payments"] += amt
            st["paid_amount"] += amt
            st["paid_date"] = d.isoformat()
            add_tx(rand_time(rng, d), "payment", -amt, "Pembayaran Tagihan", "payment", channel="mobile_banking")
            cc_payments.append((d, amt, card["card_id"]))
        # 2) denda telat sehari setelah jatuh tempo
        if prev and date.fromisoformat(prev["due_date"]) + timedelta(days=1) == d \
                and prev["paid_amount"] < prev["minimum_due"]:
            fee = min(config.CC_LATE_FEE_CAP, round(prev["total_due"] * config.CC_LATE_FEE_PCT, -2))
            bal += fee
            period["fees"] += fee
            add_tx(datetime(d.year, d.month, d.day, 0, 5), "fee", fee, "Denda Keterlambatan", "fee")
        # 3) langganan bulanan
        for (merchant, cat, amt, cur, orig), sub_day in subs:
            if d.day == sub_day:
                purchase(rand_time(rng, d, (1, 5)), merchant, cat, amt, channel="online", is_recurring=True,
                         currency=cur, original_amount=orig or amt)
        # 4) belanja harian
        trip = next((t for t in trips if t[0] <= d <= t[1]), None)
        spiking = persona == "spending_spike" and d > ref - timedelta(days=30)
        lam = rate * (3.0 if spiking else 1.0) * (1.5 if trip else 1.0)
        for _ in range(poisson(rng, lam)):
            if trip:
                cur = trip[2]
                country, fx, merchants = FOREIGN[cur]
                cat = rng.choice(FOREIGN_CATS)
                amount = log_uniform(rng, *CATEGORIES[cat][1])
                purchase(rand_time(rng, d), rng.choice(merchants), cat, amount, channel=rng.choice(["offline", "contactless"]),
                         location=country, currency=cur, original_amount=round(amount / fx, 2))
            else:
                cat = weighted_choice(rng, spike_weights if spiking else weights)
                amount = log_uniform(rng, *CATEGORIES[cat][1])
                online = cat in ("ecommerce", "travel") or rng.random() < 0.25
                purchase(rand_time(rng, d), rng.choice(CATEGORIES[cat][2]), cat, amount,
                         channel="online" if online else rng.choice(["offline", "contactless"]),
                         location="Online" if online else cust["city"])
        for t0, _, _ in trips:  # pesan tiket & hotel sebelum berangkat
            if d == t0 - timedelta(days=14):
                purchase(rand_time(rng, d), rng.choice(["Traveloka", "tiket.com", "Garuda Indonesia"]), "travel",
                         log_uniform(rng, 4_000_000, 12_000_000), channel="online", location="Online")
        if d == unusual_day:
            amount = log_uniform(rng, 6_000_000, 14_000_000, step=1000)
            purchase(datetime(d.year, d.month, d.day, rng.randint(1, 3), rng.randint(0, 59)), "GLOBAL LUXE ONLINE",
                     "ecommerce", amount, channel="online", location="Online (Luar Negeri)",
                     currency="USD", original_amount=round(amount / FOREIGN["USD"][1], 2))
        # 5) cetak tagihan
        if d in stmt_dates:
            if prev:
                unpaid = prev["total_due"] - prev["paid_amount"]
                if unpaid > 0:
                    interest = round(unpaid * config.CC_INTEREST_MONTHLY, -2)
                    bal += interest
                    period["interest"] += interest
                    add_tx(datetime(d.year, d.month, d.day, 0, 1), "interest", interest, "Bunga Kartu Kredit", "interest")
            total = max(0, round(bal))
            minimum = 0 if total == 0 else min(total, max(config.CC_MIN_PAYMENT_FLOOR,
                                                          round(total * config.CC_MIN_PAYMENT_PCT, -2)))
            due = d + timedelta(days=config.CC_DUE_DAYS)
            st = {"statement_id": f"ST-{card['card_id']}-{d:%Y%m}", "card_id": card["card_id"],
                  "customer_id": cust["customer_id"], "period_start": period["start"].isoformat(),
                  "statement_date": d.isoformat(), "due_date": due.isoformat(),
                  "previous_balance": round(period["prev_balance"]), "new_purchases": period["purchases"],
                  "payments": period["payments"], "interest": period["interest"], "fees": period["fees"],
                  "total_due": total, "minimum_due": minimum, "paid_amount": 0, "paid_date": None}
            statements.append(st)
            schedule_payment(rng, pay_queue, st, persona, cfg["pay"], d, due, d == last_stmt_date)
            prev = st
            period = {"start": d + timedelta(days=1), "prev_balance": bal, "purchases": 0, "payments": 0,
                      "interest": 0, "fees": 0}
        d += timedelta(days=1)

    for st in statements:
        finalize_statement(st, ref)
    card["current_balance"] = round(bal)
    card["available_limit"] = round(limit - bal)
    return txs, statements, cc_payments


def schedule_payment(rng, queue, st, persona, mode, stmt_date, due, is_last):
    total, minimum = st["total_due"], st["minimum_due"]
    if total <= 0 or (is_last and persona in ("due_soon", "overdue")):
        return
    if mode == "full":
        amt, pay = total, due - timedelta(days=rng.randint(0, 8))
    elif mode == "min":
        amt, pay = minimum, due - timedelta(days=rng.randint(0, 5))
    else:  # erratic: kadang lunas, kadang minimum & telat
        r = rng.random()
        if r < 0.45:
            amt, pay = total, due - timedelta(days=rng.randint(0, 4))
        elif r < 0.8:
            amt, pay = minimum, due + timedelta(days=rng.randint(2, 9))
        else:
            amt, pay = round(rng.uniform(minimum, total), -3), due - timedelta(days=rng.randint(0, 3))
    pay = max(pay, stmt_date + timedelta(days=1))
    queue.setdefault(pay, []).append((st, amt))


def finalize_statement(st, ref):
    due = date.fromisoformat(st["due_date"])
    paid, total, minimum = st["paid_amount"], st["total_due"], st["minimum_due"]
    paid_late = st["paid_date"] is not None and date.fromisoformat(st["paid_date"]) > due
    if total == 0:
        status = "no_bill"
    elif paid >= total:
        status = "paid_full"
    elif due >= ref and not paid_late:
        status = "open"
    elif paid >= minimum and not paid_late:
        status = "paid_minimum" if paid <= minimum * 1.05 else "paid_partial"
    else:
        status = "late"
    st["status"] = status
    st["paid_late"] = paid_late or (status == "late")
    st["days_past_due"] = (ref - due).days if due < ref and paid < minimum else 0


# ---------------------------------------------------------------- loans
def make_loans(rng, ids, cust, persona, ref, force=False):
    p = 0.6 if persona == "overdue" else 0.3
    if not force and rng.random() > p:
        return []
    income = cust["monthly_income"]
    options = ["KTA"] + (["KKB"] if income >= 8_000_000 else []) + (["KPR"] if income >= 15_000_000 else [])
    kind = "KTA" if force else rng.choice(options)
    rate, (plo, phi), tenors = {"KPR": (0.08, (300, 1500), [120, 180, 240]), "KKB": (0.065, (80, 400), [36, 48, 60]),
                                "KTA": (0.11, (10, 150), [12, 24, 36, 48])}[kind]
    principal = round(min(rng.uniform(plo, phi) * 1_000_000, income * {"KPR": 120, "KKB": 30, "KTA": 8}[kind]), -6)
    tenor = rng.choice(tenors)
    r = rate / 12
    installment = round(principal * r / (1 - (1 + r) ** -tenor), -3)
    elapsed = rng.randint(1, tenor - 2)
    remaining = tenor - elapsed
    outstanding = round(installment * (1 - (1 + r) ** -remaining) / r, -3)
    due_day = rng.randint(1, 28)
    dpd = rng.randint(5, 25) if persona == "overdue" and rng.random() < 0.4 else 0
    autodebet = rng.random() < 0.75
    next_due = next_monthly(due_day, ref)
    if force:  # nasabah demo C0008: cicilan KTA jatuh tempo 2 hari lagi, autodebet mati
        next_due, autodebet, dpd = ref + timedelta(days=2), False, 0
        due_day = next_due.day
    if dpd:
        next_due = ref - timedelta(days=dpd)
    return [{
        "loan_id": ids("LN", 5), "customer_id": cust["customer_id"], "type": kind,
        "product": {"KPR": "KPR Rumah Idaman", "KKB": "Kredit Kendaraan", "KTA": "Kredit Tanpa Agunan"}[kind],
        "principal": principal, "outstanding": outstanding, "interest_rate_pa": rate, "tenor_months": tenor,
        "remaining_months": remaining, "monthly_installment": installment, "due_day": due_day,
        "next_due_date": next_due.isoformat(), "autodebet": autodebet, "days_past_due": dpd,
        "status": "past_due" if dpd else "current",
    }]


# ---------------------------------------------------------------- savings
def simulate_savings(rng, ids, cust, persona, start, ref, cc_payments, loans):
    income = cust["monthly_income"]
    low = persona in ("revolver_near_limit", "overdue", "minimum_payer", "no_cc")
    bal = round(income * (rng.uniform(0.1, 0.6) if low else rng.uniform(1.0, 6.0)), -3)
    if persona == "due_soon":
        bal = round(income * rng.uniform(2.5, 5.0), -3)
    product = {"Prioritas": "Tabungan Prioritas", "Emerald": "Tabungan Plus"}.get(cust["segment"], "Tabungan Simpel")
    acct = {"account_id": ids("SA", 5), "customer_id": cust["customer_id"], "product": product,
            "opened_date": cust["joined_date"], "balance": 0, "avg_balance_3m": 0,
            "is_payroll": cust["occupation"] not in ("Wiraswasta", "Pengusaha", "Freelancer"), "status": "active"}
    payday = 25 if acct["is_payroll"] else rng.randint(1, 28)
    outflow_rate = income * (rng.uniform(0.85, 1.0) if low else rng.uniform(0.35, 0.65)) / 30 / 450_000
    if persona == "no_cc" and loans:  # demo: saldo tipis menjelang cicilan
        outflow_rate *= 1.4
    cc_by_day = {}
    for d, amt, card_id in cc_payments:
        cc_by_day.setdefault(d, []).append((amt, card_id))
    debit_kinds = [  # (kategori, deskripsi, rentang, bobot)
        ("qris", ["QRIS - Warung Bu Sri", "QRIS - Kopi Janji Jiwa", "QRIS - Apotek K24", "QRIS - Parkir"], (15_000, 300_000), 35),
        ("ewallet_topup", ["Top Up GoPay", "Top Up OVO", "Top Up DANA", "Top Up ShopeePay"], (50_000, 1_000_000), 25),
        ("transfer_out", ["Transfer ke Orang Tua", "Transfer ke Rekening Lain", "BI-FAST Transfer", "Arisan"], (100_000, 5_000_000), 15),
        ("bill_payment", ["PLN Pascabayar", "PDAM", "Telkom IndiHome", "BPJS Kesehatan", "Pajak Kendaraan"], (100_000, 1_500_000), 12),
        ("atm_withdrawal", ["Tarik Tunai ATM"], (100_000, 2_000_000), 13),
    ]
    txs, daily = [], []

    def add(dt, direction, cat, desc, amt):
        nonlocal bal
        if direction == "debit" and amt > bal:
            return False
        bal += amt if direction == "credit" else -amt
        txs.append({"txn_id": ids("ST"), "account_id": acct["account_id"], "customer_id": cust["customer_id"],
                    "datetime": dt.isoformat(), "direction": direction, "category": cat, "description": desc,
                    "amount": amt, "balance_after": round(bal)})
        return True

    d = start + timedelta(days=1)
    while d <= ref:
        if d.day == payday:
            amt = round(income * rng.uniform(0.95, 1.05), -3)
            add(datetime(d.year, d.month, d.day, 6, 0), "credit", "salary" if acct["is_payroll"] else "business_income",
                "Gaji Bulanan" if acct["is_payroll"] else "Pendapatan Usaha", amt)
        if rng.random() < 0.06:
            add(rand_time(rng, d), "credit", "transfer_in", "Transfer Masuk", log_uniform(rng, 100_000, 3_000_000))
        for loan in loans:
            if loan["autodebet"] and d.day == loan["due_day"] and not loan["days_past_due"]:
                add(datetime(d.year, d.month, d.day, 7, 0), "debit", "loan_installment",
                    f"Autodebet Cicilan {loan['type']}", loan["monthly_installment"])
        for amt, card_id in cc_by_day.get(d, []):
            add(rand_time(rng, d), "debit", "cc_payment", f"Pembayaran Kartu Kredit {card_id}", amt)
        for _ in range(poisson(rng, outflow_rate)):
            cat, descs, rng_amt, _ = rng.choices(debit_kinds, weights=[k[3] for k in debit_kinds])[0]
            add(rand_time(rng, d), "debit", cat, rng.choice(descs), log_uniform(rng, *rng_amt))
        daily.append(bal)
        d += timedelta(days=1)

    acct["balance"] = round(bal)
    acct["avg_balance_3m"] = round(sum(daily[-90:]) / len(daily[-90:]))
    return acct, txs


# ---------------------------------------------------------------- main
def generate(n_customers, seed, ref):
    rng = random.Random(seed)
    ids = Ids()
    start = ref - timedelta(days=HISTORY_DAYS)
    data = {k: [] for k in ["customers", "savings_accounts", "savings_transactions", "credit_cards",
                            "cc_transactions", "cc_statements", "loans"]}
    names = [p for p in PERSONAS]
    for i in range(1, n_customers + 1):
        persona = DEMO_PERSONAS[i - 1] if i <= len(DEMO_PERSONAS) else \
            rng.choices(names, weights=[PERSONAS[p]["w"] for p in names])[0]
        cust = make_customer(rng, i, persona, ref)
        if i == 8:  # demo no_cc: penghasilan menengah agar saldo vs cicilan relevan
            cust["monthly_income"], cust["segment"] = 9_500_000, "Reguler"
        data["customers"].append(cust)

        cc_payments = []
        if persona != "no_cc":
            card = make_card(rng, ids, cust, persona, ref)
            txs, stmts, cc_payments = simulate_card(rng, ids, card, cust, persona, start, ref)
            data["credit_cards"].append(card)
            data["cc_transactions"].extend(txs)
            data["cc_statements"].extend(stmts)
        loans = make_loans(rng, ids, cust, persona, ref, force=(i == 8))
        data["loans"].extend(loans)
        acct, stxs = simulate_savings(rng, ids, cust, persona, start, ref, cc_payments, loans)
        data["savings_accounts"].append(acct)
        data["savings_transactions"].extend(stxs)

    data["offers"] = OFFERS
    data["meta"] = {"reference_date": ref.isoformat(), "history_start": start.isoformat(), "seed": seed,
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                    "counts": {k: len(v) for k, v in data.items() if isinstance(v, list)}}
    return data


def generate_and_save(customers=200, seed=42, ref: date | None = None, out=config.DATA_DIR) -> dict:
    ref = ref or date.today()
    data = generate(max(customers, len(DEMO_PERSONAS)), seed, ref)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in data.items():
        (out / f"{name}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return data["meta"]


def main():
    ap = argparse.ArgumentParser(description="Generate data dummy perbankan (JSON)")
    ap.add_argument("--customers", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--ref-date", default=None, help="Tanggal 'hari ini' simulasi, default hari ini")
    ap.add_argument("--out", default=str(config.DATA_DIR))
    args = ap.parse_args()
    ref = date.fromisoformat(args.ref_date) if args.ref_date else None
    meta = generate_and_save(args.customers, args.seed, ref, args.out)
    print(f"Data tersimpan di {args.out}  (reference_date={meta['reference_date']})")
    for k, v in meta["counts"].items():
        print(f"  {k:<22} {v:>8,}")


if __name__ == "__main__":
    main()
