# driftgate

> Agents may act on infrastructure only within their mandate — and only on verified reality.

**Status:** scope only. Nothing is implemented yet. Lab-only research prototype.

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

Related: [ai2rules](https://github.com/sv-pro/ai2rules) — deterministic execution governance
for agents (what an agent can do). driftgate adds the other half: what it may act on.
