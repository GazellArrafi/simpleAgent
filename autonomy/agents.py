"""Agent otonom (ReAct) untuk mode autopilot: Manager → Case Handler → Analis (+ rekan) / Communicator.
Agent bebas memilih tools & rekan; aturan bank ditegakkan DI DALAM tools (lihat autonomy.md bagian 3)."""

import json
import uuid
from datetime import timedelta
from functools import lru_cache
from typing import Literal

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

import config
from agents.analysts import ANALYSTS
from agents.communicator import CTA, FOOTER, greeting, validate
from agents.data_agent import build_context
from autonomy import screener, store
from autonomy.runner import run_agent
from bank_data import tools as T
from bank_data.repository import get_repo
from channels import outbox, telegram
from llm import get_llm

# Papan kasus: insight hasil analitik per nasabah. send_message hanya boleh memakai insight dari sini.
CASE_BOARD: dict[str, dict[str, dict]] = {}
_budget = {"date": None, "cases": [], "max": 5}
THINK = "Sebelum memanggil tool, tulis 1 kalimat singkat alasanmu (Bahasa Indonesia)."


def get_recent_transactions(customer_id: str, days: int = 30, category: str = "") -> str:
    """Ringkasan transaksi kartu kredit terbaru (maks 40 baris, kolom penting saja). category opsional."""
    rows = get_repo().get_cc_transactions(_cid(customer_id), days=min(days, 90), category=category or None)
    return _json([{"tgl": t["datetime"][:16], "tipe": t["type"], "merchant": t["merchant"], "kategori": t["category"],
                   "nominal": t["amount"], "status": t["status"], "lokasi": t["location"]} for t in rows[-40:]])


def get_savings_overview(customer_id: str) -> str:
    """Saldo tabungan + 10 mutasi terakhir."""
    cid = _cid(customer_id)
    repo = get_repo()
    return _json({"rekening": repo.get_savings_accounts(cid),
                  "mutasi_terakhir": [{k: t[k] for k in ("datetime", "direction", "description", "amount")}
                                      for t in repo.get_savings_transactions(cid, days=30)[-10:]]})


DATA_TOOLS = [T.get_customer_profile, T.get_cc_statements, T.get_spending_by_category, T.get_loans,
              StructuredTool.from_function(get_recent_transactions), StructuredTool.from_function(get_savings_overview)]
if config.DATA_BACKEND == "postgres":  # analis juga bisa menulis query SQL sendiri (read-only)
    from bank_data.sql_tools import SQL_TOOLS
    DATA_TOOLS += SQL_TOOLS


def _today():
    return get_repo().reference_date()


def _sim() -> str:
    return _today().isoformat()


def _json(obj, limit=6000) -> str:
    s = json.dumps(obj, ensure_ascii=False, default=str)
    return s if len(s) <= limit else s[:limit] + " …(dipotong)"


def _cid(customer_id: str) -> str:
    cid = customer_id.strip().upper()
    if not get_repo().get_customer(cid):
        raise ValueError(f"Nasabah {customer_id} tidak ditemukan")
    return cid


def _delinquent(cid: str) -> bool:
    repo = get_repo()
    return any(s["days_past_due"] > 0 for s in repo.get_cc_statements(cid)[-1:]) or \
        any(l["days_past_due"] > 0 for l in repo.get_loans(cid))


# ================================================================ ANALIS
class Finding(BaseModel):
    insight_id: str = Field(description="insight_id persis dari hasil run_*_analysis")
    severity: Literal["critical", "warning", "info"]
    recommendation: str = Field(description="Rekomendasi personal 1-2 kalimat untuk nasabah")


class AnalystReport(BaseModel):
    summary: str = Field(description="Kesimpulan analisa 2-4 kalimat")
    findings: list[Finding] = Field(default_factory=list)
    contact_customer: bool = Field(description="Apakah nasabah perlu dihubungi sekarang")
    urgency: Literal["tinggi", "sedang", "rendah"]


ANALYST_SYSTEM = """Kamu adalah {title} di sebuah bank di Indonesia — agent otonom dalam tim personalisasi nasabah.
Fokus: {focus}

Cara kerja (kamu yang memutuskan detailnya):
1. Panggil `{tool}` lebih dulu — itu hasil hitungan resmi sistem (metrik + temuan berbasis aturan).
2. Gali data tambahan HANYA bila hasil analisa belum menjawab pertanyaan (hemat: maksimal 2 tool data).
   Bila tersedia `run_sql`, kamu boleh menulis query SELECT sendiri (cek `describe_database` dulu).
{colleague}
Lalu laporkan kesimpulan dalam format laporan.

Aturan: jangan mengarang atau menghitung ulang angka; `insight_id` di findings HARUS berasal dari hasil `{tool}`.
Kalau tidak ada temuan, findings kosong dan contact_customer=false. {think}"""
COLLEAGUE_HINT = ("3. Kalau temuanmu menyentuh domain lain (mis. limit ↔ tagihan, belanja ↔ limit, cicilan ↔ saldo), "
                  "kamu boleh bertanya ke rekan analis lewat `ask_colleague` (maksimal 1 kali).")


def _analysis_tool(name: str) -> StructuredTool:
    a = ANALYSTS[name]

    def run(customer_id: str) -> str:
        cid = _cid(customer_id)
        ctx, _ = build_context(cid, dict.fromkeys(["profile", *a.needs]))
        metrics, insights = a.compute(ctx, _today())
        CASE_BOARD.setdefault(cid, {}).update({i["insight_id"]: i for i in insights})
        return _json({"metrik": metrics, "temuan": [
            {k: i[k] for k in ("insight_id", "code", "severity", "title", "facts", "recommendation")} for i in insights]})

    return StructuredTool.from_function(
        run, name=f"run_{name.removesuffix('_analyst')}_analysis",
        description=f"Analitik resmi {a.title}: metrik + temuan berbasis aturan bank untuk satu nasabah.")


def _ask_colleague_tool(me: str) -> StructuredTool:
    others = [n for n in ANALYSTS if n != me]

    def ask_colleague(colleague: str, customer_id: str, question: str) -> str:
        if colleague not in others:
            return f"Rekan tidak dikenal. Pilihan: {', '.join(others)}"
        return consult(colleague, customer_id, question, asker=me, allow_colleague=False)

    return StructuredTool.from_function(
        ask_colleague, name="ask_colleague",
        description=f"Tanya rekan analis lain tentang nasabah yang sama. colleague: {', '.join(others)}")


@lru_cache(maxsize=None)
def analyst_agent(name: str, allow_colleague: bool):
    a = ANALYSTS[name]
    tool = _analysis_tool(name)
    tools = [tool, *DATA_TOOLS] + ([_ask_colleague_tool(name)] if allow_colleague else [])
    prompt = ANALYST_SYSTEM.format(title=a.title, focus=a.focus, tool=tool.name, think=THINK,
                                   colleague=COLLEAGUE_HINT if allow_colleague else "")
    return create_agent(get_llm(), tools, system_prompt=prompt, response_format=ToolStrategy(AnalystReport))


def consult(name: str, customer_id: str, question: str, asker: str = "case_handler", allow_colleague=True) -> str:
    cid = _cid(customer_id)
    if not ANALYSTS[name].eligible(get_repo().overview(cid)):
        return f"{name}: tidak relevan — nasabah tidak memiliki produk yang dianalisa analis ini."
    res = run_agent(name, analyst_agent(name, allow_colleague),
                    f"Nasabah: {cid}\nTanggal hari ini: {_sim()}\nPermintaan dari {asker}: {question}",
                    cid, recursion_limit=20)
    report = res["structured"]
    if not report:
        return res["text"] or "Analis tidak memberi laporan."
    board = CASE_BOARD.get(cid, {})
    for f in report.findings:
        if f.insight_id in board and f.recommendation.strip():
            board[f.insight_id]["recommendation"] = f.recommendation.strip()[:400]
    return _json(report.model_dump())


# ================================================================ COMMUNICATOR
COMM_SYSTEM = """Kamu adalah Communicator bank — agent otonom yang menulis & mengirim notifikasi aplikasi ke nasabah.
1. Cek `get_contact_history` (sapaan yang benar, pesan yang sudah terkirim) dan `get_insight` (fakta resmi).
2. Putuskan sendiri insight mana yang layak dikirim (boleh tidak mengirim apa-apa kalau tidak perlu / sudah pernah).
3. Kirim lewat `send_message`. Kalau DITOLAK, baca alasannya, perbaiki pesan, lalu coba lagi (maks 2 kali per insight).

Gaya: Bahasa Indonesia sopan & hangat, awali dengan sapaan dari get_contact_history. title ≤60 karakter,
body ≤500 karakter, 2-4 kalimat. Angka & tanggal disalin PERSIS dari facts. Jangan minta PIN/OTP/password,
jangan pakai link, jangan tulis footer keamanan (ditambahkan sistem). Akhiri dengan ringkasan apa yang kamu kirim. {think}"""


def get_contact_history(customer_id: str) -> str:
    """Riwayat kontak nasabah: sapaan yang benar, pesan 14 hari terakhir, catatan memori, follow-up terbuka."""
    cid = _cid(customer_id)
    since = (_today() - timedelta(days=14)).isoformat()
    msgs = [{k: r[k] for k in ("sim_date", "code", "title", "status")} for r in outbox.for_customer(cid)
            if r.get("sim_date", "") >= since]
    return _json({"sapaan": greeting(get_repo().get_customer(cid)), "pesan_14_hari": msgs,
                  "memori": store.get_memory(cid, 8), "followup_terbuka": store.list_followups("open", cid)})


def get_insight(customer_id: str, insight_id: str = "") -> str:
    """Fakta resmi insight hasil analisa (kosongkan insight_id untuk melihat semua insight nasabah)."""
    board = CASE_BOARD.get(_cid(customer_id), {})
    if insight_id:
        return _json(board.get(insight_id) or f"insight {insight_id} tidak ada. Tersedia: {list(board)}")
    return _json(list(board.values()))


def send_message(customer_id: str, insight_id: str, title: str, body: str) -> str:
    """Kirim notifikasi ke nasabah. Ditolak bila melanggar aturan bank (alasan dikembalikan)."""
    cid = _cid(customer_id)
    ins = CASE_BOARD.get(cid, {}).get(insight_id)
    if not ins:
        return "DITOLAK: insight_id tidak dikenal. Gunakan insight dari hasil analisa (lihat get_insight)."
    body, title = body.strip(), title.strip()
    problem = validate(body, ins) or ("judul terlalu panjang" if len(title) > 80 else None)
    if problem:
        return f"DITOLAK: {problem}. Perbaiki pesan lalu kirim lagi."
    d, history = _today(), outbox.for_customer(cid)
    if any(r["insight_id"] == insight_id for r in history):
        return "DITOLAK: insight ini sudah pernah dikirim ke nasabah. Jangan kirim ulang."
    if any(r["code"] == ins["code"] and r["sim_date"] >= (d - timedelta(days=2)).isoformat() for r in history):
        return "DITOLAK: topik yang sama sudah dikirim dalam 2 hari terakhir (anti-spam)."
    if sum(r["sim_date"] == d.isoformat() for r in history) >= 2:
        return "DITOLAK: batas 2 pesan per nasabah per hari tercapai."
    if sum(r["sim_date"] >= (d - timedelta(days=6)).isoformat() for r in history) >= 5:
        return "DITOLAK: batas 5 pesan per nasabah per minggu tercapai."
    if ins["category"] == "offer" and _delinquent(cid):
        return "DITOLAK: nasabah sedang menunggak — penawaran tidak boleh dikirim (responsible lending)."
    record = {"message_id": "AP" + uuid.uuid4().hex[:10], "customer_id": cid, "sim_date": d.isoformat(),
              "insight_id": insight_id, "code": ins["code"], "agent": ins["agent"], "severity": ins["severity"],
              "category": ins["category"], "title": title, "body": body,
              "cta": CTA.get(ins["code"]) or ins["facts"].get("cara", ""), "footer": FOOTER, "source": "autopilot",
              "channels": ["app"], "status": "sent", "created_at": d.isoformat() + "T09:00:00", "send_at": d.isoformat() + "T09:00:00"}
    if telegram.enabled():
        ok, info = telegram.send(telegram.format_message(record), get_repo().get_customer(cid).get("telegram_chat_id"))
        record["telegram"] = info
        if ok:
            record["channels"].append("telegram")
    outbox.append(record)
    store.add_memory(cid, "communicator", f"Mengirim pesan {ins['code']}: {title}", d.isoformat())
    return f"TERKIRIM ({', '.join(record['channels'])}): {title}"


@lru_cache(maxsize=1)
def communicator_agent():
    tools = [StructuredTool.from_function(f) for f in (get_contact_history, get_insight, send_message)]
    return create_agent(get_llm(), tools, system_prompt=COMM_SYSTEM.format(think=THINK))


# ================================================================ CASE HANDLER
CASE_SYSTEM = """Kamu adalah Case Handler — agent otonom yang menangani SATU nasabah sampai tuntas.
Kamu yang memutuskan langkahnya. Pola umum:
- Baca `read_customer_memory` (riwayat, follow-up, kejadian hari ini) & `get_customer_overview`.
- Konsultasikan analis yang relevan (`consult_*`) — pilih sendiri, boleh lebih dari satu, beri pertanyaan yang spesifik.
- Putuskan: hubungi nasabah (`ask_communicator` + instruksi insight mana & nadanya) atau cukup dipantau.
- Jika perlu memastikan hasilnya (mis. apakah nasabah sudah bayar), `schedule_followup` ke tanggal yang masuk akal.
- Tutup follow-up lama yang sudah selesai (`close_followup`) & tulis catatan ringkas (`write_memory`).
Hindari spam: kalau nasabah baru saja dihubungi untuk hal yang sama, jangan hubungi lagi.
Akhiri dengan ringkasan 2-3 kalimat: temuan, tindakan, langkah berikutnya. {think}"""


def read_customer_memory(customer_id: str) -> str:
    """Memori tim tentang nasabah: catatan sebelumnya, follow-up terbuka, pesan 14 hari terakhir, kejadian hari ini."""
    cid = _cid(customer_id)
    since = (_today() - timedelta(days=14)).isoformat()
    return _json({"memori": store.get_memory(cid, 10), "followup_terbuka": store.list_followups("open", cid),
                  "pesan_14_hari": [{k: r[k] for k in ("sim_date", "code", "title")} for r in outbox.for_customer(cid)
                                    if r.get("sim_date", "") >= since],
                  "kejadian_hari_ini": [e for e in store.events_on(_sim()) if e["customer_id"] == cid]})


def ask_communicator(customer_id: str, instruction: str) -> str:
    """Minta Communicator menghubungi nasabah. instruction: insight mana yang dikirim, tujuan & nada pesan."""
    cid = _cid(customer_id)
    if not CASE_BOARD.get(cid):
        return "Belum ada insight untuk nasabah ini. Konsultasikan analis dulu."
    res = run_agent("communicator", communicator_agent(),
                    f"Nasabah: {cid}\nTanggal: {_sim()}\nInstruksi dari case handler: {instruction}", cid, recursion_limit=20)
    return res["text"] or "Communicator selesai tanpa ringkasan."


def schedule_followup(customer_id: str, in_days: int, reason: str) -> str:
    """Jadwalkan pengecekan ulang nasabah ini N hari lagi (1-14)."""
    cid = _cid(customer_id)
    fu = store.add_followup(cid, _today() + timedelta(days=max(1, min(14, in_days))), reason, "case_handler", _sim())
    return f"Follow-up {fu['followup_id']} dijadwalkan {fu['due_date']}: {reason}"


def close_followup(followup_id: str, outcome: str) -> str:
    """Tutup follow-up yang sudah selesai, dengan hasilnya."""
    return "Follow-up ditutup." if store.close_followup(followup_id, outcome, _sim()) else "Follow-up tidak ditemukan/sudah ditutup."


def write_memory(customer_id: str, note: str) -> str:
    """Simpan catatan ringkas tentang nasabah untuk tim di hari-hari berikutnya."""
    store.add_memory(_cid(customer_id), "case_handler", note[:500], _sim())
    return "Catatan disimpan."


def _consult_tool(name: str) -> StructuredTool:
    a = ANALYSTS[name]

    def run(customer_id: str, question: str) -> str:
        return consult(name, customer_id, question)

    return StructuredTool.from_function(run, name=f"consult_{name}", description=f"Minta {a.title} menganalisa nasabah. {a.description}")


@lru_cache(maxsize=1)
def case_agent():
    tools = [T.get_customer_overview, *[_consult_tool(n) for n in ANALYSTS],
             *[StructuredTool.from_function(f) for f in (read_customer_memory, ask_communicator, schedule_followup,
                                                          close_followup, write_memory)]]
    return create_agent(get_llm(), tools, system_prompt=CASE_SYSTEM.format(think=THINK))


# ================================================================ MANAGER
MANAGER_SYSTEM = """Kamu adalah Manager tim personalisasi nasabah sebuah bank — agent OTONOM.
Tidak ada yang akan memberimu perintah harian: kamu bangun setiap hari simulasi, menilai situasi, dan memutuskan sendiri.
Tools: `get_today_briefing` (kejadian baru, follow-up jatuh tempo, budget), `scan_portfolio` (radar nasabah —
kamu pilih kriteria yang sesuai misi), `read_customer_memory`, `open_case` (delegasikan satu nasabah ke Case Handler),
`close_followup`, `write_daily_report`.
Prinsip: utamakan yang paling mendesak & paling berdampak pada misi, hormati budget kasus, jangan buka kasus
untuk nasabah yang baru saja ditangani tanpa alasan baru, dan selalu akhiri hari dengan `write_daily_report`
(ringkas: apa yang terjadi, keputusanmu, hasil, rencana besok). {think}"""


def get_today_briefing() -> str:
    """Briefing hari ini: tanggal, ringkasan kejadian baru dari dunia, follow-up jatuh tempo, sisa budget kasus."""
    d = _sim()
    events = store.events_on(d)
    counts = {}
    for e in events:
        counts[e["type"]] = counts.get(e["type"], 0) + 1
    notable = [e for e in events if e["priority"] == "high" or e["type"] in ("cc_payment_received", "loan_paid")]
    reports = store.read_reports()
    return _json({"tanggal": d, "jumlah_kejadian": counts, "kejadian_penting": notable[:30],
                  "followup_jatuh_tempo": store.due_followups(d),
                  "budget_kasus_tersisa": _budget["max"] - len(_budget["cases"]),
                  "laporan_kemarin": reports[-1]["report"][:800] if reports else None}, limit=9000)


def scan_portfolio(criteria: list[str], limit: int = 10) -> str:
    return _json(screener.scan(criteria, limit))


scan_portfolio.__doc__ = ("Radar portofolio: cari nasabah yang cocok dengan kriteria. Kriteria tersedia: "
                          + "; ".join(f"{k} = {v}" for k, v in screener.CRITERIA.items()))


def open_case(customer_id: str, goal: str) -> str:
    """Delegasikan satu nasabah ke Case Handler dengan tujuan yang jelas. Memakai 1 budget kasus."""
    cid = _cid(customer_id)
    if cid in _budget["cases"]:
        return f"Kasus {cid} sudah dibuka hari ini."
    if len(_budget["cases"]) >= _budget["max"]:
        return "DITOLAK: budget kasus hari ini habis. Prioritaskan sisanya besok / catat di laporan."
    _budget["cases"].append(cid)
    mission = store.load_mission()
    res = run_agent("case_handler", case_agent(),
                    f"Tanggal: {_sim()}\nMisi tim: {mission['goal']}\nBatasan: {mission['constraints']}\n"
                    f"Nasabah: {cid}\nTujuan dari Manager: {goal}", cid, recursion_limit=40)
    return res["text"] or "Case handler selesai tanpa ringkasan."


def write_daily_report(report: str) -> str:
    """Tulis laporan harian (wajib sebelum selesai)."""
    store.add_report(_sim(), report)
    return "Laporan disimpan."


@lru_cache(maxsize=1)
def manager_agent():
    tools = [StructuredTool.from_function(f) for f in (get_today_briefing, scan_portfolio, read_customer_memory,
                                                        open_case, close_followup, write_daily_report)]
    return create_agent(get_llm(), tools, system_prompt=MANAGER_SYSTEM.format(think=THINK))


def run_manager_day() -> dict:
    mission = store.load_mission()
    _budget.update(date=_sim(), cases=[], max=int(mission.get("max_cases_per_day", 5)))
    return run_agent("manager", manager_agent(),
                     f"Selamat pagi. Hari ini {_sim()}.\nMISI: {mission['goal']}\nBATASAN: {mission['constraints']}\n"
                     f"Budget: maksimal {_budget['max']} kasus hari ini.\nMulailah bekerja.", recursion_limit=60)
