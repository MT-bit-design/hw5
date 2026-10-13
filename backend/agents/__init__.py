"""The five Campus Customs roles. Each file says who the agent is and which MCP tools it may use."""

from backend.agents.accounting import SPEC as ACCOUNTING
from backend.agents.boss import SPEC as BOSS
from backend.agents.customer_service import SPEC as CUSTOMER_SERVICE
from backend.agents.facilities import SPEC as FACILITIES
from backend.agents.inventory import SPEC as INVENTORY

SPECS = {s.name: s for s in (BOSS, INVENTORY, ACCOUNTING, FACILITIES, CUSTOMER_SERVICE)}
