"""State bersama yang mengalir di LangGraph (lihat design.md bagian 3)."""

import operator
from typing import Annotated, TypedDict


class AgentState(TypedDict, total=False):
    customer_id: str
    sim_date: str
    objective: str
    overview: dict
    plan: list[str]
    plan_reason: str
    context: dict
    insights: Annotated[list[dict], operator.add]       # digabung dari analis yang jalan paralel
    analyst_notes: Annotated[list[dict], operator.add]
    selected: list[dict]
    held: list[dict]
    messages: list[dict]
    deliveries: list[dict]
    trace: Annotated[list[dict], operator.add]
