"""
Offline stand-in for the GenLayer SDK surface used by the AgentBazaar contracts (and by the unchanged AgentTrust
reference contract). It is NOT GenVM: it runs no real LLM and no real network. It exists to test contract logic,
and it is deliberately stricter than a naive mock:

  - TreeMap / DynArray fields are zero-initialised; assigning to a TreeMap field raises; only the container API
    that has been proven live is available (TreeMap: get(key), [], []=; DynArray: append, len, [i], iteration)
  - storage dataclasses must be decorated with allow_storage; u256 and str fields are type-checked, so a bare int
    assigned to a u256 field raises; values stored in a TreeMap are copied (later changes to the local object
    are NOT persisted, exactly like real storage)
  - scalar storage fields are NOT zero-initialised: reading a field that __init__ never set raises
  - run_nondet_unsafe runs the leader once and then every validator with an independent LLM call; an exception in
    a validator counts as a disagreement; the leader value reaches validator_fn as an object with .calldata
  - strict_eq and prompt_comparative re-run the function on every validator; prompt_comparative requires principle=
  - any attribute access on a contract instance inside a non-deterministic block raises (self must not be captured)
  - web and LLM access outside a non-deterministic block raises
  - gl.get_contract_at(addr).view().method(...) calls a view of another deployed contract (arguments and results
    pass through calldata encoding, and the callee's state must not change);
    gl.get_contract_at(addr).emit(on="accepted").method(...) queues a write that runs after the calling
    transaction succeeds, with the emitting contract as sender, and is dropped if the transaction reverts
  - emit_transfer(value=...) records a payout; passing on= raises
"""
import sys
import types

from .runtime import Contract, NondetConsensusError, Sequence, gl
from .storage import Address, DynArray, TreeMap, allow_storage, dataclass, u256


def install():
    module = types.ModuleType("genlayer")
    module.gl = gl
    module.Address = Address
    module.u256 = u256
    module.TreeMap = TreeMap
    module.DynArray = DynArray
    module.allow_storage = allow_storage
    module.Contract = Contract
    module.__all__ = ["gl", "Address", "u256", "TreeMap", "DynArray", "allow_storage"]
    sys.modules["genlayer"] = module
    return module


def reset():
    gl.message.sender_address = Address("0x00000000000000000000000000000000000000a1")
    gl.message.value = u256(0)
    gl.eq_principle._force_fail_once = False
    gl.eq_principle.principles.clear()
    gl.nondet.web.pages.clear()
    gl.nondet.web.statuses.clear()
    gl.nondet.web.calls.clear()
    gl.nondet.web.handlers.clear()
    gl.nondet.llm = None
    gl.nondet.prompts.clear()
    gl.nondet.mode = None
    gl.nondet.index = 0
    gl.nondet._stack.clear()
    gl.vm.validators = 5
    gl.vm.validator_runs = 0
    gl.vm.rounds = 0
    gl.vm._forced = None
    gl.contracts.clear()
    gl.stack.clear()
    gl.emitted.clear()
    gl.transfers.clear()


__all__ = ["gl", "install", "reset", "Address", "u256", "TreeMap", "DynArray", "allow_storage", "dataclass", "Contract",
           "NondetConsensusError", "Sequence"]
