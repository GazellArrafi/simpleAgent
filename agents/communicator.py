"""Communicator: menulis pesan personal untuk nasabah dari insight terpilih (rules.md C).
Output LLM divalidasi; kalau gagal pakai template."""

import re
import time

from pydantic import BaseModel, Field

import config
from agents.base import profile_for_llm, to_json, trace
from llm import structured

FOOTER = "🔒 Bank tidak pernah meminta PIN, OTP, atau password Anda."
CTA = {
    "CC_OVERDUE": "Bayar sekarang di app: Kartu Kredit > Bayar Tagihan",
    "CC_DUE_SOON": "Bayar di app: Kartu Kredit > Bayar Tagihan",
    "CC_DUE_UPCOMING": "Lihat tagihan di app: Kartu Kredit > Tagihan",
    "CC_MIN_PAYMENT_HABIT": "Simulasikan cicilan tagihan di app: Kartu Kredit > Cicilan Tagihan",
    "CC_AUTODEBET_SUGGEST": "Aktifkan di app: Kartu Kredit > Autodebet",
    "CC_LIMIT_CRITICAL": "Cek limit & bayar sebagian di app: Kartu Kredit",
    "CC_LIMIT_HIGH": "Cek limit di app: Kartu Kredit",
    "CC_LIMIT_PROJECTION": "Pantau limit di app: Kartu Kredit",
    "SPENDING_SPIKE": "Lihat ringkasan belanja di app: Insight Keuangan",
    "SPENDING_VS_INCOME": "Lihat ringkasan belanja di app: Insight Keuangan",
    "UNUSUAL_TRANSACTION": "Blokir sementara di app: Kartu Kredit > Kelola Kartu",
    "SUBSCRIPTION_SUMMARY": "Lihat transaksi berulang di app: Kartu Kredit > Transaksi",
    "LOAN_OVERDUE": "Bayar cicilan di app: Pinjaman > Bayar",
    "LOAN_DUE_SOON": "Bayar / aktifkan autodebet di app: Pinjaman",
}
# Footer keamanan ditambahkan kode, jadi isi pesan tidak perlu menyebut kredensial sama sekali → tolak semua.
FORBIDDEN = re.compile(r"\b(PIN|OTP|password|kata\s*sandi|CVV|CVC)\b|https?://|www\.|bit\.ly", re.I)
RUPIAH = re.compile(r"Rp\s?\d{1,3}(?:\.\d{3})*")

SYSTEM = """Kamu adalah Communicator di sebuah bank di Indonesia. Tulis pesan notifikasi aplikasi untuk nasabah,
SATU pesan untuk SETIAP insight yang diberikan.

Aturan:
- Bahasa Indonesia yang sopan, hangat, jelas. Awali dengan sapaan persis: "{greeting}".
- `title` maksimal 60 karakter. `body` maksimal 500 karakter, 2-4 kalimat, boleh pakai 1 emoji yang relevan.
- Sebut angka & tanggal penting PERSIS seperti di `facts` (jangan hitung ulang, jangan bulatkan, jangan mengarang).
- Sertakan rekomendasi yang personal (gunakan field `recommendation`).
- Untuk insight severity critical: tegas tapi tetap sopan, tidak menakut-nakuti.
- Untuk penawaran (category offer): ringan, tidak memaksa.
- DILARANG meminta PIN/OTP/password/CVV/data pribadi, DILARANG menyertakan link. Jangan tulis footer keamanan (ditambahkan sistem).
- `insight_id` harus sama persis dengan input."""


class Message(BaseModel):
    insight_id: str
    title: str = Field(description="Judul notifikasi, maks 60 karakter")
    body: str = Field(description="Isi pesan, maks 500 karakter")


class Messages(BaseModel):
    items: list[Message]


def greeting(profile: dict) -> str:
    if profile.get("segment") == "Prioritas" or profile.get("age", 0) >= 45:
        return f"{'Bapak' if profile.get('gender') == 'M' else 'Ibu'} {profile.get('nickname', '')}"
    return f"Kak {profile.get('nickname', '')}"


def template(insight: dict, greet: str) -> tuple[str, str]:
    if insight["category"] == "offer":
        f = insight["facts"]
        return f["penawaran"], f"Halo {greet}, ada penawaran yang mungkin cocok untuk Anda: {f['penawaran']}.\n\n{f['deskripsi']}"
    facts = "\n".join(f"• {k.replace('_', ' ').capitalize()}: {v}" for k, v in insight["facts"].items())
    return insight["title"], f"Halo {greet}, {insight['title'][0].lower() + insight['title'][1:]}.\n\n{facts}\n\n{insight['recommendation']}"


def validate(body: str, insight: dict) -> str | None:
    """Return alasan gagal, atau None kalau lolos."""
    if not body or len(body) > config.RULES["max_body_chars"]:
        return "panjang pesan tidak valid"
    if FORBIDDEN.search(body):
        return "mengandung kata/link terlarang"
    allowed = (" ".join(map(str, insight["facts"].values())) + " " + insight["recommendation"]).replace(" ", "")
    for amount in RUPIAH.findall(body):
        if amount.replace(" ", "") not in allowed:
            return f"angka {amount} tidak ada di facts"
    return None


def node(state: dict) -> dict:
    started = time.perf_counter()
    selected = state.get("selected", [])
    if not selected:
        return {"messages": [], "trace": [trace("communicator", "tidak ada pesan", "Tidak ada insight yang perlu dikirim.")]}
    profile = state["context"]["profile"]
    greet = greeting(profile)
    payload = {"nasabah": profile_for_llm(profile), "sapaan": greet,
               "insights": [{k: i[k] for k in ("insight_id", "severity", "category", "title", "facts", "recommendation")}
                            for i in selected]}
    out, err = structured(Messages, SYSTEM.format(greeting=greet), to_json(payload))
    drafts = {m.insight_id: m for m in out.items} if out else {}

    messages, notes = [], []
    for i in selected:
        draft, source = drafts.get(i["insight_id"]), "llm"
        problem = "tidak ada draft LLM" if not draft else validate(draft.body.strip(), i)
        if problem:
            title, body = template(i, greet)
            source = "template"
            if out:
                notes.append(f"{i['code']}: {problem} → template")
        else:
            title, body = draft.title.strip()[:80], draft.body.strip()
        messages.append({"insight_id": i["insight_id"], "code": i["code"], "agent": i["agent"],
                         "severity": i["severity"], "category": i["category"], "title": title, "body": body,
                         "cta": CTA.get(i["code"]) or i["facts"].get("cara", ""), "footer": FOOTER, "source": source})
    detail = "\n".join(f"[{m['source']}] {m['title']}" for m in messages)
    if notes:
        detail += "\nGuard: " + "; ".join(notes)
    if err and err != "offline":
        detail += f"\nLLM gagal: {err}"
    return {"messages": messages,
            "trace": [trace("communicator", f"menulis {len(messages)} pesan untuk {greet}", detail,
                            llm=any(m["source"] == "llm" for m in messages), started=started)]}
