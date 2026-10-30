"""Read access to lab nodes, and nothing else.

The observe layer is read-only by construction: there is no method that takes a command.
Callers name one of the operations in READ_OPS; the argv for it comes from this file.
A write operation is not refused here, it does not exist (tests/test_readonly.py).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol


class ReadOp(str, Enum):
    BGP_SUMMARY = "bgp_summary"
    BGP_ROUTES = "bgp_routes"
    LINKS = "links"
    ADDRS = "addrs"
    NFT_RULESET = "nft_ruleset"


# vtysh commands are given without the vtysh prefix; the executor adds it per backend.
VTYSH = {
    ReadOp.BGP_SUMMARY: "show bgp summary json",
    ReadOp.BGP_ROUTES: "show bgp ipv4 unicast json",
}
SHELL = {
    ReadOp.LINKS: ["ip", "-j", "-d", "link", "show"],
    ReadOp.ADDRS: ["ip", "-j", "addr", "show"],
    ReadOp.NFT_RULESET: ["nft", "-j", "list", "ruleset"],
}


class ReadError(Exception):
    """The node could not be read. Callers treat the result as unknown, never as healthy."""


@dataclass(frozen=True)
class NodeRef:
    name: str                     # inventory name, e.g. "edge-sc"
    netns: str | None = None      # netns backend
    frr_pathspace: str | None = None
    container: str | None = None  # docker / containerlab backend


class Executor(Protocol):
    def read(self, node: NodeRef, op: ReadOp) -> str: ...


def argv_for(op: ReadOp, vtysh_prefix: list[str]) -> list[str]:
    op = ReadOp(op)  # anything outside the enum raises ValueError
    if op in VTYSH:
        return [*vtysh_prefix, "-c", VTYSH[op]]
    return list(SHELL[op])


def _run(argv: list[str], timeout: float) -> str:
    try:
        res = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ReadError(f"{argv[0]}: {e}") from e
    if res.returncode != 0:
        raise ReadError(f"{' '.join(argv)}: exit {res.returncode}: {res.stderr.strip()[:200]}")
    return res.stdout


class NetnsExecutor:
    """Lab on Linux network namespaces (lab/netns/lab.sh). Needs root."""

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def read(self, node: NodeRef, op: ReadOp) -> str:
        if not node.netns:
            raise ReadError(f"{node.name}: no netns in inventory")
        vtysh = ["vtysh", "-N", node.frr_pathspace] if node.frr_pathspace else ["vtysh"]
        return _run(["ip", "netns", "exec", node.netns, *argv_for(op, vtysh)], self.timeout)


class DockerExecutor:
    """Lab on containerlab (lab/clab). Each node is a container."""

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def read(self, node: NodeRef, op: ReadOp) -> str:
        if not node.container:
            raise ReadError(f"{node.name}: no container in inventory")
        return _run(["docker", "exec", node.container, *argv_for(op, ["vtysh"])], self.timeout)


class FixtureExecutor:
    """Replays captured output: <dir>/<node>.<op>.json. Used by tests and demos."""

    PREFIX = {"edge-sc": "sc", "edge-cust": "cust", "filter": "filter"}
    SUFFIX = {ReadOp.NFT_RULESET: "nft"}

    def __init__(self, directory: str | Path):
        self.dir = Path(directory)

    def read(self, node: NodeRef, op: ReadOp) -> str:
        op = ReadOp(op)
        name = f"{self.PREFIX.get(node.name, node.name)}.{self.SUFFIX.get(op, op.value)}.json"
        path = self.dir / name
        if not path.exists():
            raise ReadError(f"no fixture {path}")
        return path.read_text()
