import json

from tests._bootstrap import (FAKE_AT_PATH, GEN, LEDGER_PATH, MARKET_PATH, REAL_AT_PATH, REGISTRY_PATH, World, addr, gl)

OWNER = addr(0xA0)
CLIENT = addr(0xB1)
AGENT1 = addr(0xC1)
AGENT2 = addr(0xC2)
AGENT3 = addr(0xC3)
AGENT4 = addr(0xC4)
STRANGER = addr(0xD3)

PROFILE_BASE = "https://raw.githubusercontent.com/acme/agents/main/"
SHA = "ab" * 32

JOB_SPEC = (
    "Build a REST API service in Flask.\n"
    "The service must expose POST /users and GET /users/{id} endpoints.\n"
    "Every endpoint must require token authentication.\n"
    "Deliver unit tests covering the endpoints."
)
STRONG_PITCH = (
    "I will build the Flask service with POST /users and GET /users/{id} endpoints. "
    "I will add token authentication on every endpoint and ship unit tests for the endpoints."
)
PARTIAL_PITCH = "I can build the Flask service quickly and test it. Happy to start today."
POOR_PITCH = "I am a motivated professional with many years of experience and I love challenges."


def profile_page(owner, lines):
    return "# Agent profile\n\nOwner wallet: " + str(owner) + "\n\n" + "\n".join(lines) + "\n"


def words(text):
    out = []
    cur = ""
    for ch in text.lower():
        if ch.isalnum():
            cur += ch
        else:
            if cur:
                out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return out


def between(prompt, start, end):
    a = prompt.index(start)
    a = prompt.index(">>>\n", a) + 4
    b = prompt.index("\n<<<" + end, a)
    return prompt[a:b]


class MarketLLM:
    def __init__(self):
        self.registry_override = None
        self.fit_override = None
        self.at_verdict = "PASS"
        self.at_quote = ""
        self.calls = []

    def at_verifier(self, prompt):
        items = []
        for line in prompt.split("\n"):
            if line.startswith("<<<ITEM "):
                rest = line[len("<<<ITEM "):]
                items.append(json.loads(rest[rest.index("{"):rest.rindex("}") + 1])["evidence_id"])
        quotes = [{"evidence_id": items[0], "quote": self.at_quote}] if (items and self.at_quote and self.at_verdict == "PASS") else []
        return {"verdict": self.at_verdict, "quotes": quotes, "reason": "scripted AgentTrust verdict"}

    def __call__(self, prompt, mode, index):
        if "You are one independent verifier" in prompt:
            self.calls.append(("agenttrust", mode, index))
            return self.at_verifier(prompt)
        if "agent registry" in prompt:
            self.calls.append(("registry", mode, index))
            if self.registry_override is not None:
                return self.registry_override(prompt, mode, index)
            return self.registry(prompt)
        if "job market" in prompt:
            self.calls.append(("fit", mode, index))
            if self.fit_override is not None:
                return self.fit_override(prompt, mode, index)
            return self.fit(prompt)
        raise Exception("unexpected prompt in test LLM")

    @staticmethod
    def registry(prompt):
        page = between(prompt, "<<<PAGE ", "END_PAGE")
        head = prompt.split("CLAIMED CAPABILITIES:\n", 1)[1].split("\nA capability is supported", 1)[0]
        claims = []
        for line in head.split("\n"):
            idx, cap = line.split(": ", 1)
            quote = ""
            for page_line in page.split("\n"):
                if cap.lower() in page_line.lower() and page_line.strip().lower() != ("capabilities: " + cap).lower():
                    quote = page_line.strip()
                    break
            claims.append({"index": int(idx), "supported": quote != "", "quote": quote})
        return {"claims": claims, "reason": "scripted registry answer"}

    @staticmethod
    def fit(prompt):
        spec = between(prompt, "<<<SPEC ", "END_SPEC")
        pitch = between(prompt, "<<<PITCH ", "END_PITCH")
        spec_words = set(w for w in words(spec) if len(w) >= 5)
        shared = [w for w in words(pitch) if w in spec_words]
        shared_unique = sorted(set(shared))
        if len(shared_unique) >= 4:
            fit = "STRONG_FIT"
        elif len(shared_unique) >= 1:
            fit = "PARTIAL_FIT"
        else:
            fit = "POOR_FIT"
        pitch_quote = ""
        spec_quote = ""
        if shared_unique:
            word = shared_unique[0]
            for sentence in pitch.replace("\n", " ").split(". "):
                if word in words(sentence):
                    pitch_quote = sentence.strip().rstrip(".")
                    break
            for line in spec.split("\n"):
                if word in words(line):
                    spec_quote = line.strip()
                    break
        return {"fit": fit, "pitch_quote": pitch_quote, "spec_quote": spec_quote, "reason": "scripted fit answer"}


def at_record(agreement_id, buyer, worker, amount, status, **kw):
    rec = {
        "agreement_id": agreement_id, "buyer": str(buyer).lower(), "worker": str(worker).lower(), "title": "[JB-1] Build a REST API",
        "description": "Agreement for the REST API job.", "currency": "GEN", "amount": str(amount), "deadline": 1_800_000_000 + 90 * 86400,
        "created_at": 1_800_000_000 + 10, "status": status, "funded": 1, "accepted_at": 1_800_000_000 + 20,
        "settle_worker": "0", "settle_buyer": "0", "certificate_hash": "", "protocol_result": "",
    }
    if status == "SETTLED":
        rec["settle_worker"] = str(amount)
    elif status == "REFUNDED":
        rec["settle_buyer"] = str(amount)
    if status in ("SETTLED", "FINALIZED", "REFUNDED", "CANCELLED"):
        rec["certificate_hash"] = SHA
    rec.update(kw)
    return rec


class Bazaar:
    def __init__(self, validators=5, wire=True, real_at=False, market_path=MARKET_PATH):
        self.w = World(validators)
        self.llm = MarketLLM()
        gl.nondet.llm = self.llm
        self.registry = self.w.deploy(REGISTRY_PATH, "AgentRegistry", OWNER)
        self.ledger = self.w.deploy(LEDGER_PATH, "ReputationLedger", OWNER)
        self.market = self.w.deploy(market_path, "JobMarket", OWNER)
        if real_at:
            self.at = self.w.deploy(REAL_AT_PATH, "AgentTrust", OWNER)
        else:
            self.at = self.w.deploy(FAKE_AT_PATH, "FakeAgentTrust", OWNER)
        if wire:
            self.wire()

    def wire(self):
        self.w.tx(OWNER, self.market, "set_wiring", str(self.at), str(self.registry), str(self.ledger))
        self.w.tx(OWNER, self.ledger, "set_wiring", str(self.at), str(self.market))
        self.w.tx(OWNER, self.registry, "set_job_market", str(self.market))

    def tx(self, sender, handle, method, *args, **kw):
        return self.w.tx(sender, handle, method, *args, **kw)

    def view(self, handle, method, *args):
        return self.w.view(handle, method, *args)

    def put_at(self, record):
        self.w.tx(OWNER, self.at, "put", record["agreement_id"], json.dumps(record))

    def register(self, owner, name, caps=("code review", "python testing"), verify=True, page=None):
        url = PROFILE_BASE + name.lower().replace(" ", "-") + ".md"
        lines = ["I offer " + c + " for open source projects." for c in caps]
        gl.nondet.web.pages[url] = page if page is not None else profile_page(owner, lines)
        aid = self.tx(owner, self.registry, "register_agent", name, url, ", ".join(caps))
        if verify:
            self.tx(STRANGER, self.registry, "verify_claims", aid)
        return aid

    def post_job(self, client=CLIENT, budget=10 * GEN, window=6 * 3600, title="Build a REST API", spec=JOB_SPEC):
        return self.tx(client, self.market, "post_job", title, spec, budget, self.w.now + window)

    def bid(self, bidder, job_id, price=5 * GEN, pitch=STRONG_PITCH, assess=True):
        bid_id = self.tx(bidder, self.market, "submit_bid", job_id, price, pitch)
        if assess:
            self.tx(STRANGER, self.market, "assess_bid", bid_id)
        return bid_id
