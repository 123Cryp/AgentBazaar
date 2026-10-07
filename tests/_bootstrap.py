"""
Test bootstrap: installs the offline GenLayer SDK stub as the `genlayer` module and exposes helpers.

Every test file starts with:  from tests._bootstrap import *
Run all tests from the repository root:  python3 -m unittest discover
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests import genlayer_stub  # noqa: E402

genlayer_stub.install()

from tests.genlayer_stub import NondetConsensusError, Sequence, gl  # noqa: E402,F401
from tests.genlayer_stub.world import GEN, START, World, addr  # noqa: E402,F401

REGISTRY_PATH = "contracts/agent_registry.py"
MARKET_PATH = "contracts/job_market.py"
LEDGER_PATH = "contracts/reputation_ledger.py"
FAKE_AT_PATH = "tests/fixtures/fake_agent_trust.py"
REAL_AT_PATH = "tests/fixtures/agenttrust_reference.py"


def path_of(rel):
    return os.path.join(ROOT, rel)


def expect_raises(fn, fragment=None):
    try:
        fn()
    except Exception as e:
        if fragment is not None and fragment not in str(e):
            raise AssertionError("raised %s: %s (expected to contain %r)" % (type(e).__name__, e, fragment))
        return e
    raise AssertionError("expected an exception containing %r, none raised" % (fragment,))
