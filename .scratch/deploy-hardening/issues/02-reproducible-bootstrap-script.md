# 02: Reproducible server bootstrap script

**What to build:** Standing up the pilot box (`farmer-chat-deploy-al2023`) took
a long sequence of manual SSH one-liners -- dnf installs, venv creation,
`ffmpeg` via an ad-hoc pip-package symlink, systemd unit authoring. None of
it is captured anywhere rerunnable. Write one versioned `deploy/bootstrap.sh`
that takes a fresh Amazon Linux 2023 box from nothing to a running
`farmer-api.service`, using the lockfile from ticket 01 instead of floor-pinned
`requirements.txt`.

**Blocked by:** 01 (Pin dependencies with a lockfile)

**Status:** ready-for-agent

- [ ] `deploy/bootstrap.sh` installs git/nginx/python tooling, clones the repo, builds the venv from the lockfile, installs `ffmpeg` via a documented (not ad-hoc) method, writes and enables the systemd unit
- [ ] Running it against a brand-new AL2023 instance produces a working `farmer-api.service` with no manual intervention beyond supplying `runtime.env`
- [ ] The script is idempotent -- safe to re-run on a box that already has some of this done
