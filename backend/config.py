"""Settings for the agent team. The model name lives here and nowhere else."""

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT / "backend"
PROMPTS_DIR = BACKEND_DIR / "prompts"
MCP_SERVER_SCRIPT = ROOT / "mcp_server" / "server.py"
AUDIT_PATH = ROOT / "output" / "audit_trail.json"

load_dotenv(BACKEND_DIR / ".env")

# The only model the team may use, called through Portkey.
MODEL_NAME = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

# The MCP server can take ~10s to start (FastMCP import on a synced folder); PydanticAI's default is 5s.
MCP_INIT_TIMEOUT_S = 30

# Safety limits so nothing loops forever or burns tokens.
MAX_DELEGATION_DEPTH = 2        # Boss -> specialist -> one more specialist, no deeper
MAX_STEPS_PER_TICKET = 60       # model calls + tool calls across every agent on one ticket
MAX_OUTPUT_TOKENS = 4_000       # per model reply, reasoning included (2,000 was too tight)
REASONING_EFFORT = "low"        # enough to follow the rules, cheap on tokens
USAGE_LIMITS = UsageLimits(     # shared by every agent working on one ticket
    request_limit=30,
    tool_calls_limit=40,
    total_tokens_limit=100_000,
)


class MissingApiKey(RuntimeError):
    """PORTKEY_API_KEY is not set."""


def build_model() -> OpenAIResponsesModel:
    api_key = os.getenv("PORTKEY_API_KEY", "").strip()
    if not api_key or api_key.startswith("your-"):
        raise MissingApiKey("PORTKEY_API_KEY is not set in backend/.env")
    client = AsyncOpenAI(
        base_url=PORTKEY_BASE_URL,
        api_key=api_key,
        default_headers={"x-portkey-api-key": api_key},
        timeout=120,  # per model request; 60s timed out on a slow provider (run 3871abba50ed)
        max_retries=1,
    )
    # Responses API: the Azure deployment behind Portkey only allows tools + reasoning there.
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


def model_settings() -> OpenAIResponsesModelSettings:
    return OpenAIResponsesModelSettings(
        max_tokens=MAX_OUTPUT_TOKENS, openai_reasoning_effort=REASONING_EFFORT
    )
