"""Append-only audit trail for every agent-loop step.

Rows go to output/audit_trail.json (a JSON array). Each write loads the file,
adds the row, and replaces the file atomically, so old runs are never wiped.
Before writing, text is scrubbed of API keys, emails, phone numbers, and the
names of customers seen in ticket results, because the repo is public.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.models import AuditEvent, TicketRun

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]\d{4}(?!\d)")
SUMMARY_CHARS = 400
REPLACE_RETRIES = 8
CUSTOMER_TICKET_TYPES = {"customer_order"}


class AuditLog:
    def __init__(self, path: Path):
        self.path = path
        self._secrets = [s for s in (os.getenv("PORTKEY_API_KEY", "").strip(),) if s]

    # ---------- scrubbing ----------

    def learn_customer_names(self, run: TicketRun, tool_result: Any) -> None:
        """Remember requester names on customer tickets so they never reach the file."""
        rows = []
        if isinstance(tool_result, dict):
            rows = tool_result.get("open_tickets") or [tool_result]
        for row in rows:
            if isinstance(row, dict) and row.get("type") in CUSTOMER_TICKET_TYPES and row.get("requester"):
                name = str(row["requester"])
                run.redact_names.add(name)
                run.redact_names.update(part for part in name.split() if len(part) >= 3)

    def scrub(self, run: TicketRun, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: self.scrub(run, v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.scrub(run, v) for v in value]
        if not isinstance(value, str):
            return value
        for secret in self._secrets:
            value = value.replace(secret, "[REDACTED-KEY]")
        value = EMAIL_RE.sub("[REDACTED-EMAIL]", value)
        value = PHONE_RE.sub("[REDACTED-PHONE]", value)
        for name in sorted(run.redact_names, key=len, reverse=True):
            value = re.sub(re.escape(name), "[CUSTOMER]", value, flags=re.IGNORECASE)
        return value

    def summarize(self, run: TicketRun, value: Any) -> str:
        text = value if isinstance(value, str) else json.dumps(value, default=str)
        text = self.scrub(run, text)
        return text if len(text) <= SUMMARY_CHARS else text[: SUMMARY_CHARS - 3] + "..."

    # ---------- writing ----------

    def record(self, run: TicketRun, **fields: Any) -> AuditEvent:
        if fields.get("tool_input") is not None:
            fields["tool_input"] = self.scrub(run, fields["tool_input"])
        event = AuditEvent(
            time=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            run_id=run.run_id,
            ticket=run.ticket_id,
            step=run.steps,
            **fields,
        )
        self._append(event.model_dump(mode="json", exclude_none=True))
        return event

    def _append(self, row: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        rows: list = []
        if self.path.exists() and self.path.stat().st_size:
            rows = json.loads(self.path.read_text(encoding="utf-8"))
        rows.append(row)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        # Sync tools like OneDrive can lock the file for a moment on Windows; retry briefly.
        for attempt in range(REPLACE_RETRIES):
            try:
                os.replace(tmp, self.path)
                return
            except PermissionError:
                if attempt == REPLACE_RETRIES - 1:
                    raise
                time.sleep(0.25 * (attempt + 1))
