"""M1 invariant: the observe layer cannot write. Writes are not refused, they do not exist."""

import inspect

import pytest

from driftgate import executor
from driftgate.executor import SHELL, VTYSH, ReadOp, argv_for

WRITE_WORDS = {"add", "del", "delete", "set", "flush", "insert", "replace", "configure",
               "conf", "no", "clear", "write", "copy", "reload", "kill", "restart"}


@pytest.mark.parametrize("op", list(ReadOp))
def test_every_operation_is_a_read(op):
    argv = argv_for(op, ["vtysh"])
    words = set(" ".join(argv).lower().split())
    assert not (words & WRITE_WORDS), argv
    assert ("show" in words) or ("list" in words), argv


def test_operation_table_is_closed():
    assert set(VTYSH) | set(SHELL) == set(ReadOp)
    with pytest.raises(ValueError):
        argv_for("ip link set gre-cust down", ["vtysh"])


def test_no_executor_accepts_a_command():
    for cls in (executor.NetnsExecutor, executor.DockerExecutor, executor.FixtureExecutor):
        public = [n for n, _ in inspect.getmembers(cls, inspect.isfunction) if not n.startswith("_")]
        assert public == ["read"], (cls.__name__, public)
        params = list(inspect.signature(cls.read).parameters)
        assert params == ["self", "node", "op"], (cls.__name__, params)
