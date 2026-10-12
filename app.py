"""UI mockup simpleAgent (Streamlit).  Jalankan:  streamlit run app.py"""

import html

import pandas as pd
import streamlit as st

import config
from agents.analysts import ANALYSTS
from agents.supervisor import DEFAULT_OBJECTIVE
from analytics.common import rp, tgl
from llm import is_online, llm_status

st.set_page_config(page_title="simpleAgent — Personalisasi Nasabah", page_icon="🏦", layout="wide")

SEV_COLOR = {"critical": "#d64545", "warning": "#e0a100", "info": "#3b82f6"}
SEV_LABEL = {"critical": "KRITIS", "warning": "PERHATIAN", "info": "INFO"}
NODE_LABEL = {"supervisor_plan": "Supervisor · rencana", "data_agent": "Data Agent", "supervisor_review": "Supervisor · review",
              "communicator": "Communicator", "delivery": "Delivery", **{n: a.title for n, a in ANALYSTS.items()}}

st.markdown("""
<style>
.phone {max-width: 420px; margin: 0 auto; border: 10px solid rgba(128,128,128,.35); border-radius: 32px;
        padding: 18px 14px; min-height: 420px; background: rgba(128,128,128,.06);}
.phone-head {text-align:center; font-size:.8rem; opacity:.7; margin-bottom:10px;}
.notif {border-left: 5px solid var(--sev); background: rgba(128,128,128,.12); border-radius: 12px;
        padding: 10px 12px; margin-bottom: 12px; font-size: .9rem;}
.notif .meta {font-size:.72rem; opacity:.75; display:flex; justify-content:space-between; margin-bottom:4px;}
.notif .badge {color: var(--sev); font-weight: 700;}
.notif .title {font-weight: 700; margin-bottom: 4px;}
.notif .cta {margin-top: 8px; font-weight: 600;}
.notif .footer {margin-top: 6px; font-size: .72rem; opacity: .7;}
.sev {display:inline-block; padding:1px 8px; border-radius:10px; color:white; font-size:.72rem; font-weight:700;}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------- data
def repo():
    from bank_data.repository import get_repo
    return get_repo()  # di-cache per proses (lru_cache), dipakai bersama oleh agent


def data_ready() -> bool:
    if config.DATA_BACKEND == "postgres":
        try:
            repo()
            return True
        except Exception:
            return False
    return (config.DATA_DIR / "meta.json").exists()


def regenerate(n, seed):
    from bank_data.repository import reload_repo
    from data_gen.generate_data import generate_and_save
    generate_and_save(n, seed)
    if config.DATA_BACKEND == "postgres":
        from bank_data.db_admin import load_from_json
        load_from_json(log=lambda *_: None)
    reload_repo()


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("🏦 simpleAgent")
    st.caption("Mockup multi-agent personalisasi nasabah")
    st.markdown(f"**LLM:** `{llm_status()}`  \n**Sumber data:** `{config.DATA_BACKEND}`")
    if not data_ready():
        st.warning("Data dummy belum ada.")
        if st.button("Generate data dummy", type="primary"):
            with st.spinner("Membuat data..."):
                regenerate(200, 42)
            st.rerun()
        st.stop()
    R = repo()
    st.markdown(f"**Tanggal simulasi:** {tgl(R.reference_date(), with_day=True)}")
    customers = R.list_customers()
    labels = {c["customer_id"]: f"{c['customer_id']} · {c['full_name']} · {c['demo_persona']}" for c in customers}
    cid = st.selectbox("Nasabah", list(labels), format_func=labels.get,
                       help="Label setelah nama = persona dari generator (hanya untuk demo, tidak dipakai agent).")
    objective = st.text_area("Objective untuk Supervisor", DEFAULT_OBJECTIVE, height=90)
    run = st.button("▶ Jalankan agent", type="primary", width="stretch")

    with st.expander("Batch (simulasi job harian)"):
        n_batch = st.number_input("Jumlah nasabah", 1, len(customers), min(20, len(customers)))
        if not is_online():
            st.caption("Mode offline: cepat (±0,1 dtk/nasabah).")
        else:
            st.caption("Mode LLM: ±7 panggilan LLM per nasabah.")
        run_batch = st.button("Jalankan batch", width="stretch")
    with st.expander("Pengaturan data"):
        n_gen = st.number_input("Jumlah nasabah", 8, 5000, 200, step=50)
        seed = st.number_input("Seed", 0, 99999, 42)
        if st.button("Generate ulang data", width="stretch"):
            with st.spinner("Membuat data..."):
                regenerate(int(n_gen), int(seed))
            st.session_state.pop("result", None)
            st.rerun()
        if st.button("Kosongkan outbox", width="stretch"):
            from channels import outbox
            outbox.clear()
            st.toast("Outbox dikosongkan")
    m = R.meta["counts"]
    st.caption(f"{m['customers']:,} nasabah · {m['cc_transactions']:,} transaksi CC · "
               f"{m['savings_transactions']:,} mutasi tabungan · {m['cc_statements']:,} tagihan · {m['loans']:,} pinjaman")


# ---------------------------------------------------------------- run
def run_one(customer_id):
    from graph.workflow import run_customer
    with st.status("Agent bekerja...", expanded=True) as status:
        def on_step(node):
            st.write(f"✔ {NODE_LABEL.get(node, node)}")
        result = run_customer(customer_id, objective, on_step=on_step)
        status.update(label="Selesai", state="complete", expanded=False)
    st.session_state["result"] = result


if run:
    run_one(cid)

if run_batch:
    from graph.workflow import run_customer
    bar, sent = st.progress(0.0, "Batch berjalan..."), 0
    targets = customers[: int(n_batch)]
    for i, c in enumerate(targets, 1):
        res = run_customer(c["customer_id"], objective)
        sent += sum(1 for d in res.get("deliveries", []) if d["status"] != "duplicate_skipped")
        bar.progress(i / len(targets), f"{i}/{len(targets)} · {c['full_name']}")
    st.success(f"Batch selesai: {len(targets)} nasabah diproses, {sent} pesan baru masuk outbox.")

result = st.session_state.get("result")
if result and result["customer_id"] != cid:
    result = None

# ---------------------------------------------------------------- header
cust = R.get_customer(cid)
cards, loans, savings = R.get_credit_cards(cid), R.get_loans(cid), R.get_savings_accounts(cid)
st.subheader(f"{cust['full_name']}  ·  {cust['segment']}")
st.caption(f"{cust['occupation']} · {cust['city']} · {cust['age']} th · penghasilan {rp(cust['monthly_income'])}/bln · "
           f"kanal: {cust['preferred_channel']} · consent marketing: {'ya' if cust['marketing_consent'] else 'tidak'}")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Saldo tabungan", rp(sum(a["balance"] for a in savings)))
if cards:
    card = cards[0]
    sts = R.get_cc_statements(cid)
    c2.metric("Limit CC terpakai", rp(card["current_balance"]), f"{card['current_balance'] / card['credit_limit']:.0%} dari {rp(card['credit_limit'])}",
              delta_color="off")
    if sts:
        c3.metric("Tagihan CC terakhir", rp(sts[-1]["total_due"]), f"jatuh tempo {tgl(sts[-1]['due_date'])} · {sts[-1]['status']}",
                  delta_color="off")
else:
    c2.metric("Kartu kredit", "—")
c4.metric("Pinjaman", ", ".join(l["type"] for l in loans) or "—",
          f"cicilan {rp(loans[0]['monthly_installment'])}" if loans else None, delta_color="off")

tabs = st.tabs(["🧭 Alur Agent", "🔎 Hasil Analisa", "📱 Inbox Nasabah", "🗂️ Data Nasabah", "💬 Tanya Data Agent", "📤 Outbox",
                "🤖 Autopilot"])


# ---------------------------------------------------------------- tab: alur
def graph_dot(res):
    plan = set(res["plan"]) if res else set()
    ran = lambda n: res is not None and (n in plan or n not in ANALYSTS)  # noqa: E731
    def node(n, shape="box"):
        color = "#2e7d32" if ran(n) else "#9e9e9e"
        style = "filled" if ran(n) else "dashed"
        fill = "#e8f5e9" if ran(n) else "#fafafa"
        return f'"{n}" [label="{NODE_LABEL[n]}", shape={shape}, style="{style},rounded", color="{color}", fillcolor="{fill}", fontcolor="#222"];'
    lines = ["digraph G {", 'rankdir=LR; bgcolor="transparent"; node [fontname="Helvetica", fontsize=11];',
             'edge [color="#888"];', '"start" [label="Trigger", shape=circle, style=filled, fillcolor="#ddd"];']
    lines += [node(n) for n in NODE_LABEL]
    lines += ['"start" -> "supervisor_plan" -> "data_agent";']
    for a in ANALYSTS:
        style = "solid" if res and a in plan else "dashed"
        lines.append(f'"data_agent" -> "{a}" [style={style}]; "{a}" -> "supervisor_review" [style={style}];')
    lines += ['"supervisor_review" -> "communicator" -> "delivery";', "}"]
    return "\n".join(lines)


with tabs[0]:
    st.graphviz_chart(graph_dot(result), width="stretch")
    if not result:
        st.info("Pilih nasabah lalu klik **▶ Jalankan agent** di sidebar.")
    else:
        st.markdown(f"**Objective:** {result['objective']}")
        for t in result["trace"]:
            badge = " `LLM`" if t["llm"] else ""
            dur = f" · {t['duration_ms']} ms" if "duration_ms" in t else ""
            with st.container(border=True):
                st.markdown(f"**{t['agent']}**{badge} — {t['action']}  \n<small>{t['ts']}{dur}</small>",
                            unsafe_allow_html=True)
                if t["detail"]:
                    st.code(t["detail"], language=None)


# ---------------------------------------------------------------- tab: analisa
def sev_badge(sev):
    return f'<span class="sev" style="background:{SEV_COLOR[sev]}">{SEV_LABEL[sev]}</span>'


with tabs[1]:
    if not result:
        st.info("Belum ada hasil. Jalankan agent dulu.")
    else:
        for note in result.get("analyst_notes", []):
            with st.container(border=True):
                st.markdown(f"### {note['title']} {'`LLM`' if note['llm'] else '`aturan`'}")
                st.write(note["analysis"])
                for ins in [i for i in result["insights"] if i["agent"] == note["agent"]]:
                    st.markdown(f"{sev_badge(ins['severity'])} **{ins['title']}** <small>`{ins['code']}` · prioritas {ins['priority']}</small>",
                                unsafe_allow_html=True)
                    st.table(pd.DataFrame(ins["facts"].items(), columns=["fakta", "nilai"]).set_index("fakta"))
                    st.markdown(f"💡 _{ins['recommendation']}_")
                with st.expander("Metrik mentah"):
                    st.json(note["metrics"], expanded=False)
        st.markdown("#### Keputusan Supervisor")
        cols = st.columns(2)
        cols[0].markdown("**Dikirim**")
        for i in result.get("selected", []):
            cols[0].markdown(f"{sev_badge(i['severity'])} {i['title']}", unsafe_allow_html=True)
        cols[1].markdown("**Ditahan**")
        for i in result.get("held", []):
            cols[1].markdown(f"{sev_badge(i['severity'])} {i['title']}  \n<small>↳ {i['hold_reason']}</small>",
                             unsafe_allow_html=True)


# ---------------------------------------------------------------- tab: inbox
with tabs[2]:
    from channels import outbox
    msgs = sorted(outbox.for_customer(cid), key=lambda r: r["created_at"], reverse=True)
    items = []
    for r in msgs:
        body = html.escape(r["body"]).replace("\n", "<br>")
        status = "🕗 dijadwalkan " + r["send_at"][11:16] if r["status"] == "scheduled" else "✓ terkirim"
        items.append(
            f'<div class="notif" style="--sev:{SEV_COLOR[r["severity"]]}">'
            f'<div class="meta"><span class="badge">{SEV_LABEL[r["severity"]]}</span>'
            f'<span>{r["created_at"][:16].replace("T", " ")} · {status} · {", ".join(r["channels"])}</span></div>'
            f'<div class="title">{html.escape(r["title"])}</div><div>{body}</div>'
            f'<div class="cta">👉 {html.escape(r["cta"])}</div><div class="footer">{html.escape(r["footer"])}</div></div>')
    empty = '<div style="text-align:center;opacity:.6;margin-top:120px">Belum ada notifikasi</div>'
    st.markdown(f'<div class="phone"><div class="phone-head">🔔 Notifikasi · {html.escape(cust["nickname"])}</div>'
                f'{"".join(items) or empty}</div>', unsafe_allow_html=True)
    if result and any(d["status"] == "duplicate_skipped" for d in result.get("deliveries", [])):
        st.caption("Sebagian pesan tidak dikirim ulang karena aturan dedup (insight yang sama di tanggal simulasi yang sama). "
                   "Kosongkan outbox di sidebar untuk mengulang demo.")


# ---------------------------------------------------------------- tab: data
def df(rows, cols=None):
    frame = pd.DataFrame(rows)
    return frame[cols] if cols and not frame.empty else frame


with tabs[3]:
    sub = st.tabs(["Profil", "Kartu kredit", "Tagihan CC", "Transaksi CC", "Tabungan", "Pinjaman"])
    with sub[0]:
        st.json({k: v for k, v in cust.items()})
    with sub[1]:
        st.dataframe(df(cards), width="stretch", hide_index=True)
    with sub[2]:
        st.dataframe(df(R.get_cc_statements(cid)), width="stretch", hide_index=True)
    with sub[3]:
        days = st.slider("Periode (hari)", 7, 180, 30, key="cc_days")
        tx = R.get_cc_transactions(cid, days=days)
        st.caption(f"{len(tx)} transaksi")
        st.dataframe(df(tx, ["datetime", "type", "merchant", "category", "amount", "currency", "original_amount",
                             "channel", "location", "status", "decline_reason", "is_recurring"]).iloc[::-1],
                     width="stretch", hide_index=True)
    with sub[4]:
        st.dataframe(df(savings), width="stretch", hide_index=True)
        stx = R.get_savings_transactions(cid, days=60)
        st.dataframe(df(stx, ["datetime", "direction", "category", "description", "amount", "balance_after"]).iloc[::-1],
                     width="stretch", hide_index=True)
    with sub[5]:
        st.dataframe(df(loans), width="stretch", hide_index=True)


# ---------------------------------------------------------------- tab: tanya data agent
with tabs[4]:
    st.caption("Agent ReAct dengan tools yang sama seperti Data Agent. Contoh: *berapa total belanja dining "
               f"{cid} 30 hari terakhir?* atau *siapa nasabah segmen Prioritas di Bandung?*")
    if not is_online():
        st.warning("Fitur ini butuh LLM. Isi MODEL_NAME dan API key di .env.")
    chat = st.session_state.setdefault("chat", [])
    for msg in chat:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("calls"):
                with st.expander("Tools yang dipanggil"):
                    st.code("\n".join(msg["calls"]), language=None)
    if q := st.chat_input("Tanya data nasabah...", disabled=not is_online()):
        from agents.data_chat import ask
        chat.append({"role": "user", "content": q})
        with st.spinner("Data Agent mencari data..."):
            history = [{"role": m["role"], "content": m["content"]} for m in chat[:-1]][-6:]
            answer, calls = ask(q, history)
        chat.append({"role": "assistant", "content": answer, "calls": calls})
        st.rerun()


# ---------------------------------------------------------------- tab: outbox
with tabs[5]:
    from channels import outbox
    rows = outbox.read_all()
    if not rows:
        st.info("Outbox masih kosong.")
    else:
        frame = pd.DataFrame(rows)
        c1, c2, c3 = st.columns(3)
        c1.metric("Total pesan", len(frame))
        c2.metric("Nasabah dijangkau", frame["customer_id"].nunique())
        c3.metric("Ditulis LLM", int((frame["source"] == "llm").sum()))
        st.dataframe(frame[["created_at", "customer_id", "severity", "code", "title", "status", "channels", "source"]]
                     .iloc[::-1], width="stretch", hide_index=True)


# ---------------------------------------------------------------- tab: autopilot
KIND_ICON = {"tick": "🌍", "start": "▶️", "think": "💭", "tool": "🔧", "done": "✅", "error": "⚠️", "report": "📝"}


def autopilot_alive(state: dict) -> bool:
    from datetime import datetime
    hb = state.get("heartbeat")
    return bool(state.get("running") and hb and (datetime.now() - datetime.fromisoformat(hb)).total_seconds() < 15)


with tabs[6]:
    import subprocess
    import sys

    from autonomy import store as ap

    st.markdown("Beri **misi** sekali, lalu biarkan agent bekerja sendiri: tiap putaran dunia maju 1 hari "
                "(transaksi, tagihan, pembayaran, keterlambatan), Manager bangun, memilih nasabah, mendelegasikan ke "
                "Case Handler → Analis → Communicator, dan menjadwalkan follow-up. Detail: `autonomy.md`.")
    mission = ap.load_mission()
    with st.expander("🎯 Misi tim", expanded=False):
        with st.form("mission"):
            goal = st.text_area("Misi", mission["goal"], height=100)
            cons = st.text_area("Batasan", mission["constraints"], height=70)
            mx = st.number_input("Maks kasus per hari (budget)", 1, 30, int(mission["max_cases_per_day"]))
            if st.form_submit_button("Simpan misi"):
                ap.save_mission({"goal": goal, "constraints": cons, "max_cases_per_day": int(mx)})
                st.toast("Misi disimpan — dipakai mulai hari simulasi berikutnya")

    state = ap.get_state()
    alive = autopilot_alive(state)
    c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 1])
    n_days = c1.number_input("Hari simulasi (0 = terus)", 0, 365, 7)
    gap = c2.number_input("Jeda per hari (detik)", 0.0, 300.0, 5.0, step=1.0)
    if c3.button("▶ Start", type="primary", disabled=alive, width="stretch"):
        log = (ap.DIR / "autopilot.log").open("a", encoding="utf-8")
        subprocess.Popen([sys.executable, "main.py", "autopilot", "--days", str(int(n_days)), "--interval", str(gap)],
                         cwd=config.BASE_DIR, stdout=log, stderr=subprocess.STDOUT,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        st.toast("Autopilot dimulai")
    if c4.button("⏹ Stop", disabled=not alive, width="stretch"):
        ap.request_stop()
        st.toast("Autopilot akan berhenti setelah langkah saat ini")
    if c5.button("🧹 Reset jejak", disabled=alive, width="stretch", help="Hapus feed, memori, follow-up, laporan (data nasabah tetap)"):
        ap.reset_all()
        st.rerun()
    if not is_online():
        st.caption("Mode offline: dunia tetap bergerak, nasabah prioritas diproses pipeline aturan (tanpa agent yang berpikir).")

    @st.fragment(run_every=2)
    def live_panel():
        s = ap.get_state()
        on = autopilot_alive(s)
        st.markdown(f"**Status:** {'🟢 berjalan' if on else '⚪ berhenti'} · mode `{s.get('mode', '-')}` · "
                    f"tanggal simulasi **{s.get('sim_date', R.reference_date().isoformat())}** · "
                    f"hari ke-{s.get('days_done', 0)} · {s.get('phase', '-')}"
                    + (f"  \n⚠️ {s['error']}" if s.get("error") else ""))
        left, right = st.columns([3, 2])
        with left:
            st.markdown("##### Feed agent (live)")
            lines = []
            for a in reversed(ap.read_activity(150)):
                indent = "&nbsp;" * 6 * a["depth"]
                who = f"<b>{html.escape(a['agent'])}</b>" + (f" <small>[{a['customer_id']}]</small>" if a.get("customer_id") else "")
                lines.append(f"<div style='margin:2px 0'>{indent}{KIND_ICON.get(a['kind'], '•')} <small>{a['sim_date'] or ''} {a['ts']}</small> "
                             f"{who}: {html.escape(a['text'])}</div>")
            st.markdown("<div style='height:520px;overflow-y:auto;font-size:.82rem;border:1px solid rgba(128,128,128,.3);"
                        f"border-radius:8px;padding:8px'>{''.join(lines) or 'Belum ada aktivitas.'}</div>", unsafe_allow_html=True)
        with right:
            st.markdown("##### 📝 Laporan harian Manager")
            for r in reversed(ap.read_reports()[-5:]):
                with st.container(border=True):
                    st.markdown(f"**{r['sim_date']}**  \n{r['report']}")
            st.markdown("##### ⏰ Follow-up terbuka")
            fus = ap.list_followups("open")
            st.dataframe(pd.DataFrame(fus)[["due_date", "customer_id", "reason"]] if fus else pd.DataFrame(),
                         hide_index=True, width="stretch")
            st.markdown("##### 🌍 Kejadian terbaru")
            ev = ap.read_events(40)
            st.dataframe(pd.DataFrame(ev[::-1])[["date", "customer_id", "type", "detail"]] if ev else pd.DataFrame(),
                         hide_index=True, width="stretch", height=220)

    live_panel()
