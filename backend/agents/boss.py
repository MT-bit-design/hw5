"""Boss: reads each ticket, picks who works on it, and makes the final call."""

from backend.models import AgentSpec

SPEC = AgentSpec(
    name="boss",
    title="Boss",
    prompt_file="boss.md",
    mcp_tools=("list_open_tickets", "get_ticket", "record_decision"),
)
