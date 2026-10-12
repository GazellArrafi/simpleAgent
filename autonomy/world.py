"""World simulator: memajukan dunia 1 hari & memunculkan kejadian baru (autonomy.md bagian 4).

Simulator mewakili 'perilaku manusia', jadi boleh memakai demo_persona. Pesan dari agent
(outbox 3 hari terakhir) menaikkan peluang nasabah membayar -> dampak kerja agent terlihat.
"""

import random
from datetime import date, datetime, timedelta

import config
from analytics.common import rp
from autonomy import store
from channels import outbox
from data_gen.generate_data import FOREIGN, finalize_statement, log_uniform, month_day, next_monthly, poisson

FULL_PAYERS = {"healthy", "traveler", "dormant", "spending_spike"}
MIN_PAYERS = {"revolver_near_limit", "minimum_payer"}
CC_REMINDERS = {"CC_DUE_SOON", "CC_DUE_UPCOMING", "CC_OVERDUE", "CC_MIN_PAYMENT_HABIT", "CC_LIMIT_CRITICAL", "CC_LIMIT_HIGH"}
LOAN_REMINDERS = {"LOAN_DUE_SOON", "LOAN_OVERDUE"}


class World:
    def __init__(self, repo, seed: int = 7):
        self.repo = repo
        self.seed = seed

    # ---------------------------------------------------------------- utama
    def step(self) -> list[dict]:
        repo = self.repo
        self.d = repo.reference_date() + timedelta(days=1)
        self.rng = random.Random(f"{self.seed}-{self.d.isoformat()}")
        self.events, self.seq = [], 0
        reminded = self._recent_reminders()
        with repo.transaction():  # postgres: 1 hari = 1 transaksi (semua atau tidak sama sekali)
            for cust in repo.list_customers():
                cid = cust["customer_id"]
                codes = reminded.get(cid, set())
                for acct in repo.get_savings_accounts(cid):
                    self._salary(cust, acct)
                for card in repo.get_credit_cards(cid):
                    self._card_day(cust, card, bool(codes & CC_REMINDERS))
                for loan in repo.get_loans(cid):
                    self._loan_day(cust, loan, bool(codes & LOAN_REMINDERS))
            repo.set_reference_date(self.d)
        repo.save()
        store.add_events(self.events)
        return self.events

    def _recent_reminders(self) -> dict[str, set]:
        since = (self.d - timedelta(days=3)).isoformat()
        out = {}
        for r in outbox.read_all():
            if r.get("sim_date", "") >= since:
                out.setdefault(r["customer_id"], set()).add(r["code"])
        return out

    # ---------------------------------------------------------------- helper
    def _id(self, prefix):
        self.seq += 1
        return f"{prefix}{self.d:%Y%m%d}{self.seq:05d}"

    def _dt(self, hours=(7, 23)):
        return datetime(self.d.year, self.d.month, self.d.day, self.rng.randint(*hours), self.rng.randint(0, 59))

    def _event(self, cid, typ, detail, high=False):
        self.events.append({"date": self.d.isoformat(), "customer_id": cid, "type": typ, "detail": detail,
                            "priority": "high" if high else "normal"})

    def _savings(self, cid, direction, category, desc, amount) -> bool:
        accts = self.repo.get_savings_accounts(cid)
        if not accts:
            return False
        acct = accts[0]
        if direction == "debit" and acct["balance"] < amount:
            return False
        acct["balance"] += amount if direction == "credit" else -amount
        self.repo.update_account(acct)
        self.repo.add_row("savings_transactions", {
            "txn_id": self._id("ST"), "account_id": acct["account_id"], "customer_id": cid,
            "datetime": self._dt().isoformat(), "direction": direction, "category": category,
            "description": desc, "amount": amount, "balance_after": acct["balance"]})
        return True

    def _cc_tx(self, cust, card, typ, amount, merchant, category, status="approved", **extra):
        tx = {"txn_id": self._id("CT"), "card_id": card["card_id"], "customer_id": cust["customer_id"],
              "datetime": extra.pop("dt", self._dt()).isoformat(), "type": typ, "merchant": merchant,
              "category": category, "amount": amount, "currency": "IDR", "original_amount": amount,
              "channel": "system", "location": "Indonesia", "is_recurring": False, "status": status,
              "decline_reason": None}
        tx.update(extra)
        self.repo.add_row("cc_transactions", tx)

    def _set_balance(self, card, bal):
        card["current_balance"] = round(bal)
        card["available_limit"] = round(card["credit_limit"] - bal)
        self.repo.update_card(card)

    # ---------------------------------------------------------------- tabungan
    def _salary(self, cust, acct):
        payday = 25 if acct["is_payroll"] else 1
        if self.d.day == payday:
            amt = round(cust["monthly_income"] * self.rng.uniform(0.95, 1.05), -3)
            self._savings(cust["customer_id"], "credit", "salary" if acct["is_payroll"] else "business_income",
                          "Gaji Bulanan" if acct["is_payroll"] else "Pendapatan Usaha", amt)

    # ---------------------------------------------------------------- kartu kredit
    def _purchase(self, cust, card, merchant, category, amount, **extra):
        cid = cust["customer_id"]
        if card["current_balance"] + amount > card["credit_limit"]:
            self._cc_tx(cust, card, "purchase", amount, merchant, category, status="declined",
                        decline_reason="Melebihi limit kartu", **extra)
            self._event(cid, "cc_declined", f"Transaksi {merchant} {rp(amount)} ditolak (limit tidak cukup)", high=True)
            return
        self._set_balance(card, card["current_balance"] + amount)
        self._cc_tx(cust, card, "purchase", amount, merchant, category, **extra)
        if amount >= 5_000_000:
            self._event(cid, "cc_large_transaction", f"Transaksi besar {merchant} {rp(amount)} ({extra.get('location', '')})",
                        high=True)

    def _card_day(self, cust, card, reminded):
        cid, rng, d = cust["customer_id"], self.rng, self.d
        history = [t for t in self.repo.get_cc_transactions(cid, days=60, until=d - timedelta(days=1))
                   if t["card_id"] == card["card_id"]]
        past = [t for t in history if t["type"] == "purchase" and t["status"] == "approved"
                and not t["is_recurring"] and t.get("currency", "IDR") == "IDR"]
        for _ in range(poisson(rng, len(past) / 60)):  # belanja baru = resample kebiasaan sendiri
            tpl = rng.choice(past)
            self._purchase(cust, card, tpl["merchant"], tpl["category"], max(1000, round(tpl["amount"] * rng.uniform(0.7, 1.3), -2)),
                           channel=tpl["channel"], location=tpl["location"])
        seen = set()
        for t in history:  # langganan bulanan
            if t["is_recurring"] and t["status"] == "approved" and t["merchant"] not in seen \
                    and datetime.fromisoformat(t["datetime"]).day == d.day and t["datetime"][:10] < d.isoformat():
                seen.add(t["merchant"])
                self._purchase(cust, card, t["merchant"], t["category"], t["amount"], channel="online",
                               is_recurring=True, currency=t.get("currency", "IDR"), original_amount=t.get("original_amount"),
                               dt=datetime(d.year, d.month, d.day, 3, rng.randint(0, 59)))
        if rng.random() < 0.003:  # sesekali: transaksi besar dini hari di merchant asing
            amount = log_uniform(rng, 6_000_000, 14_000_000, step=1000)
            self._purchase(cust, card, "GLOBAL LUXE ONLINE", "ecommerce", amount, channel="online",
                           location="Online (Luar Negeri)", currency="USD",
                           original_amount=round(amount / FOREIGN["USD"][1], 2), dt=self._dt((1, 3)))

        sts = self.repo.get_cc_statements(cid)
        sts = [s for s in sts if s["card_id"] == card["card_id"]]
        if d == month_day(d.year, d.month, card["statement_day"]):
            sts.append(self._cut_statement(cust, card, sts[-1] if sts else None, history))
        if sts:
            self._payment_day(cust, card, sts[-1], reminded)

    def _cut_statement(self, cust, card, prev, history):
        d, bal = self.d, card["current_balance"]
        interest = 0
        if prev and prev["total_due"] > prev["paid_amount"]:
            interest = round((prev["total_due"] - prev["paid_amount"]) * config.CC_INTEREST_MONTHLY, -2)
            bal += interest
            self._set_balance(card, bal)
            self._cc_tx(cust, card, "interest", interest, "Bunga Kartu Kredit", "interest",
                        dt=datetime(d.year, d.month, d.day, 0, 1))
        since = prev["statement_date"] if prev else "0000"
        period = [t for t in history if t["datetime"][:10] > since]
        total = max(0, round(bal))
        minimum = 0 if total == 0 else min(total, max(config.CC_MIN_PAYMENT_FLOOR, round(total * config.CC_MIN_PAYMENT_PCT, -2)))
        due = d + timedelta(days=config.CC_DUE_DAYS)
        st = {"statement_id": f"ST-{card['card_id']}-{d:%Y%m}", "card_id": card["card_id"], "customer_id": cust["customer_id"],
              "period_start": (date.fromisoformat(since) + timedelta(days=1)).isoformat() if prev else d.isoformat(),
              "statement_date": d.isoformat(), "due_date": due.isoformat(),
              "previous_balance": prev["total_due"] if prev else 0,
              "new_purchases": sum(t["amount"] for t in period if t["type"] == "purchase" and t["status"] == "approved"),
              "payments": -sum(t["amount"] for t in period if t["type"] == "payment"),
              "interest": interest, "fees": sum(t["amount"] for t in period if t["type"] == "fee"),
              "total_due": total, "minimum_due": minimum, "paid_amount": 0, "paid_date": None}
        finalize_statement(st, d)
        self.repo.add_row("cc_statements", st)
        self._event(cust["customer_id"], "cc_statement_issued",
                    f"Tagihan baru {rp(total)} (minimum {rp(minimum)}), jatuh tempo {due.isoformat()}")
        return st

    def _payment_day(self, cust, card, st, reminded):
        cid, persona, rng, d = cust["customer_id"], cust["demo_persona"], self.rng, self.d
        due = date.fromisoformat(st["due_date"])
        days_to_due = (due - d).days
        remaining = st["total_due"] - st["paid_amount"]
        remaining_min = st["minimum_due"] - st["paid_amount"]
        p, amount = 0.0, 0
        if remaining > 0:
            if persona == "due_soon":
                p, amount = (0.6 if reminded else 0.04), remaining
            elif persona in FULL_PAYERS:
                p = 0.9 if days_to_due <= 0 else 0.5 if days_to_due <= 2 else 0.12 if days_to_due <= 10 else 0.0
                amount = remaining
            elif persona in MIN_PAYERS and remaining_min > 0:
                p = (0.35 if days_to_due <= 4 else 0.05) + (0.2 if reminded else 0)
                amount = min(remaining, remaining_min * (2 if reminded else 1))
            elif persona == "overdue" and remaining_min > 0:
                p, amount = (0.35 if reminded else 0.03), remaining_min
        if amount > 0 and rng.random() < p:
            self._set_balance(card, card["current_balance"] - amount)
            st["paid_amount"] += amount
            st["paid_date"] = d.isoformat()
            self._cc_tx(cust, card, "payment", -amount, "Pembayaran Tagihan", "payment", channel="mobile_banking")
            self._savings(cid, "debit", "cc_payment", f"Pembayaran Kartu Kredit {card['card_id']}", amount)
            self._event(cid, "cc_payment_received",
                        f"Bayar tagihan {rp(amount)} dari {rp(st['total_due'])}" + (" (setelah diingatkan)" if reminded else ""))
        if d == due + timedelta(days=1) and st["paid_amount"] < st["minimum_due"]:
            fee = min(config.CC_LATE_FEE_CAP, round(st["total_due"] * config.CC_LATE_FEE_PCT, -2))
            self._set_balance(card, card["current_balance"] + fee)
            self._cc_tx(cust, card, "fee", fee, "Denda Keterlambatan", "fee", dt=datetime(d.year, d.month, d.day, 0, 5))
            self._event(cid, "cc_payment_missed", f"Lewat jatuh tempo {due.isoformat()} tanpa bayar minimum, denda {rp(fee)}",
                        high=True)
        finalize_statement(st, d)
        self.repo.update_statement(st)

    # ---------------------------------------------------------------- pinjaman
    def _loan_day(self, cust, loan, reminded):
        cid, persona, rng, d = cust["customer_id"], cust["demo_persona"], self.rng, self.d
        due = date.fromisoformat(loan["next_due_date"])

        def pay(how):
            self._savings(cid, "debit", "loan_installment", f"Cicilan {loan['type']} ({how})", loan["monthly_installment"])
            loan.update(days_past_due=0, status="current", remaining_months=max(0, loan["remaining_months"] - 1),
                        outstanding=max(0, loan["outstanding"] - round(loan["monthly_installment"] * 0.6)),
                        next_due_date=next_monthly(loan["due_day"], due + timedelta(days=1)).isoformat())
            self._event(cid, "loan_paid", f"Cicilan {loan['type']} {rp(loan['monthly_installment'])} dibayar ({how})"
                        + (" setelah diingatkan" if reminded else ""))

        if loan["days_past_due"] > 0:
            if rng.random() < (0.4 if reminded else 0.04):
                pay("pelunasan tunggakan")
            else:
                loan["days_past_due"] = (d - due).days
        elif d == due:
            savings = sum(a["balance"] for a in self.repo.get_savings_accounts(cid))
            if loan["autodebet"] and savings >= loan["monthly_installment"]:
                pay("autodebet")
            elif rng.random() < (0.85 if reminded else 0.3 if persona in ("overdue", "no_cc") else 0.7):
                pay("manual")
            else:
                loan.update(days_past_due=1, status="past_due")
                self._event(cid, "loan_missed", f"Cicilan {loan['type']} {rp(loan['monthly_installment'])} tidak terbayar",
                            high=True)
        elif 0 < (due - d).days <= 3 and not loan["autodebet"] and reminded and rng.random() < 0.5:
            pay("manual, lebih awal")
        self.repo.update_loan(loan)
