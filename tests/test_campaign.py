import importlib.util
import json
import os
import unittest

from tests._bootstrap import GEN, ROOT, expect_raises, gl
from tests.support.scenario import AGENT1, AGENT2, CLIENT, STRANGER, Bazaar

spec = importlib.util.spec_from_file_location("make_campaign", os.path.join(ROOT, "scripts", "make_campaign.py"))
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)

DAY = 24 * 3600
RAW = "https://raw.githubusercontent.com/123Cryp/AgentBazaar/" + campaign.COMMIT + "/contracts/reputation_ledger.py"
UPLOADED = os.path.join(ROOT, "tests", "fixtures", "ledger_at_campaign_commit.py")


class LiveCampaignReplay(unittest.TestCase):
    """Replays the exact arguments of docs/LIVE_CAMPAIGN.md against the real AgentTrust code."""

    def test_the_campaign_happy_path_succeeds_with_its_exact_arguments(self):
        b = Bazaar(real_at=True, market_path="build/job_market_short_window.py")
        with open(UPLOADED, encoding="utf-8") as fh:
            gl.nondet.web.pages[RAW] = fh.read()
        b.llm.at_quote = "def record_outcome"
        b.register(AGENT1, "Alpha Agent")
        b.register(AGENT2, "Beta Agent")
        title, job_spec, budget = campaign.JOB
        jid = b.tx(CLIENT, b.market, "post_job", title, job_spec, budget, b.w.now + 900)
        self.assertEqual(jid, "JB-1")
        p1, pitch1 = campaign.BID1
        p2, pitch2 = campaign.BID2
        bd1 = b.tx(AGENT1, b.market, "submit_bid", jid, p1, pitch1)
        bd2 = b.tx(AGENT2, b.market, "submit_bid", jid, p2, pitch2)

        def fit(prompt, mode, index):
            if "confirm record_outcome" in prompt:
                return {"fit": "STRONG_FIT", "pitch_quote": "confirm record_outcome", "spec_quote": "confirm that record_outcome exists", "reason": "on topic"}
            return {"fit": "POOR_FIT", "pitch_quote": "", "spec_quote": "", "reason": "generic"}

        b.llm.fit_override = fit
        self.assertEqual(b.tx(CLIENT, b.market, "assess_bid", bd1), "STRONG_FIT")
        self.assertEqual(b.tx(CLIENT, b.market, "assess_bid", bd2), "POOR_FIT")
        expect_raises(lambda: b.tx(CLIENT, b.market, "select_bid", jid, bd2), "only bids assessed as STRONG_FIT or PARTIAL_FIT")
        self.assertEqual(b.tx(CLIENT, b.market, "select_bid", jid, bd1), "AWARDED")
        self.assertEqual(b.view(b.registry, "get_agent_by_owner", str(AGENT1))["selections"], 1)
        t, d, s = campaign.AGREEMENT
        aid = b.tx(CLIENT, b.at, "create_agreement", t, d, s, str(AGENT1), "GEN", p1, b.w.now + DAY, campaign.REQS, "STRICT", "STANDARD", "JURY")
        self.assertEqual(p1 % GEN, 0)
        b.tx(CLIENT, b.at, "fund", aid, value=p1)
        self.assertEqual(b.tx(CLIENT, b.market, "link_agreement", jid, aid), "LINKED")
        b.tx(AGENT1, b.at, "accept", aid)
        b.tx(AGENT1, b.at, "start_work", aid)
        b.tx(AGENT1, b.at, "submit_deliverable", aid, campaign.STATEMENT, campaign.EVIDENCE)
        while b.view(b.at, "get_agreement", aid)["status"] == "DELIVERED":
            b.tx(AGENT1, b.at, "freeze_evidence", aid)
        b.tx(CLIENT, b.at, "verify_requirement", aid, "REQ-001")
        self.assertEqual(b.tx(CLIENT, b.at, "aggregate", aid), "PASS")
        self.assertEqual(b.tx(CLIENT, b.market, "sync_agreement", jid), "LINKED")
        b.w.advance(DAY + 1)
        self.assertEqual(b.tx(CLIENT, b.at, "settle", aid), "SETTLED")
        self.assertEqual(b.tx(CLIENT, b.market, "sync_agreement", jid), "CLOSED")
        self.assertEqual(b.tx(CLIENT, b.ledger, "record_outcome", aid), "COMPLETED")
        expect_raises(lambda: b.tx(CLIENT, b.ledger, "record_outcome", aid), "already recorded")
        p = b.view(b.ledger, "get_profile", str(AGENT1))
        self.assertEqual((p["completed"], p["qualified_completed"], p["market_completed"], p["score"], p["tier"]),
                         (1, 1, 1, 666, "ESTABLISHED"))
        self.assertEqual(b.w.failed_emits, [])

    def test_the_evidence_file_fits_the_agenttrust_item_limit(self):
        with open(UPLOADED, encoding="utf-8") as fh:
            self.assertLess(len(fh.read()), 20000)

    def test_the_generated_campaign_states_the_score_the_replay_produces(self):
        with open(os.path.join(ROOT, "docs", "LIVE_CAMPAIGN.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("score 666, tier ESTABLISHED", text)
        self.assertIn(campaign.COMMIT, text)
        json.loads(campaign.REQS)
        json.loads(campaign.EVIDENCE)


if __name__ == "__main__":
    unittest.main()
