#!/usr/bin/env bash
# Takes a fresh Amazon Linux 2023 EC2 instance to a running farmer-api.service.
# Idempotent -- safe to re-run on a box that already has some of this done.
#
# Usage: run as ec2-user on the target box, from anywhere:
#   curl -fsSL https://raw.githubusercontent.com/himanshuchoudhary247/farm_logging/dev/deploy/bootstrap.sh | bash
# or, if the repo is already cloned:
#   bash deploy/bootstrap.sh
#
# Does NOT write runtime.env -- that has real credentials and is never
# scripted (see docs/09-aws-and-bedrock.md; prefer an IAM instance role over
# static keys entirely, see ticket 03 in .scratch/deploy-hardening/).
set -euo pipefail

REPO_URL="https://github.com/himanshuchoudhary247/farm_logging.git"
REPO_DIR="$HOME/farmer_chat"
DATA_DIR="$HOME/farmer_chat_data"
BRANCH="dev"
PYTHON_PKG="python3.13"
PYTHON_BIN="/usr/bin/python3.13"

echo "== system packages =="
sudo dnf install -y git nginx python3-pip python3-virtualenv "$PYTHON_PKG" "${PYTHON_PKG}-pip"

echo "== runtime data dir (OUTSIDE the repo clone -- storage.py writes real farmer
     data here at runtime; a repo path means every 'git reset --hard' on a
     redeploy destroys live data, which almost happened writing this script) =="
if [ ! -d "$DATA_DIR" ]; then
  mkdir -p "$DATA_DIR"
  if [ -d "$REPO_DIR/data" ]; then
    # First-ever run on this box: carry over the repo's checked-in seed/example
    # data once. After this, $DATA_DIR is authoritative and the repo's own
    # data/ is never read again (FARMER_CHAT_DATA_DIR is set in the systemd
    # unit below).
    cp -r "$REPO_DIR/data/." "$DATA_DIR/"
  fi
fi

echo "== repo =="
if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" fetch origin "$BRANCH"
  git -C "$REPO_DIR" checkout "$BRANCH"
  git -C "$REPO_DIR" reset --hard "origin/$BRANCH"
else
  git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$REPO_DIR"
fi
# Fresh box: the repo was not cloned yet when $DATA_DIR was created above,
# so seed it now -- only while it is still empty.
if [ -d "$REPO_DIR/data" ] && [ -z "$(ls -A "$DATA_DIR")" ]; then
  cp -r "$REPO_DIR/data/." "$DATA_DIR/"
fi
cd "$REPO_DIR"

echo "== venv (from the lockfile, not requirements.txt's floors -- see docs/06-configuration-reference.md) =="
if [ ! -d .venv ]; then
  "$PYTHON_BIN" -m venv .venv
fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.lock.txt

echo "== ffmpeg (AL2023's default repos don't ship it -- licensing. Use the pip-packaged static
     build instead of curling a raw binary from a third-party URL) =="
FFMPEG_BIN="$(.venv/bin/python -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')"
sudo ln -sf "$FFMPEG_BIN" /usr/local/bin/ffmpeg
sudo chmod +x /usr/local/bin/ffmpeg
ffmpeg -version | head -1

echo "== systemd unit =="
sudo tee /etc/systemd/system/farmer-api.service > /dev/null <<EOF
[Unit]
Description=FarmHerd FastAPI backend
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=$REPO_DIR
EnvironmentFile=-$REPO_DIR/runtime.env
Environment=PYTHONPATH=$REPO_DIR
Environment=FARMER_CHAT_DATA_DIR=$DATA_DIR
ExecStart=$REPO_DIR/.venv/bin/uvicorn services.api_service.main:app --host 0.0.0.0 --port 8001 --workers 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable farmer-api.service

echo "== done =="
echo "Next: create $REPO_DIR/runtime.env (see docs/06-configuration-reference.md for required vars),"
echo "then: sudo systemctl start farmer-api.service"
