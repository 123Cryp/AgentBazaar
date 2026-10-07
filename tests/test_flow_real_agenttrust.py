import json
import unittest

from tests._bootstrap import GEN, expect_raises, gl
from tests.support.scenario import AGENT1, AGENT2, CLIENT, OWNER, STRANGER, STRONG_PITCH, Bazaar, JOB_SPEC

HOUR = 3600
DAY = 24 * HOUR
REPO = "https://github.com/acme-agent/health-api"
COMMIT = "3" * 40
RAW = "https://raw.githubusercontent.com/acme-agent/health-api/" + COMMIT + "/src/app.py"
APP = 'from flask import Flask\n\napp = Flask(__name__)\n\n\n@app.route("/health")\ndef health():\n    return "ok", 200\n'
QUOTE = '@app.route("/health")'
REQS = [{"id": "REQ-001", "description": "The service exposes a /health endpoint.", "method": "CODE_INSPECTION",
         "evidence_requirements": "Source of the health endpoint handler."}]


class RealAgentTrustFlow(unittest.TestCase):
    def setUp(self):
        self.b = Bazaar(real_at=True)
        self.m, self.at, self.led = self.b.market, self.b.at, self.b.ledger
        gl.nondet.web.pages[RAW] = APP
        self.b.llm.at_quote = QUOTE
        self.b.register(AGENT1, "Alpha Agent")
        self.b.register(AGENT2, "Beta Agent")

    def at_tx(self, sender, method, *args, **kw):
        return self.b.tx(sender, self.at, method, *args, **kw)

    def agreement(self, aid_hint="JB-1", worker=AGENT1, amount=5 * GEN, deadline_in=30 * DAY, title=None):
        return self.at_tx(CLIENT, "create_agreement", title or "[" + aid_hint + "] Health endpoint", "Add a health endpoint to the service.",
                          "Deliver a Flask service that exposes GET /health returning 200.", str(worker), "GEN", amount,
                          self.b.w.now + deadline_in, json.dumps(REQS), "STRICT", "STANDARD", "JURY")

    def award(self, price=5 * GEN, who=AGENT1):
        jid = self.b.post_job()
        bid = self.b.bid(who, jid, price=price)
        self.b.tx(CLIENT, self.m, "select_bid", jid, bid)
        return jid

    def deliver(self, aid, evidence_commit=COMMIT):
        self.at_tx(AGENT1, "accept", aid)
        self.at_tx(AGENT1, "start_work", aid)
        evidence = json.dumps([{"kind": "github_file", "repository": REPO, "commit": evidence_commit, "path": "src/app.py"}])
        self.at_tx(AGENT1, "submit_deliverable", aid, "The health endpoint is implemented in src/app.py.", evidence)
        while self.status(aid) == "DELIVERED":
            self.at_tx(AGENT1, "freeze_evidence", aid)
        self.at_tx(STRANGER, "verify_requirement", aid, "REQ-001")
        return self.at_tx(STRANGER, "aggregate", aid)

    def status(self, aid):
        return self.b.view(self.at, "get_agreement", aid)["status"]

    def ledger_ok(self):
        acc = {k: int(v) for k, v in self.b.view(self.at, "get_accounting").items()}
        held = acc["escrow_locked"] + acc["stakes_locked"] + acc["bonds_locked"] + acc["claimable_total"] + acc["treasury"]
        self.assertEqual(acc["total_in"] - acc["total_out"], held)
        self.assertEqual(self.b.w.balance[str(self.at)] - self.b.w.stuck[str(self.at)], acc["total_in"] - acc["total_out"])

    def test_the_record_fields_used_by_the_marketplace_exist_in_the_real_contract(self):
        aid = self.agreement()
        rec = self.b.view(self.at, "get_agreement", aid)
        for key in ("agreement_id", "buyer", "worker", "title", "description", "currency", "amount", "deadline", "created_at", "status",
                    "funded", "accepted_at", "settle_worker", "settle_buyer", "certificate_hash"):
            self.assertIn(key, rec)
        self.assertEqual((rec["status"], rec["funded"], rec["amount"], rec["currency"]), ("CREATED", 0, str(5 * GEN), "GEN"))
        self.assertIsInstance(rec["amount"], str)

    def test_full_lifecycle_through_the_marketplace_to_reputation(self):
        jid = self.award()
        aid = self.agreement()
        expect_raises(lambda: self.b.tx(CLIENT, self.m, "link_agreement", jid, aid), "funded and not yet delivered")
        self.at_tx(CLIENT, "fund", aid, value=5 * GEN)
        self.assertEqual(self.b.tx(CLIENT, self.m, "link_agreement", jid, aid), "LINKED")
        self.assertEqual(self.deliver(aid), "PASS")
        self.assertEqual(self.status(aid), "VERIFIED_PASS")
        self.assertEqual(self.b.tx(STRANGER, self.m, "sync_agreement", jid), "LINKED")
        expect_raises(lambda: self.b.tx(STRANGER, self.led, "record_outcome", aid), "not in a final outcome state")
        expect_raises(lambda: self.at_tx(STRANGER, "settle", aid), "challenge window is still open")
        self.b.w.advance(DAY + 1)
        self.assertEqual(self.at_tx(STRANGER, "settle", aid), "SETTLED")
        self.assertEqual(self.b.tx(STRANGER, self.m, "sync_agreement", jid), "CLOSED")
        job = self.b.view(self.m, "get_job", jid)
        self.assertEqual((job["status"], job["outcome"], job["agreement_id"]), ("CLOSED", "SETTLED", aid))
        self.assertEqual(self.b.tx(STRANGER, self.led, "record_outcome", aid), "COMPLETED")
        expect_raises(lambda: self.b.tx(STRANGER, self.led, "record_outcome", aid), "already recorded")
        p = self.b.view(self.led, "get_profile", str(AGENT1))
        self.assertEqual((p["completed"], p["market_completed"], p["total_earned"], p["pos_points"], p["tier"]), (1, 1, str(5 * GEN), 50 * 100, "ESTABLISHED"))
        self.assertEqual(p["score"], 5000 * 1000 // (5000 + 2000))
        o = self.b.view(self.led, "get_outcome", aid)
        self.assertEqual((o["via_market"], o["job_id"], o["buyer"], o["status"]), (1, jid, str(CLIENT), "SETTLED"))
        cert = self.b.view(self.at, "get_certificate_hash", aid)
        self.assertEqual(o["certificate_hash"], cert)
        self.assertEqual(self.b.w.failed_emits, [])
        self.ledger_ok()

    def test_a_failed_verification_refunds_the_buyer_and_costs_reputation(self):
        jid = self.award()
        aid = self.agreement()
        self.at_tx(CLIENT, "fund", aid, value=5 * GEN)
        self.b.tx(CLIENT, self.m, "link_agreement", jid, aid)
        self.b.llm.at_verdict = "FAIL"
        self.assertEqual(self.deliver(aid), "FAIL")
        expect_raises(lambda: self.at_tx(CLIENT, "claim_refund", aid), "dispute window is still open")
        self.b.w.advance(3 * DAY + 1)
        self.assertEqual(self.at_tx(CLIENT, "claim_refund", aid), "REFUNDED")
        self.assertEqual(self.b.tx(STRANGER, self.m, "sync_agreement", jid), "CLOSED")
        self.assertEqual(self.b.tx(STRANGER, self.led, "record_outcome", aid), "REFUNDED")
        p = self.b.view(self.led, "get_profile", str(AGENT1))
        self.assertEqual((p["refunded"], p["completed"], p["neg_points"], p["score"], p["total_earned"]), (1, 0, 5000 * 2, 0, "0"))
        self.ledger_ok()

    def test_cancelling_after_funding_does_not_penalise_the_worker(self):
        jid = self.award()
        aid = self.agreement()
        self.at_tx(CLIENT, "fund", aid, value=5 * GEN)
        self.b.tx(CLIENT, self.m, "link_agreement", jid, aid)
        self.assertEqual(self.at_tx(CLIENT, "cancel", aid), "REFUNDED")
        self.assertEqual(self.b.tx(STRANGER, self.m, "sync_agreement", jid), "CLOSED")
        self.assertEqual(self.b.tx(STRANGER, self.led, "record_outcome", aid), "UNACCEPTED")
        p = self.b.view(self.led, "get_profile", str(AGENT1))
        self.assertEqual((p["unaccepted"], p["refunded"], p["neg_points"], p["score"], p["total_volume"]), (1, 0, 0, 0, "0"))
        self.ledger_ok()

    def test_a_worker_who_never_accepts_is_not_penalised_but_one_who_vanishes_after_accepting_is(self):
        jid = self.award()
        aid = self.agreement(deadline_in=2 * DAY)
        self.at_tx(CLIENT, "fund", aid, value=5 * GEN)
        self.b.tx(CLIENT, self.m, "link_agreement", jid, aid)
        self.b.w.advance(2 * DAY + 1)
        self.assertEqual(self.at_tx(STRANGER, "expire_if_timed_out", aid), "TIMEOUT")
        self.assertEqual(self.at_tx(CLIENT, "claim_refund", aid), "REFUNDED")
        self.assertEqual(self.b.tx(STRANGER, self.led, "record_outcome", aid), "UNACCEPTED")
        jid2 = self.award()
        aid2 = self.agreement(aid_hint="JB-2", deadline_in=2 * DAY)
        self.at_tx(CLIENT, "fund", aid2, value=5 * GEN)
        self.b.tx(CLIENT, self.m, "link_agreement", jid2, aid2)
        self.at_tx(AGENT1, "accept", aid2)
        self.at_tx(AGENT1, "start_work", aid2)
        self.b.w.advance(2 * DAY + 1)
        self.assertEqual(self.at_tx(STRANGER, "expire_if_timed_out", aid2), "TIMEOUT")
        self.assertEqual(self.at_tx(CLIENT, "claim_refund", aid2), "REFUNDED")
        self.assertEqual(self.b.tx(STRANGER, self.led, "record_outcome", aid2), "REFUNDED")
        p = self.b.view(self.led, "get_profile", str(AGENT1))
        self.assertEqual((p["unaccepted"], p["refunded"], p["completed"]), (1, 1, 0))
        self.ledger_ok()

    def test_the_marketplace_refuses_agreements_that_do_not_match_the_award(self):
        jid = self.award()
        cases = (
            (dict(worker=AGENT2), "worker is not the winning bidder"),
            (dict(amount=6 * GEN), "amount must equal"),
            (dict(title="Health endpoint without a token"), "must contain the token [JB-1]"),
        )
        for kw, frag in cases:
            aid = self.agreement(**kw)
            self.at_tx(CLIENT, "fund", aid, value=kw.get("amount", 5 * GEN))
            expect_raises(lambda aid=aid: self.b.tx(CLIENT, self.m, "link_agreement", jid, aid), frag)
        self.assertEqual(self.b.view(self.m, "get_job", jid)["status"], "AWARDED")

    def test_an_agreement_created_by_another_buyer_cannot_be_linked(self):
        jid = self.award()
        aid = self.at_tx(OWNER, "create_agreement", "[JB-1] Health endpoint", "Add a health endpoint to the service.",
                         "Deliver a Flask service that exposes GET /health returning 200.", str(AGENT1), "GEN", 5 * GEN,
                         self.b.w.now + 30 * DAY, json.dumps(REQS), "STRICT", "STANDARD", "JURY")
        self.at_tx(OWNER, "fund", aid, value=5 * GEN)
        expect_raises(lambda: self.b.tx(OWNER, self.m, "link_agreement", jid, aid), "only the client or the winning bidder")
        expect_raises(lambda: self.b.tx(AGENT1, self.m, "link_agreement", jid, aid), "buyer is not the job client")

    def test_a_delivered_agreement_cannot_be_linked_late(self):
        jid = self.award()
        aid = self.agreement()
        self.at_tx(CLIENT, "fund", aid, value=5 * GEN)
        self.at_tx(AGENT1, "accept", aid)
        self.at_tx(AGENT1, "start_work", aid)
        evidence = json.dumps([{"kind": "github_file", "repository": REPO, "commit": COMMIT, "path": "src/app.py"}])
        self.at_tx(AGENT1, "submit_deliverable", aid, "The health endpoint is implemented in src/app.py.", evidence)
        expect_raises(lambda: self.b.tx(CLIENT, self.m, "link_agreement", jid, aid), "funded and not yet delivered")


if __name__ == "__main__":
    unittest.main()
