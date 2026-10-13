"""Run the agent team on one ticket.

    python -m backend.run 101
"""

import argparse
import asyncio
import os
import sys

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from backend.config import MissingApiKey  # noqa: E402
from backend.team import Team  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Campus Customs agent team on a ticket.")
    parser.add_argument("ticket_id", type=int)
    args = parser.parse_args()
    try:
        team = Team()
    except MissingApiKey as exc:
        print(f"Stopped: {exc}", file=sys.stderr)
        return 2
    reply = asyncio.run(team.run_ticket(args.ticket_id))
    print(reply.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
