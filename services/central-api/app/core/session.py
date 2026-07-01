"""Session token — cryptographically unique per launch, inherited by child processes.

The Go supervisor (or start-all.ps1) sets OGAS_SESSION_TOKEN in the environment
before spawning any child process.  Every service reflects it in /health so that
preflight can distinguish "port is alive" from "port is alive and belongs to
*this* launch batch".
"""

import os
import uuid
from datetime import datetime, timezone


PROCESS_ID = os.getpid()
PROCESS_STARTED_AT = datetime.now(timezone.utc).isoformat()


def get_session_token() -> str:
    """Return the session token from the environment, generating one if absent.

    Standalone / manual starts won't have a token — we generate a fresh one so
    that preflight at least sees a consistent value across central-api and its
    own health endpoint.
    """
    token = os.environ.get("OGAS_SESSION_TOKEN")
    if not token:
        token = str(uuid.uuid4())
        os.environ["OGAS_SESSION_TOKEN"] = token
    return token


def get_process_identity() -> dict[str, str | int]:
    """Stable identity of this Python process for freshness verification."""
    return {
        "process_id": PROCESS_ID,
        "process_started_at": PROCESS_STARTED_AT,
    }
