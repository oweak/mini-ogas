from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import paramiko


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def run(ssh: paramiko.SSHClient, command: str) -> None:
    print(f"$ {command}")
    stdin, stdout, stderr = ssh.exec_command(command, get_pty=True)
    sudo_password = env("MINI_OGAS_SSH_PASSWORD")
    if command.strip().startswith("sudo ") and sudo_password:
        stdin.write(sudo_password + "\n")
        stdin.flush()
    while not stdout.channel.exit_status_ready():
        if stdout.channel.recv_ready():
            sys.stdout.write(stdout.channel.recv(4096).decode("utf-8", errors="ignore"))
        if stderr.channel.recv_stderr_ready():
            sys.stderr.write(stderr.channel.recv_stderr(4096).decode("utf-8", errors="ignore"))
        time.sleep(0.1)
    sys.stdout.write(stdout.read().decode("utf-8", errors="ignore"))
    sys.stderr.write(stderr.read().decode("utf-8", errors="ignore"))
    status = stdout.channel.recv_exit_status()
    if status != 0:
        raise RuntimeError(f"command failed with status {status}: {command}")


def main() -> None:
    host = env("MINI_OGAS_SSH_HOST", "82.156.217.166")
    user = env("MINI_OGAS_SSH_USER", "ubuntu")
    password = env("MINI_OGAS_SSH_PASSWORD")
    package = Path(env("MINI_OGAS_NODE_PACKAGE", ".runtime/dist/mini-ogas-cloud-node.tar.gz")).resolve()

    if not password:
        raise SystemExit("MINI_OGAS_SSH_PASSWORD is required")
    if not package.exists():
        raise SystemExit(f"package not found: {package}")

    ssh = paramiko.SSHClient()
    # Load known hosts; warn but accept on first connect (safer than AutoAddPolicy)
    known_hosts = os.path.expanduser("~/.ssh/known_hosts")
    try:
        ssh.load_host_keys(known_hosts)
    except (OSError, IOError):
        pass
    ssh.set_missing_host_key_policy(paramiko.WarningPolicy())
    ssh.connect(hostname=host, username=user, password=password, timeout=20,
                look_for_keys=False, allow_agent=False)
    try:
        sftp = ssh.open_sftp()
        run(ssh, "rm -rf ~/mini-ogas-cloud-node && mkdir -p ~/mini-ogas-cloud-node")
        remote_archive = "/home/ubuntu/mini-ogas-cloud-node/mini-ogas-cloud-node.tar.gz"
        print(f"upload {package} -> {remote_archive}")
        sftp.put(str(package), remote_archive)
        sftp.close()
        run(ssh, "cd ~/mini-ogas-cloud-node && tar -xzf mini-ogas-cloud-node.tar.gz")
        run(ssh, "cd ~/mini-ogas-cloud-node && chmod +x install-node-agent.sh")
        run(ssh, "cd ~/mini-ogas-cloud-node && sudo -S ./install-node-agent.sh")
        run(ssh, "sudo -S systemctl status mini-ogas-node-agent --no-pager")
    finally:
        ssh.close()


if __name__ == "__main__":
    main()
