"""Parsers and audit against output captured from the real netns lab (FRR 8.4, iproute2 6.1).

Fixtures:
  lab-vxlan/              healthy lab, tunnel as VXLAN (sandbox kernel had no ip_gre)
  lab-vxlan-tunnel-down/  same lab, edge-sc tunnel set down; BGP fell back to Active
"""

from pathlib import Path

import pytest

from driftgate.audit import FAIL, PASS, UNKNOWN, audit_asset
from driftgate.executor import FixtureExecutor, ReadOp
from driftgate.inventory import load_inventory
from driftgate.observe import observe, parse_links

ROOT = Path(__file__).resolve().parents[1]
FIX = Path(__file__).parent / "fixtures"
CLOCK = lambda: "2026-10-30T18:35:00+00:00"  # noqa: E731


@pytest.fixture
def inv():
    return load_inventory(ROOT / "lab" / "inventory.toml")


def statuses(result):
    return {c.name: c.status for c in result.checks}


def test_observe_healthy_scrubbing_edge(inv):
    obs = observe(FixtureExecutor(FIX / "lab-vxlan"), inv.node("edge-sc"),
                  [ReadOp.BGP_SUMMARY, ReadOp.BGP_ROUTES, ReadOp.LINKS, ReadOp.ADDRS], CLOCK)
    assert obs.errors == {}
    assert obs.observed_at == CLOCK()
    (peer,) = obs.bgp_peers
    assert (peer.peer, peer.remote_as, peer.state, peer.prefixes_received) == ("172.16.0.2", 65002, "Established", 1)
    assert {r.prefix for r in obs.bgp_routes} == {"10.255.0.1/32", "198.51.100.0/24"}
    tun = next(l for l in obs.links if l.name == "gre-cust")
    assert (tun.kind, tun.local, tun.remote, tun.admin_up, tun.carrier) == ("vxlan", "10.0.0.1", "10.0.0.2", True, True)
    assert obs.addrs["gre-cust"] == ["172.16.0.1/30"]


def test_iproute2_fan_map_artefact_is_repaired():
    raw = (FIX / "lab-vxlan" / "sc.links.json").read_text()
    assert "fan-map" in raw                         # the captured output really is broken JSON
    assert any(l.remote == "10.0.0.2" for l in parse_links(raw))


def test_audit_passes_on_healthy_lab(inv):
    res = audit_asset(inv.assets["cust-1"], inv, FixtureExecutor(FIX / "lab-vxlan"), CLOCK)
    assert res.passed, statuses(res)


def test_audit_fails_when_tunnel_is_down(inv):
    res = audit_asset(inv.assets["cust-1"], inv, FixtureExecutor(FIX / "lab-vxlan-tunnel-down"), CLOCK)
    st = statuses(res)
    assert not res.passed
    assert st["tunnel_present"] == PASS
    assert st["tunnel_up"] == FAIL
    assert st["bgp_established"] == FAIL
    assert st["prefix_received"] == FAIL


def test_unreadable_node_is_unknown_never_pass(inv, tmp_path):
    # Only the scrubbing edge was captured; the filter node cannot be read.
    for f in (FIX / "lab-vxlan").glob("sc.*.json"):
        (tmp_path / f.name).write_text(f.read_text())
    res = audit_asset(inv.assets["cust-1"], inv, FixtureExecutor(tmp_path), CLOCK)
    assert statuses(res)["filter_table_present"] == UNKNOWN
    assert not res.passed


def test_malformed_output_is_unknown(inv, tmp_path):
    for f in (FIX / "lab-vxlan").glob("*.json"):
        (tmp_path / f.name).write_text(f.read_text())
    (tmp_path / "sc.bgp_summary.json").write_text("% Unknown command")
    res = audit_asset(inv.assets["cust-1"], inv, FixtureExecutor(tmp_path), CLOCK)
    assert statuses(res)["bgp_established"] == UNKNOWN
    assert not res.passed


def test_nodes_outside_the_model_are_not_addressable(inv):
    with pytest.raises(KeyError):
        inv.node("sw1")
