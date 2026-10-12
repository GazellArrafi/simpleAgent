"""Helper bersama untuk agent: catatan jejak (trace) & ringkasan profil untuk LLM."""

import json
import time
from datetime import datetime

from analytics.common import rp


def trace(agent: str, action: str, detail: str = "", *, llm: bool = False, started: float | None = None, **extra):
    entry = {"ts": datetime.now().strftime("%H:%M:%S"), "agent": agent, "action": action, "detail": detail,
             "llm": llm}
    if started is not None:
        entry["duration_ms"] = round((time.perf_counter() - started) * 1000)
    entry.update(extra)
    return entry


def profile_for_llm(profile: dict) -> dict:
    """Data minimal yang boleh dikirim ke LLM (tanpa HP/email) — rules.md D."""
    return {"nama_panggilan": profile.get("nickname"), "usia": profile.get("age"), "segmen": profile.get("segment"),
            "pekerjaan": profile.get("occupation"), "kota": profile.get("city"),
            "penghasilan_bulanan": rp(profile.get("monthly_income", 0))}


def to_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str, indent=1)
