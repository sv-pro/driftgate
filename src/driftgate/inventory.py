"""Recorded state: what driftgate believes exists. In M1 this is a TOML file; later a database.

Nodes not listed here are outside the model (drift class E): driftgate never writes to them.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .executor import NodeRef


@dataclass(frozen=True)
class Asset:
    name: str
    prefix: str
    scrubbing_node: str
    tunnel_if: str
    peer: str
    peer_as: int
    filter_node: str


@dataclass(frozen=True)
class Inventory:
    nodes: dict[str, NodeRef]
    assets: dict[str, Asset]

    def node(self, name: str) -> NodeRef:
        if name not in self.nodes:
            raise KeyError(f"{name} is not in the inventory (outside the model)")
        return self.nodes[name]


def load_inventory(path: str | Path) -> Inventory:
    data = tomllib.loads(Path(path).read_text())
    nodes = {name: NodeRef(name=name, netns=n.get("netns"), frr_pathspace=n.get("frr_pathspace"),
                           container=n.get("container"))
             for name, n in data.get("nodes", {}).items()}
    assets = {}
    for name, a in data.get("assets", {}).items():
        asset = Asset(name=name, prefix=a["prefix"], scrubbing_node=a["scrubbing_node"],
                      tunnel_if=a["tunnel_if"], peer=a["peer"], peer_as=int(a["peer_as"]),
                      filter_node=a["filter_node"])
        for ref in (asset.scrubbing_node, asset.filter_node):
            if ref not in nodes:
                raise ValueError(f"asset {name} refers to unknown node {ref}")
        assets[name] = asset
    return Inventory(nodes=nodes, assets=assets)
