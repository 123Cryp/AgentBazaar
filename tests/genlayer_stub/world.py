"""
A tiny chain for the offline tests: several contracts, a controllable clock, transactional rollback, emitted
cross-contract messages, and a native-value ledger.

    world = World()
    reg = world.deploy("contracts/agent_registry.py", "AgentRegistry", OWNER)
    world.tx(USER, reg, "register_agent", "Name", "https://...", "caps")
    world.view(reg, "get_agent", "AG-1")

A reverting transaction leaves no state change in ANY contract and drops every message it emitted. Value attached to
a reverting payable call stays in the contract with no record (tracked in world.stuck), like the live network.
"""
import copy
import importlib.util
import os
import sys
from collections import defaultdict

from . import install, reset
from .runtime import _calldata, gl
from .storage import Address, u256

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
START = 1_800_000_000
GEN = 10 ** 18


def addr(n):
    return Address("0x" + format(n, "040x"))


class Handle:
    def __init__(self, address, name, module):
        self.address = address
        self.name = name
        self.module = module

    def __str__(self):
        return self.address


class World:
    def __init__(self, validators=5, start=START):
        install()
        reset()
        gl.vm.validators = validators
        self.now = start
        self.handles = {}
        self.balance = defaultdict(int)
        self.stuck = defaultdict(int)
        self.wallets = defaultdict(int)
        self.failed_emits = []
        self.delivered = []
        self.txs = 0
        self._next = 0x1000
        self._modules = {}

    def advance(self, seconds):
        self.now += seconds

    def load(self, path, key=None):
        full = path if os.path.isabs(path) else os.path.join(ROOT, path)
        name = "_ab_%d_%s" % (id(self), key or os.path.basename(full)[:-3])
        if name in self._modules:
            return self._modules[name]
        spec = importlib.util.spec_from_file_location(name, full)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        if hasattr(module, "_now"):
            module._now = lambda: self.now
        self._modules[name] = module
        return module

    def deploy(self, path, class_name, deployer, *args, key=None):
        module = self.load(path, key)
        address = str(addr(self._next))
        self._next += 1
        gl.message.sender_address = Address(deployer)
        gl.message.value = u256(0)
        gl.stack[:] = [address]
        try:
            instance = getattr(module, class_name)(*args)
        finally:
            gl.stack[:] = []
        gl.contracts[address] = instance
        handle = Handle(address, class_name, module)
        self.handles[address] = handle
        return handle

    def instance(self, handle):
        return gl.contracts[str(handle)]

    def _snapshot(self):
        return {a: copy.deepcopy({k: v for k, v in c.__dict__.items() if not k.startswith("_gl_")}) for a, c in gl.contracts.items()}

    def _restore(self, snap):
        for a, state in snap.items():
            c = gl.contracts[a]
            keep = {k: v for k, v in c.__dict__.items() if k.startswith("_gl_")}
            c.__dict__.clear()
            c.__dict__.update(keep)
            c.__dict__.update(state)

    def _apply_transfers(self):
        for to, amount, source in gl.transfers:
            if source:
                self.balance[source] -= amount
            if to in gl.contracts:
                self.balance[to] += amount
            else:
                self.wallets[to] += amount
        gl.transfers.clear()

    def _call(self, sender, address, method, args, value):
        instance = gl.contracts[address]
        fn = getattr(type(instance), method, None)
        if fn is None or getattr(fn, "_gl_kind", None) != "write":
            raise AssertionError("[stub] " + method + " is not a write method")
        if value and not getattr(fn, "_gl_payable", False):
            raise AssertionError("[stub] " + method + " is not payable but value was attached")
        gl.message.sender_address = Address(sender)
        gl.message.value = u256(value)
        gl.stack[:] = [address]
        try:
            return getattr(instance, method)(*args)
        finally:
            gl.stack[:] = []

    def tx(self, sender, handle, method, *args, value=0):
        address = str(handle)
        before = self._snapshot()
        gl.emitted.clear()
        gl.transfers.clear()
        try:
            result = self._call(sender, address, method, _calldata(list(args), "tx arguments"), value)
        except BaseException:
            self._restore(before)
            gl.emitted.clear()
            gl.transfers.clear()
            self.balance[address] += value
            self.stuck[address] += value
            raise
        self.balance[address] += value
        self._apply_transfers()
        self.txs += 1
        self._flush_emits()
        return _calldata(result, "tx result")

    def _flush_emits(self):
        while gl.emitted:
            e = gl.emitted.pop(0)
            before = self._snapshot()
            mark = len(gl.emitted)
            gl.transfers.clear()
            try:
                self._call(e["sender"], e["target"], e["method"], e["args"], 0)
            except BaseException as err:
                self._restore(before)
                del gl.emitted[mark:]
                gl.transfers.clear()
                self.failed_emits.append({"target": e["target"], "method": e["method"], "error": str(err), "sender": e["sender"]})
                continue
            self._apply_transfers()
            self.delivered.append(e)

    def view(self, handle, method, *args):
        address = str(handle)
        instance = gl.contracts[address]
        fn = getattr(type(instance), method, None)
        if fn is None or getattr(fn, "_gl_kind", None) != "view":
            raise AssertionError("[stub] " + method + " is not a view method")
        before = self._snapshot()
        gl.stack[:] = [address]
        try:
            result = getattr(instance, method)(*_calldata(list(args), "view arguments"))
        finally:
            gl.stack[:] = []
        assert self._snapshot() == before, "view " + method + " mutated state"
        return _calldata(result, "view result")
