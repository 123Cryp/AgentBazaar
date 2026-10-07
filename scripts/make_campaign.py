#!/usr/bin/env python3
"""
Generates docs/LIVE_CAMPAIGN.md: the ordered Studio test table with full wallet addresses in every step.

    python3 scripts/make_campaign.py W1 W2 W3 W4 W5 [REGISTRY LEDGER MARKET]

Unknown values are printed as <WALLET-n ADDRESS> / <REGISTRY ADDRESS> and so on.
"""
import os
import sys

AT = "0x9d04ea1E3C0BBA11c85e7325C87D2E009AcF3ccc"
ROLES = ["client / buyer / deployer", "agent / worker", "second bidder", "juror", "juror"]
REPO = "https://github.com/123Cryp/AgentBazaar"
COMMIT = "7c7709513d660386eb50041029ea5b0f9e140cc3"
REQS = '[{"id":"REQ-001","description":"The reputation ledger contract defines a record_outcome method.","method":"CODE_INSPECTION","evidence_requirements":"Source of contracts/reputation_ledger.py."}]'
EVIDENCE = '[{"kind":"github_file","repository":"https://github.com/123Cryp/AgentBazaar","commit":"%s","path":"contracts/reputation_ledger.py"}]' % COMMIT
JOB = ("Review the reputation ledger contract", "Review contracts/reputation_ledger.py and confirm that record_outcome exists and records each agreement only once.", 5 * 10 ** 18)
BID1 = (4 * 10 ** 18, "I will review contracts/reputation_ledger.py, confirm record_outcome and check that each agreement is recorded only once.")
BID2 = (3 * 10 ** 18, "I can do this quickly and cheaply.")
AGREEMENT = ("[JB-1] Review the reputation ledger contract", "Code review for AgentBazaar job JB-1.", "Confirm that contracts/reputation_ledger.py defines record_outcome.")
STATEMENT = "record_outcome is defined in contracts/reputation_ledger.py."
RAW = "https://raw.githubusercontent.com/123Cryp/AgentBazaar/main/docs/profiles/"


def main(argv):
    w = list(argv[:5]) + [None] * (5 - len(argv[:5]))
    w = [x or "<WALLET-%d ADDRESS>" % (i + 1) for i, x in enumerate(w)]
    extra = list(argv[5:8]) + [None] * (3 - len(argv[5:8]))
    reg = extra[0] or "<REGISTRY ADDRESS>"
    led = extra[1] or "<LEDGER ADDRESS>"
    mkt = extra[2] or "<MARKET ADDRESS>"
    rows = []

    def split_args(text):
        out = []
        cur = ""
        quote = None
        depth = 0
        i = 0
        while i < len(text):
            ch = text[i]
            if quote:
                if ch == "\\" and i + 1 < len(text):
                    cur += text[i + 1]
                    i += 2
                    continue
                if ch == quote and depth == 0:
                    quote = None
                else:
                    cur += ch
            elif ch in ("'", '"'):
                quote = ch
            elif ch == "," and depth == 0:
                out.append(cur.strip())
                cur = ""
            else:
                cur += ch
            i += 1
        if cur.strip() != "":
            out.append(cur.strip())
        return out

    def step(wallet, target, method, args, expect, alarm=""):
        if args.startswith("no args") or args == "-" or args.startswith("(") or "(then" in args:
            shown = args
        else:
            parts = split_args(args)
            shown = " <br> ".join("%d) `%s`" % (n, x.replace("|", "/")) for n, x in enumerate(parts, 1))
        rows.append((wallet, target, method, shown, expect, alarm))

    reqs = REQS
    evidence = EVIDENCE
    profile2 = "https://github.com/123Cryp/AgentBazaar/blob/main/docs/profiles/alpha-agent.md"
    profile3 = "https://github.com/123Cryp/AgentBazaar/blob/main/docs/profiles/beta-agent.md"
    step(1, "deploy", "AgentRegistry: contracts/agent_registry.py", "no args", "address -> REGISTRY", "A red row on a deploy is a real failure; send the error")
    step(1, "deploy", "ReputationLedger: contracts/reputation_ledger.py", "no args", "address -> LEDGER")
    step(1, "deploy", "JobMarket: build/job_market_short_window.py", "no args", "address -> MARKET", "Short-window build: one hour = one minute")
    step(1, "ledger " + led, "set_wiring", '"%s", "%s"' % (AT, mkt), "WIRED", "Repeat it once: the second call must fail with already wired")
    step(1, "market " + mkt, "set_wiring", '"%s", "%s", "%s"' % (AT, reg, led), "WIRED")
    step(1, "registry " + reg, "set_job_market", '"%s"' % mkt, "the market address")
    step(1, "registry " + reg, "register_agent", '"Alpha Agent", "%s", "python apis, code review"' % profile2, "AG-1 (done by mistake with Wallet 1 in the first run; keep as a negative test)", "Wallet 1 does not own the page address, so verify_claims on AG-1 must be rejected")
    step(2, "registry " + reg, "register_agent", '"Alpha Agent", "%s", "python apis, code review"' % profile2, "AG-2", "docs/profiles/alpha-agent.md must be on GitHub first and contain " + w[1])
    step(3, "registry " + reg, "register_agent", '"Beta Agent", "%s", "data cleaning"' % profile3, "AG-3", "docs/profiles/beta-agent.md must contain " + w[2])
    step(1, "registry " + reg, "verify_claims", '"AG-2"', "CLAIMS_SUPPORTED", "Web + LLM consensus: wait for the result before the next step")
    step(1, "registry " + reg, "verify_claims", '"AG-3"', "CLAIMS_SUPPORTED or CLAIMS_PARTIAL", "CLAIMS_UNSUPPORTED would block bidding")
    step(1, "registry " + reg, "verify_claims", '"AG-1"', "CLAIMS_UNSUPPORTED with claims_detail ADDRESS_NOT_FOUND", "Proof-of-control negative test: read get_agent AG-1 afterwards")
    step(1, "market " + mkt, "post_job", '"%s", "%s", %d, NOW+900' % JOB, "JB-1", "NOW = current unix time (https://www.unixtimestamp.com); the deadline must be at least 120 s ahead")
    step(2, "market " + mkt, "submit_bid", '"JB-1", %d, "%s"' % BID1, "BD-1", "Price is exactly 4 GEN because the Value field takes whole GEN")
    step(3, "market " + mkt, "submit_bid", '"JB-1", %d, "%s"' % BID2, "BD-2")
    step(1, "market " + mkt, "assess_bid", '"BD-1"', "STRONG_FIT or PARTIAL_FIT", "LLM consensus; if it fails, send the error")
    step(1, "market " + mkt, "assess_bid", '"BD-2"', "POOR_FIT expected")
    step(1, "market " + mkt, "list_bids (read)", '"JB-1"', "BD-1 ranked first")
    step(1, "market " + mkt, "select_bid", '"JB-1", "BD-2"', "must FAIL: only strong or partial fits", "This failure is the expected result")
    step(1, "market " + mkt, "select_bid", '"JB-1", "BD-1"', "AWARDED", "Then check registry get_agent_by_owner for Wallet 2: selections = 1 (cross-contract emit)")
    step(1, "AgentTrust " + AT, "create_agreement", '"%s", "%s", "%s", "%s", "GEN", %d, NOW+86400, \'%s\', "STRICT", "STANDARD", "JURY"' % (AGREEMENT + (w[1], BID1[0], reqs)), "AT-n (note the number)", "Title must contain [JB-1]")
    step(1, "AgentTrust " + AT, "fund (Value = 4)", '"AT-n"', "FUNDED", "Whole GEN only. The transfer can show as a red (constructor) row: Studio display only")
    step(1, "market " + mkt, "link_agreement", '"JB-1", "AT-n"', "LINKED", "Then ledger get_info: the link emit lands shortly after")
    step(2, "AgentTrust " + AT, "accept", '"AT-n"', "ACCEPTED")
    step(2, "AgentTrust " + AT, "start_work", '"AT-n"', "IN_PROGRESS")
    step(2, "AgentTrust " + AT, "submit_deliverable", '"AT-n", "%s", \'%s\'' % (STATEMENT, evidence), "DELIVERED", "github_file evidence at a fixed commit")
    step(2, "AgentTrust " + AT, "freeze_evidence", '"AT-n"', "repeat until the status leaves DELIVERED")
    step(1, "AgentTrust " + AT, "verify_requirement", '"AT-n", "REQ-001"', "PASS")
    step(1, "AgentTrust " + AT, "aggregate", '"AT-n"', "PASS / VERIFIED_PASS")
    step(1, "market " + mkt, "sync_agreement", '"JB-1"', "LINKED (not final yet)")
    step(1, "AgentTrust " + AT, "settle (after the 24-minute challenge window)", '"AT-n"', "SETTLED", "Too early gives: challenge window is still open")
    step(1, "market " + mkt, "sync_agreement", '"JB-1"', "CLOSED")
    step(1, "ledger " + led, "record_outcome", '"AT-n"', "COMPLETED")
    step(1, "ledger " + led, "record_outcome", '"AT-n"', "must FAIL: already recorded", "Replay protection")
    step(1, "ledger " + led, "get_profile (read)", '"%s"' % w[1].lower(), "completed 1, qualified_completed 1, market_completed 1, score 666, tier ESTABLISHED")
    step(1, "ledger " + led, "record_outcome", '"AT-1" (then AT-2 ... AT-5)', "an outcome kind, or a clear rejection such as not in a final outcome state", "Old AgentTrust agreements; any clear message is a valid result")
    step(4, "frontend", "Settings: paste the 4 addresses, Live mode, Connect wallet; post a job from the site", "-", "a JB-2 visible on the Jobs page", "Real wallet-sent transaction from the frontend")
    out = ["# Live Studio campaign", "", "Generated by `scripts/make_campaign.py`. Run one step at a time and wait for each transaction to finish. Never send parallel reads. In Studio, type each argument into its own box exactly as shown, without surrounding quotes (the quotes are only needed for a single JSON array field). Wallets 4 and 5 are only needed for the optional dispute path in the AgentTrust guide.", "",
           "| Wallet | Role | Full address |", "|---|---|---|"]
    for i in range(5):
        out.append("| Wallet %d | %s | `%s` |" % (i + 1, ROLES[i], w[i]))
    out += ["", "AgentTrust test build: `%s` (WINDOW_UNIT = 60)." % AT, "",
            "| # | Wallet and address | Target | Method | Arguments | Expected | Alarms |", "|---|---|---|---|---|---|---|"]
    for n, (wl, target, method, args, expect, alarm) in enumerate(rows, 1):
        out.append("| %d | Wallet %d `%s` | %s | %s | %s | %s | %s |" % (n, wl, w[wl - 1], target, method, args, expect, alarm))
    out.append("")
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs")
    os.makedirs(os.path.join(base, "profiles"), exist_ok=True)
    pages = {
        "alpha-agent.md": ("Alpha Agent", w[1], ["python apis: I build and review Python HTTP APIs, including Flask services with health checks.",
                                                 "code review: I review smart contract code and report access-control and state-machine issues."]),
        "beta-agent.md": ("Beta Agent", w[2], ["data cleaning: I normalise CSV exports, fix date formats and remove duplicate rows."]),
    }
    for fname, (name, wallet, lines) in pages.items():
        with open(os.path.join(base, "profiles", fname), "w", encoding="utf-8") as fh:
            fh.write("# " + name + "\n\nOperator wallet: " + wallet + "\n\n" + "\n\n".join(lines) + "\n")
    path = os.path.join(base, "LIVE_CAMPAIGN.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    print("wrote", os.path.normpath(path), "with", len(rows), "steps")


if __name__ == "__main__":
    main(sys.argv[1:])
