# logMaster

A self-hosted systemd journal log viewer with Authentik SSO authentication.

## Overview

logMaster consists of two independent Flask/Gunicorn applications:

```
logMaster/
├── server/     # Web UI — Authentik OIDC auth, service tabs, log rendering
└── daemon/     # Log API — queries journalctl and returns JSON
```

```
Browser ──OIDC──► Authentik
   │
   ▼
server (port 5000)
   │  POST /logs  (shared secret)
   ▼
daemon (port 5001)
   │  subprocess
   ▼
journalctl
```

The **server** authenticates users via Authentik and renders log data in a browser UI. The **daemon** runs on any systemd host, exposes a single authenticated HTTP endpoint, and pipes requests into `journalctl`. Multiple daemons can be configured — one per host — each mapped to a set of services in `config.json`.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | Both components |
| systemd | Daemon host must run systemd (Linux only) |
| Authentik | Any reachable Authentik instance |
| `rsync` | Used by `setup.sh --install-service` |

---

## Quick Start

### 1. Daemon

```bash
cd daemon
./setup.sh                  # create venv, install deps, copy .env.example → .env
nano .env                   # set LOG_API_SHARED_SECRET
source .venv/bin/activate
python daemon.py            # dev server on port 5001
```

### 2. Server

```bash
cd server
./setup.sh                  # create venv, install deps, copy .env.example → .env
nano .env                   # fill in Authentik + shared secret values
nano config.json            # add your services
source .venv/bin/activate
python server.py            # dev server on port 5000
```

---

## Service Configuration

`server/config.json` defines which services appear as tabs in the UI.

```json
{
  "services": [
    {
      "name":         "Nginx",
      "service_name": "nginx.service",
      "address":      "http://192.168.1.10:5001"
    },
    {
      "name":         "Postgresql",
      "service_name": "postgresql.service",
      "address":      "http://192.168.1.11:5001"
    }
  ]
}
```

| Field | Description |
|---|---|
| `name` | Display name shown in the tab bar |
| `service_name` | Exact systemd unit name passed to `journalctl -u` |
| `address` | URL of the daemon instance that hosts this service |

The config is loaded once at server startup. Restart the server after editing it.

---

## Systemd Deployment

Install both components as systemd services on their respective hosts.

### Daemon host

```bash
cd daemon
sudo ./setup.sh --install-service
```

### Server host

```bash
cd server
sudo ./setup.sh --install-service
```

Both scripts copy files to `/root/logMaster/{daemon,server}/`, install the service unit, and start it immediately.

After any update, copy the new files and run:

```bash
systemctl restart logMasterDaemon   # on the daemon host
systemctl restart logMasterServer   # on the server host
```

Tail logs:

```bash
journalctl -u logMasterDaemon -f
journalctl -u logMasterServer -f
```

---

## Authentik Setup

1. In Authentik, go to **Applications → Providers → Create → OAuth2/OpenID Provider**.
2. Set the redirect URI to match `AUTHENTIK_REDIRECT_URI` in `server/.env`:
   ```
   http://your-host:5000/callback
   ```
3. Copy the **Client ID** and **Client Secret** into `server/.env`.
4. Create an **Application** linked to the provider and note the application slug — this is the value used in `AUTHENTIK_CLIENT_ID`.

---

## Environment Variables

See [`server/.env.example`](server/.env.example) and [`daemon/.env.example`](daemon/.env.example) for full reference.

### server/.env

| Variable | Required | Description |
|---|---|---|
| `APP_SECRET_KEY` | Yes | Flask session signing key — use a long random string |
| `AUTHENTIK_BASE_URL` | Yes | Base URL of your Authentik instance, e.g. `https://auth.example.com` |
| `AUTHENTIK_CLIENT_ID` | Yes | OAuth2 application slug from Authentik |
| `AUTHENTIK_CLIENT_SECRET` | Yes | OAuth2 client secret from Authentik |
| `AUTHENTIK_REDIRECT_URI` | Yes | Must match the redirect URI registered in Authentik |
| `LOG_API_SHARED_SECRET` | Yes | Must match the daemon's value |
| `LOG_API_URL` | No | Fallback daemon URL if a service has no `address` (default: `http://127.0.0.1:5001`) |
| `APP_PORT` | No | Port to bind (default: `5000`) |
| `FLASK_DEBUG` | No | Set `true` for development only (default: `false`) |

### daemon/.env

| Variable | Required | Description |
|---|---|---|
| `LOG_API_SHARED_SECRET` | Yes | Shared secret — must match the server's value |
| `LOG_API_PORT` | No | Port to bind (default: `5001`) |
| `FLASK_DEBUG` | No | Set `true` for development only (default: `false`) |

---

## Security Notes

- The shared secret is the only authentication mechanism on the daemon endpoint. Use a strong random value and keep it out of version control.
- The daemon validates the systemd unit name against a strict regex (`^[\w.\-]+$`) before passing it to `journalctl` — no shell interpolation is used.
- Both systemd services run with `NoNewPrivileges`, `PrivateTmp`, and `ProtectSystem=strict`.
- The daemon runs as `root` to access the journal. If you prefer an unprivileged user, add them to the `systemd-journal` group and remove the `User=root` line from the service file.
