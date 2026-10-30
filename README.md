# driftgate

> Agents may act on infrastructure only within their mandate — and only on verified reality.

**Status:** M1 (lab, observation, read-only audit). Lab-only research prototype.

An agent's mandate is checked against the state its system *believes*. When the database,
the devices and other people's automation drift apart, a well-governed agent does the wrong
thing perfectly within the rules. driftgate puts a gate in front of every write: the target
must be an object the system provably owns, whose recorded state matches a fresh
observation. Drift is classified into a few types; each fixable type has its own named,
deterministic procedure, and everything else goes to a human.

The scenario is a small DDoS-mitigation lab built from public tools (containerlab,
FRRouting, nftables). The pattern is general.

- [SCOPE.md](SCOPE.md) — the one-page scope of v1: state layers, drift classes, invariants,
  lab, evaluation scenarios, milestones.
- [docs/m1-lab-and-observe.md](docs/m1-lab-and-observe.md) — M1: what it does, acceptance
  checks, decisions, how to run.

```console
$ sudo .venv/bin/driftgate audit
cust-1: PASS
  pass    tunnel_present         gre-cust: kind=vxlan 10.0.0.1->10.0.0.2  [edge-sc @ 2026-10-30T18:37:24+00:00]
  pass    tunnel_up              gre-cust: admin_up=True carrier=True  [edge-sc @ 2026-10-30T18:37:24+00:00]
  pass    bgp_established        172.16.0.2: state=Established remote_as=65002  [edge-sc @ 2026-10-30T18:37:24+00:00]
  pass    prefix_received        198.51.100.0/24 via 172.16.0.2 as_path='65002' best=True  [edge-sc @ 2026-10-30T18:37:24+00:00]
  pass    filter_table_present   tables: inet dg  [filter @ 2026-10-30T18:37:24+00:00]
```

Related: [ai2rules](https://github.com/sv-pro/ai2rules) — deterministic execution governance
for agents (what an agent can do). driftgate adds the other half: what it may act on.
