"""
Portable entry point for PyInstaller-bundled Mini-OGAS Central API.

Usage:
    python run_portable.py           # development
    mini-ogas-central-api.exe        # after PyInstaller build
"""
import os
import sys
from pathlib import Path


def main() -> None:
    # Ensure .env is loaded from the executable's directory (portable mode)
    exe_dir = Path(sys.executable).parent
    env_file = exe_dir / ".env"
    if env_file.exists():
        print(f"[portable] Loading environment from: {env_file}")

    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

    import uvicorn
    import main as app_module

    host = os.getenv("CENTRAL_API_HOST", "0.0.0.0")
    port = int(os.getenv("CENTRAL_API_PORT", "8080"))

    print("[portable] Starting Mini-OGAS Central API")
    print(f"[portable] Listening on {host}:{port}")
    print(f"[portable] Dashboard: http://{host}:{port}")

    uvicorn.run(
        app_module.app,
        host=host,
        port=port,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()
