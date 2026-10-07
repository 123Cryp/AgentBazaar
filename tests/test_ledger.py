import json
import unittest

from tests._bootstrap import GEN, addr, expect_raises
from tests.support.scenario import AGENT1, AGENT2, AGENT3, CLIENT, OWNER, SHA, STRANGER, Bazaar, at_record

UNIT = 10 ** 17


class LedgerBase(unittest.TestCase):
    def setUp(self):
        self.b = Bazaar()
        self.led = self.b.ledger
        self.n = 0

    def new_id(self):
        self.n += 1
        return "AT-" + str(self.n)

    def record(self, status, amount=1 * GEN, worker=AGENT1, buyer=CLIENT, sender=STRANGER, aid=None, **kw):
        aid = aid or self.new_id()
        self.b.put_at(at_record(aid, buyer, worker, amount, status, **kw))
        return aid, self.b.tx(sender, self.led, "record_outcome", aid)

    def profile(self, who=AGENT1):
        return self.b.view(self.led, "get_profile", str(who))

    def link(self, aid, job="JB-1"):
        return self.b.tx(self.b.market, self.led, "mark_market_link", aid, job)


class ClassificationTests(LedgerBase):
    def test_settled_is_a_completed_job(self):
        aid, kind = self.record("SETTLED", 2 * GEN)
        self.assertEqual(kind, "COMPLETED")
        p = self.profile()
        self.assertEqual((p["completed"], p["refunded"], p["disputed_lost"], p["unaccepted"]), (1, 0, 0, 0))
        self.assertEqual((p["total_earned"], p["total_volume"], p["known"]), (str(2 * GEN), str(2 * GEN), 1))
        o = self.b.view(self.led, "get_outcome", aid)
        self.assertEqual((o["kind"], o["worker"], o["buyer"], o["amount"], o["status"], o["via_market"]),
                         ("COMPLETED", str(AGENT1), str(CLIENT), str(2 * GEN), "SETTLED", 0))
        self.assertEqual(o["certificate_hash"], SHA)

    def test_finalized_in_favour_of_the_worker_counts_as_completed_after_dispute(self):
        aid, kind = self.record("FINALIZED", settle_worker=str(GEN), settle_buyer="0")
        self.assertEqual(kind, "COMPLETED_AFTER_DISPUTE")
        p = self.profile()
        self.assertEqual((p["completed"], p["disputed_won"], p["disputed_lost"], p["total_earned"]), (1, 1, 0, str(GEN)))

    def test_finalized_in_favour_of_the_buyer_is_a_lost_dispute(self):
        aid, kind = self.record("FINALIZED", settle_worker="0", settle_buyer=str(GEN))
        self.assertEqual(kind, "DISPUTED_LOST")
        p = self.profile()
        self.assertEqual((p["completed"], p["disputed_lost"], p["total_earned"], p["total_volume"]), (0, 1, "0", str(GEN)))
        self.assertGreater(p["neg_points"], 0)

    def test_refund_after_acceptance_is_a_failure(self):
        aid, kind = self.record("REFUNDED")
        self.assertEqual(kind, "REFUNDED")
        p = self.profile()
        self.assertEqual((p["refunded"], p["completed"], p["neg_points"], p["success_bps"]), (1, 0, 10 * 100 * 2, 0))

    def test_refund_before_acceptance_does_not_penalise_the_worker(self):
        aid, kind = self.record("REFUNDED", accepted_at=0)
        self.assertEqual(kind, "UNACCEPTED")
        p = self.profile()
        self.assertEqual((p["unaccepted"], p["refunded"], p["neg_points"], p["pos_points"], p["score"], p["total_volume"], p["success_bps"]),
                         (1, 0, 0, 0, 0, "0", 0))
        self.assertEqual(self.b.view(self.led, "get_info")["total_volume"], "0")

    def test_non_final_or_unfunded_agreements_are_rejected(self):
        for status in ("CREATED", "FUNDED", "ACCEPTED", "IN_PROGRESS", "DELIVERED", "VERIFICATION_PENDING", "VERIFIED_PASS",
                       "VERIFIED_FAIL", "INSUFFICIENT_EVIDENCE", "DISPUTED", "CHALLENGE", "FINAL_REVIEW", "TIMEOUT", "CANCELLED"):
            expect_raises(lambda status=status: self.record(status, certificate_hash=SHA), "not in a final outcome state")
        expect_raises(lambda: self.record("SETTLED", funded=0), "never funded")
        self.assertEqual(self.b.view(self.led, "get_info")["outcome_count"], 0)

    def test_inconsistent_settlements_are_rejected(self):
        expect_raises(lambda: self.record("SETTLED", settle_worker=str(GEN // 2), settle_buyer=str(GEN // 2)), "pay the worker in full")
        expect_raises(lambda: self.record("SETTLED", settle_worker=str(2 * GEN)), "does not add up")
        expect_raises(lambda: self.record("REFUNDED", settle_worker=str(GEN // 2), settle_buyer=str(GEN // 2)), "refund the buyer in full")
        expect_raises(lambda: self.record("FINALIZED", settle_worker=str(GEN // 2), settle_buyer=str(GEN // 2)), "one side in full")
        expect_raises(lambda: self.record("SETTLED", amount=0, settle_worker="0"), "does not add up")
        expect_raises(lambda: self.record("SETTLED", amount=10 ** 31, settle_worker=str(10 ** 31)), "does not add up")

    def test_other_record_defects_are_rejected(self):
        expect_raises(lambda: self.record("SETTLED", certificate_hash=""), "no sealed certificate")
        expect_raises(lambda: self.record("SETTLED", certificate_hash="XYZ"), "no sealed certificate")
        expect_raises(lambda: self.record("SETTLED", currency="USD"), "only GEN")
        expect_raises(lambda: self.record("SETTLED", worker=CLIENT, buyer=CLIENT), "must differ")
        rec = at_record("AT-5", CLIENT, AGENT1, GEN, "SETTLED")
        rec["agreement_id"] = "AT-99"
        self.b.tx(OWNER, self.b.at, "put", "AT-5", json.dumps(rec))
        expect_raises(lambda: self.b.tx(STRANGER, self.led, "record_outcome", "AT-5"), "unexpected agreement record")

    def test_unknown_agreement_and_bad_ids(self):
        expect_raises(lambda: self.b.tx(STRANGER, self.led, "record_outcome", "AT-404"), "unknown agreement_id")
        for bad in ("at-1", "AT-", "AT-1; DROP", "1", "", "AT-1234567890"):
            expect_raises(lambda bad=bad: self.b.tx(STRANGER, self.led, "record_outcome", bad), "must look like AT-1")


class AntiGamingTests(LedgerBase):
    def test_an_outcome_can_be_recorded_only_once(self):
        aid, _ = self.record("SETTLED")
        before = self.profile()
        expect_raises(lambda: self.b.tx(STRANGER, self.led, "record_outcome", aid), "already recorded")
        expect_raises(lambda: self.b.tx(AGENT1, self.led, "record_outcome", aid), "already recorded")
        self.assertEqual(self.profile(), before)

    def test_the_caller_cannot_influence_the_recorded_data(self):
        results = []
        for i, sender in enumerate((AGENT1, CLIENT, STRANGER, OWNER)):
            b = Bazaar()
            b.put_at(at_record("AT-1", CLIENT, AGENT1, 3 * GEN, "SETTLED"))
            b.tx(sender, b.ledger, "record_outcome", "AT-1")
            o = b.view(b.ledger, "get_outcome", "AT-1")
            o.pop("recorder")
            results.append((o, b.view(b.ledger, "get_profile", str(AGENT1))))
        self.assertTrue(all(r == results[0] for r in results))
        self.assertEqual(results[0][1]["completed"], 1)

    def test_recording_requires_wiring_and_the_wiring_is_one_time_owner_only(self):
        b = Bazaar(wire=False)
        b.put_at(at_record("AT-1", CLIENT, AGENT1, GEN, "SETTLED"))
        expect_raises(lambda: b.tx(STRANGER, b.ledger, "record_outcome", "AT-1"), "not wired")
        expect_raises(lambda: b.tx(STRANGER, b.ledger, "set_wiring", str(b.at), str(b.market)), "only the contract owner")
        expect_raises(lambda: b.tx(OWNER, b.ledger, "set_wiring", "0x0000000000000000000000000000000000000000", str(b.market)), "zero address")
        b.tx(OWNER, b.ledger, "set_wiring", str(b.at), str(b.market))
        expect_raises(lambda: b.tx(OWNER, b.ledger, "set_wiring", str(b.at), str(b.market)), "already wired")
        self.assertEqual(b.tx(STRANGER, b.ledger, "record_outcome", "AT-1"), "COMPLETED")

    def test_only_the_wired_market_can_mark_links(self):
        for caller in (STRANGER, OWNER, AGENT1, CLIENT, self.b.at):
            expect_raises(lambda caller=caller: self.b.tx(caller, self.led, "mark_market_link", "AT-1", "JB-1"), "only the wired job market")
        b = Bazaar(wire=False)
        expect_raises(lambda: b.tx(STRANGER, b.ledger, "mark_market_link", "AT-1", "JB-1"), "not wired")

    def test_mark_market_link_validates_and_cannot_be_repeated_or_late(self):
        expect_raises(lambda: self.link("at-1"), "must look like AT-1")
        expect_raises(lambda: self.link("AT-1", "job1"), "must look like JB-1")
        self.assertEqual(self.link("AT-1"), "LINKED")
        expect_raises(lambda: self.link("AT-1", "JB-2"), "already linked")
        aid, _ = self.record("SETTLED", aid="AT-2")
        expect_raises(lambda: self.link("AT-2"), "already recorded")

    def test_market_origin_is_read_from_the_link_not_from_the_caller(self):
        self.link("AT-1", "JB-5")
        aid, kind = self.record("SETTLED", aid="AT-1", sender=AGENT1)
        o = self.b.view(self.led, "get_outcome", "AT-1")
        self.assertEqual((o["via_market"], o["job_id"]), (1, "JB-5"))
        self.assertEqual(self.profile()["market_completed"], 1)

    def test_dust_jobs_carry_no_weight(self):
        for i in range(30):
            self.record("SETTLED", amount=UNIT - 1, buyer=addr(0x5000 + i))
        p = self.profile()
        self.assertEqual((p["completed"], p["pos_points"], p["score"]), (30, 0, 0))

    def test_splitting_money_into_many_small_jobs_never_beats_one_job(self):
        def points_for(amounts):
            b = Bazaar()
            for i, amount in enumerate(amounts):
                aid = "AT-%d" % (i + 1)
                b.put_at(at_record(aid, addr(0x6000 + i), AGENT1, amount, "SETTLED"))
                b.tx(b.market, b.ledger, "mark_market_link", aid, "JB-1")
                b.tx(STRANGER, b.ledger, "record_outcome", aid)
            return b.view(b.ledger, "get_profile", str(AGENT1))["pos_points"]

        for whole in (3 * GEN, 4 * GEN, 7 * GEN + 12345, 9 * GEN):
            single = points_for([whole])
            for parts in (2, 3, 5, 10, 40):
                self.assertLessEqual(points_for([whole // parts] * parts), single, (whole, parts))

    def test_dust_farming_with_many_clients_earns_nothing(self):
        farm = Bazaar()
        for i in range(40):
            aid = "AT-%d" % (i + 1)
            farm.put_at(at_record(aid, addr(0x6500 + i), AGENT1, UNIT - 1, "SETTLED"))
            farm.tx(farm.market, farm.ledger, "mark_market_link", aid, "JB-1")
            farm.tx(STRANGER, farm.ledger, "record_outcome", aid)
        p = farm.view(farm.ledger, "get_profile", str(AGENT1))
        self.assertEqual((p["completed"], p["pos_points"], p["score"], p["tier"]), (40, 0, 0, "EMERGING"))

    def test_many_clients_do_not_unlock_top_tiers_without_diversity(self):
        b = Bazaar()
        for i in range(6):
            aid = "AT-%d" % (i + 1)
            b.put_at(at_record(aid, CLIENT, AGENT1, 100 * GEN, "SETTLED"))
            b.tx(b.market, b.ledger, "mark_market_link", aid, "JB-1")
            b.tx(STRANGER, b.ledger, "record_outcome", aid)
        p = b.view(b.ledger, "get_profile", str(AGENT1))
        self.assertEqual((p["completed"], p["distinct_clients"], p["tier"]), (6, 1, "ESTABLISHED"))

    def test_repeat_business_with_one_client_decays(self):
        points = []
        for i in range(4):
            self.link("AT-%d" % (i + 1), "JB-1")
            self.record("SETTLED", amount=1 * GEN, aid="AT-%d" % (i + 1))
            points.append(self.b.view(self.led, "get_outcome", "AT-%d" % (i + 1))["points"])
        self.assertEqual(points, [1000, 500, 333, 250])
        p = self.profile()
        self.assertEqual((p["completed"], p["distinct_clients"], p["pos_points"]), (4, 1, sum(points)))

    def test_distinct_clients_each_count_in_full(self):
        for i in range(3):
            self.link("AT-%d" % (i + 1), "JB-1")
            self.record("SETTLED", amount=1 * GEN, buyer=addr(0x7000 + i), aid="AT-%d" % (i + 1))
        p = self.profile()
        self.assertEqual((p["distinct_clients"], p["pos_points"]), (3, 3000))

    def test_off_market_outcomes_count_half(self):
        aid, _ = self.record("SETTLED", amount=1 * GEN)
        self.assertEqual(self.b.view(self.led, "get_outcome", aid)["points"], 500)
        self.assertEqual(self.profile()["market_completed"], 0)

    def test_failures_cost_double_and_are_not_decayed(self):
        self.link("AT-1")
        self.record("SETTLED", aid="AT-1")
        self.record("REFUNDED", aid="AT-2")
        self.record("REFUNDED", aid="AT-3")
        p = self.profile()
        self.assertEqual((p["neg_points"], p["pos_points"], p["refunded"]), (2 * 2000, 1000, 2))
        self.assertEqual(p["score"], 1000 * 1000 // (1000 + 4000 + 2000))
        self.assertEqual(p["success_bps"], 3333)


class ScoreTests(LedgerBase):
    def test_score_formula_and_weight_table(self):
        table = {UNIT - 1: 0, UNIT: 1, 4 * UNIT: 4, 1 * GEN: 10, 10 * GEN: 100, 1000 * GEN: 100, 10 ** 24: 100}
        for amount, weight in table.items():
            b = Bazaar()
            b.put_at(at_record("AT-1", CLIENT, AGENT1, amount, "SETTLED"))
            b.tx(b.market, b.ledger, "mark_market_link", "AT-1", "JB-1")
            b.tx(STRANGER, b.ledger, "record_outcome", "AT-1")
            p = b.view(b.ledger, "get_profile", str(AGENT1))
            self.assertEqual(p["pos_points"], weight * 100, amount)
            self.assertEqual(p["score"], weight * 100 * 1000 // (weight * 100 + 2000))

    def test_score_is_bounded_and_monotonic_in_successes(self):
        last = -1
        for i in range(12):
            self.link("AT-%d" % (i + 1))
            self.record("SETTLED", amount=100 * GEN, buyer=addr(0x8000 + i), aid="AT-%d" % (i + 1))
            score = self.profile()["score"]
            self.assertGreater(score, last)
            self.assertLess(score, 1000)
            last = score

    def test_tiers(self):
        def tier_after(n_jobs, amount, status="SETTLED"):
            b = Bazaar()
            for i in range(n_jobs):
                b.put_at(at_record("AT-%d" % (i + 1), addr(0x9000 + i), AGENT1, amount, status))
                b.tx(b.market, b.ledger, "mark_market_link", "AT-%d" % (i + 1), "JB-1")
                b.tx(STRANGER, b.ledger, "record_outcome", "AT-%d" % (i + 1))
            return b.view(b.ledger, "get_profile", str(AGENT1))

        self.assertEqual(self.profile(AGENT3)["tier"], "NEW")
        self.assertEqual(tier_after(1, 1 * GEN)["tier"], "EMERGING")
        self.assertEqual(tier_after(1, 100 * GEN)["tier"], "ESTABLISHED")
        self.assertEqual(tier_after(3, 100 * GEN)["tier"], "TRUSTED")
        self.assertEqual(tier_after(5, 100 * GEN)["tier"], "ELITE")
        self.assertEqual(tier_after(1, 100 * GEN, "REFUNDED")["tier"], "EMERGING")

    def test_unknown_address_has_a_zero_profile(self):
        p = self.profile(STRANGER)
        self.assertEqual((p["known"], p["score"], p["completed"], p["tier"], p["total_earned"]), (0, 0, 0, "NEW", "0"))
        self.assertEqual(self.b.view(self.led, "get_score", str(STRANGER)), 0)


class ViewTests(LedgerBase):
    def test_leaderboard_orders_by_score_then_earnings(self):
        for who, jobs in ((AGENT1, 1), (AGENT2, 3), (AGENT3, 2)):
            for j in range(jobs):
                aid = self.new_id()
                self.link(aid)
                self.record("SETTLED", amount=10 * GEN, worker=who, buyer=addr(0xA000 + self.n), aid=aid)
        rows = self.b.view(self.led, "list_leaderboard", 10)
        self.assertEqual([r["address"] for r in rows], [str(AGENT2), str(AGENT3), str(AGENT1)])
        self.assertEqual([r["rank"] for r in rows], [1, 2, 3])
        self.assertEqual(len(self.b.view(self.led, "list_leaderboard", 2)), 2)
        for bad in (0, 101):
            expect_raises(lambda bad=bad: self.b.view(self.led, "list_leaderboard", bad), "limit")

    def test_leaderboard_tie_break_is_deterministic(self):
        for who in (AGENT3, AGENT1, AGENT2):
            aid = self.new_id()
            self.link(aid)
            self.record("SETTLED", amount=10 * GEN, worker=who, buyer=addr(0xB000 + self.n), aid=aid)
        rows = self.b.view(self.led, "list_leaderboard", 10)
        self.assertEqual([r["address"] for r in rows], sorted([str(AGENT1), str(AGENT2), str(AGENT3)]))

    def test_outcome_listing_and_paging(self):
        ids = [self.record("SETTLED", amount=GEN, buyer=addr(0xC000 + i))[0] for i in range(5)]
        page = self.b.view(self.led, "list_outcomes", 0, 3)
        self.assertEqual([o["agreement_id"] for o in page], ids[::-1][:3])
        self.assertEqual([o["agreement_id"] for o in self.b.view(self.led, "list_outcomes", 3, 10)], ids[::-1][3:])
        self.assertEqual(self.b.view(self.led, "list_outcomes", 9, 10), [])
        mine = self.b.view(self.led, "list_agent_outcomes", str(AGENT1), 1, 2)
        self.assertEqual([o["agreement_id"] for o in mine], ids[::-1][1:3])
        self.assertEqual(self.b.view(self.led, "list_agent_outcomes", str(STRANGER), 0, 5), [])
        self.assertEqual(self.b.view(self.led, "get_outcome", "AT-404"), {})
        self.assertEqual(self.b.view(self.led, "outcome_count"), 5)
        for args in ((-1, 5), (0, 0), (0, 101)):
            expect_raises(lambda args=args: self.b.view(self.led, "list_outcomes", *args), "limit")
            expect_raises(lambda args=args: self.b.view(self.led, "list_agent_outcomes", str(AGENT1), *args), "limit")

    def test_info_reports_the_scoring_parameters(self):
        info = self.b.view(self.led, "get_info")
        self.assertEqual((info["wired"], info["agent_trust"], info["job_market"]), (1, str(self.b.at), str(self.b.market)))
        self.assertEqual(info["scoring"]["prior"], 2000)
        self.assertEqual(info["scoring"]["off_market_percent"], 50)


if __name__ == "__main__":
    unittest.main()
