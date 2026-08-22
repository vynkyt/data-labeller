#!/usr/bin/env bash
# Usage (after SSH-ing into your nest container as root, e.g. ssh you@hackclub.app):
#   curl -fsSL https://raw.githubusercontent.com/vynkyt/data-labeller/main/deploy/nest-setup.sh | bash
#
# Or clone first and run:
#   bash data-labeller/deploy/nest-setup.sh
#
# Env overrides (optional):
#   APP_PORT=8123        port uvicorn listens on locally
#   SUBDOMAIN=...        public hostname to publish (default: <hostname>.hackclub.app)
#                        e.g. SUBDOMAIN=labeller.vkyt.hackclub.app
#   GEMINI_API_KEY=...   use real Gemini for AI QC; if unset, the demo falls
#                        back to GEMINI_MOCK_VERDICT=MIXED (~70% pass / 30% fail)
#   REPO_URL=...         git repo to clone
set -euo pipefail

APP_DIR="$HOME/data-labeller"
REPO_URL="${REPO_URL:-https://github.com/vynkyt/data-labeller.git}"
PORT="${APP_PORT:-8123}"
SUBDOMAIN="${SUBDOMAIN:-$(hostname).hackclub.app}"

# New Nest containers have no per-user Caddy; the reverse proxy is managed
# via the web dashboard at https://dashboard.hackclub.app instead.
OLD_NEST_CADDY=0
if systemctl --user cat caddy >/dev/null 2>&1; then
    OLD_NEST_CADDY=1
fi

echo "==> Installing uv (Python package manager)"
if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

echo "==> Cloning / updating $REPO_URL"
if [ -d "$APP_DIR/.git" ]; then
    git -C "$APP_DIR" pull --ff-only
else
    rm -rf "$APP_DIR"
    git clone "$REPO_URL" "$APP_DIR"
fi

echo "==> Installing dependencies"
cd "$APP_DIR/python"
uv sync --no-dev

echo "==> Creating systemd service (keeps the app running 24/7)"
BIND_HOST="127.0.0.1"
if [ "$OLD_NEST_CADDY" = "0" ]; then
    # New Nest: the dashboard reverse proxy reaches the container over the
    # network, so the app must listen on all interfaces.
    BIND_HOST="0.0.0.0"
fi
# Real Gemini when an API key is provided; mock otherwise so AI QC works out of the box.
if [ -n "${GEMINI_API_KEY:-}" ]; then
    echo "==> Using real Gemini for AI QC (GEMINI_API_KEY provided)"
    AI_ENV_LINE="Environment=GEMINI_API_KEY=$GEMINI_API_KEY"
else
    echo "==> No GEMINI_API_KEY set; using mixed mock verdicts for AI QC"
    AI_ENV_LINE="Environment=GEMINI_MOCK_VERDICT=MIXED"
fi
cat > /etc/systemd/system/data-labeller.service <<EOF
[Unit]
Description=Data Labeller FastAPI app
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Restart=always
RestartSec=5
WorkingDirectory=$APP_DIR/python
Environment=AUTO_SEED=1
$AI_ENV_LINE
ExecStart=$HOME/.local/bin/uv run --no-sync uvicorn main:app --host $BIND_HOST --port $PORT

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable data-labeller.service
systemctl restart data-labeller.service

if [ "$OLD_NEST_CADDY" = "1" ]; then
    echo "==> Configuring Caddy to serve $SUBDOMAIN -> port $PORT"
    export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
    cat > "$HOME/Caddyfile" <<EOF
{
    admin unix//home/$USER/caddy-admin.sock
}
http://$SUBDOMAIN {
    bind unix/.webserver.sock|777
    reverse_proxy :$PORT
}
EOF
    systemctl --user reload caddy
else
    echo "==> New Nest detected (no local Caddy)"
    echo ""
    echo " Finish the public URL in the Nest dashboard:"
    echo "   1. Open https://dashboard.hackclub.app and log in"
    echo "   2. Go to the Domains tab"
    echo "   3. Add domain:  $SUBDOMAIN"
    echo "      Target port: $PORT"
    echo "   HTTPS + DNS are handled for *.hackclub.app automatically."
    echo ""
fi

echo "==> Waiting for the app to start..."
sleep 3
for i in $(seq 1 10); do
    if curl -fsS "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then
        echo ""
        echo "=========================================="
        echo " Done! The app is running on port $PORT."
        if [ "$OLD_NEST_CADDY" = "1" ]; then
            echo " Your demo is live at:"
        else
            echo " Once you added the domain in the dashboard, it is live at:"
            echo " (allow a few minutes for the HTTPS certificate)"
        fi
        echo "   https://$SUBDOMAIN"
        echo ""
        echo " Demo tasks are pre-loaded (AUTO_SEED)."
        echo " Service commands:"
        echo "   systemctl restart data-labeller"
        echo "   journalctl -u data-labeller -f"
        echo "=========================================="
        exit 0
    fi
    sleep 2
done

echo "WARNING: app did not respond yet. Check logs with: journalctl -u data-labeller -n 50"
exit 1
