from __future__ import annotations

import os
import select
import signal
import socket
import sys
import threading
import time

import paramiko


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def pipe_channel_to_local(channel: paramiko.Channel, local_host: str, local_port: int) -> None:
    try:
        local = socket.create_connection((local_host, local_port), timeout=10)
    except OSError as exc:
        print(f"cannot connect local target {local_host}:{local_port}: {exc}", file=sys.stderr)
        channel.close()
        return

    with local, channel:
        while True:
            readable, _, _ = select.select([local, channel], [], [])
            if local in readable:
                data = local.recv(4096)
                if not data:
                    break
                channel.sendall(data)
            if channel in readable:
                data = channel.recv(4096)
                if not data:
                    break
                local.sendall(data)


def main() -> None:
    host = env("MINI_OGAS_SSH_HOST", "82.156.217.166")
    user = env("MINI_OGAS_SSH_USER", "ubuntu")
    password = env("MINI_OGAS_SSH_PASSWORD")
    local_host = env("MINI_OGAS_LOCAL_API_HOST", "127.0.0.1")
    local_port = int(env("MINI_OGAS_LOCAL_API_PORT", "8080"))
    remote_host = env("MINI_OGAS_REMOTE_FORWARD_HOST", "127.0.0.1")
    remote_port = int(env("MINI_OGAS_REMOTE_FORWARD_PORT", "18080"))

    if not password:
        raise SystemExit("MINI_OGAS_SSH_PASSWORD is required")

    client = paramiko.SSHClient()
    # Load known hosts; warn but accept on first connect (safer than AutoAddPolicy)
    known_hosts = os.path.expanduser("~/.ssh/known_hosts")
    try:
        client.load_host_keys(known_hosts)
    except (OSError, IOError):
        pass
    client.set_missing_host_key_policy(paramiko.WarningPolicy())
    client.connect(hostname=host, username=user, password=password, timeout=20,
                   look_for_keys=False, allow_agent=False)
    transport = client.get_transport()
    if transport is None:
        raise RuntimeError("SSH transport is not available")

    transport.request_port_forward(remote_host, remote_port)
    print(f"reverse tunnel open: cloud {remote_host}:{remote_port} -> local {local_host}:{local_port}", flush=True)

    stopped = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal stopped
        stopped = True
        try:
            transport.cancel_port_forward(remote_host, remote_port)
        finally:
            client.close()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    try:
        while not stopped:
            channel = transport.accept(timeout=5)
            if channel is None:
                continue
            thread = threading.Thread(
                target=pipe_channel_to_local,
                args=(channel, local_host, local_port),
                daemon=True,
            )
            thread.start()
    finally:
        client.close()
        time.sleep(0.2)


if __name__ == "__main__":
    main()
