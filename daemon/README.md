# logMaster Daemon

Flask/Gunicorn HTTP API that accepts authenticated log queries and returns systemd journal entries as JSON. Designed to run on any systemd Linux host alongside the services being monitored.

## Files

```
daemon/
├── daemon.py                 # Flask application
├── gunicorn.conf.py          # Gunicorn worker/binding settings
├── requirements.txt
├── setup.sh                  # Setup and service installer
├── .env.example              # Environment variable reference
└── logMasterDaemon.service   # systemd unit file
```

## Configuration

### .env

Copy `.env.example` to `.env` and set the shared secret before starting.

```
LOG_API_SHARED_SECRET=<strong random string>
LOG_API_PORT=5001
FLASK_DEBUG=false
```

`LOG_API_SHARED_SECRET` must match the value configured in the server's `.env`.

## Setup

```bash
./setup.sh                       # create venv, install deps, copy .env
nano .env                        # set LOG_API_SHARED_SECRET
```

### Install as systemd service

```bash
sudo ./setup.sh --install-service
```

This will:
1. Create a `logmaster` system user (if not present)
2. Add `logmaster` to the `systemd-journal` group
3. Copy files to `/root/logMaster/daemon/`
4. Install and enable `logMasterDaemon.service`

### Manual start (development)

```bash
source .venv/bin/activate
python daemon.py
```

## API

### POST /logs

Fetch journal entries for a service within a time range.

**Request**

```
Content-Type: application/json
```

```json
{
  "shared_secret": "your-shared-secret",
  "service_name":  "nginx.service",
  "start_date":    "2024-01-15 00:00:00",
  "end_date":      "2024-01-15 23:59:59"
}
```

| Field | Type | Description |
|---|---|---|
| `shared_secret` | string | Must match `LOG_API_SHARED_SECRET` on the daemon |
| `service_name` | string | Systemd unit name. Only `[A-Za-z0-9._-]` characters accepted |
| `start_date` | string | `YYYY-MM-DD` or `YYYY-MM-DD HH:MM:SS` |
| `end_date` | string | `YYYY-MM-DD` or `YYYY-MM-DD HH:MM:SS` |

**Response — 200 OK**

```json
{
  "service":    "nginx.service",
  "start_date": "2024-01-15 00:00:00",
  "end_date":   "2024-01-15 23:59:59",
  "count":      42,
  "entries":    [ { ...journald fields... } ]
}
```

Each entry is a raw journald JSON object. Commonly used fields:

| Field | Description |
|---|---|
| `__REALTIME_TIMESTAMP` | Microseconds since Unix epoch |
| `MESSAGE` | Log message string |
| `PRIORITY` | Syslog priority: 0 (emerg) – 7 (debug) |
| `_PID` | Process ID |
| `_SYSTEMD_UNIT` | Unit name |
| `SYSLOG_IDENTIFIER` | Process/unit identifier |

**Error responses**

| Status | Cause |
|---|---|
| `400` | Missing or invalid field |
| `401` | Wrong `shared_secret` |
| `415` | Request is not `application/json` |
| `500` | `journalctl` not found or server misconfigured |
| `504` | `journalctl` timed out (30 s limit) |

## Querying from the CLI

### curl

```bash
curl -s -X POST http://127.0.0.1:5001/logs \
  -H "Content-Type: application/json" \
  -d '{
    "shared_secret": "your-shared-secret",
    "service_name":  "nginx.service",
    "start_date":    "2024-01-15 00:00:00",
    "end_date":      "2024-01-15 23:59:59"
  }' | python3 -m json.tool
```

### Python (one-liner)

```bash
python3 -c "
import requests, json

resp = requests.post('http://127.0.0.1:5001/logs', json={
    'shared_secret': 'your-shared-secret',
    'service_name':  'nginx.service',
    'start_date':    '2024-01-15 00:00:00',
    'end_date':      '2024-01-15 23:59:59',
})
data = resp.json()
print(f'{data[\"count\"]} entries')
for e in data['entries']:
    print(e.get('MESSAGE', ''))
"
```

### Python script

```python
import requests
from datetime import datetime, timedelta

DAEMON_URL   = "http://127.0.0.1:5001"
SHARED_SECRET = "your-shared-secret"

def fetch_logs(service, hours=48):
    now   = datetime.now()
    since = now - timedelta(hours=hours)
    resp  = requests.post(
        f"{DAEMON_URL}/logs",
        json={
            "shared_secret": SHARED_SECRET,
            "service_name":  service,
            "start_date":    since.strftime("%Y-%m-%d %H:%M:%S"),
            "end_date":      now.strftime("%Y-%m-%d %H:%M:%S"),
        },
        timeout=35,
    )
    resp.raise_for_status()
    return resp.json()

data = fetch_logs("nginx.service")
print(f"Fetched {data['count']} entries")
for entry in data["entries"]:
    print(entry.get("MESSAGE", ""))
```

## Gunicorn

`gunicorn.conf.py` binds to `0.0.0.0:5001` and spawns `CPU count` sync workers. Each worker may fork a `journalctl` subprocess per request, so the worker count is kept lower than the server's default. Adjust `workers` and `bind` as needed.

## Security Notes

- The daemon performs no user authentication beyond the shared secret. Restrict network access so only the server can reach port 5001 (firewall rule or private network).
- `service_name` is validated against `^[\w.\-]+$` before use. `journalctl` is called via `subprocess.run` with a list argument — no shell interpolation occurs.
