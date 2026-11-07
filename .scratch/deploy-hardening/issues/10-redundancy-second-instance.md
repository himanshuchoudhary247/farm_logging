# 10: Redundancy -- second instance behind a load balancer

**What to build:** The pilot runs on exactly one instance; a crash or reboot
is a full outage until systemd restarts it. Stand up a second instance
(using the bootstrap script from ticket 02, so it's identical to the first)
behind a load balancer, with the TLS/domain layer from ticket 04 terminating
at the load balancer instead of nginx on a single box.

**Blocked by:** 02 (Reproducible bootstrap script), 04 (HTTPS via domain + nginx)

**Status:** ready-for-agent

- [ ] A second instance stood up via the bootstrap script, serving identical traffic
- [ ] A load balancer (ALB) in front of both, health-checking `/healthz`
- [ ] TLS terminates at the load balancer (replacing the single box's nginx TLS role)
- [ ] One instance can be stopped manually with zero visible downtime to a caller
