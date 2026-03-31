import os
import time
import threading
import urllib.parse
import requests
import json
from flask import Flask, jsonify, render_template_string
from instagrapi import Client
from instagrapi.exceptions import RateLimitError

SESSION_ID_1 = os.getenv("SESSION_ID_1")
SESSION_ID_2 = os.getenv("SESSION_ID_2")
SESSION_ID_3 = os.getenv("SESSION_ID_3")
SESSION_ID_4 = os.getenv("SESSION_ID_4")
GROUP_IDS = os.getenv("GROUP_IDS", "")
MESSAGE_TEXT = os.getenv("MESSAGE_TEXT", "Hello 👋")
SELF_URL = os.getenv("SELF_URL", "")
NC_TITLES_RAW = os.getenv("NC_TITLES", "")
SPAM_START_OFFSET = 1
SPAM_GAP_BETWEEN_ACCOUNTS = 10
NC_START_OFFSET = 1
NC_ACC_GAP = 4
MSG_REFRESH_DELAY = int(os.getenv("MSG_REFRESH_DELAY", "1"))
BURST_COUNT = int(os.getenv("BURST_COUNT", "1"))
SELF_PING_INTERVAL = int(os.getenv("SELF_PING_INTERVAL", "60"))
COOLDOWN_ON_ERROR = int(os.getenv("COOLDOWN_ON_ERROR", "300"))
TITLE_CHECK_COOLDOWN = int(os.getenv("TITLE_CHECK_COOLDOWN", "20"))

DOC_ID = os.getenv("DOC_ID", "29088580780787855")
CSRF_TOKEN = os.getenv("CSRF_TOKEN", "")

app = Flask(__name__)

MAX_SESSION_LOGS = 500
session_logs = {
    "acc1": [],
    "acc2": [],
    "acc3": [],
    "acc4": [],
    "system": []
}
logs_lock = threading.Lock()
LAST_TITLE_CHECK = {}

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bot Dashboard</title>
    <style>
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: Arial, sans-serif;
            background: #0f1115;
            color: #e6edf3;
        }
        .topbar {
            padding: 16px 20px;
            background: #161b22;
            border-bottom: 1px solid #30363d;
            position: sticky;
            top: 0;
            z-index: 10;
        }
        .topbar h1 {
            margin: 0 0 6px 0;
            font-size: 22px;
        }
        .topbar .meta {
            color: #9da7b3;
            font-size: 14px;
        }
        .wrap {
            padding: 16px;
        }
        .cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 14px;
            margin-bottom: 16px;
        }
        .card, .settings {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 12px;
            padding: 14px;
        }
        .card h2, .settings h2 {
            margin: 0 0 10px 0;
            font-size: 16px;
        }
        .stat, .setting-row {
            font-size: 13px;
            color: #9da7b3;
            margin: 6px 0;
            word-break: break-word;
        }
        .setting-row b {
            color: #e6edf3;
        }
        .settings-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 14px;
            margin-bottom: 16px;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 14px;
        }
        .logbox {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 12px;
            overflow: hidden;
        }
        .loghead {
            padding: 10px 14px;
            border-bottom: 1px solid #30363d;
            font-weight: bold;
            background: #1c2128;
        }
        .logcontent {
            height: 320px;
            overflow-y: auto;
            padding: 10px;
            font-family: Consolas, monospace;
            font-size: 12px;
            line-height: 1.45;
            white-space: pre-wrap;
            word-break: break-word;
        }
        .line {
            padding: 3px 0;
            border-bottom: 1px dashed rgba(255,255,255,0.05);
        }
        .ok { color: #3fb950; }
        .warn { color: #d29922; }
        .err { color: #f85149; }
        .info { color: #79c0ff; }
        .muted { color: #9da7b3; }
        .controls {
            margin-top: 10px;
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        button {
            background: #238636;
            border: none;
            color: white;
            padding: 8px 12px;
            border-radius: 8px;
            cursor: pointer;
        }
        button.secondary {
            background: #30363d;
        }
        .pill {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 999px;
            background: #21262d;
            color: #c9d1d9;
            font-size: 12px;
            margin: 2px 4px 2px 0;
        }
    </style>
</head>
<body>
    <div class="topbar">
        <h1>Bot Dashboard</h1>
        <div class="meta">Live logs + settings + account summary</div>
        <div class="controls">
            <button onclick="refreshNow()">Refresh now</button>
            <button class="secondary" onclick="toggleAutoRefresh()" id="toggleBtn">Pause auto refresh</button>
        </div>
    </div>

    <div class="wrap">
        <div class="settings-grid">
            <div class="settings">
                <h2>Runtime Settings</h2>
                <div id="settingsPanel"></div>
            </div>
            <div class="settings">
                <h2>Group IDs</h2>
                <div id="groupsPanel"></div>
            </div>
            <div class="settings">
                <h2>NC Titles</h2>
                <div id="titlesPanel"></div>
            </div>
        </div>

        <div class="cards" id="summaryCards"></div>

        <div class="grid">
            <div class="logbox"><div class="loghead">System Logs</div><div class="logcontent" id="system"></div></div>
            <div class="logbox"><div class="loghead">Account 1 Logs</div><div class="logcontent" id="acc1"></div></div>
            <div class="logbox"><div class="loghead">Account 2 Logs</div><div class="logcontent" id="acc2"></div></div>
            <div class="logbox"><div class="loghead">Account 3 Logs</div><div class="logcontent" id="acc3"></div></div>
            <div class="logbox"><div class="loghead">Account 4 Logs</div><div class="logcontent" id="acc4"></div></div>
        </div>
    </div>

    <script>
        let autoRefresh = true;

        function cls(line) {
            const l = line.toLowerCase();
            if (l.includes("❌") || l.includes("failed")) return "err";
            if (l.includes("⚠")) return "warn";
            if (l.includes("✅") || l.includes("started")) return "ok";
            if (l.includes("🔐") || l.includes("🔁") || l.includes("http")) return "info";
            return "muted";
        }

        function escapeHtml(text) {
            return String(text)
                .replaceAll("&", "&amp;")
                .replaceAll("<", "&lt;")
                .replaceAll(">", "&gt;");
        }

        function renderLines(id, lines) {
            const el = document.getElementById(id);
            const wasNearBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 20;
            el.innerHTML = (lines || []).map(line => `<div class="line ${cls(line)}">${escapeHtml(line)}</div>`).join("");
            if (wasNearBottom) el.scrollTop = el.scrollHeight;
        }

        function renderSummary(data) {
            const cards = document.getElementById("summaryCards");
            const stats = data.stats || {};
            cards.innerHTML = Object.keys(stats).map(key => {
                const s = stats[key];
                return `
                    <div class="card">
                        <h2>${escapeHtml(key.toUpperCase())}</h2>
                        <div class="stat">Total logs: ${s.total}</div>
                        <div class="stat">Last log: ${escapeHtml(s.last || "None")}</div>
                    </div>
                `;
            }).join("");
        }

        function renderSettings(settings) {
            document.getElementById("settingsPanel").innerHTML = `
                <div class="setting-row"><b>Server Time:</b> ${escapeHtml(settings.server_time || "")}</div>
                <div class="setting-row"><b>NC_ACC_GAP:</b> ${escapeHtml(settings.NC_ACC_GAP)} sec</div>
                <div class="setting-row"><b>TITLE_CHECK_COOLDOWN:</b> ${escapeHtml(settings.TITLE_CHECK_COOLDOWN)} sec</div>
                <div class="setting-row"><b>SPAM_GAP_BETWEEN_ACCOUNTS:</b> ${escapeHtml(settings.SPAM_GAP_BETWEEN_ACCOUNTS)} sec</div>
                <div class="setting-row"><b>MSG_REFRESH_DELAY:</b> ${escapeHtml(settings.MSG_REFRESH_DELAY)} sec</div>
                <div class="setting-row"><b>BURST_COUNT:</b> ${escapeHtml(settings.BURST_COUNT)}</div>
                <div class="setting-row"><b>SELF_PING_INTERVAL:</b> ${escapeHtml(settings.SELF_PING_INTERVAL)} sec</div>
                <div class="setting-row"><b>MESSAGE_TEXT:</b> ${escapeHtml(settings.MESSAGE_TEXT)}</div>
            `;

            const groups = settings.GROUP_IDS || [];
            document.getElementById("groupsPanel").innerHTML = groups.length
                ? groups.map(g => `<span class="pill">${escapeHtml(g)}</span>`).join("")
                : '<div class="setting-row">No groups configured</div>';

            const titles = settings.NC_TITLES || [];
            document.getElementById("titlesPanel").innerHTML = titles.length
                ? titles.map(t => `<span class="pill">${escapeHtml(t)}</span>`).join("")
                : '<div class="setting-row">No NC titles configured</div>';
        }

        async function fetchLogs() {
            try {
                const res = await fetch('/logs');
                const data = await res.json();
                renderSummary(data);
                renderSettings(data.settings || {});
                renderLines("system", data.logs.system || []);
                renderLines("acc1", data.logs.acc1 || []);
                renderLines("acc2", data.logs.acc2 || []);
                renderLines("acc3", data.logs.acc3 || []);
                renderLines("acc4", data.logs.acc4 || []);
            } catch (e) {
                console.error("Dashboard fetch error:", e);
            }
        }

        function refreshNow() { fetchLogs(); }

        function toggleAutoRefresh() {
            autoRefresh = !autoRefresh;
            document.getElementById("toggleBtn").innerText = autoRefresh
                ? "Pause auto refresh"
                : "Resume auto refresh";
        }

        fetchLogs();
        setInterval(() => {
            if (autoRefresh) fetchLogs();
        }, 1000);
    </script>
</body>
</html>
"""

def _push_log(session, msg):
    if session not in session_logs:
        session = "system"
    with logs_lock:
        session_logs[session].append(msg)
        if len(session_logs[session]) > MAX_SESSION_LOGS:
            session_logs[session].pop(0)

def log(msg, session="system"):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    _push_log(session, line)

@app.route("/health")
def health():
    return jsonify({"status": "ok", "message": "Bot process alive"})

def summarize(lines):
    rev = list(reversed(lines))
    last_login = next((l for l in rev if "Logged in" in l), None)
    last_send_ok = next((l for l in rev if "✅" in l and "sent to" in l), None)
    last_send_err = next((l for l in rev if "Send failed" in l or "⚠ send failed" in l), None)
    last_title_ok = next((l for l in rev if "changed title" in l and "📝" in l), None)
    last_title_err = next((l for l in rev if "Title change" in l or "GraphQL title" in l), None)
    return {
        "last_login": last_login,
        "last_send_ok": last_send_ok,
        "last_send_error": last_send_err,
        "last_title_ok": last_title_ok,
        "last_title_error": last_title_err,
    }

@app.route("/status")
def status():
    with logs_lock:
        acc1_logs = session_logs["acc1"][-80:]
        acc2_logs = session_logs["acc2"][-80:]
        acc3_logs = session_logs["acc3"][-80:]
        acc4_logs = session_logs["acc4"][-80:]
        system_last = session_logs["system"][-5:]

    return jsonify({
        "ok": True,
        "acc1": summarize(acc1_logs),
        "acc2": summarize(acc2_logs),
        "acc3": summarize(acc3_logs),
        "acc4": summarize(acc4_logs),
        "system_last": system_last
    })

@app.route("/logs")
def logs():
    with logs_lock:
        data = {
            "system": session_logs["system"][-200:],
            "acc1": session_logs["acc1"][-200:],
            "acc2": session_logs["acc2"][-200:],
            "acc3": session_logs["acc3"][-200:],
            "acc4": session_logs["acc4"][-200:]
        }

    stats = {
        key: {
            "total": len(val),
            "last": val[-1] if val else None
        }
        for key, val in data.items()
    }

    settings = {
        "server_time": time.strftime('%Y-%m-%d %H:%M:%S'),
        "NC_ACC_GAP": NC_ACC_GAP,
        "TITLE_CHECK_COOLDOWN": TITLE_CHECK_COOLDOWN,
        "SPAM_GAP_BETWEEN_ACCOUNTS": SPAM_GAP_BETWEEN_ACCOUNTS,
        "MSG_REFRESH_DELAY": MSG_REFRESH_DELAY,
        "BURST_COUNT": BURST_COUNT,
        "SELF_PING_INTERVAL": SELF_PING_INTERVAL,
        "MESSAGE_TEXT": MESSAGE_TEXT,
        "GROUP_IDS": [g.strip() for g in GROUP_IDS.split(",") if g.strip()],
        "NC_TITLES": [t.strip() for t in NC_TITLES_RAW.split(",") if t.strip()]
    }

    return jsonify({
        "ok": True,
        "logs": data,
        "stats": stats,
        "settings": settings
    })

@app.route("/dashboard")
def dashboard():
    return render_template_string(DASHBOARD_HTML)

def decode_session(session):
    if not session:
        return session
    try:
        return urllib.parse.unquote(session)
    except Exception:
        return session

def get_nc_titles():
    return [t.strip() for t in NC_TITLES_RAW.split(",") if t.strip()]

NC_TITLES = get_nc_titles()

def title_matches_nc(current_title: str) -> bool:
    if not current_title:
        return False
    lower = current_title.lower()
    for sub in NC_TITLES:
        if sub.lower() in lower:
            return True
    return False

def should_check_title(gid):
    now = time.time()
    key = str(gid)
    last_check = LAST_TITLE_CHECK.get(key, 0)
    if now - last_check < TITLE_CHECK_COOLDOWN:
        return False
    LAST_TITLE_CHECK[key] = now
    return True

def get_current_thread_title(cl, thread_id):
    try:
        thread = cl.direct_thread(int(thread_id))
        return getattr(thread, "thread_title", None) or getattr(thread, "title", None) or ""
    except Exception as e:
        log(f"⚠ Could not fetch current title for {thread_id}: {e}", session="system")
        return ""

def login_session(session_id, name_hint=""):
    session_id = decode_session(session_id)
    try:
        cl = Client()
        cl.delay_range = [1, 3]
        cl.login_by_sessionid(session_id)
        uname = getattr(cl, "username", None) or name_hint or "unknown"
        log(f"✅ Logged in {uname}", session=name_hint or "system")
        return cl
    except Exception as e:
        log(f"❌ Login failed ({name_hint}): {e}", session=name_hint or "system")
        return None

def safe_send_message(cl, gid, msg, acc_name):
    try:
        cl.direct_send(msg, thread_ids=[int(gid)])
        log(f"✅ {getattr(cl,'username','?')} sent to {gid}", session=acc_name)
        return True
    except Exception as e:
        log(f"⚠ Send failed ({getattr(cl,'username','?')}) -> {gid}: {e}", session=acc_name)
        return False

def rename_thread(cl, thread_id, title):
    try:
        cl.private_request(
            f"direct_v2/threads/{thread_id}/update_title/",
            data={"title": title}
        )
        return True
    except RateLimitError:
        return False
    except Exception:
        return False

def spam_loop(clients, groups):
    if not groups:
        log("⚠ No groups for messaging loop.", session="system")
        return

    time.sleep(SPAM_START_OFFSET)

    idx = 0
    n = len(clients)
    while True:
        cl = clients[idx]
        acc_name = f"acc{idx+1}"

        try:
            for gid in groups:
                for _ in range(BURST_COUNT):
                    ok = safe_send_message(cl, gid, MESSAGE_TEXT, acc_name)
                    if not ok:
                        log(
                            f"⚠ send failed by {getattr(cl,'username','?')}, cooling down {COOLDOWN_ON_ERROR}s",
                            session=acc_name
                        )
                        time.sleep(COOLDOWN_ON_ERROR)
                    time.sleep(MSG_REFRESH_DELAY)
                time.sleep(0.5)
        except Exception as e:
            log(f"❌ Exception in {acc_name} message loop: {e}", session=acc_name)

        try:
            time.sleep(SPAM_GAP_BETWEEN_ACCOUNTS)
        except Exception:
            pass

        idx = (idx + 1) % n

def parse_nc_titles():
    base = [t.strip() for t in NC_TITLES_RAW.split(",") if t.strip()]
    default_title = MESSAGE_TEXT[:40] or "NC"
    while len(base) < 4:
        base.append(default_title)
    return base[:4]

def nc_loop(clients, groups, titles_map):
    if not groups:
        log("⚠ No groups for title loop.", session="system")
        return

    if not NC_TITLES:
        log("⚠ NC_TITLES is empty, nc loop disabled.", session="system")
        return

    per_account_titles = parse_nc_titles()
    log(f"NC titles per account: {per_account_titles}", session="system")
    log(f"TITLE_CHECK_COOLDOWN={TITLE_CHECK_COOLDOWN}s", session="system")

    time.sleep(NC_START_OFFSET)

    idx = 0
    n = len(clients)

    while True:
        cl = clients[idx]
        acc_name = f"acc{idx+1}"
        account_title = per_account_titles[idx]

        try:
            for gid in groups:
                if not should_check_title(gid):
                    log(f"⏭ Skipping title check for {gid} (cooldown active)", session=acc_name)
                    continue

                current_title = get_current_thread_title(cl, gid)

                if title_matches_nc(current_title):
                    log(
                        f"✅ {gid} already matches NC title ({current_title}) — skipping",
                        session=acc_name
                    )
                    continue

                titles = titles_map.get(str(gid)) or titles_map.get(int(gid)) or [account_title]
                t = titles[0]

                ok = rename_thread(cl, gid, t)
                if ok:
                    log(
                        f"📝 {getattr(cl,'username','?')} changed title for {gid} -> {t}",
                        session=acc_name
                    )
                else:
                    log(
                        f"⚠ Title change failed for {gid} by {getattr(cl,'username','?')}",
                        session=acc_name
                    )

                time.sleep(1)
        except Exception as e:
            log(f"❌ Exception in {acc_name} title loop: {e}", session=acc_name)

        try:
            time.sleep(NC_ACC_GAP)
        except Exception:
            pass

        idx = (idx + 1) % n

def self_ping_loop():
    while True:
        if SELF_URL:
            try:
                requests.get(SELF_URL, timeout=10)
                log("🔁 Self ping successful", session="system")
            except Exception as e:
                log(f"⚠ Self ping failed: {e}", session="system")
        time.sleep(SELF_PING_INTERVAL)

def start_bot():
    log(
        "STARTUP: "
        f"SESSION_ID_1={repr(SESSION_ID_1)}, "
        f"SESSION_ID_2={repr(SESSION_ID_2)}, "
        f"SESSION_ID_3={repr(SESSION_ID_3)}, "
        f"SESSION_ID_4={repr(SESSION_ID_4)}, "
        f"GROUP_IDS={repr(GROUP_IDS)}, MESSAGE_TEXT={repr(MESSAGE_TEXT)}, "
        f"NC_TITLES={repr(NC_TITLES_RAW)}",
        session="system"
    )

    s1 = decode_session(SESSION_ID_1)
    s2 = decode_session(SESSION_ID_2)
    s3 = decode_session(SESSION_ID_3)
    s4 = decode_session(SESSION_ID_4)

    sessions = [s1, s2, s3, s4]
    if not all(sessions):
        log("❌ All 4 session IDs (SESSION_ID_1..4) are required in environment", session="system")
        return

    groups = [g.strip() for g in GROUP_IDS.split(",") if g.strip()]
    if not groups:
        log("❌ GROUP_IDS is empty or invalid", session="system")
        return

    titles_map = {}
    raw_titles = os.getenv("GROUP_TITLES", "")
    if raw_titles:
        try:
            titles_map = json.loads(raw_titles)
        except Exception as e:
            log(f"⚠ GROUP_TITLES JSON parse error: {e}. Using fallback titles.", session="system")

    clients = []
    for i, s in enumerate(sessions, 1):
        log(f"🔐 Logging in account {i}...", session="system")
        cl = login_session(s, f"acc{i}")
        if not cl:
            log(f"❌ Account {i} login failed — aborting start", session="system")
            return
        clients.append(cl)

    try:
        t1 = threading.Thread(target=spam_loop, args=(clients, groups), daemon=True)
        t1.start()
        log("▶ Started spam loop with 4 accounts (1s start, 10s gap between accounts)", session="system")
    except Exception as e:
        log(f"❌ Failed to start spam loop thread: {e}", session="system")

    try:
        t2 = threading.Thread(target=nc_loop, args=(clients, groups, titles_map), daemon=True)
        t2.start()
        log("▶ Started nc loop with 4 accounts (1s start, 4s gap between accounts)", session="system")
    except Exception as e:
        log(f"❌ Failed to start nc loop thread: {e}", session="system")

    try:
        t3 = threading.Thread(target=self_ping_loop, daemon=True)
        t3.start()
        log("▶ Started self-ping loop", session="system")
    except Exception as e:
        log(f"⚠ Failed to start self-ping thread: {e}", session="system")

def run_bot_once():
    try:
        threading.Thread(target=start_bot, daemon=True).start()
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ❌ Failed to start bot (import-time): {e}", flush=True)

run_bot_once()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    log(f"HTTP server starting on port {port}", session="system")
    try:
        app.run(host="0.0.0.0", port=port)
    except Exception as e:
        log(f"❌ Flask run failed: {e}", session="system")