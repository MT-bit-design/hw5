"""Inventory: checks stock by SKU and size, finds shortfalls, and finds who can restock."""

from backend.models import AgentSpec

SPEC = AgentSpec(
    name="inventory",
    title="Inventory",
    prompt_file="inventory.md",
    mcp_tools=("get_ticket", "check_stock", "quote_bulk_order", "find_restock_vendors"),
)
