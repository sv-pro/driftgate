"""Against the running netns lab. Skipped unless root and `lab/netns/lab.sh up` has been run.

  sudo DG_TUNNEL=vxlan lab/netns/lab.sh up && sudo .venv/bin/pytest -m lab
"""

import os
import subprocess
from pathlib import Path

import pytest

from driftgate.audit import audit_asset
from driftgate.executor import NetnsExecutor, ReadOp
from driftgate.inventory import load_inventory
from driftgate.observe import observe

ROOT = Path(__file__).resolve().parents[1]


def _lab_up() -> bool:
    if os.geteuid() != 0:
        return False
    out = subprocess.run(["ip", "netns", "list"], capture_output=True, text=True).stdout
    return "dg-sc" in out


pytestmark = [pytest.mark.lab, pytest.mark.skipif(not _lab_up(), reason="netns lab not running")]


def test_live_observe_and_audit():
    inv = load_inventory(ROOT / "lab" / "inventory.toml")
    obs = observe(NetnsExecutor(), inv.node("edge-sc"), list(ReadOp))
    assert obs.errors.keys() <= {"nft_ruleset"}   # edge-sc has no nftables ruleset of its own
    res = audit_asset(inv.assets["cust-1"], inv, NetnsExecutor())
    assert res.passed, [(c.name, c.status, c.evidence) for c in res.checks]
