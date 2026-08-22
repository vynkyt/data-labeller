#!/usr/bin/env bash
# Data Labeller - one-shot setup for Hack Club Nest.
#
# Usage (after SSH-ing into your nest account):
#   curl -fsSL https://raw.githubusercontent.com/vynkyt/data-labeller/main/deploy/nest-setup.sh | bash
#
# Or clone first and run:
#   bash data-labeller/deploy/nest-setup.sh
#
# Env overrides (optional):
#   APP_PORT=8123        port uvicorn listens on locally
#   REPO_URL=...         git repo to clone
set -euo pipefail

APP_DIR="$HOME/data-labeller"
REPO_URL="${REPO_URL:-https://github.com/vynkyt/data-labeller.git}"
PORT="${APP_PORT:-8123}"
SUBDOMAIN="${SUBDOMAIN:-$USER.hackclub.app}"

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
ExecStart=$HOME/.local/bin/uv run --no-sync uvicorn main:app --host 127.0.0.1 --port $PORT

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now data-labeller.service

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

echo "==> Waiting for the app to start..."
sleep 3
for i in $(seq 1 10); do
    if curl -fsS "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then
        echo ""
        echo "=========================================="
        echo " Done! Your demo is live at:"
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
