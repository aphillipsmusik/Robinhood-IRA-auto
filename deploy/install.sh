#!/usr/bin/env bash
# Full deployment installer for Robinhood OKLL Automation
# Target: Raspberry Pi Ubuntu 24.04 LTS
# Run as: sudo bash deploy/install.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_USER="${SUDO_USER:-ubuntu}"
APP_HOME="/home/${APP_USER}"
VENV_DIR="${REPO_DIR}/.venv"
SERVICE_DIR="/etc/systemd/system"

echo "==> Installing system packages"
apt-get update -qq
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    chromium-browser \
    xvfb \
    x11-utils \
    libglib2.0-0 \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2t64

echo "==> Creating Python virtual environment"
sudo -u "${APP_USER}" python3 -m venv "${VENV_DIR}"
sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install --upgrade pip -q
sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install -r "${REPO_DIR}/requirements.txt" -q

echo "==> Installing Playwright browser"
sudo -u "${APP_USER}" "${VENV_DIR}/bin/playwright" install chromium

echo "==> Setting up .env"
if [ ! -f "${REPO_DIR}/.env" ]; then
    cp "${REPO_DIR}/.env.example" "${REPO_DIR}/.env"
    chown "${APP_USER}:${APP_USER}" "${REPO_DIR}/.env"
    chmod 600 "${REPO_DIR}/.env"
    echo ""
    echo "  *** ACTION REQUIRED ***"
    echo "  Edit ${REPO_DIR}/.env and fill in your credentials before starting."
    echo ""
fi

echo "==> Installing systemd services"
sed "s|__REPO_DIR__|${REPO_DIR}|g; s|__APP_USER__|${APP_USER}|g; s|__VENV_DIR__|${VENV_DIR}|g" \
    "${REPO_DIR}/deploy/xvfb.service" > "${SERVICE_DIR}/okll-xvfb.service"

sed "s|__REPO_DIR__|${REPO_DIR}|g; s|__APP_USER__|${APP_USER}|g; s|__VENV_DIR__|${VENV_DIR}|g" \
    "${REPO_DIR}/deploy/chromium-trading.service" > "${SERVICE_DIR}/okll-chromium.service"

sed "s|__REPO_DIR__|${REPO_DIR}|g; s|__APP_USER__|${APP_USER}|g; s|__VENV_DIR__|${VENV_DIR}|g" \
    "${REPO_DIR}/deploy/okll-trader.service" > "${SERVICE_DIR}/okll-trader.service"

echo "==> Enabling services"
systemctl daemon-reload
systemctl enable okll-xvfb.service okll-chromium.service okll-trader.service

echo ""
echo "Installation complete."
echo ""
echo "Next steps:"
echo "  1. Edit ${REPO_DIR}/.env with your Robinhood credentials and TOTP secret"
echo "  2. Start everything:  sudo systemctl start okll-xvfb okll-chromium okll-trader"
echo "  3. Watch logs:        journalctl -fu okll-trader"
echo "  Or use the Makefile:  make start  /  make logs  /  make status"
