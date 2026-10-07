# v0.2.16
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
import datetime
import re
from genlayer import *
from dataclasses import dataclass

PROTOCOL = "AgentBazaar.ReputationLedger"
PROTOCOL_VERSION = "1.0"

OUTCOME_STATES = {"SETTLED", "FINALIZED", "REFUNDED"}
K_COMPLETED = "COMPLETED"
K_COMPLETED_DISPUTE = "COMPLETED_AFTER_DISPUTE"
K_REFUNDED = "REFUNDED"
K_DISPUTED_LOST = "DISPUTED_LOST"
K_UNACCEPTED = "UNACCEPTED"

WEIGHT_UNIT = 10 ** 17
WEIGHT_CAP = 100
SCALE = 100
PRIOR = 20 * SCALE
NEG_FACTOR = 2
OFF_MARKET_PERCENT = 50
SCORE_MAX = 1000
MAX_PAGE_SIZE = 100
MAX_SCAN = 500
MAX_AMOUNT = 10 ** 30

_ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}\Z")
_AGREEMENT_RE = re.compile(r"^AT-[0-9]{1,9}\Z")
_JOB_RE = re.compile(r"^JB-[0-9]{1,9}\Z")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}\Z")
_ZERO_ADDR = "0x0000000000000000000000000000000000000000"


def _now() -> int:
    return int(datetime.datetime.now(datetime.timezone.utc).timestamp())


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _addr(value, name: str) -> str:
    if not isinstance(value, str) or not _ADDR_RE.match(value.strip()):
        raise Exception(name + " must be a 0x-prefixed 20-byte hex address")
    out = value.strip().lower()
    if out == _ZERO_ADDR:
        raise Exception(name + " must not be the zero address")
    return out


def _base_weight(amount: int) -> int:
    return min(WEIGHT_CAP, amount // WEIGHT_UNIT)


def _score(pos: int, neg: int) -> int:
    return (pos * SCORE_MAX) // (pos + neg + PRIOR)


def _success_bps(completed: int, refunded: int, lost: int) -> int:
    total = completed + refunded + lost
    if total == 0:
        return 0
    return (completed * 10000) // total


def _tier(known: int, score: int, completed: int, clients: int) -> str:
    if known == 0:
        return "NEW"
    if score >= 900 and completed >= 5 and clients >= 3:
        return "ELITE"
    if score >= 700 and completed >= 3 and clients >= 2:
        return "TRUSTED"
    if score >= 400:
        return "ESTABLISHED"
    return "EMERGING"


def _classify(status: str, amount: int, to_worker: int, to_buyer: int, accepted_at: int, funded: int) -> str:
    if status not in OUTCOME_STATES:
        raise Exception("agreement is not in a final outcome state: " + status)
    if funded != 1:
        raise Exception("agreement was never funded")
    if amount <= 0 or amount > MAX_AMOUNT or to_worker < 0 or to_buyer < 0 or to_worker + to_buyer != amount:
        raise Exception("agreement settlement does not add up to its amount")
    if status == "SETTLED":
        if to_worker != amount:
            raise Exception("a settled agreement must pay the worker in full")
        return K_COMPLETED
    if status == "FINALIZED":
        if to_worker == amount:
            return K_COMPLETED_DISPUTE
        if to_buyer == amount:
            return K_DISPUTED_LOST
        raise Exception("a finalized agreement must pay one side in full")
    if to_buyer != amount:
        raise Exception("a refunded agreement must refund the buyer in full")
    if accepted_at == 0:
        return K_UNACCEPTED
    return K_REFUNDED


@allow_storage
@dataclass
class Profile:
    address: str
    completed: u256
    qualified_completed: u256
    refunded: u256
    disputed_lost: u256
    disputed_won: u256
    unaccepted: u256
    market_completed: u256
    total_earned: u256
    total_volume: u256
    pos_points: u256
    neg_points: u256
    distinct_clients: u256
    first_at: u256
    last_at: u256


@allow_storage
@dataclass
class Outcome:
    agreement_id: str
    worker: str
    buyer: str
    amount: u256
    status: str
    kind: str
    via_market: u256
    job_id: str
    pair_index: u256
    points: u256
    recorded_at: u256
    recorder: str
    certificate_hash: str


class ReputationLedger(gl.Contract):
    profiles: TreeMap[str, Profile]
    outcomes: TreeMap[str, Outcome]
    market_links: TreeMap[str, str]
    pair_counts: TreeMap[str, u256]
    worker_items: TreeMap[str, str]
    worker_counts: TreeMap[str, u256]
    worker_list: DynArray[str]
    outcome_list: DynArray[str]
    owner: str
    agent_trust: str
    job_market: str
    wired: u256
    total_volume: u256

    def __init__(self):
        self.owner = str(gl.message.sender_address).lower()
        self.agent_trust = ""
        self.job_market = ""
        self.wired = u256(0)
        self.total_volume = u256(0)

    def _sender(self) -> str:
        return str(gl.message.sender_address).lower()

    def _need_wired(self) -> None:
        if int(self.wired) != 1:
            raise Exception("the ledger is not wired yet")

    def _profile_view(self, who: str) -> dict:
        p = self.profiles.get(who)
        if p is None:
            return {
                "address": who, "known": 0, "completed": 0, "refunded": 0, "disputed_lost": 0, "disputed_won": 0,
                "unaccepted": 0, "market_completed": 0, "qualified_completed": 0, "total_earned": "0", "total_volume": "0", "pos_points": 0,
                "neg_points": 0, "distinct_clients": 0, "score": 0, "success_bps": 0, "tier": "NEW", "first_at": 0,
                "last_at": 0, "outcome_count": 0,
            }
        pos = int(p.pos_points)
        neg = int(p.neg_points)
        score = _score(pos, neg)
        completed = int(p.completed)
        wc = self.worker_counts.get(str(p.address))
        return {
            "address": str(p.address), "known": 1, "completed": completed, "refunded": int(p.refunded),
            "disputed_lost": int(p.disputed_lost), "disputed_won": int(p.disputed_won), "unaccepted": int(p.unaccepted),
            "market_completed": int(p.market_completed), "qualified_completed": int(p.qualified_completed), "total_earned": str(int(p.total_earned)),
            "total_volume": str(int(p.total_volume)), "pos_points": pos, "neg_points": neg,
            "distinct_clients": int(p.distinct_clients), "score": score,
            "success_bps": _success_bps(completed, int(p.refunded), int(p.disputed_lost)),
            "tier": _tier(1, score, int(p.qualified_completed), int(p.distinct_clients)), "first_at": int(p.first_at), "last_at": int(p.last_at),
            "outcome_count": 0 if wc is None else int(wc),
        }

    def _outcome_dict(self, o: Outcome) -> dict:
        return {
            "agreement_id": str(o.agreement_id), "worker": str(o.worker), "buyer": str(o.buyer),
            "amount": str(int(o.amount)), "status": str(o.status), "kind": str(o.kind), "via_market": int(o.via_market),
            "job_id": str(o.job_id), "pair_index": int(o.pair_index), "points": int(o.points),
            "recorded_at": int(o.recorded_at), "recorder": str(o.recorder), "certificate_hash": str(o.certificate_hash),
        }

    @gl.public.write
    def set_wiring(self, agent_trust: str, job_market: str) -> str:
        if self._sender() != self.owner:
            raise Exception("only the contract owner can set the wiring")
        if int(self.wired) == 1:
            raise Exception("the ledger is already wired and cannot be changed")
        self.agent_trust = _addr(agent_trust, "agent_trust")
        self.job_market = _addr(job_market, "job_market")
        self.wired = u256(1)
        return "WIRED"

    @gl.public.write
    def mark_market_link(self, agreement_id: str, job_id: str) -> str:
        self._need_wired()
        if self._sender() != self.job_market:
            raise Exception("only the wired job market can mark a market link")
        if not isinstance(agreement_id, str) or not _AGREEMENT_RE.match(agreement_id):
            raise Exception("agreement_id must look like AT-1")
        if not isinstance(job_id, str) or not _JOB_RE.match(job_id):
            raise Exception("job_id must look like JB-1")
        if self.outcomes.get(agreement_id) is not None:
            raise Exception("the outcome of this agreement is already recorded")
        if self.market_links.get(agreement_id) is not None:
            raise Exception("this agreement is already linked to a job")
        self.market_links[agreement_id] = job_id
        return "LINKED"

    @gl.public.write
    def record_outcome(self, agreement_id: str) -> str:
        self._need_wired()
        if not isinstance(agreement_id, str) or not _AGREEMENT_RE.match(agreement_id):
            raise Exception("agreement_id must look like AT-1")
        if self.outcomes.get(agreement_id) is not None:
            raise Exception("outcome already recorded for " + agreement_id)
        raw = gl.get_contract_at(Address(self.agent_trust)).view().get_agreement(agreement_id)
        if not isinstance(raw, dict) or str(raw.get("agreement_id", "")) != agreement_id:
            raise Exception("AgentTrust returned an unexpected agreement record")
        worker = _addr(str(raw.get("worker", "")), "worker")
        buyer = _addr(str(raw.get("buyer", "")), "buyer")
        if worker == buyer:
            raise Exception("worker and buyer must differ")
        if str(raw.get("currency", "")) != "GEN":
            raise Exception("only GEN agreements are counted")
        amount = int(str(raw.get("amount", "0")))
        to_worker = int(str(raw.get("settle_worker", "0")))
        to_buyer = int(str(raw.get("settle_buyer", "0")))
        status = str(raw.get("status", ""))
        kind = _classify(status, amount, to_worker, to_buyer, int(raw.get("accepted_at", 0)), int(raw.get("funded", 0)))
        cert = str(raw.get("certificate_hash", ""))
        if not _HEX64_RE.match(cert):
            raise Exception("the agreement has no sealed certificate yet")
        link = self.market_links.get(agreement_id)
        via_market = 1 if link is not None else 0
        job_id = str(link) if link is not None else ""
        base = _base_weight(amount) * SCALE
        pair_key = worker + "|" + buyer
        pair_prev = self.pair_counts.get(pair_key)
        pair_index = (int(pair_prev) if pair_prev is not None else 0)
        pos = 0
        neg = 0
        earned = 0
        if (kind == K_COMPLETED or kind == K_COMPLETED_DISPUTE) and base > 0:
            pair_index += 1
            pos = base // pair_index
            if via_market == 0:
                pos = (pos * OFF_MARKET_PERCENT) // 100
        if kind == K_COMPLETED or kind == K_COMPLETED_DISPUTE:
            earned = to_worker
        elif kind == K_REFUNDED or kind == K_DISPUTED_LOST:
            neg = base * NEG_FACTOR
        now = _now()
        p = self.profiles.get(worker)
        if p is None:
            self.profiles[worker] = Profile(
                address=worker, completed=u256(0), qualified_completed=u256(0), refunded=u256(0), disputed_lost=u256(0), disputed_won=u256(0),
                unaccepted=u256(0), market_completed=u256(0), total_earned=u256(0), total_volume=u256(0),
                pos_points=u256(0), neg_points=u256(0), distinct_clients=u256(0), first_at=u256(now),
                last_at=u256(now),
            )
            self.worker_list.append(worker)
            p = self.profiles.get(worker)
        if kind == K_COMPLETED or kind == K_COMPLETED_DISPUTE:
            p.completed = u256(int(p.completed) + 1)
            if kind == K_COMPLETED_DISPUTE:
                p.disputed_won = u256(int(p.disputed_won) + 1)
            if via_market == 1:
                p.market_completed = u256(int(p.market_completed) + 1)
            if base > 0:
                p.qualified_completed = u256(int(p.qualified_completed) + 1)
                if pair_prev is None:
                    p.distinct_clients = u256(int(p.distinct_clients) + 1)
                self.pair_counts[pair_key] = u256(pair_index)
        elif kind == K_REFUNDED:
            p.refunded = u256(int(p.refunded) + 1)
        elif kind == K_DISPUTED_LOST:
            p.disputed_lost = u256(int(p.disputed_lost) + 1)
        else:
            p.unaccepted = u256(int(p.unaccepted) + 1)
        if kind != K_UNACCEPTED:
            p.total_volume = u256(int(p.total_volume) + amount)
        p.total_earned = u256(int(p.total_earned) + earned)
        p.pos_points = u256(int(p.pos_points) + pos)
        p.neg_points = u256(int(p.neg_points) + neg)
        p.last_at = u256(now)
        wc = self.worker_counts.get(worker)
        wn = 0 if wc is None else int(wc)
        self.worker_items[worker + "#" + str(wn)] = agreement_id
        self.worker_counts[worker] = u256(wn + 1)
        self.outcomes[agreement_id] = Outcome(
            agreement_id=agreement_id, worker=worker, buyer=buyer, amount=u256(amount), status=status, kind=kind,
            via_market=u256(via_market), job_id=job_id, pair_index=u256(pair_index), points=u256(pos),
            recorded_at=u256(now), recorder=self._sender(), certificate_hash=cert,
        )
        self.outcome_list.append(agreement_id)
        if kind != K_UNACCEPTED:
            self.total_volume = u256(int(self.total_volume) + amount)
        return kind

    @gl.public.view
    def get_info(self) -> dict:
        return {
            "protocol": PROTOCOL, "protocol_version": PROTOCOL_VERSION, "owner": str(self.owner),
            "agent_trust": str(self.agent_trust), "job_market": str(self.job_market), "wired": int(self.wired),
            "outcome_count": len(self.outcome_list), "agent_count": len(self.worker_list),
            "total_volume": str(int(self.total_volume)),
            "scoring": {
                "weight_unit": str(WEIGHT_UNIT), "weight_cap": WEIGHT_CAP, "scale": SCALE, "prior": PRIOR,
                "negative_factor": NEG_FACTOR, "off_market_percent": OFF_MARKET_PERCENT, "score_max": SCORE_MAX,
            },
        }

    @gl.public.view
    def get_profile(self, address: str) -> dict:
        return self._profile_view(str(address).strip().lower())

    @gl.public.view
    def get_score(self, address: str) -> int:
        return int(self._profile_view(str(address).strip().lower())["score"])

    @gl.public.view
    def get_outcome(self, agreement_id: str) -> dict:
        o = self.outcomes.get(str(agreement_id))
        if o is None:
            return {}
        return self._outcome_dict(o)

    @gl.public.view
    def outcome_count(self) -> int:
        return len(self.outcome_list)

    @gl.public.view
    def list_outcomes(self, offset: int, limit: int) -> list:
        if offset < 0 or limit < 1 or limit > MAX_PAGE_SIZE:
            raise Exception("offset must be >= 0 and limit between 1 and " + str(MAX_PAGE_SIZE))
        out = []
        index = len(self.outcome_list) - 1 - offset
        while index >= 0 and len(out) < limit:
            out.append(self._outcome_dict(self.outcomes.get(str(self.outcome_list[index]))))
            index -= 1
        return out

    @gl.public.view
    def list_agent_outcomes(self, address: str, offset: int, limit: int) -> list:
        if offset < 0 or limit < 1 or limit > MAX_PAGE_SIZE:
            raise Exception("offset must be >= 0 and limit between 1 and " + str(MAX_PAGE_SIZE))
        p = self.profiles.get(str(address).strip().lower())
        if p is None:
            return []
        who = str(p.address)
        wc = self.worker_counts.get(who)
        out = []
        pos = (0 if wc is None else int(wc)) - 1 - offset
        while pos >= 0 and len(out) < limit:
            out.append(self._outcome_dict(self.outcomes.get(str(self.worker_items.get(who + "#" + str(pos))))))
            pos -= 1
        return out

    @gl.public.view
    def list_leaderboard(self, limit: int) -> list:
        if limit < 1 or limit > MAX_PAGE_SIZE:
            raise Exception("limit must be between 1 and " + str(MAX_PAGE_SIZE))
        rows = []
        for i in range(min(len(self.worker_list), MAX_SCAN)):
            view = self._profile_view(str(self.worker_list[i]))
            rows.append((-int(view["score"]), -int(view["total_earned"]), -int(view["completed"]), view["address"], view))
        rows.sort(key=lambda r: (r[0], r[1], r[2], r[3]))
        out = []
        for r in rows[:limit]:
            entry = dict(r[4])
            entry["rank"] = len(out) + 1
            out.append(entry)
        return out
