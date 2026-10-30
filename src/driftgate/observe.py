"""Observation: what is actually on a node, normalised and timestamped.

Parsers take the raw JSON the tools print and keep only what driftgate reasons about.
A part that cannot be read is recorded as an error, never as an empty (healthy-looking) value.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Callable

from .executor import Executor, NodeRef, ReadError, ReadOp

TUNNEL_KINDS = {"gre", "gretap", "vxlan", "ipip"}


@dataclass(frozen=True)
class BgpPeer:
    peer: str
    remote_as: int
    state: str
    prefixes_received: int
    description: str = ""


@dataclass(frozen=True)
class BgpRoute:
    prefix: str
    peer: str            # "(unspec)" for locally originated
    as_path: str
    best: bool


@dataclass(frozen=True)
class Link:
    name: str
    kind: str            # veth, vxlan, gre, ... ("" for loopback)
    admin_up: bool       # UP flag
    carrier: bool        # LOWER_UP flag
    local: str = ""      # tunnel endpoints, if a tunnel
    remote: str = ""


@dataclass(frozen=True)
class NftRule:
    family: str
    table: str
    chain: str
    handle: int
    comment: str


@dataclass
class Observation:
    node: str
    observed_at: str                         # ISO 8601, UTC
    bgp_peers: list[BgpPeer] | None = None   # None = not read (see errors)
    bgp_routes: list[BgpRoute] | None = None
    links: list[Link] | None = None
    addrs: dict[str, list[str]] | None = None
    nft_tables: list[str] | None = None      # "family name"
    nft_rules: list[NftRule] | None = None
    errors: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)


# --- parsers -----------------------------------------------------------------

def parse_bgp_summary(raw: str) -> list[BgpPeer]:
    peers = json.loads(raw).get("ipv4Unicast", {}).get("peers", {})
    return [
        BgpPeer(peer=ip, remote_as=int(p.get("remoteAs", 0)), state=p.get("state", "Unknown"),
                prefixes_received=int(p.get("pfxRcd", 0)), description=p.get("desc", ""))
        for ip, p in sorted(peers.items())
    ]


def parse_bgp_routes(raw: str) -> list[BgpRoute]:
    out = []
    for prefix, paths in sorted(json.loads(raw).get("routes", {}).items()):
        for p in paths:
            out.append(BgpRoute(prefix=prefix, peer=p.get("peerId", ""), as_path=p.get("path", ""),
                                best=bool(p.get("bestpath", False))))
    return out


def _repair_ip_json(raw: str) -> str:
    # Some iproute2 builds (seen: Ubuntu iproute2-6.1.0 with the "fan" patch) print
    # `"remote":"10.0.0.2"fan-map ,` inside `ip -j -d link` for vxlan, which is not JSON.
    # Remove exactly that artefact; anything else malformed still fails loudly.
    return raw.replace('"fan-map ,', '",').replace("fan-map ,", ",")


def parse_links(raw: str) -> list[Link]:
    out = []
    for item in json.loads(_repair_ip_json(raw)):
        info = item.get("linkinfo", {}) or {}
        data = info.get("info_data", {}) or {}
        flags = set(item.get("flags", []))
        out.append(Link(name=item["ifname"], kind=info.get("info_kind", "") or "",
                        admin_up="UP" in flags, carrier="LOWER_UP" in flags,
                        local=str(data.get("local", "")), remote=str(data.get("remote", ""))))
    return out


def parse_addrs(raw: str) -> dict[str, list[str]]:
    return {i["ifname"]: [f"{a['local']}/{a['prefixlen']}" for a in i.get("addr_info", [])]
            for i in json.loads(raw)}


def parse_nft(raw: str) -> tuple[list[str], list[NftRule]]:
    tables, rules = [], []
    for obj in json.loads(raw).get("nftables", []):
        if "table" in obj:
            t = obj["table"]
            tables.append(f"{t['family']} {t['name']}")
        elif "rule" in obj:
            r = obj["rule"]
            rules.append(NftRule(family=r["family"], table=r["table"], chain=r["chain"],
                                 handle=int(r["handle"]), comment=r.get("comment", "")))
    return tables, rules


# --- observing a node --------------------------------------------------------

def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def observe(ex: Executor, node: NodeRef, ops: list[ReadOp],
            clock: Callable[[], str] = _utcnow) -> Observation:
    obs = Observation(node=node.name, observed_at=clock())
    for op in ops:
        try:
            raw = ex.read(node, op)
            if op is ReadOp.BGP_SUMMARY:
                obs.bgp_peers = parse_bgp_summary(raw)
            elif op is ReadOp.BGP_ROUTES:
                obs.bgp_routes = parse_bgp_routes(raw)
            elif op is ReadOp.LINKS:
                obs.links = parse_links(raw)
            elif op is ReadOp.ADDRS:
                obs.addrs = parse_addrs(raw)
            elif op is ReadOp.NFT_RULESET:
                obs.nft_tables, obs.nft_rules = parse_nft(raw)
        except (ReadError, ValueError, KeyError) as e:   # JSONDecodeError is a ValueError
            obs.errors[op.value] = str(e)[:300]
    return obs
