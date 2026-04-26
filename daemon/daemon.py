"""
Log API - Single endpoint that queries journald and returns JSON log entries.
Accepts POST /logs with JSON: shared_secret, service_name, start_date, end_date
"""

import os
import subprocess
import json
import re
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify

app = Flask(__name__)

SHARED_SECRET = os.environ.get("LOG_API_SHARED_SECRET", "")
PAGE_SIZE = 500

# Only allow simple systemd unit names (letters, digits, hyphens, underscores, dots)
_SAFE_UNIT = re.compile(r"^[\w.\-]+$")
# Page cursor = __REALTIME_TIMESTAMP of the oldest entry on the previous page
# (decimal microseconds since epoch)
_SAFE_CURSOR = re.compile(r"^[0-9]+$")


def _validate_date(value: str) -> bool:
    """Accept ISO-8601 dates/datetimes that journalctl understands."""
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?$", value))


@app.route("/logs", methods=["POST"])
def get_logs():
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 415

    data = request.get_json(silent=True) or {}

    # Authenticate
    secret = data.get("shared_secret", "")
    if not SHARED_SECRET:
        return jsonify({"error": "Server misconfigured: LOG_API_SHARED_SECRET not set"}), 500
    if secret != SHARED_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    # Validate inputs
    service_name = data.get("service_name", "").strip()
    start_date = data.get("start_date", "").strip()
    end_date = data.get("end_date", "").strip()
    cursor = data.get("cursor", "").strip()

    if not service_name or not _SAFE_UNIT.match(service_name):
        return jsonify({"error": "Invalid or missing service_name"}), 400
    if not start_date or not _validate_date(start_date):
        return jsonify({"error": "Invalid or missing start_date (use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)"}), 400
    if not end_date or not _validate_date(end_date):
        return jsonify({"error": "Invalid or missing end_date (use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)"}), 400
    if cursor and not _SAFE_CURSOR.match(cursor):
        return jsonify({"error": "Invalid cursor format"}), 400

    # Fetch PAGE_SIZE + 1 to detect whether more entries exist.
    fetch_n = PAGE_SIZE + 1

    # When paginating, use the oldest entry's timestamp from the previous page
    # as an exclusive upper bound so journalctl only scans the older portion.
    if cursor:
        try:
            ts_us = int(cursor)
            ts_dt = (
                datetime.fromtimestamp(ts_us / 1_000_000, tz=timezone.utc)
                - timedelta(microseconds=1)
            )
            effective_until = ts_dt.strftime("%Y-%m-%d %H:%M:%S.%f")
        except (ValueError, OverflowError, OSError):
            return jsonify({"error": "Invalid cursor value"}), 400
    else:
        effective_until = end_date

    cmd = [
        "journalctl",
        "-u", service_name,
        "--output=json",
        f"--since={start_date}",
        f"--until={effective_until}",
        "--no-pager",
        "--reverse",
        "-n", str(fetch_n),
    ]

    print(f"[journalctl] {' '.join(cmd)}", flush=True)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return jsonify({"error": "journalctl timed out"}), 504
    except FileNotFoundError:
        return jsonify({"error": "journalctl not found on this system"}), 500

    if result.returncode not in (0, 1):  # 1 = no entries found, which is fine
        return jsonify({"error": "journalctl error", "detail": result.stderr.strip()}), 500

    # journalctl --output=json emits one JSON object per line.
    # Fields that contain non-UTF-8 data are represented as arrays of
    # byte integers — decode them back to strings so every entry is a
    # flat key→string map.
    entries = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        for key, value in entry.items():
            if isinstance(value, list):
                try:
                    entry[key] = bytes(value).decode("utf-8", errors="replace")
                except (TypeError, ValueError):
                    entry[key] = str(value)
        entries.append(entry)

    has_more = len(entries) > PAGE_SIZE
    entries = entries[:PAGE_SIZE]
    # next_cursor = realtime timestamp (µs) of the oldest entry on this page.
    # The next request will use it as an exclusive --until upper bound.
    next_cursor = entries[-1].get("__REALTIME_TIMESTAMP") if has_more and entries else None

    return jsonify({
        "service": service_name,
        "start_date": start_date,
        "end_date": end_date,
        "count": len(entries),
        "has_more": has_more,
        "next_cursor": next_cursor,
        "entries": entries,
    })


if __name__ == "__main__":
    port = int(os.environ.get("LOG_API_PORT", 5001))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
