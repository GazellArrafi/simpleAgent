"""Lima agent analis. Masing-masing: hitung metrik (deterministik) -> LLM menafsirkan & memberi rekomendasi."""

import time
from dataclasses import dataclass
from datetime import date
from typing import Callable

from pydantic import BaseModel, Field

from agents.base import profile_for_llm, to_json, trace
from analytics import cc_billing, cc_limit, loan, offer, spending
from llm import structured

SYSTEM = """Kamu adalah {title} di sebuah bank di Indonesia.
Fokusmu: {focus}

Kamu menerima profil singkat nasabah, METRIK yang sudah dihitung sistem, dan daftar TEMUAN (insight) berbasis aturan.
Tugas:
1. `analysis`: ringkasan analisa internal 2-4 kalimat (Bahasa Indonesia) untuk tim bank — apa kondisi nasabah & risikonya.
2. `items`: untuk SETIAP temuan, tulis `recommendation` 1-2 kalimat yang personal & konkret, ditujukan ke nasabah.

Aturan keras:
- Jangan menghitung ulang atau mengarang angka/tanggal. Hanya pakai angka yang tertulis di `facts` atau metrik.
- Jangan meminta PIN, OTP, password, atau data pribadi. Jangan menyertakan link.
- `insight_id` harus sama persis dengan yang diberikan."""


class RecommendationItem(BaseModel):
    insight_id: str
    recommendation: str = Field(description="Rekomendasi personal 1-2 kalimat untuk nasabah")


class AnalystReview(BaseModel):
    analysis: str = Field(description="Ringkasan analisa internal 2-4 kalimat")
    items: list[RecommendationItem] = Field(default_factory=list)


@dataclass
class AnalystAgent:
    name: str
    title: str
    description: str          # dibaca supervisor saat memilih analis
    focus: str                # persona untuk LLM
    needs: tuple[str, ...]    # data yang diminta ke Data Agent
    eligible: Callable[[dict], bool]
    compute: Callable

    def node(self, state: dict) -> dict:
        started = time.perf_counter()
        sim = date.fromisoformat(state["sim_date"])
        metrics, insights = self.compute(state["context"], sim)
        analysis, used_llm, err = self._review(state["context"].get("profile", {}), metrics, insights)
        codes = ", ".join(f"{i['code']}({i['severity']})" for i in insights) or "tidak ada temuan"
        note = {"agent": self.name, "title": self.title, "analysis": analysis, "metrics": metrics,
                "insight_count": len(insights), "llm": used_llm}
        return {"insights": insights, "analyst_notes": [note],
                "trace": [trace(self.name, "analisa selesai", codes + (f" | LLM fallback: {err}" if err else ""),
                                llm=used_llm, started=started)]}

    def _review(self, profile, metrics, insights):
        if not insights:  # tidak ada temuan -> tidak perlu memanggil LLM (hemat biaya)
            return "Tidak ada temuan yang perlu ditindaklanjuti dari data saat ini.", False, None
        fallback = " ".join(i["title"] + "." for i in insights)
        payload = {"profil": profile_for_llm(profile), "metrik": metrics,
                   "temuan": [{k: i[k] for k in ("insight_id", "code", "severity", "title", "facts", "recommendation")}
                              for i in insights]}
        out, err = structured(AnalystReview, SYSTEM.format(title=self.title, focus=self.focus), to_json(payload))
        if not out:
            return fallback, False, None if err == "offline" else err
        by_id = {i["insight_id"]: i for i in insights}
        for item in out.items:
            rec = item.recommendation.strip()
            if item.insight_id in by_id and rec and len(rec) <= 400:
                by_id[item.insight_id]["recommendation"] = rec
        return out.analysis.strip() or fallback, True, None


ANALYSTS: dict[str, AnalystAgent] = {a.name: a for a in [
    AnalystAgent(
        "cc_billing_analyst", "Analis Tagihan Kartu Kredit",
        "Cek jatuh tempo & status pembayaran tagihan CC, tunggakan, kebiasaan bayar minimum, saran autodebet.",
        "pengingat jatuh tempo, tunggakan, dan kesehatan pola pembayaran kartu kredit.",
        ("profile", "cards", "statements", "savings"),
        lambda o: o["has_credit_card"], cc_billing.analyze),
    AnalystAgent(
        "cc_limit_analyst", "Analis Limit Kartu Kredit",
        "Hitung pemakaian limit CC, transaksi ditolak, dan proyeksi kapan limit habis.",
        "pemakaian limit dan risiko transaksi tertolak.",
        ("cards", "cc_transactions"),
        lambda o: o["has_credit_card"], cc_limit.analyze),
    AnalystAgent(
        "spending_analyst", "Analis Pola Belanja",
        "Bandingkan belanja 30 hari vs bulan sebelumnya, kategori yang melonjak, langganan, transaksi tidak biasa.",
        "pola belanja, lonjakan pengeluaran, langganan rutin, dan transaksi mencurigakan.",
        ("profile", "cc_transactions"),
        lambda o: o["has_credit_card"] and o["cc_transactions_90d"] > 0, spending.analyze),
    AnalystAgent(
        "loan_analyst", "Analis Pinjaman",
        "Cek cicilan KPR/KKB/KTA yang mendekati jatuh tempo atau tertunggak, dan kecukupan saldo.",
        "cicilan pinjaman dan kecukupan saldo untuk membayarnya.",
        ("loans", "savings"),
        lambda o: o["has_loan"], loan.analyze),
    AnalystAgent(
        "offer_analyst", "Analis Penawaran Personal",
        "Pilih 1 penawaran/promo paling relevan dari katalog (hanya jika nasabah consent marketing).",
        "next-best-offer yang relevan dan bertanggung jawab (tidak menawarkan kredit ke nasabah bermasalah).",
        ("profile", "cards", "statements", "cc_transactions", "loans", "savings", "offers"),
        lambda o: o["marketing_consent"], offer.analyze),
]}
