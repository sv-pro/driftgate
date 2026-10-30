"""driftgate CLI (M1: read-only).

  driftgate observe <node> [--backend netns|docker|fixtures:<dir>] [--inventory FILE]
  driftgate audit [<asset>] [--backend ...] [--inventory FILE] [--json]

Exit code of `audit`: 0 if every audited asset passed, 1 if any check failed or was unknown.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from .audit import audit_asset
from .executor import DockerExecutor, Executor, FixtureExecutor, NetnsExecutor, ReadOp
from .inventory import load_inventory
from .observe import observe


def make_executor(spec: str) -> Executor:
    if spec == "netns":
        return NetnsExecutor()
    if spec == "docker":
        return DockerExecutor()
    if spec.startswith("fixtures:"):
        return FixtureExecutor(spec.split(":", 1)[1])
    raise SystemExit(f"unknown backend {spec!r}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="driftgate")
    ap.add_argument("--inventory", default="lab/inventory.toml")
    ap.add_argument("--backend", default="netns")
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("observe", help="observe one node")
    o.add_argument("node")
    a = sub.add_parser("audit", help="audit assets (all if none named)")
    a.add_argument("asset", nargs="?")
    a.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    inv = load_inventory(args.inventory)
    ex = make_executor(args.backend)

    if args.cmd == "observe":
        print(observe(ex, inv.node(args.node), list(ReadOp)).to_json())
        return 0

    names = [args.asset] if args.asset else sorted(inv.assets)
    results = [audit_asset(inv.assets[n], inv, ex) for n in names]
    if args.json:
        print(json.dumps([{"asset": r.asset, "passed": r.passed,
                           "checks": [asdict(c) for c in r.checks]} for r in results], indent=2))
    else:
        for r in results:
            print(f"{r.asset}: {'PASS' if r.passed else 'NOT PASSED'}")
            for c in r.checks:
                print(f"  {c.status:7} {c.name:22} {c.evidence}  [{c.node} @ {c.observed_at}]")
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
