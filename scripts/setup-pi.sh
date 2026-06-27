#!/usr/bin/env bash
# Melo LMS — Raspberry Pi 5 setup script
# Run as root: sudo bash setup-pi.sh
set -euo pipefail

MELO_USER="melo"
MELO_DIR="/opt/melo"
PYTHON_MIN="3.11"

echo "==> Installing system dependencies"
apt-get update -qq
apt-get install -y --no-install-recommends \
  ffmpeg \
  python3 \
  python3-pip \
  curl \
  git \
  ca-certificates

# Install uv (fast Python package manager)
echo "==> Installing uv"
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
ln -sf "$HOME/.local/bin/uv" /usr/local/bin/uv

# Verify Python version
PYTHON_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
if python3 -c "import sys; sys.exit(0 if (sys.version_info >= (3,11)) else 1)"; then
  echo "==> Python $PYTHON_VER OK"
else
  echo "ERROR: Python >= $PYTHON_MIN required (found $PYTHON_VER)"
  exit 1
fi

# Create melo system user
echo "==> Creating system user '$MELO_USER'"
id -u "$MELO_USER" &>/dev/null || useradd --system --home-dir "$MELO_DIR" --shell /usr/sbin/nologin "$MELO_USER"

# Create install directory
echo "==> Setting up $MELO_DIR"
mkdir -p "$MELO_DIR"
chown "$MELO_USER:$MELO_USER" "$MELO_DIR"

# Copy LMS code (run from repo root)
if [[ -f "pyproject.toml" ]]; then
  echo "==> Copying LMS code to $MELO_DIR"
  cp -r lms setup pyproject.toml uv.lock "$MELO_DIR/"
  chown -R "$MELO_USER:$MELO_USER" "$MELO_DIR"
fi

# Install Python deps
echo "==> Installing Python dependencies"
cd "$MELO_DIR"
uv sync --no-dev

# Create .env from template
if [[ ! -f "$MELO_DIR/.env" ]]; then
  echo "==> Creating .env template"
  cat > "$MELO_DIR/.env" <<'ENV'
# Fill in all values before starting the LMS
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
GCP_PROJECT_ID=
KMS_LOCATION=us-central1
KMS_KEY_RING=
KMS_KEY_NAME=
R2_BUCKET=melo-live-segments
R2_ENDPOINT=https://ACCOUNT_ID.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_PUBLIC_BASE=
SHELTER_ID=
LOCAL_DEV=false
LOG_LEVEL=INFO
PRIVACY_FILTER_ENABLED=true
SETUP_API_TOKEN=
# Comma-separated list of allowed dashboard origins, e.g.:
# SETUP_CORS_ORIGINS=https://melo.example.com,http://localhost:5173
SETUP_CORS_ORIGINS=
ENV
  chown "$MELO_USER:$MELO_USER" "$MELO_DIR/.env"
  echo "==> Edit $MELO_DIR/.env before starting the service"
fi

# Install systemd service
echo "==> Installing systemd service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cp "$REPO_ROOT/deploy/melo-lms.service" /etc/systemd/system/
systemctl daemon-reload

echo ""
echo "Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit /opt/melo/.env with your credentials"
echo "  2. sudo systemctl enable melo-lms"
echo "  3. sudo systemctl start melo-lms"
echo "  4. sudo journalctl -u melo-lms -f"
