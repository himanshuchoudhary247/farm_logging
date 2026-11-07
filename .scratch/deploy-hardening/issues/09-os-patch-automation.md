# 09: OS patch automation

**What to build:** The box is on a fresh Amazon Linux 2023 install
(supported until 2029) but has no patch cadence set up -- security updates
only land if someone remembers to SSH in and run `dnf update`. Set up
automated security patching on a schedule.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `dnf-automatic` (or equivalent) configured for security updates on a schedule
- [ ] Reboot policy decided and documented (auto-reboot on kernel update vs. notify-only) -- a surprise reboot of the only instance is itself a real outage risk until ticket 10 lands
- [ ] Verified a dry-run actually applies an available update
