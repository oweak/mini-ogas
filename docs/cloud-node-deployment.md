# Tencent Cloud Node Deployment

Current target server:

- Provider: Tencent Cloud
- Region: Beijing / Beijing Zone 2
- Public IPv4: `82.156.217.166`
- OS: Ubuntu
- Role: Mini-OGAS workshop child node

## Network design

The laptop remains the central control node. The cloud server runs `node-agent`.

Because most home networks cannot receive inbound traffic directly, use an SSH reverse tunnel:

```text
cloud node 127.0.0.1:18080 -> laptop 127.0.0.1:8080
```

Then the cloud node agent can use:

```text
CENTRAL_API_URL=http://127.0.0.1:18080
```

## Tencent Cloud security group

Open inbound:

- TCP `22` from your laptop IP for SSH.

You do not need to open port `18080` to the public internet when using the reverse tunnel, because the agent only uses `127.0.0.1` on the cloud server.

## Local commands

From project root:

```powershell
.\scripts\start-central-api.ps1
.\scripts\connect-cloud-reverse-tunnel.ps1 -ServerIp 82.156.217.166 -User ubuntu
.\scripts\deploy-cloud-node.ps1 -ServerIp 82.156.217.166 -User ubuntu -NodeCode milling-cloud-01 -WorkshopType milling
```

If you use an SSH key:

```powershell
.\scripts\connect-cloud-reverse-tunnel.ps1 -ServerIp 82.156.217.166 -User ubuntu -KeyPath C:\path\to\key.pem
.\scripts\deploy-cloud-node.ps1 -ServerIp 82.156.217.166 -User ubuntu -KeyPath C:\path\to\key.pem
```

## Cloud checks

On the cloud server:

```bash
sudo systemctl status mini-ogas-node-agent --no-pager
sudo journalctl -u mini-ogas-node-agent -f
curl http://127.0.0.1:18080/health
```

If `curl http://127.0.0.1:18080/health` fails, the reverse tunnel is not running or the local central API is not started.
