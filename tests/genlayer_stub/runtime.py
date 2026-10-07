import copy
import json

from .storage import Address, DynArray, TreeMap, coerce, u256


class NondetConsensusError(Exception):
    pass


class _Return:
    def __init__(self, calldata):
        self.calldata = calldata


def _calldata(value, path="value"):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, str):
        return str(value)
    if isinstance(value, bytes):
        return value
    if isinstance(value, (list, tuple)):
        return [_calldata(v, path + "[]") for v in value]
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise TypeError("[stub] calldata dict keys must be str at " + path)
            out[str(k)] = _calldata(v, path + "." + k)
        return out
    raise TypeError("[stub] value of type %s cannot be encoded as calldata at %s" % (type(value).__name__, path))


class Contract:
    def __new__(cls, *args, **kwargs):
        instance = object.__new__(cls)
        hints = {}
        for klass in reversed(cls.__mro__):
            for name, annotation in getattr(klass, "__annotations__", {}).items():
                hints[name] = annotation
        object.__setattr__(instance, "_gl_hints", hints)
        for name, annotation in hints.items():
            if isinstance(annotation, type) and issubclass(annotation, (TreeMap, DynArray)):
                object.__setattr__(instance, name, annotation())
        return instance

    def __setattr__(self, name, value):
        hints = object.__getattribute__(self, "_gl_hints")
        if name in hints:
            if gl.nondet.mode is not None:
                raise Exception("[stub] contract storage written inside a non-deterministic block: " + name)
            value = coerce(type(self).__name__, name, hints[name], value)
        object.__setattr__(self, name, value)

    def __getattribute__(self, name):
        if gl.nondet.mode is not None and not name.startswith("__") and name != "_gl_hints":
            raise Exception("[stub] self." + name + " used inside a non-deterministic block: leader/validator functions must not capture self")
        return object.__getattribute__(self, name)


class _Message:
    def __init__(self):
        self.sender_address = Address("0x00000000000000000000000000000000000000a1")
        self.value = u256(0)


class _VM:
    NondetConsensusError = NondetConsensusError
    Return = _Return

    def __init__(self):
        self.validators = 5
        self.validator_runs = 0
        self.rounds = 0
        self._forced = None

    def force_leader_result(self, value):
        self._forced = (value,)

    def run_nondet_unsafe(self, leader_fn, validator_fn):
        nd = gl.nondet
        self.rounds += 1
        nd._enter("leader", 0)
        try:
            if self._forced is not None:
                leader_result = self._forced[0]
                self._forced = None
            else:
                leader_result = leader_fn()
        finally:
            nd._exit()
        leader_result = _calldata(leader_result, "leader result")
        agree = 0
        for i in range(self.validators):
            nd._enter("validator", i)
            try:
                ok = validator_fn(_Return(copy.deepcopy(leader_result)))
            except Exception:
                ok = False
            finally:
                nd._exit()
            self.validator_runs += 1
            if ok is True:
                agree += 1
        if agree * 2 <= self.validators:
            raise NondetConsensusError("validators rejected the leader result (%d/%d agreed)" % (agree, self.validators))
        return leader_result


def default_comparator(leader, mine, principle):
    try:
        a = json.loads(leader)
        b = json.loads(mine)
        if isinstance(a, dict) and isinstance(b, dict) and "fit" in a and "fit" in b:
            return a["fit"] == b["fit"]
    except Exception:
        pass
    return leader == mine


class _EqPrinciple:
    def __init__(self):
        self._force_fail_once = False
        self.comparator = default_comparator
        self.principles = []

    def force_fail_next(self):
        self._force_fail_once = True

    def _run(self, fn, same):
        if self._force_fail_once:
            self._force_fail_once = False
            raise NondetConsensusError("forced disagreement (test)")
        nd = gl.nondet
        nd._enter("leader", 0)
        try:
            leader_value = _calldata(fn(), "leader result")
        finally:
            nd._exit()
        agree = 0
        for i in range(gl.vm.validators):
            nd._enter("validator", i)
            try:
                ok = same(leader_value, fn())
            except Exception:
                ok = False
            finally:
                nd._exit()
            if ok:
                agree += 1
        if agree * 2 <= gl.vm.validators:
            raise NondetConsensusError("validators saw a different value (%d/%d agreed)" % (agree, gl.vm.validators))
        return leader_value

    def strict_eq(self, fn):
        return self._run(fn, lambda leader, mine: leader == mine)

    def prompt_comparative(self, fn, principle=None):
        if not isinstance(principle, str) or not principle.strip():
            raise TypeError("[stub] prompt_comparative needs a non-empty principle= string")
        self.principles.append(principle)
        return self._run(fn, lambda leader, mine: self.comparator(leader, mine, principle))


class _Response:
    def __init__(self, status, body):
        self.status = status
        self.body = body


class Sequence:
    def __init__(self, *bodies):
        self.bodies = list(bodies)
        self.calls = 0

    def next(self):
        body = self.bodies[min(self.calls, len(self.bodies) - 1)]
        self.calls += 1
        return body


class _Web:
    def __init__(self):
        self.pages = {}
        self.statuses = {}
        self.calls = []
        self.handlers = []

    def _body(self, url):
        for prefix, fn in self.handlers:
            if url.startswith(prefix) and url not in self.pages:
                return fn(url)
        page = self.pages[url]
        return page.next() if isinstance(page, Sequence) else page

    def _known(self, url):
        return url in self.pages or any(url.startswith(p) for p, _ in self.handlers)

    def render(self, url, mode="text"):
        if gl.nondet.mode is None:
            raise Exception("[stub] web access outside a non-deterministic block")
        self.calls.append(("render", url))
        if not self._known(url):
            raise Exception("[stub] no page registered for url: " + url)
        return self._body(url)

    def get(self, url, headers=None):
        if gl.nondet.mode is None:
            raise Exception("[stub] web access outside a non-deterministic block")
        self.calls.append(("get", url))
        if not self._known(url):
            raise Exception("[stub] no page registered for url: " + url)
        return _Response(self.statuses.get(url, 200), self._body(url).encode("utf-8"))


class _Nondet:
    def __init__(self):
        self.web = _Web()
        self.llm = None
        self.prompts = []
        self.mode = None
        self.index = 0
        self._stack = []

    def _enter(self, mode, index):
        self._stack.append((self.mode, self.index))
        self.mode, self.index = mode, index

    def _exit(self):
        self.mode, self.index = self._stack.pop()

    def exec_prompt(self, prompt, response_format=None, images=None):
        if self.mode is None:
            raise Exception("[stub] exec_prompt outside a non-deterministic block")
        self.prompts.append(prompt)
        if self.llm is None:
            raise Exception("[stub] exec_prompt called but no LLM handler is installed")
        out = self.llm(prompt, self.mode, self.index)
        return copy.deepcopy(out)


def _view(fn):
    fn._gl_kind = "view"
    return fn


def _write(fn):
    fn._gl_kind = "write"
    return fn


def _payable(fn):
    fn._gl_kind = "write"
    fn._gl_payable = True
    return fn


class _WriteDecorator:
    payable = staticmethod(_payable)

    def __call__(self, fn):
        return _write(fn)


class _Public:
    write = _WriteDecorator()
    view = staticmethod(_view)


class _ViewProxy:
    def __init__(self, address):
        self._address = address

    def __getattr__(self, name):
        address = self._address

        def call(*args, **kwargs):
            instance = gl.contracts.get(address)
            if instance is None:
                raise Exception("[stub] no contract is deployed at " + address)
            fn = getattr(type(instance), name, None)
            if fn is None or getattr(fn, "_gl_kind", None) != "view":
                raise Exception("[stub] " + name + " is not a view method of the contract at " + address)
            args = _calldata(list(args), "view arguments")
            kwargs = _calldata(kwargs, "view arguments")
            before = copy.deepcopy({k: v for k, v in instance.__dict__.items() if not k.startswith("_gl_")})
            saved = (gl.message.sender_address, gl.message.value)
            gl.message.sender_address = Address(gl.stack[-1] if gl.stack else str(gl.message.sender_address))
            gl.message.value = u256(0)
            gl.stack.append(address)
            try:
                result = getattr(instance, name)(*args, **kwargs)
            finally:
                gl.stack.pop()
                gl.message.sender_address, gl.message.value = saved
            after = {k: v for k, v in instance.__dict__.items() if not k.startswith("_gl_")}
            if after != before:
                raise AssertionError("[stub] view " + name + " mutated the state of the contract at " + address)
            return _calldata(result, "view result")

        return call


class _EmitProxy:
    def __init__(self, address):
        self._address = address

    def __getattr__(self, name):
        address = self._address

        def call(*args, **kwargs):
            instance = gl.contracts.get(address)
            if instance is None:
                raise Exception("[stub] no contract is deployed at " + address)
            fn = getattr(type(instance), name, None)
            if fn is None or getattr(fn, "_gl_kind", None) != "write":
                raise Exception("[stub] " + name + " is not a write method of the contract at " + address)
            sender = gl.stack[-1] if gl.stack else str(gl.message.sender_address)
            gl.emitted.append({"sender": sender, "target": address, "method": name,
                               "args": _calldata(list(args), "emit arguments"), "kwargs": _calldata(kwargs, "emit arguments")})
            return None

        return call


class _ContractHandle:
    def __init__(self, address):
        self.address = str(address).lower()

    def view(self):
        return _ViewProxy(self.address)

    def emit(self, on=None):
        if on not in ("accepted", "finalized"):
            raise TypeError("[stub] emit(on=...) must be 'accepted' or 'finalized'")
        return _EmitProxy(self.address)

    def emit_transfer(self, value=0, on=None):
        if on is not None:
            raise TypeError("SystemError: 2: inval (emit_transfer to an EOA takes only value=)")
        source = gl.stack[-1] if gl.stack else ""
        gl.transfers.append((self.address, int(value), source))


class _GL:
    def __init__(self):
        self.Contract = Contract
        self.message = _Message()
        self.vm = _VM()
        self.eq_principle = _EqPrinciple()
        self.nondet = _Nondet()
        self.public = _Public()
        self.contracts = {}
        self.stack = []
        self.emitted = []
        self.transfers = []

    def get_contract_at(self, address):
        return _ContractHandle(address)


gl = _GL()
