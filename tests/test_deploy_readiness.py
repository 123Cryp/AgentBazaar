import hashlib
import importlib.util
import io
import os
import tokenize
import unittest

from tests._bootstrap import ROOT, path_of

spec = importlib.util.spec_from_file_location("check_contract", os.path.join(ROOT, "scripts", "deploy", "check_contract.py"))
check_contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_contract)

spec2 = importlib.util.spec_from_file_location("build_short_window", os.path.join(ROOT, "scripts", "deploy", "build_short_window.py"))
build_short_window = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(build_short_window)

CONTRACTS = ["agent_registry", "job_market", "reputation_ledger"]
HEADER1 = "# v0.2.16"
HEADER2 = '# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }'
REFERENCE_SHA256 = "85935078c1b1aab7a68b4d43e70111c15576bddd4ea68f27c9bf37ea8faf5164"

GOOD = HEADER1 + "\n" + HEADER2 + '''
from genlayer import *
from dataclasses import dataclass


class C(gl.Contract):
    items: TreeMap[str, str]
    names: DynArray[str]

    def __init__(self):
        pass

    @gl.public.view
    def get(self, key: str) -> str:
        return str(self.items.get(key))
'''


def problems(src):
    return check_contract.check(src)


class StudioReadyFiles(unittest.TestCase):
    def test_every_contract_passes_the_studio_lint(self):
        for name in CONTRACTS:
            with open(path_of("contracts/" + name + ".py"), encoding="utf-8") as fh:
                self.assertEqual(problems(fh.read()), [], name)

    def test_files_have_exactly_the_two_header_lines_then_code(self):
        for name in CONTRACTS:
            with open(path_of("contracts/" + name + ".py"), encoding="utf-8") as fh:
                src = fh.read()
            lines = src.split("\n")
            self.assertEqual((lines[0], lines[1]), (HEADER1, HEADER2), name)
            self.assertTrue(lines[2].startswith("import "), name)
            comments = [t for t in tokenize.generate_tokens(io.StringIO(src).readline) if t.type == tokenize.COMMENT]
            self.assertEqual(len(comments), 2, name)
            self.assertNotIn('"""', src, name)
            self.assertTrue(src.isascii(), name)
            self.assertTrue(src.endswith("\n") and not src.endswith("\n\n"), name)
            self.assertIn("from genlayer import *\nfrom dataclasses import dataclass\n", src, name)

    def test_the_good_sample_is_clean(self):
        self.assertEqual(problems(GOOD), [])

    def test_the_lint_catches_each_known_studio_failure(self):
        bad = {
            "comment": GOOD.replace("class C", "# a comment\nclass C"),
            "docstring": GOOD.replace("    def __init__(self):\n        pass", '    def __init__(self):\n        """doc"""\n        pass'),
            "non-ascii": GOOD.replace("str(self", "str(self) + 'café' if False else str(self"),
            "treemap len": GOOD.replace("return str(self.items.get(key))", "return str(len(self.items))"),
            "treemap in": GOOD.replace("return str(self.items.get(key))", "return 'a' if key in self.items else 'b'"),
            "treemap get default": GOOD.replace("self.items.get(key)", "self.items.get(key, '')"),
            "treemap iteration": GOOD.replace("return str(self.items.get(key))", "return ','.join([k for k in self.items])"),
            "init assigns storage": GOOD.replace("        pass", "        self.names = []"),
            "float": GOOD.replace("return str(self.items.get(key))", "return str(0.5)"),
            "division": GOOD.replace("return str(self.items.get(key))", "return str(4 / 2)"),
            "bool param": GOOD.replace("key: str", "key: bool"),
            "unproven gl attribute": GOOD.replace("return str(self.items.get(key))", "return str(gl.message.timestamp)"),
            "unknown import": GOOD.replace("from genlayer import *", "import os\nfrom genlayer import *"),
            "emit without on": GOOD.replace("return str(self.items.get(key))", "gl.get_contract_at(Address(key)).emit().go()\n        return key"),
            "emit wrong on": GOOD.replace("return str(self.items.get(key))", 'gl.get_contract_at(Address(key)).emit(on="finalized").go()\n        return key'),
            "emit_transfer on": GOOD.replace("return str(self.items.get(key))", 'gl.get_contract_at(Address(key)).emit_transfer(value=u256(1), on="accepted")\n        return key'),
            "self in module function": GOOD.replace("class C", "def helper():\n    return self\n\n\nclass C"),
            "missing annotation": GOOD.replace("key: str) -> str", "key) -> str"),
            "wrong header": GOOD.replace(HEADER1, "# v0.1.0"),
            "dataclass import order": GOOD.replace("from genlayer import *\nfrom dataclasses import dataclass", "from dataclasses import dataclass\nfrom genlayer import *"),
            "storage field type": GOOD.replace("class C", "@allow_storage\n@dataclass\nclass Row:\n    amount: int\n\n\nclass C"),
            "run_nondet_unsafe keyword": GOOD.replace("return str(self.items.get(key))", "gl.vm.run_nondet_unsafe(a, validator_fn=b)\n        return key"),
        }
        for label, src in bad.items():
            self.assertNotEqual(problems(src), [], label)
            if label not in ("wrong header", "dataclass import order"):
                self.assertNotEqual(src, GOOD, label)


class BuildArtifacts(unittest.TestCase):
    def test_the_committed_short_window_build_is_reproducible(self):
        with open(path_of("build/job_market_short_window.py"), encoding="utf-8") as fh:
            committed = fh.read()
        self.assertEqual(committed, build_short_window.render(60))

    def test_the_short_window_build_differs_from_the_contract_in_one_line_only(self):
        with open(path_of("contracts/job_market.py"), encoding="utf-8") as fh:
            src = fh.read().split("\n")
        with open(path_of("build/job_market_short_window.py"), encoding="utf-8") as fh:
            built = fh.read().split("\n")
        diff = [(a, b) for a, b in zip(src, built) if a != b]
        self.assertEqual(len(src), len(built))
        self.assertEqual(diff, [("WINDOW_UNIT = 3600", "WINDOW_UNIT = 60")])
        self.assertEqual(problems("\n".join(built)), [])

    def test_the_agenttrust_reference_is_the_unchanged_deployed_contract(self):
        with open(path_of("tests/fixtures/agenttrust_reference.py"), "rb") as fh:
            self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), REFERENCE_SHA256)


if __name__ == "__main__":
    unittest.main()
