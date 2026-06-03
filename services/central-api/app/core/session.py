"""Session token — cryptographically unique per launch, inherited by child processes.

The Go supervisor (or start-all.ps1) sets OGAS_SESSION_TOKEN in the environment
before spawning any child process.  Every service reflects it in /health so that
preflight can distinguish "port is alive" from "port is alive and belongs to
*this* launch batch".
"""

import os
import uuid


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
