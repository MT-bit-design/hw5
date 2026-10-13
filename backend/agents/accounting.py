"""Accounting: watches cash and invoices, checks margins, and prepares payments and
purchase orders for a human to approve."""

from backend.models import AgentSpec

SPEC = AgentSpec(
    name="accounting",
    title="Accounting",
    prompt_file="accounting.md",
    mcp_tools=(
        "get_ticket", "get_bills_and_cash", "get_invoice", "check_margin", "quote_bulk_order",
        "find_restock_vendors", "request_payment", "request_purchase_order",
    ),
)
