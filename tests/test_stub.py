import unittest

from tests._bootstrap import NondetConsensusError, World, addr, expect_raises, gl, path_of
from tests import genlayer_stub as stub
from tests.genlayer_stub.storage import DynArray, TreeMap, u256

PROBE = '''
from genlayer import *
from dataclasses import dataclass


@allow_storage
@dataclass
class Row:
    name: str
    qty: u256
    tags: DynArray[str]


def capture_leader(box):
    def leader_fn() -> str:
        return box.read()
    def validator_fn(res) -> bool:
        return True
    return gl.vm.run_nondet_unsafe(leader_fn, validator_fn)


class Probe(gl.Contract):
    rows: TreeMap[str, Row]
    names: DynArray[str]
    counts: TreeMap[str, u256]
    owner: str
    total: u256

    def __init__(self):
        self.owner = str(gl.message.sender_address).lower()
        self.total = u256(0)

    def read(self) -> str:
        return self.owner

    @gl.public.write
    def add(self, key: str) -> str:
        row = Row(name=key, qty=u256(1), tags=[])
        self.rows[key] = row
        row.qty = u256(99)
        self.names.append(key)
        return key

    @gl.public.view
    def qty(self, key: str) -> int:
        return int(self.rows.get(key).qty)

    @gl.public.write
    def bad_int(self, key: str) -> str:
        self.rows[key] = Row(name=key, qty=5, tags=[])
        return key

    @gl.public.write
    def bad_map_assign(self) -> str:
        self.counts = {}
        return "x"

    @gl.public.write
    def bad_len(self) -> int:
        return len(self.counts)

    @gl.public.write
    def bad_in(self, key: str) -> int:
        return 1 if key in self.counts else 0

    @gl.public.write
    def bad_get_default(self, key: str) -> int:
        return int(self.counts.get(key, 0))

    @gl.public.write
    def capture_self(self) -> str:
        return capture_leader(self)

    @gl.public.view
    def sneaky_view(self) -> int:
        self.total = u256(int(self.total) + 1)
        return 1

    @gl.public.write
    def call_sneaky(self, other: str) -> int:
        return gl.get_contract_at(Address(other)).view().sneaky_view()

    @gl.public.write
    def pay(self, who: str) -> str:
        gl.get_contract_at(Address(who)).emit_transfer(value=u256(1), on="accepted")
        return "x"

    @gl.public.write
    def web_outside(self) -> str:
        return gl.nondet.web.render("https://example.com/a", mode="text")

    @gl.public.write
    def ping_other(self, other: str, key: str) -> str:
        gl.get_contract_at(Address(other)).emit(on="accepted").add(key)
        if key == "boom":
            raise Exception("boom")
        return key

    @gl.public.write
    def comparative_no_principle(self) -> str:
        def fn() -> str:
            return "x"
        return gl.eq_principle.prompt_comparative(fn)

    @gl.public.view
    def read_unset(self) -> int:
        return len(self.names)

    @gl.public.view
    def read_total(self) -> int:
        return int(self.total)

    @gl.public.write
    def explode(self) -> str:
        raise Exception("kaboom")

    @gl.public.write
    def emit_explode(self, other: str) -> str:
        self.names.append("sent")
        gl.get_contract_at(Address(other)).emit(on="accepted").explode()
        return "sent"
'''


class StubTests(unittest.TestCase):
    def setUp(self):
        import os
        import tempfile
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "probe.py")
        with open(self.path, "w") as fh:
            fh.write(PROBE)
        self.w = World()
        self.a = self.w.deploy(self.path, "Probe", addr(1), key="probe_a")
        self.b = self.w.deploy(self.path, "Probe", addr(2), key="probe_b")

    def test_containers_are_zero_initialised(self):
        inst = self.w.instance(self.a)
        self.assertIsInstance(inst.rows, TreeMap)
        self.assertIsInstance(inst.names, DynArray)
        self.assertEqual(self.w.view(self.a, "read_unset"), 0)

    def test_scalar_fields_are_not_zero_initialised(self):
        import os
        src = PROBE.replace("        self.total = u256(0)\n", "")
        path = os.path.join(self.dir, "probe2.py")
        with open(path, "w") as fh:
            fh.write(src)
        w = World()
        h = w.deploy(path, "Probe", addr(1), key="probe2")
        expect_raises(lambda: w.view(h, "read_total"), "total")

    def test_stored_objects_are_copied(self):
        self.w.tx(addr(9), self.a, "add", "k")
        self.assertEqual(self.w.view(self.a, "qty", "k"), 1)

    def test_bare_int_into_u256_field_is_rejected(self):
        expect_raises(lambda: self.w.tx(addr(9), self.a, "bad_int", "k"), "u256")

    def test_u256_range(self):
        expect_raises(lambda: u256(-1), "out of range")
        expect_raises(lambda: u256(2 ** 256), "out of range")

    def test_treemap_assignment_and_unproven_api_are_rejected(self):
        expect_raises(lambda: self.w.tx(addr(9), self.a, "bad_map_assign"), "TreeMap")
        expect_raises(lambda: self.w.tx(addr(9), self.a, "bad_len"), "len(TreeMap)")
        expect_raises(lambda: self.w.tx(addr(9), self.a, "bad_in", "k"), "'in' on a TreeMap")
        expect_raises(lambda: self.w.tx(addr(9), self.a, "bad_get_default", "k"), None)

    def test_self_cannot_be_captured_by_nondet_blocks(self):
        expect_raises(lambda: self.w.tx(addr(9), self.a, "capture_self"), "must not capture self")

    def test_view_called_cross_contract_must_not_mutate(self):
        expect_raises(lambda: self.w.tx(addr(9), self.a, "call_sneaky", str(self.b)), "mutated")
        expect_raises(lambda: self.w.view(self.b, "sneaky_view"), "mutated")

    def test_emit_transfer_with_on_is_rejected(self):
        expect_raises(lambda: self.w.tx(addr(9), self.a, "pay", str(addr(5))), "takes only value")

    def test_web_access_outside_nondet_is_rejected(self):
        expect_raises(lambda: self.w.tx(addr(9), self.a, "web_outside"), "outside a non-deterministic block")

    def test_emit_runs_after_success_with_emitter_as_sender(self):
        self.w.tx(addr(9), self.a, "ping_other", str(self.b), "k1")
        self.assertEqual(self.w.view(self.b, "qty", "k1"), 1)
        self.assertEqual(self.w.failed_emits, [])
        self.assertEqual(self.w.delivered[-1]["sender"], str(self.a))

    def test_emit_is_dropped_when_the_transaction_reverts(self):
        expect_raises(lambda: self.w.tx(addr(9), self.a, "ping_other", str(self.b), "boom"), "boom")
        expect_raises(lambda: self.w.view(self.b, "qty", "boom"), None)
        self.assertEqual(self.w.delivered, [])

    def test_failed_emit_is_recorded_and_does_not_undo_the_caller(self):
        self.assertEqual(self.w.tx(addr(9), self.a, "emit_explode", str(self.b)), "sent")
        self.assertEqual(self.w.view(self.a, "read_unset"), 1)
        self.assertEqual(len(self.w.failed_emits), 1)
        self.assertIn("kaboom", self.w.failed_emits[0]["error"])

    def test_prompt_comparative_requires_a_principle(self):
        expect_raises(lambda: self.w.tx(addr(9), self.a, "comparative_no_principle"), "principle")

    def test_rollback_restores_every_contract(self):
        self.w.tx(addr(9), self.a, "add", "keep")
        expect_raises(lambda: self.w.tx(addr(9), self.a, "ping_other", str(self.b), "boom"), "boom")
        self.assertEqual(self.w.view(self.a, "read_unset"), 1)

    def test_validator_disagreement_fails_consensus(self):
        gl.vm.validators = 5
        calls = []

        def leader_fn():
            return "A"

        def validator_fn(res):
            calls.append(1)
            return len(calls) <= 2

        with self.assertRaises(NondetConsensusError):
            gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
        self.assertEqual(len(calls), 5)


if __name__ == "__main__":
    unittest.main()
