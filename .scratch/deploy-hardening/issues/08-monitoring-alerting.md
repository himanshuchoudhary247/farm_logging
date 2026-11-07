# 08: Monitoring + alerting on uptime

**What to build:** Nothing currently tells anyone the service is down except
manually checking. Add a health check that runs on a schedule and pages
someone (email/SNS) when `/healthz` fails or the instance itself stops/fails
its EC2 status checks.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] A scheduled check (CloudWatch Synthetics canary, or EventBridge + Lambda, or equivalent) hits `/healthz` on an interval
- [ ] A CloudWatch alarm on the instance's own status-check metric
- [ ] Both alarms notify a real channel (SNS -> email at minimum) someone actually monitors
- [ ] Verified by deliberately stopping the service and confirming the alert actually fires
