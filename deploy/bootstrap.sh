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
# (No virtualenv package: the venv below is made with python3.13 -m venv,
# which is part of Python itself.)
sudo dnf install -y git nginx python3-pip "$PYTHON_PKG" "${PYTHON_PKG}-pip"

echo "== runtime data dir (OUTSIDE the repo clone -- storage.py writes real farmer
     data here at runtime; a repo path means every 'git reset --hard' on a
     redeploy destroys live data, which almost happened writing this script) =="
# Copies the repo clone's data/ into $DATA_DIR, once: only while $DATA_DIR
# is missing or empty. Copied to a temporary folder first and moved into
# place at the end, so a copy that fails halfway never leaves a half-filled
# $DATA_DIR that later runs would take as done. After this, $DATA_DIR is
# authoritative and the repo's own data/ is never read again
# (FARMER_CHAT_DATA_DIR is set in the systemd unit below).
seed_data_dir() {
  if [ ! -d "$REPO_DIR/data" ]; then
    return 0
  fi
  if [ -d "$DATA_DIR" ] && [ -n "$(ls -A "$DATA_DIR")" ]; then
    return 0
  fi
  local tmp="${DATA_DIR}.seeding"
  rm -rf "$tmp"
  mkdir -p "$tmp"
  cp -a "$REPO_DIR/data/." "$tmp/"
  rm -rf "$DATA_DIR"
  mv "$tmp" "$DATA_DIR"
  echo "seeded $DATA_DIR from $REPO_DIR/data"
}

# Before the repo update: a box that ran without FARMER_CHAT_DATA_DIR has its
# real farmer data inside the clone -- it is moved out before the
# 'git reset --hard' below can overwrite it.
seed_data_dir

echo "== repo =="
if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" fetch origin "$BRANCH"
  git -C "$REPO_DIR" checkout "$BRANCH"
  git -C "$REPO_DIR" reset --hard "origin/$BRANCH"
else
  git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$REPO_DIR"
fi
# After the clone: on a fresh box there was no clone yet above, so the
# checked-in seed data is copied now. Does nothing when $DATA_DIR already
# has data.
seed_data_dir
mkdir -p "$DATA_DIR"
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
