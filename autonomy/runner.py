"""Menjalankan satu agent ReAct sambil mencatat pikiran & tool call-nya ke activity log (feed live UI).
Kedalaman delegasi (manager → case → analis → rekan) dilacak dengan contextvar untuk indentasi feed."""

import contextvars
import json

from langgraph.errors import GraphRecursionError

from autonomy import store
from bank_data.repository import get_repo

_depth = contextvars.ContextVar("agent_depth", default=0)


def _text(content) -> str:
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return str(content or "")


def _short(s, n=280) -> str:
    s = s if isinstance(s, str) else json.dumps(s, ensure_ascii=False, default=str)
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n] + "…"


def run_agent(name: str, agent, prompt: str, customer_id: str | None = None, recursion_limit: int = 30) -> dict:
    """Return {"text": jawaban akhir, "structured": structured_response | None}."""
    depth = _depth.get()
    sim = get_repo().reference_date().isoformat()
    token = _depth.set(depth + 1)
    store.log(name, "start", _short(prompt, 400), depth, customer_id, sim)
    values = {}
    try:
        for mode, chunk in agent.stream({"messages": [{"role": "user", "content": prompt}]},
                                        {"recursion_limit": recursion_limit}, stream_mode=["updates", "values"]):
            if mode == "values":
                values = chunk
                continue
            for update in chunk.values():
                for msg in (update or {}).get("messages", []) if isinstance(update, dict) else []:
                    if msg.type != "ai":
                        continue
                    thought = _text(msg.content).strip()
                    if thought and msg.tool_calls:
                        store.log(name, "think", _short(thought, 500), depth, customer_id, sim)
                    for tc in msg.tool_calls:
                        args = ", ".join(f"{k}={_short(v, 300 if k == 'query' else 80)}" for k, v in tc["args"].items())
                        store.log(name, "tool", f"{tc['name']}({args})", depth, customer_id, sim)
    except GraphRecursionError:
        store.log(name, "error", "berhenti: batas langkah tercapai", depth, customer_id, sim)
        return {"text": "Agent berhenti karena batas langkah tercapai.", "structured": None, "error": "recursion"}
    except Exception as e:  # jaringan / provider error: jangan matikan autopilot
        store.log(name, "error", f"{type(e).__name__}: {_short(str(e), 200)}", depth, customer_id, sim)
        return {"text": f"Agent gagal: {type(e).__name__}", "structured": None, "error": type(e).__name__}
    finally:
        _depth.reset(token)
    msgs = values.get("messages", [])
    text = next((_text(m.content) for m in reversed(msgs) if m.type == "ai" and _text(m.content).strip()), "")
    structured = values.get("structured_response")
    summary = structured.model_dump() if hasattr(structured, "model_dump") else text
    store.log(name, "done", _short(summary, 600), depth, customer_id, sim)
    return {"text": text, "structured": structured, "error": None}
