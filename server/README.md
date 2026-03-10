# logMaster Server

Flask/Gunicorn web application that authenticates users via Authentik OIDC and renders systemd journal logs fetched from one or more logMaster Daemon instances.

## Files

```
server/
├── server.py                 # Flask application
├── config.json               # Service tab configuration
├── gunicorn.conf.py          # Gunicorn worker/binding settings
├── requirements.txt
├── setup.sh                  # Setup and service installer
├── .env.example              # Environment variable reference
├── logMasterServer.service   # systemd unit file
└── templates/
    ├── base.html             # Layout, nav, service tab bar
    ├── index.html            # Date range query form
    └── logs.html             # Log results table
```

## Configuration

### config.json

Defines the services shown as tabs. Loaded once at startup — restart the server after editing.

```json
{
  "services": [
    {
      "name":         "Nginx",
      "service_name": "nginx.service",
      "address":      "http://192.168.1.10:5001"
    }
  ]
}
```

- `name` — tab label displayed in the UI
- `service_name` — systemd unit name sent to the daemon
- `address` — URL of the daemon that hosts this service; falls back to `LOG_API_URL` in `.env` if omitted

### .env

Copy `.env.example` to `.env` and fill in all required values before starting.

```
APP_SECRET_KEY=<long random string>
AUTHENTIK_BASE_URL=https://auth.example.com
AUTHENTIK_CLIENT_ID=<application slug>
AUTHENTIK_CLIENT_SECRET=<client secret>
AUTHENTIK_REDIRECT_URI=http://your-host:5000/callback
LOG_API_SHARED_SECRET=<must match daemon>
LOG_API_URL=http://127.0.0.1:5001
APP_PORT=5000
FLASK_DEBUG=false
```

## Setup

```bash
./setup.sh                       # create venv, install deps, copy .env
nano .env                        # fill in required values
nano config.json                 # add your services
```

### Install as systemd service

```bash
sudo ./setup.sh --install-service
```

This will:
1. Create a `logmaster` system user (if not present)
2. Copy files to `/root/logMaster/server/`
3. Install and enable `logMasterServer.service`

### Manual start (development)

```bash
source .venv/bin/activate
python server.py
```

## Routes

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Log query form; `?tab=<service_name>` selects the active tab |
| `POST` | `/logs` | Fetch and render logs for the selected service and time range |
| `GET` | `/login` | Redirect to Authentik authorization endpoint |
| `GET` | `/callback` | Authentik OIDC callback; establishes session |
| `GET` | `/logout` | Clear session and redirect to Authentik end-session |

## Gunicorn

`gunicorn.conf.py` binds to `0.0.0.0:5000` and spawns `2 * CPU + 1` sync workers. Adjust `workers` and `bind` there as needed.
