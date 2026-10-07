import copy
import dataclasses

_CACHE = {}


class Address(str):
    pass


class u256(int):
    def __new__(cls, value=0):
        v = int(value)
        if v < 0 or v >= 2 ** 256:
            raise OverflowError("[stub] u256 out of range: " + str(v))
        return super().__new__(cls, v)


def _generic(cls, item):
    args = item if isinstance(item, tuple) else (item,)
    key = (cls, args)
    if key not in _CACHE:
        _CACHE[key] = type(cls.__name__, (cls,), {"_args": args})
    return _CACHE[key]


def _check_type(where, expected, value):
    if expected is str:
        if not isinstance(value, str):
            raise TypeError("[stub] %s expects str, got %s" % (where, type(value).__name__))
    elif expected is u256:
        if not isinstance(value, u256):
            raise TypeError("[stub] %s expects u256(...), got %s: wrap the value in u256()" % (where, type(value).__name__))
    elif isinstance(expected, type) and getattr(expected, "_gl_storage", False):
        if not isinstance(value, expected):
            raise TypeError("[stub] %s expects %s, got %s" % (where, expected.__name__, type(value).__name__))


class TreeMap:
    _args = ()

    def __class_getitem__(cls, item):
        return _generic(cls, item)

    def __init__(self):
        self._d = {}

    def _key(self, key):
        if self._args and self._args[0] is str and not isinstance(key, str):
            raise TypeError("[stub] TreeMap key must be str, got " + type(key).__name__)
        return key

    def get(self, key):
        return self._d.get(self._key(key))

    def __getitem__(self, key):
        return self._d[self._key(key)]

    def __setitem__(self, key, value):
        key = self._key(key)
        if len(self._args) > 1:
            _check_type("TreeMap value", self._args[1], value)
        if getattr(type(value), "_gl_storage", False):
            value = copy.deepcopy(value)
        self._d[key] = value

    def __eq__(self, other):
        return isinstance(other, TreeMap) and self._d == other._d

    __hash__ = None

    def __len__(self):
        raise TypeError("[stub] len(TreeMap) has not been proven to work live; keep a DynArray of keys instead")

    def __iter__(self):
        raise TypeError("[stub] iterating a TreeMap has not been proven to work live; keep a DynArray of keys instead")

    def __contains__(self, key):
        raise TypeError("[stub] 'in' on a TreeMap has not been proven to work live; use .get(key) is None")

    def __bool__(self):
        raise TypeError("[stub] truth value of a TreeMap is not supported")


class DynArray:
    _args = ()

    def __class_getitem__(cls, item):
        return _generic(cls, item)

    def __init__(self, items=()):
        self._l = []
        for x in items:
            self.append(x)

    def append(self, value):
        if self._args:
            _check_type("DynArray element", self._args[0], value)
        self._l.append(value)

    def __len__(self):
        return len(self._l)

    def __getitem__(self, index):
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            raise TypeError("[stub] DynArray supports only non-negative integer indexes")
        return self._l[index]

    def __iter__(self):
        return iter(list(self._l))

    def __eq__(self, other):
        return isinstance(other, DynArray) and self._l == other._l

    __hash__ = None


def coerce(owner, name, annotation, value):
    where = owner + "." + name
    if isinstance(annotation, type) and issubclass(annotation, DynArray):
        if not isinstance(value, (list, DynArray)):
            raise TypeError("[stub] %s expects a list, got %s" % (where, type(value).__name__))
        return annotation(list(value))
    if isinstance(annotation, type) and issubclass(annotation, TreeMap):
        raise AssertionError("Is right the same storage type? TreeMap <- assigning to " + where + " is not allowed")
    _check_type(where, annotation, value)
    return value


def allow_storage(cls):
    hints = dict(getattr(cls, "__annotations__", {}))

    def __setattr__(self, name, value):
        if name in hints:
            value = coerce(cls.__name__, name, hints[name], value)
        object.__setattr__(self, name, value)

    cls.__setattr__ = __setattr__
    cls._gl_storage = True
    cls._gl_hints = hints
    return cls


dataclass = dataclasses.dataclass
