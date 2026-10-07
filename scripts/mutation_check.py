#!/usr/bin/env python3
"""
Mutation check of the test suite: each mutant breaks one guard in a contract (an authorization check, a replay
check, a grounding check, a bound ...) and the whole offline suite must then fail. A surviving mutant means a
guard that no test protects.

    python3 scripts/mutation_check.py            # runs every mutant in parallel (about a minute)
    python3 scripts/mutation_check.py -k ledger  # only mutants whose label contains 'ledger'
"""
import concurrent.futures
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
R = "contracts/agent_registry.py"
L = "contracts/reputation_ledger.py"
M = "contracts/job_market.py"

MUTANTS = [
    ("registry: any caller may re-verify", R, 'if a.claims_status != C_UNVERIFIED and who != a.owner:', 'if False:'),
    ("registry: owner address proof removed", R, 'if owner_addr not in text.lower():', 'if False:'),
    ("registry: leader quotes need no grounding", R, 'if len(quote) < MIN_QUOTE or len(quote) > MAX_QUOTE or not _grounded(quote, text):', 'if len(quote) < MIN_QUOTE or len(quote) > MAX_QUOTE:'),
    ("registry: validators skip quote grounding", R, 'if len(q["quote"]) < MIN_QUOTE or len(q["quote"]) > MAX_QUOTE or not _grounded(q["quote"], text):', 'if len(q["quote"]) < MIN_QUOTE or len(q["quote"]) > MAX_QUOTE:'),
    ("registry: validators accept any verdict", R, 'return value["verdict"] == mine["value"]["verdict"]', 'return True'),
    ("registry: note_selection open to everyone", R, 'if self.job_market == "" or self._sender() != self.job_market:', 'if False:'),
    ("registry: wiring can be changed", R, 'if self.job_market != "":', 'if False:'),
    ("registry: wiring open to everyone", R, 'if self._sender() != self.owner:', 'if False:'),
    ("registry: host allowlist removed", R, 'if not allowed:', 'if False:'),
    ("registry: one profile per address removed", R, 'if self.owner_index.get(who) is not None:', 'if False:'),
    ("ledger: replay protection removed", L, 'if self.outcomes.get(agreement_id) is not None:\n            raise Exception("outcome already recorded for "', 'if False:\n            raise Exception("outcome already recorded for "'),
    ("ledger: anyone can mark market links", L, 'if self._sender() != self.job_market:', 'if False:'),
    ("ledger: unaccepted refunds penalise", L, 'if accepted_at == 0:\n        return K_UNACCEPTED', 'if False:\n        return K_UNACCEPTED'),
    ("ledger: no repeat-client decay", L, 'pos = base // pair_index', 'pos = base'),
    ("ledger: off-market weighs fully", L, 'if via_market == 0:', 'if False:'),
    ("ledger: weight unit changed", L, 'WEIGHT_UNIT = 10 ** 17', 'WEIGHT_UNIT = 10 ** 16'),
    ("ledger: weight cap removed", L, 'WEIGHT_CAP = 100', 'WEIGHT_CAP = 10 ** 9'),
    ("ledger: settled need not pay in full", L, 'if to_worker != amount:\n            raise Exception("a settled', 'if False:\n            raise Exception("a settled'),
    ("ledger: unwired ledger records", L, 'def record_outcome(self, agreement_id: str) -> str:\n        self._need_wired()', 'def record_outcome(self, agreement_id: str) -> str:\n        pass'),
    ("ledger: failures cost nothing", L, 'neg = base * NEG_FACTOR', 'neg = 0'),
    ("ledger: wiring can be changed", L, 'if int(self.wired) == 1:\n            raise Exception("the ledger is already wired', 'if False:\n            raise Exception("the ledger is already wired'),
    ("ledger: certificate not required", L, 'if not _HEX64_RE.match(cert):', 'if False:'),
    ("ledger: mismatched record accepted", L, 'str(raw.get("agreement_id", "")) != agreement_id', 'False'),
    ("ledger: distinct clients not counted", L, 'if pair_prev is None:\n                p.distinct_clients', 'if False:\n                p.distinct_clients'),
    ("market: anyone can select", M, 'if self._sender() != j.client:\n            raise Exception("only the client can select a bid")', 'if False:\n            raise Exception("only the client can select a bid")'),
    ("market: poor fits can be selected", M, 'if FIT_RANK.get(str(b.fit), 0) < 1:', 'if False:'),
    ("market: link ignores the buyer", M, 'if str(a.get("buyer", "")) != j.client:', 'if False:'),
    ("market: link ignores the worker", M, 'if str(a.get("worker", "")) != j.winner:', 'if False:'),
    ("market: link ignores the amount", M, 'if str(a.get("currency", "")) != "GEN" or int(str(a.get("amount", "0"))) != int(j.winning_price):', 'if False:'),
    ("market: link ignores the job token", M, 'if token not in (str(a.get("title", "")) + " " + str(a.get("description", ""))):', 'if False:'),
    ("market: one agreement may link twice", M, 'if self.agreement_links.get(agreement_id) is not None:', 'if False:'),
    ("market: link ignores creation time", M, 'if int(a.get("created_at", 0)) < int(j.created_at):', 'if False:'),
    ("market: link ignores agreement state", M, 'if status not in AT_LINKABLE or int(a.get("funded", 0)) != 1:', 'if False:'),
    ("market: link open to strangers", M, 'if who != j.client and who != j.winner:', 'if False:'),
    ("market: link ignores the window", M, 'if now > int(j.link_deadline):\n            raise Exception("the link window has passed")', 'if False:\n            raise Exception("the link window has passed")'),
    ("market: client may bid on own job", M, 'if who == j.client:', 'if False:'),
    ("market: bid count unbounded", M, 'if len(j.bid_ids) >= MAX_BIDS:', 'if False:'),
    ("market: revisions unbounded", M, 'if int(b.revision) >= MAX_REVISIONS:', 'if False:'),
    ("market: fit grounding removed", M, 'if fit != F_POOR and not (pitch_ok and spec_ok):', 'if False:'),
    ("market: bids can be re-assessed", M, 'if b.fit != F_UNASSESSED:', 'if False:'),
    ("market: anyone can cancel", M, 'if self._sender() != j.client:\n            raise Exception("only the client can cancel a job")', 'if False:\n            raise Exception("only the client can cancel a job")'),
    ("market: open jobs expire immediately", M, 'if j.status == S_OPEN and now > int(j.deadline) + SELECT_GRACE:', 'if j.status == S_OPEN:'),
    ("market: awards expire immediately", M, 'if j.status == S_AWARDED and now > int(j.link_deadline):', 'if j.status == S_AWARDED:'),
    ("market: sync closes non-final jobs", M, 'if status in AT_TERMINAL:', 'if True:'),
    ("market: selection window ignored", M, 'if now > int(j.deadline) + SELECT_GRACE:\n            raise Exception("the selection window has passed")\n        if b.job_id', 'if False:\n            raise Exception("the selection window has passed")\n        if b.job_id'),
    ("market: ledger link emit dropped", M, 'gl.get_contract_at(Address(self.ledger)).emit(on="accepted").mark_market_link(agreement_id, job_id)', 'pass'),
    ("market: registry selection emit dropped", M, 'gl.get_contract_at(Address(self.registry)).emit(on="accepted").note_selection(str(b.bidder), job_id)', 'pass'),
    ("market: anyone can withdraw a bid", M, 'if self._sender() != b.bidder:', 'if False:'),
    ("market: foreign bids can be selected", M, 'if b.job_id != job_id:', 'if False:'),
    ("market: wiring can be changed", M, 'if int(self.wired) == 1:\n            raise Exception("the market is already wired', 'if False:\n            raise Exception("the market is already wired'),
    ("market: wiring open to everyone", M, 'if self._sender() != self.owner:', 'if False:'),
    ("market: deadline bounds removed", M, 'if not _is_int(deadline) or deadline < now + MIN_BID_WINDOW or deadline > now + MAX_BID_WINDOW:', 'if False:'),
    ("market: budget bounds removed", M, 'if not _is_int(budget) or budget < MIN_AMOUNT or budget > MAX_AMOUNT:', 'if False:'),
    ("market: price may exceed budget", M, 'if not _is_int(price) or price < MIN_AMOUNT or price > int(j.budget):', 'if not _is_int(price) or price < MIN_AMOUNT:'),
    ("market: unsupported agents may bid", M, 'if str(raw.get("claims_status", "")) == "CLAIMS_UNSUPPORTED":', 'if False:'),
    ("market: inactive agents may bid", M, 'if int(raw.get("active", 0)) != 1:', 'if False:'),
    ("market: unregistered agents may bid", M, 'if not isinstance(raw, dict) or str(raw.get("agent_id", "")) == "":', 'if False:'),
]


def run(mutant):
    label, rel, old, new = mutant
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        src = fh.read()
    if src.count(old) != 1:
        return label, "BAD-PATTERN (%d matches)" % src.count(old)
    tmp = tempfile.mkdtemp(prefix="mutant_")
    try:
        shutil.copytree(ROOT, os.path.join(tmp, "repo"), ignore=shutil.ignore_patterns(".git", "__pycache__", "node_modules"))
        with open(os.path.join(tmp, "repo", rel), "w", encoding="utf-8") as fh:
            fh.write(src.replace(old, new))
        proc = subprocess.run([sys.executable, "-m", "unittest", "discover", "-q"], cwd=os.path.join(tmp, "repo"),
                              capture_output=True, text=True, timeout=300)
        return label, "KILLED" if proc.returncode != 0 else "SURVIVED"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv):
    keyword = argv[1] if len(argv) > 1 and argv[0] == "-k" else ""
    mutants = [m for m in MUTANTS if keyword in m[0]]
    workers = max(2, (os.cpu_count() or 2))
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for label, status in pool.map(run, mutants):
            results.append((label, status))
            print("%-9s %s" % (status, label), flush=True)
    bad = [r for r in results if r[1] != "KILLED"]
    print("\n%d mutants, %d killed, %d not killed" % (len(results), len(results) - len(bad), len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
