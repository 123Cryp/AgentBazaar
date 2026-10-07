#!/usr/bin/env python3
"""
Static pre-deployment check for the AgentBazaar contracts (the "stripped, deploy-ready" check).

    python3 scripts/deploy/check_contract.py            # checks every file in contracts/ and build/
    python3 scripts/deploy/check_contract.py path.py    # checks one file

Every rule comes from a real GenLayer Studio or GenVM failure recorded in earlier projects:

  H1  line 1 is '# v0.2.16' and line 2 is the pinned Depends runner line
  H2  ASCII only
  H3  no comment other than those two header lines, and no docstring (long comments broke Studio's schema step)
  A1  only gl.* attributes that have been used live are referenced
  A2  run_nondet_unsafe gets exactly two positional arguments
  A3  emit_transfer is called with value= only
  A4  module-level functions (and the closures inside them) never touch `self`
  A5  no float literals, no true division, no datetime.min/max, no print/eval/exec/open/input
  A6  __init__ never assigns a TreeMap or DynArray field
  A7  a method that reads gl.message.value is decorated payable
  A8  every public method annotates every parameter and its return type, and only uses str, int, dict, list
  A9  public methods never call other public methods
  A10 storage dataclass fields use only str, u256, Address, DynArray[str]
  A11 imports are limited to the ones proven live
  A12 cross-contract writes use .emit(on="accepted") and reads use .view()
  A13 TreeMap fields are only used through .get(key), [key] and [key] = value (no len, no in, no iteration, no default)
  A14 `from dataclasses import dataclass` follows `from genlayer import *`
"""
import ast
import io
import os
import re
import sys
import tokenize

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ALLOWED_GL = {
    ("Contract",), ("message", "sender_address"), ("message", "value"), ("public", "write"), ("public", "write", "payable"),
    ("public", "view"), ("nondet", "exec_prompt"), ("nondet", "web", "get"), ("nondet", "web", "render"),
    ("eq_principle", "strict_eq"), ("eq_principle", "prompt_comparative"), ("vm", "run_nondet_unsafe"),
    ("get_contract_at",),
}
ALLOWED_IMPORTS = {"hashlib", "json", "datetime", "re", "urllib.parse", "genlayer", "dataclasses"}
FIELD_TYPES = {"str", "u256", "Address", "DynArray[str]"}
PUBLIC_TYPES = {"str", "int", "dict", "list"}
HEADER2 = '# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }'


def attr_chain(node):
    parts = []
    while isinstance(node, (ast.Attribute, ast.Call)):
        if isinstance(node, ast.Call):
            node = node.func
            continue
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return tuple(reversed(parts))
    return None


def self_field(node):
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
        return node.attr
    return None


def check(src):
    problems = []

    def bad(rule, msg, line=None):
        problems.append("%s%s %s" % (rule, (" line %d:" % line) if line else ":", msg))

    lines = src.split("\n")
    if lines[0] != "# v0.2.16":
        bad("H1", "line 1 must be exactly '# v0.2.16'")
    if len(lines) < 2 or lines[1] != HEADER2:
        bad("H1", "line 2 must be the pinned Depends runner line")
    if not src.isascii():
        bad("H2", "file contains non-ASCII characters")
    comments = [t for t in tokenize.generate_tokens(io.StringIO(src).readline) if t.type == tokenize.COMMENT]
    if {c.start[0] for c in comments} != {1, 2} or len(comments) != 2:
        bad("H3", "only the two header comment lines are allowed (found %d comments)" % len(comments))
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                bad("H3", "docstring in %s" % getattr(node, "name", "module"), first.lineno)

    imports = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    names = []
    for n in imports:
        names.append("genlayer *" if isinstance(n, ast.ImportFrom) and n.module == "genlayer" else
                     ("dataclasses.dataclass" if isinstance(n, ast.ImportFrom) and n.module == "dataclasses" else "other"))
    if "genlayer *" not in names or "dataclasses.dataclass" not in names or names.index("dataclasses.dataclass") != names.index("genlayer *") + 1:
        bad("A14", "'from dataclasses import dataclass' must directly follow 'from genlayer import *'")

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            chain = attr_chain(node)
            if chain and chain[0] == "gl":
                sub = chain[1:]
                if not any(sub == a[:len(sub)] or sub[:len(a)] == a for a in ALLOWED_GL):
                    bad("A1", "unproven GenLayer attribute gl." + ".".join(sub), node.lineno)
        if isinstance(node, ast.Call):
            chain = attr_chain(node.func)
            if chain and chain[-1] == "run_nondet_unsafe":
                if len(node.args) != 2 or node.keywords:
                    bad("A2", "run_nondet_unsafe needs exactly two positional arguments", node.lineno)
            if chain and chain[-1] == "emit_transfer":
                if node.args or [k.arg for k in node.keywords] != ["value"]:
                    bad("A3", "emit_transfer must be called with value= only", node.lineno)
            if isinstance(node.func, ast.Name) and node.func.id in ("print", "float", "eval", "exec", "open", "input"):
                bad("A5", "forbidden call " + node.func.id, node.lineno)
            if chain and "get_contract_at" in chain and isinstance(node.func, ast.Attribute):
                if node.func.attr == "emit":
                    kws = {k.arg: k.value for k in node.keywords}
                    ok = set(kws) == {"on"} and isinstance(kws["on"], ast.Constant) and kws["on"].value == "accepted" and not node.args
                    if not ok:
                        bad("A12", 'cross-contract writes must use .emit(on="accepted")', node.lineno)
        if isinstance(node, ast.Constant) and isinstance(node.value, float):
            bad("A5", "float literal", node.lineno)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            bad("A5", "true division; use //", node.lineno)
        if isinstance(node, ast.Attribute) and node.attr in ("min", "max") and attr_chain(node) and attr_chain(node)[0] == "datetime":
            bad("A5", "datetime.min/max sentinel", node.lineno)

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name) and sub.id == "self":
                    bad("A4", "module-level function %s references self" % node.name, sub.lineno)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module]
            for n in mods:
                if n not in ALLOWED_IMPORTS:
                    bad("A11", "import of " + str(n), node.lineno)

    contracts = [n for n in tree.body if isinstance(n, ast.ClassDef) and any(attr_chain(b) == ("gl", "Contract") for b in n.bases)]
    if len(contracts) != 1:
        bad("A6", "exactly one gl.Contract subclass is expected")
    else:
        cls = contracts[0]
        storage = set()
        treemaps = set()
        for n in cls.body:
            if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
                ann = ast.unparse(n.annotation)
                if ann.startswith("TreeMap") or ann.startswith("DynArray"):
                    storage.add(n.target.id)
                if ann.startswith("TreeMap"):
                    treemaps.add(n.target.id)
        methods = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}

        def decorators(fn):
            return [".".join(attr_chain(d) or ()) for d in fn.decorator_list]

        public = {name for name, fn in methods.items() if any(d.startswith("gl.public") for d in decorators(fn))}
        init = methods.get("__init__")
        if init:
            for sub in ast.walk(init):
                if isinstance(sub, ast.Assign):
                    for t in sub.targets:
                        if isinstance(t, ast.Attribute) and t.attr in storage:
                            bad("A6", "__init__ assigns storage field " + t.attr, sub.lineno)
        for name, fn in methods.items():
            reads_value = any(isinstance(s, ast.Attribute) and attr_chain(s) == ("gl", "message", "value") for s in ast.walk(fn))
            if reads_value and "gl.public.write.payable" not in decorators(fn):
                bad("A7", "%s reads gl.message.value but is not payable" % name, fn.lineno)
            if name in public:
                params = fn.args.args[1:]
                if any(p.annotation is None for p in params) or fn.returns is None:
                    bad("A8", "%s must annotate all parameters and the return type" % name, fn.lineno)
                else:
                    for p in params:
                        if ast.unparse(p.annotation) not in PUBLIC_TYPES:
                            bad("A8", "%s parameter %s has type %s" % (name, p.arg, ast.unparse(p.annotation)), fn.lineno)
                    if ast.unparse(fn.returns) not in PUBLIC_TYPES:
                        bad("A8", "%s returns %s" % (name, ast.unparse(fn.returns)), fn.lineno)
                for s in ast.walk(fn):
                    if isinstance(s, ast.Call) and attr_chain(s.func) and len(attr_chain(s.func)) == 2 and attr_chain(s.func)[0] == "self" and attr_chain(s.func)[1] in public:
                        bad("A9", "%s calls public method %s" % (name, attr_chain(s.func)[1]), s.lineno)
            for s in ast.walk(fn):
                if isinstance(s, ast.Call) and isinstance(s.func, ast.Attribute) and s.func.attr == "get" and self_field(s.func.value) in treemaps:
                    if len(s.args) != 1 or s.keywords:
                        bad("A13", "self.%s.get must be called with exactly one argument" % self_field(s.func.value), s.lineno)
                if isinstance(s, ast.Call) and isinstance(s.func, ast.Name) and s.func.id == "len" and s.args and self_field(s.args[0]) in treemaps:
                    bad("A13", "len() of TreeMap self.%s" % self_field(s.args[0]), s.lineno)
                if isinstance(s, ast.Compare):
                    for op, comp in zip(s.ops, s.comparators):
                        if isinstance(op, (ast.In, ast.NotIn)) and self_field(comp) in treemaps:
                            bad("A13", "'in' on TreeMap self.%s" % self_field(comp), s.lineno)
                if isinstance(s, (ast.For, ast.comprehension)) and self_field(s.iter) in treemaps:
                    bad("A13", "iteration over TreeMap self.%s" % self_field(s.iter), getattr(s, "lineno", None))
                if isinstance(s, ast.Call) and isinstance(s.func, ast.Attribute) and self_field(s.func.value) in treemaps \
                        and s.func.attr in ("items", "keys", "values", "pop", "setdefault", "update", "__contains__"):
                    bad("A13", "unproven TreeMap method %s" % s.func.attr, s.lineno)

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and any(ast.unparse(d) in ("dataclass", "allow_storage") for d in node.decorator_list):
            for n in node.body:
                if isinstance(n, ast.AnnAssign) and ast.unparse(n.annotation) not in FIELD_TYPES:
                    bad("A10", "storage field %s.%s has type %s" % (node.name, ast.unparse(n.target), ast.unparse(n.annotation)), n.lineno)
    return problems


def targets(argv):
    if argv:
        return argv
    out = []
    for folder in ("contracts", "build"):
        base = os.path.join(ROOT, folder)
        if os.path.isdir(base):
            out.extend(os.path.join(base, f) for f in sorted(os.listdir(base)) if f.endswith(".py"))
    return out


def main(argv):
    failed = 0
    paths = targets(argv)
    if not paths:
        print("no contract files found")
        return 1
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            problems = check(fh.read())
        for p in problems:
            print("FAIL", os.path.relpath(path, ROOT), p)
        if problems:
            failed += 1
        else:
            print("ok: %s passes all rule groups (%d bytes)" % (os.path.relpath(path, ROOT), os.path.getsize(path)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
