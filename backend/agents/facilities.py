"""Facilities: handles shop space, leases, and rent."""

from backend.models import AgentSpec

SPEC = AgentSpec(
    name="facilities",
    title="Facilities",
    prompt_file="facilities.md",
    mcp_tools=("get_ticket", "get_lease", "get_bills_and_cash"),
)
