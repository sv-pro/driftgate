"""Audit an asset: can this asset be protected right now? Read-only.

Each check is pass, fail or unknown. Unknown (a node could not be read) is never treated
as pass: an audit passes only when every check passed on an observation it actually made.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .executor import Executor, ReadOp
from .inventory import Asset, Inventory
from .observe import TUNNEL_KINDS, Observation, _utcnow, observe

PASS, FAIL, UNKNOWN = "pass", "fail", "unknown"
DG_TABLE = "inet dg"


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    evidence: str
    node: str
    observed_at: str


@dataclass(frozen=True)
class AuditResult:
    asset: str
    checks: tuple[Check, ...]

    @property
    def passed(self) -> bool:
        return all(c.status == PASS for c in self.checks)


def _check(name: str, obs: Observation, op: ReadOp, attr: str,
           test: Callable[[], tuple[bool, str]]) -> Check:
    if op.value in obs.errors or getattr(obs, attr) is None:
        reason = obs.errors.get(op.value, "not observed")
        return Check(name, UNKNOWN, reason, obs.node, obs.observed_at)
    ok, evidence = test()
    return Check(name, PASS if ok else FAIL, evidence, obs.node, obs.observed_at)


def audit_asset(asset: Asset, inv: Inventory, ex: Executor,
                clock: Callable[[], str] = _utcnow) -> AuditResult:
    sc = observe(ex, inv.node(asset.scrubbing_node),
                 [ReadOp.LINKS, ReadOp.BGP_SUMMARY, ReadOp.BGP_ROUTES], clock)
    flt = observe(ex, inv.node(asset.filter_node), [ReadOp.NFT_RULESET], clock)

    links = {l.name: l for l in sc.links or []}
    peers = {p.peer: p for p in sc.bgp_peers or []}
    tun = links.get(asset.tunnel_if)
    peer = peers.get(asset.peer)

    def tunnel_present():
        if tun is None:
            return False, f"no interface {asset.tunnel_if}"
        return tun.kind in TUNNEL_KINDS, f"{tun.name}: kind={tun.kind} {tun.local}->{tun.remote}"

    def tunnel_up():
        if tun is None:
            return False, f"no interface {asset.tunnel_if}"
        return tun.admin_up and tun.carrier, f"{tun.name}: admin_up={tun.admin_up} carrier={tun.carrier}"

    def bgp_established():
        if peer is None:
            return False, f"no BGP peer {asset.peer}"
        ok = peer.state == "Established" and peer.remote_as == asset.peer_as
        return ok, f"{peer.peer}: state={peer.state} remote_as={peer.remote_as}"

    def prefix_received():
        hits = [r for r in sc.bgp_routes or [] if r.prefix == asset.prefix and r.peer == asset.peer]
        if not hits:
            return False, f"{asset.prefix} not received from {asset.peer}"
        return True, f"{asset.prefix} via {asset.peer} as_path={hits[0].as_path!r} best={hits[0].best}"

    def filter_table():
        tables = flt.nft_tables or []
        return DG_TABLE in tables, f"tables: {', '.join(tables) or 'none'}"

    return AuditResult(asset.name, (
        _check("tunnel_present", sc, ReadOp.LINKS, "links", tunnel_present),
        _check("tunnel_up", sc, ReadOp.LINKS, "links", tunnel_up),
        _check("bgp_established", sc, ReadOp.BGP_SUMMARY, "bgp_peers", bgp_established),
        _check("prefix_received", sc, ReadOp.BGP_ROUTES, "bgp_routes", prefix_received),
        _check("filter_table_present", flt, ReadOp.NFT_RULESET, "nft_tables", filter_table),
    ))
