"""'Tanya Data Agent': agent ReAct (LangChain create_agent) yang memanggil tools data sendiri
untuk menjawab pertanyaan bebas operator. Butuh LLM (tidak tersedia di mode offline)."""

from langchain.agents import create_agent

import config
from bank_data.repository import get_repo
from bank_data.tools import ALL_TOOLS
from llm import get_llm

SYSTEM = """Kamu adalah Data Agent bank. Jawab pertanyaan operator tentang data nasabah HANYA dengan memanggil tools.
Tanggal 'hari ini' simulasi: {today}. Jawab ringkas dalam Bahasa Indonesia, format Rupiah seperti Rp1.250.000.
Jangan menampilkan nomor HP/email nasabah kecuali diminta. Kalau data tidak ada, katakan tidak ada."""

SQL_SYSTEM = """Kamu adalah Data Agent bank yang menjawab pertanyaan dengan MENG-QUERY database PostgreSQL.
Tanggal 'hari ini' simulasi: {today}.
Langkah: 1) `describe_database` untuk memahami tabel & kolom; 2) tulis SATU query SELECT yang tepat
(utamakan agregasi SUM/COUNT/AVG + GROUP BY, filter tanggal relatif ke hari ini); 3) `run_sql`;
4) kalau ERROR, baca pesannya dan perbaiki query. Boleh beberapa query bila perlu.
Jawab ringkas dalam Bahasa Indonesia, format Rupiah seperti Rp1.250.000, dan sebutkan singkat query yang kamu pakai.
Kolom data pribadi (HP, email) memang tidak bisa diakses — jangan dicoba."""


def _text(content) -> str:
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return str(content)


def ask(question: str, history: list[dict] | None = None) -> tuple[str, list[str]]:
    llm = get_llm()
    if llm is None:
        return "Mode offline: fitur Tanya Data Agent butuh LLM. Isi MODEL_NAME & API key di .env.", []
    today = get_repo().reference_date().isoformat()
    if config.DATA_BACKEND == "postgres":  # agent menulis SQL sendiri
        from bank_data.sql_tools import SQL_TOOLS
        agent = create_agent(llm, tools=SQL_TOOLS, system_prompt=SQL_SYSTEM.format(today=today))
    else:
        agent = create_agent(llm, tools=ALL_TOOLS, system_prompt=SYSTEM.format(today=today))
    try:
        result = agent.invoke({"messages": [*(history or []), {"role": "user", "content": question}]},
                              {"recursion_limit": 25})
    except Exception as e:  # kredit habis, jaringan, batas langkah
        return f"Data Agent gagal menjawab ({type(e).__name__}: {str(e)[:160]})", []
    calls = [f"{tc['name']}({', '.join(f'{k}={v}' for k, v in tc['args'].items())})"
             for m in result["messages"] for tc in (getattr(m, "tool_calls", None) or [])]
    return _text(result["messages"][-1].content), calls
