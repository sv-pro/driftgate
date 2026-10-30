# M1 — lab, observation and audit (read-only)

Status: implemented and run in a sandbox (netns lab, FRRouting 8.4.4, VXLAN tunnel).
The containerlab topology and the GRE path are written but not yet run.

## What M1 delivers

- A lab that comes up and goes down with one command, under a lease (`lab/netns/lab.sh`).
- Observation of a node: BGP peers and routes, links and tunnels, addresses, nftables
  ruleset, normalised and timestamped (`driftgate observe <node>`).
- An audit of an asset: can it be protected right now? (`driftgate audit`).
- Recorded state as a TOML inventory (`lab/inventory.toml`). Nodes not in it are outside
  the model.

## Acceptance checks (each is a test)

| # | Requirement | Test |
|---|---|---|
| 1 | The observe layer cannot write: no method takes a command; every operation is a read | `test_readonly.py` (3 tests + one per operation) |
| 2 | A node that cannot be read, or prints malformed output, makes its checks `unknown`, and `unknown` never passes | `test_unreadable_node_is_unknown_never_pass`, `test_malformed_output_is_unknown` |
| 3 | The audit passes on a healthy lab | `test_audit_passes_on_healthy_lab`, `test_lab_live.py` |
| 4 | The audit fails when the customer tunnel is down (tunnel, BGP and prefix checks) | `test_audit_fails_when_tunnel_is_down` |
| 5 | Every check carries its evidence, the node and the observation time | output of `driftgate audit`, `Check` fields |
| 6 | Nodes outside the inventory are not addressable | `test_nodes_outside_the_model_are_not_addressable` |
| 7 | The lab lease: reap destroys an expired lab, and a lab without a lease | run by hand (below); not yet automated |

Fixtures are captured from the running lab, not written by hand: healthy, and with the
scrubbing-edge tunnel set down (BGP fell to `Active` within the 9 s hold time).

## Decisions

- **Closed read operations.** `ReadOp` lists the five reads; the argv for each lives in
  `executor.py`. An executor has one public method, `read(node, op)`. Writing is not
  refused by a check, it has no code path (the M1 form of ABSENT).
- **Unknown is not healthy.** A parser error or an unreachable node is recorded per
  operation in `Observation.errors`; the audit reports `unknown`, and only all-`pass` passes.
- **VXLAN fallback.** The scenario means GRE. Kernels without `ip_gre` (this sandbox) use
  `DG_TUNNEL=vxlan`, the same L3 overlay. The audit accepts both tunnel kinds.
- **Real-world output is not always valid JSON.** Ubuntu's iproute2 6.1 prints
  `"remote":"10.0.0.2"fan-map ,` for VXLAN links. The parser removes exactly that artefact;
  any other malformed output still fails, and becomes `unknown`.
- **The lease is written before the lab is built**, so a crash half-way leaves a lease to
  reap, never nodes without one. `reap` treats lab nodes without a lease as expired.
- **Two backends, one inventory.** `netns` (tested) and `docker` for containerlab
  (written, not yet run); `fixtures:<dir>` replays captured output for tests and demos.

## Run

```bash
sudo apt-get install -y frr nftables        # FRRouting 8.x from the distribution
make venv
make lab-up TTL=2h                           # DG_TUNNEL=vxlan if the kernel has no ip_gre
make audit
make test                                    # sudo .venv/bin/pytest -m lab for the live test
make lab-down
```

Lease checks done by hand in the sandbox: not expired → nothing happens; expired → lab
torn down; lease file removed while nodes exist → lab torn down; no FRR processes left.

## Not in M1

Drift classes, ownership tags, recorded vs observed diff (M2); any write (M3); the agent (M4).
