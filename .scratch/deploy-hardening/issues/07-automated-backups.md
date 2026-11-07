# 07: Automated backups for data/

**What to build:** Farmer data (animals, health logs, appointments,
consultations, farmers.json) lives as JSON files on one EBS volume with no
backup schedule. A disk failure or bad deploy loses it permanently. Set up
scheduled EBS snapshots and prove a restore actually works, not just that
snapshots exist.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Scheduled EBS snapshots of the root volume (e.g. AWS Backup or a lifecycle policy), retention documented
- [ ] A documented restore drill has actually been run once: snapshot -> new volume -> attach -> verify the JSON data reads back correctly
- [ ] RPO (how much data could be lost between snapshots) is stated explicitly, not assumed
