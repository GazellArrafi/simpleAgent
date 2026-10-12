"""Merakit LangGraph: supervisor -> data agent -> analis paralel (Send) -> review -> communicator -> delivery."""

from functools import lru_cache

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from agents import communicator, data_agent, delivery, supervisor
from agents.analysts import ANALYSTS
from bank_data.repository import get_repo
from graph.state import AgentState


def dispatch_analysts(state: AgentState):
    """Fan-out: setiap analis yang ditugaskan supervisor jalan paralel dengan salinan context."""
    if not state.get("plan"):
        return "supervisor_review"
    payload = {k: state[k] for k in ("customer_id", "sim_date", "objective", "context")}
    return [Send(name, payload) for name in state["plan"]]


@lru_cache(maxsize=1)
def build_graph():
    g = StateGraph(AgentState)
    g.add_node("supervisor_plan", supervisor.plan_node)
    g.add_node("data_agent", data_agent.node)
    for name, agent in ANALYSTS.items():
        g.add_node(name, agent.node)
    g.add_node("supervisor_review", supervisor.review_node)
    g.add_node("communicator", communicator.node)
    g.add_node("delivery", delivery.node)

    g.add_edge(START, "supervisor_plan")
    g.add_edge("supervisor_plan", "data_agent")
    g.add_conditional_edges("data_agent", dispatch_analysts, [*ANALYSTS, "supervisor_review"])
    for name in ANALYSTS:
        g.add_edge(name, "supervisor_review")
    g.add_edge("supervisor_review", "communicator")
    g.add_edge("communicator", "delivery")
    g.add_edge("delivery", END)
    return g.compile()


def run_customer(customer_id: str, objective: str | None = None, on_step=None, on_update=None) -> dict:
    """Jalankan seluruh alur untuk satu nasabah. on_step(node_name) dipanggil tiap node selesai (untuk UI);
    on_update(node_name, update) sama, tapi ikut membawa output node tersebut."""
    init = {"customer_id": customer_id.strip().upper(), "sim_date": get_repo().reference_date().isoformat(),
            "objective": objective or supervisor.DEFAULT_OBJECTIVE,
            "insights": [], "analyst_notes": [], "trace": []}
    final = init
    for mode, chunk in build_graph().stream(init, stream_mode=["updates", "values"]):
        if mode == "updates":
            for node, update in chunk.items():
                if on_step:
                    on_step(node)
                if on_update:
                    on_update(node, update)
        elif mode == "values":
            final = chunk
    return final
