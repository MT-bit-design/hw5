"""Customer Service: writes drafts to customers. Drafts stay on the board."""

from backend.models import AgentSpec

SPEC = AgentSpec(
    name="customer_service",
    title="Customer Service",
    prompt_file="customer_service.md",
    mcp_tools=("get_ticket", "check_stock", "draft_customer_message"),
)
