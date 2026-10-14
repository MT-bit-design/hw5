"""Boss: reads each ticket, picks who works on it, and makes the final call.

The final call is written to the board by the team runner (MCP record_decision) from the
Boss's final answer, so the Boss does not call record_decision itself."""

from backend.models import AgentSpec

SPEC = AgentSpec(
    name="boss",
    title="Boss",
    prompt_file="boss.md",
    mcp_tools=("list_open_tickets", "get_ticket"),
)
