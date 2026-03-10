"""
Main web app - Authentik OIDC authentication + journald log viewer UI.
Fetches log data from the Log API (log_api.py).
"""

import os
import secrets
from datetime import datetime, timedelta
from functools import wraps

import requests
from authlib.integrations.flask_client import OAuth
from flask import (
    Flask,
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

oauth = OAuth(app)
oauth.register(
    name="authentik",
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    server_metadata_url=f"{AUTHENTIK_BASE_URL}/application/o/{CLIENT_ID}/.well-known/openid-configuration",
    client_kwargs={"scope": "openid profile email"},
)

# ── Log API config ───────────────────────────────────────────────────────────

LOG_API_URL = os.environ.get("LOG_API_URL", "http://127.0.0.1:5001")
LOG_API_SHARED_SECRET = os.environ.get("LOG_API_SHARED_SECRET", "")


# ── Auth helpers ─────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            session["next"] = request.url
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    return render_template("index.html", user=session["user"], today=today, yesterday=yesterday)


@app.route("/logs", methods=["POST"])
@login_required
def fetch_logs():
    service_name = request.form.get("service_name", "").strip()
    start_date = request.form.get("start_date", "").strip()
    end_date = request.form.get("end_date", "").strip()

    errors = []
    if not service_name:
        errors.append("Service name is required.")
    if not start_date:
        errors.append("Start date is required.")
    if not end_date:
        errors.append("End date is required.")

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("index"))

    payload = {
        "shared_secret": LOG_API_SHARED_SECRET,
        "service_name": service_name,
        "start_date": start_date,
        "end_date": end_date,
    }

    api_error = None
    log_data = None

    try:
        resp = requests.post(
            f"{LOG_API_URL}/logs",
            json=payload,
            timeout=35,
        )
        if resp.ok:
            log_data = resp.json()
        else:
            api_error = resp.json().get("error", f"API returned {resp.status_code}")
    except requests.exceptions.ConnectionError:
        api_error = f"Could not connect to Log API at {LOG_API_URL}"
    except requests.exceptions.Timeout:
        api_error = "Log API request timed out"
    except Exception as exc:  # noqa: BLE001
        api_error = str(exc)

    return render_template(
        "logs.html",
        user=session["user"],
        service_name=service_name,
        start_date=start_date,
        end_date=end_date,
        log_data=log_data,
        api_error=api_error,
    )


@app.route("/login")
def login():
    redirect_uri = url_for("auth_callback", _external=True)
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

    # End session at Authentik if possible
    end_session_url = f"{AUTHENTIK_BASE_URL}/application/o/{CLIENT_ID}/end-session/"
    post_logout = url_for("index", _external=True)
    if user:
        return redirect(f"{end_session_url}?post_logout_redirect_uri={post_logout}")
    return redirect(url_for("index"))


if __name__ == "__main__":
    port = int(os.environ.get("APP_PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
