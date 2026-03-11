"""
Main web app - Authentik OIDC authentication + journald log viewer UI.
Fetches log data from the Log API (logMasterDaemon.py).
Services are configured in config.json.
"""

import json
import os
import secrets
from datetime import datetime, timedelta
from functools import wraps

from dotenv import load_dotenv
load_dotenv()

import requests
from authlib.integrations.flask_client import OAuth
from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
    flash,
)

app = Flask(__name__)
app.secret_key = os.environ.get("APP_SECRET_KEY", secrets.token_hex(32))

# ── Authentik OIDC config ────────────────────────────────────────────────────

AUTHENTIK_BASE_URL = os.environ.get("AUTHENTIK_BASE_URL", "").rstrip("/")
CLIENT_ID = os.environ.get("AUTHENTIK_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("AUTHENTIK_CLIENT_SECRET", "")
REDIRECT_URI = os.environ.get("AUTHENTIK_REDIRECT_URI", "")

oauth = OAuth(app)
oauth.register(
    name="authentik",
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    server_metadata_url=f"{AUTHENTIK_BASE_URL}/application/o/logs/.well-known/openid-configuration",
    client_kwargs={"scope": "openid profile email"},
)

# ── Log API config ───────────────────────────────────────────────────────────

LOG_API_URL = os.environ.get("LOG_API_URL", "http://127.0.0.1:5001")
LOG_API_SHARED_SECRET = os.environ.get("LOG_API_SHARED_SECRET", "")

# ── Service config ────────────────────────────────────────────────────────────

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

with open(CONFIG_PATH) as _f:
    _config = json.load(_f)

# Ordered list for tab rendering
SERVICES: list[dict] = _config.get("services", [])

# Map for O(1) lookup by service_name
SERVICES_MAP: dict[str, dict] = {s["service_name"]: s for s in SERVICES}


# ── Auth helpers ─────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            session["next"] = request.url
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ── Helpers ───────────────────────────────────────────────────────────────────

def _default_window():
    """Return (start, end) strings covering the last 2 days."""
    now = datetime.now()
    return (
        (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
        now.strftime("%Y-%m-%dT%H:%M"),
    )


def _query_daemon(service_name, start_date, end_date):
    """Call the daemon and return (log_data, api_error)."""
    daemon_url = SERVICES_MAP.get(service_name, {}).get("address", LOG_API_URL).rstrip("/")
    payload = {
        "shared_secret": LOG_API_SHARED_SECRET,
        "service_name": service_name,
        "start_date": start_date.replace("T", " "),
        "end_date": end_date.replace("T", " "),
    }
    try:
        resp = requests.post(f"{daemon_url}/logs", json=payload, timeout=35)
        if resp.ok:
            return resp.json(), None
        return None, resp.json().get("error", f"API returned {resp.status_code}")
    except requests.exceptions.ConnectionError:
        return None, f"Could not connect to Log API at {daemon_url}"
    except requests.exceptions.Timeout:
        return None, "Log API request timed out"
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    active_tab = request.args.get("tab", "")
    if active_tab not in SERVICES_MAP:
        active_tab = SERVICES[0]["service_name"] if SERVICES else ""

    default_start, default_end = _default_window()
    start_date = request.args.get("start_date", default_start)
    end_date = request.args.get("end_date", default_end)

    return render_template(
        "index.html",
        user=session["user"],
        services=SERVICES,
        active_tab=active_tab,
        start_date=start_date,
        end_date=end_date,
    )


@app.route("/api/logs")
@login_required
def api_logs():
    tab = request.args.get("tab", "")
    if tab not in SERVICES_MAP:
        return jsonify({"error": "Unknown service"}), 400

    default_start, default_end = _default_window()
    start_date = request.args.get("start_date", default_start)
    end_date = request.args.get("end_date", default_end)

    log_data, api_error = _query_daemon(tab, start_date, end_date)
    if api_error:
        return jsonify({"error": api_error}), 502
    return jsonify(log_data)


@app.route("/login")
def login():
    redirect_uri = REDIRECT_URI or url_for("auth_callback", _external=True)
    nonce = secrets.token_urlsafe(16)
    session["oidc_nonce"] = nonce
    return oauth.authentik.authorize_redirect(redirect_uri, nonce=nonce)


@app.route("/callback")
def auth_callback():
    token = oauth.authentik.authorize_access_token()
    nonce = session.pop("oidc_nonce", None)
    user_info = oauth.authentik.parse_id_token(token, nonce=nonce)
    session["user"] = {
        "sub": user_info.get("sub"),
        "name": user_info.get("name") or user_info.get("preferred_username", "User"),
        "email": user_info.get("email", ""),
    }
    next_url = session.pop("next", url_for("index"))
    return redirect(next_url)


@app.route("/logout")
def logout():
    user = session.pop("user", None)
    session.clear()

    end_session_url = f"{AUTHENTIK_BASE_URL}/application/o/{CLIENT_ID}/end-session/"
    post_logout = url_for("index", _external=True)
    if user:
        return redirect(f"{end_session_url}?post_logout_redirect_uri={post_logout}")
    return redirect(url_for("index"))


if __name__ == "__main__":
    port = int(os.environ.get("APP_PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
