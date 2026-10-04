"""A small Catspeak (.meow) parser and interpreter for offline testing.

STONKS-9800 runs mods through Catspeak inside GameMaker, which we cannot run
here. This module implements the subset of Catspeak the mods in this repo use
so their syntax can be checked and their logic simulated against stub GML
functions. It is deliberately stricter than the real runtime:

* reading an unknown identifier, a missing struct key or an out-of-range array
  index raises instead of yielding ``undefined``;
* adding a string to a number raises (GML does too);
* functions do not capture ``let`` locals of enclosing functions (Catspeak 3
  makes no promise that they do), only file-level ("dynamic") variables.

Every exception swallowed by a ``catch`` is recorded in
``Interpreter.caught`` so tests can tell real bugs from expected failures.
"""

import math
import re

# ---------------------------------------------------------------------------
# Lexer

KEYWORDS = {
    "true", "false", "undefined", "infinity", "NaN", "and", "or", "xor", "do",
    "catch", "if", "else", "while", "for", "loop", "with", "match", "let",
    "fun", "params", "break", "continue", "return", "throw", "new", "impl",
    "self", "other",
}

OPERATORS = [
    "<<", ">>", "<=", ">=", "==", "!=", "+=", "-=", "*=", "/=", "//", "<|",
    "|>", "(", ")", "[", "]", "{", "}", ",", ":", ";", ".", "=", "<", ">",
    "+", "-", "*", "/", "%", "!", "~", "&", "|", "^",
]


class MeowSyntaxError(Exception):
    pass


class Token:
    __slots__ = ("kind", "value", "line")

    def __init__(self, kind, value, line):
        self.kind = kind    # num, str, ident, kw, op, eof
        self.value = value
        self.line = line

    def __repr__(self):
        return f"Token({self.kind}, {self.value!r}, line {self.line})"


ESCAPES = {'"': '"', "\\": "\\", "t": "\t", "n": "\n", "v": "\v", "f": "\f",
           "r": "\r", "\n": ""}


def tokenise(src):
    toks = []
    i, line, n = 0, 1, len(src)
    while i < n:
        c = src[i]
        if c == "\n":
            line += 1
            i += 1
            continue
        if c in " \t\r\v\f\u0085":
            i += 1
            continue
        if src.startswith("--", i):
            while i < n and src[i] != "\n":
                i += 1
            continue
        if c.isdigit():
            m = re.compile(r"0x[0-9A-Fa-f_]+|0b[01_]+|[0-9][0-9_]*(\.[0-9_]+)?").match(src, i)
            text = m.group(0).replace("_", "")
            if text.startswith("0x"):
                val = int(text[2:], 16)
            elif text.startswith("0b"):
                val = int(text[2:], 2)
            elif "." in text:
                val = float(text)
            else:
                val = int(text)
            toks.append(Token("num", val, line))
            i = m.end()
            continue
        if c == "#":
            m = re.compile(r"#([0-9A-Fa-f]{8}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{3,4})").match(src, i)
            if not m:
                raise MeowSyntaxError(f"line {line}: bad colour code")
            h = m.group(1)
            if len(h) in (3, 4):
                h = "".join(ch * 2 for ch in h)
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            toks.append(Token("num", r | (g << 8) | (b << 16), line))  # GML BGR
            i = m.end()
            continue
        if c == "@" and i + 1 < n and src[i + 1] == '"':
            j = src.index('"', i + 2)
            line += src.count("\n", i, j)
            toks.append(Token("str", src[i + 2:j], line))
            i = j + 1
            continue
        if c == '"':
            j, out = i + 1, []
            while True:
                if j >= n:
                    raise MeowSyntaxError(f"line {line}: unterminated string")
                ch = src[j]
                if ch == '"':
                    break
                if ch == "\\":
                    nxt = src[j + 1]
                    if nxt not in ESCAPES:
                        raise MeowSyntaxError(f"line {line}: bad escape \\{nxt}")
                    out.append(ESCAPES[nxt])
                    if nxt == "\n":
                        line += 1
                    j += 2
                    continue
                if ch == "\n":
                    line += 1
                out.append(ch)
                j += 1
            toks.append(Token("str", "".join(out), line))
            i = j + 1
            continue
        if c == "'":
            j = src.index("'", i + 1)
            body = src[i + 1:j]
            if len(body) != 1:
                raise MeowSyntaxError(f"line {line}: bad character literal")
            toks.append(Token("num", ord(body), line))
            i = j + 1
            continue
        if c == "`":
            j = src.index("`", i + 1)
            toks.append(Token("ident", src[i + 1:j], line))
            i = j + 1
            continue
        if c.isalpha() or c == "_":
            m = re.compile(r"[A-Za-z_][A-Za-z0-9_]*").match(src, i)
            word = m.group(0)
            toks.append(Token("kw" if word in KEYWORDS else "ident", word, line))
            i = m.end()
            continue
        for op in OPERATORS:
            if src.startswith(op, i):
                toks.append(Token("op", op, line))
                i += len(op)
                break
        else:
            raise MeowSyntaxError(f"line {line}: unexpected character {c!r}")
    toks.append(Token("eof", None, line))
    return toks


# ---------------------------------------------------------------------------
# Parser -> tuples ("kind", line, ...)

BINARY_LEVELS = [
    # lowest to highest, below assignment
    ("kw", ("or", "xor")),
    ("kw", ("and",)),
    ("op", ("<|", "|>")),
    ("op", ("==", "!=")),
    ("op", ("<", "<=", ">", ">=")),
    ("op", ("&", "|", "^", "<<", ">>")),
    ("op", ("+", "-")),
    ("op", ("*", "/", "//", "%")),
]

ASSIGN_OPS = ("=", "+=", "-=", "*=", "/=")
EXPR_START_KW = {"true", "false", "undefined", "infinity", "NaN", "do", "if",
                 "while", "fun", "return", "break", "continue", "throw",
                 "new", "self", "other", "match", "with"}


class Parser:
    def __init__(self, src):
        self.toks = tokenise(src)
        self.pos = 0

    def peek(self, k=0):
        return self.toks[self.pos + k]

    def next(self):
        t = self.toks[self.pos]
        self.pos += 1
        return t

    def at(self, kind, value=None):
        t = self.peek()
        return t.kind == kind and (value is None or t.value == value)

    def accept(self, kind, value=None):
        if self.at(kind, value):
            return self.next()
        return None

    def expect(self, kind, value=None):
        t = self.peek()
        if not self.at(kind, value):
            raise MeowSyntaxError(f"line {t.line}: expected {value or kind}, got {t.value!r}")
        return self.next()

    def can_start_expr(self):
        t = self.peek()
        if t.kind in ("num", "str", "ident"):
            return True
        if t.kind == "kw":
            return t.value in EXPR_START_KW
        if t.kind == "op":
            return t.value in ("(", "[", "{", "!", "~", "-", "+")
        return False

    # program / blocks -----------------------------------------------------
    def parse_program(self):
        stmts = self.parse_stmts(top=True)
        self.expect("eof")
        return ("block", 1, stmts)

    def parse_stmts(self, top=False):
        stmts = []
        while True:
            while self.accept("op", ";"):
                pass
            if self.at("eof") or (not top and self.at("op", "}")):
                return stmts
            stmts.append(self.parse_stmt())

    def parse_block(self):
        line = self.expect("op", "{").line
        stmts = self.parse_stmts()
        self.expect("op", "}")
        return ("block", line, stmts)

    def parse_stmt(self):
        if self.at("kw", "let"):
            line = self.next().line
            name = self.expect("ident").value
            init = None
            if self.accept("op", "="):
                init = self.parse_expr()
            return ("let", line, name, init)
        return self.parse_expr()

    # expressions ----------------------------------------------------------
    def parse_expr(self):
        e = self.parse_assign()
        while self.at("kw", "catch"):
            line = self.next().line
            name = self.accept("ident")
            handler = self.parse_block()
            e = ("catch", line, e, name.value if name else None, handler)
        return e

    def parse_assign(self):
        lhs = self.parse_binary(0)
        t = self.peek()
        if t.kind == "op" and t.value in ASSIGN_OPS:
            self.next()
            if lhs[0] not in ("ident", "index", "member"):
                raise MeowSyntaxError(f"line {t.line}: invalid assignment target")
            rhs = self.parse_assign()
            return ("assign", t.line, t.value, lhs, rhs)
        return lhs

    def parse_binary(self, level):
        if level == len(BINARY_LEVELS):
            return self.parse_unary()
        kind, ops = BINARY_LEVELS[level]
        lhs = self.parse_binary(level + 1)
        while self.peek().kind == kind and self.peek().value in ops:
            t = self.next()
            rhs = self.parse_binary(level + 1)
            lhs = ("binop", t.line, t.value, lhs, rhs)
        return lhs

    def parse_unary(self):
        t = self.peek()
        if t.kind == "op" and t.value in ("!", "~", "-", "+"):
            self.next()
            nt = self.peek()
            if nt.kind == "op" and nt.value in ("!", "~", "-", "+"):
                raise MeowSyntaxError(f"line {t.line}: unary operators cannot be chained")
            return ("unop", t.line, t.value, self.parse_postfix())
        return self.parse_postfix()

    def parse_postfix(self):
        e = self.parse_primary()
        while True:
            t = self.peek()
            if t.kind != "op":
                return e
            if t.value == "(":
                self.next()
                args = []
                while not self.at("op", ")"):
                    args.append(self.parse_expr())
                    if not self.accept("op", ","):
                        break
                self.expect("op", ")")
                e = ("call", t.line, e, args)
            elif t.value == ".":
                self.next()
                name = self.next()
                if name.kind not in ("ident", "kw"):
                    raise MeowSyntaxError(f"line {t.line}: expected member name")
                e = ("member", t.line, e, name.value)
            elif t.value == "[":
                self.next()
                idx = self.parse_expr()
                self.expect("op", "]")
                e = ("index", t.line, e, idx)
            else:
                return e

    def parse_primary(self):
        t = self.next()
        k, v, line = t.kind, t.value, t.line
        if k == "num":
            return ("lit", line, v)
        if k == "str":
            return ("lit", line, v)
        if k == "ident":
            return ("ident", line, v)
        if k == "op":
            if v == "(":
                e = self.parse_expr()
                self.expect("op", ")")
                return e
            if v == "[":
                items = []
                while not self.at("op", "]"):
                    items.append(self.parse_expr())
                    if not self.accept("op", ","):
                        break
                self.expect("op", "]")
                return ("array", line, items)
            if v == "{":
                pairs = []
                while not self.at("op", "}"):
                    kt = self.next()
                    if kt.kind == "op" and kt.value == "[":
                        key = self.parse_expr()
                        self.expect("op", "]")
                    elif kt.kind in ("ident", "str", "kw"):
                        key = ("lit", kt.line, str(kt.value))
                    elif kt.kind == "num":
                        key = ("lit", kt.line, str(kt.value))
                    else:
                        raise MeowSyntaxError(f"line {kt.line}: bad struct key")
                    if self.accept("op", ":"):
                        val = self.parse_expr()
                    elif kt.kind == "ident":
                        val = ("ident", kt.line, kt.value)
                    else:
                        raise MeowSyntaxError(f"line {kt.line}: expected ':'")
                    pairs.append((key, val))
                    if not self.accept("op", ","):
                        break
                self.expect("op", "}")
                return ("struct", line, pairs)
        if k == "kw":
            if v == "true":
                return ("lit", line, True)
            if v == "false":
                return ("lit", line, False)
            if v == "undefined":
                return ("lit", line, None)
            if v == "infinity":
                return ("lit", line, math.inf)
            if v == "NaN":
                return ("lit", line, math.nan)
            if v == "do":
                return self.parse_block()
            if v == "if":
                cond = self.parse_expr()
                then = self.parse_block()
                els = None
                if self.accept("kw", "else"):
                    if self.at("kw", "if"):
                        els = self.parse_primary()
                    else:
                        els = self.parse_block()
                return ("if", line, cond, then, els)
            if v == "while":
                cond = self.parse_expr()
                body = self.parse_block()
                return ("while", line, cond, body)
            if v == "fun":
                params = []
                if self.accept("op", "("):
                    while not self.at("op", ")"):
                        params.append(self.expect("ident").value)
                        if not self.accept("op", ","):
                            break
                    self.expect("op", ")")
                body = self.parse_block()
                return ("fun", line, params, body)
            if v == "return":
                val = self.parse_expr() if self.can_start_expr() else None
                return ("return", line, val)
            if v == "break":
                val = self.parse_expr() if self.can_start_expr() else None
                return ("break", line, val)
            if v == "continue":
                return ("continue", line)
            if v == "throw":
                return ("throw", line, self.parse_expr())
            if v == "self":
                return ("self", line)
            raise MeowSyntaxError(f"line {line}: '{v}' is not supported by this checker")
        raise MeowSyntaxError(f"line {line}: unexpected {v!r}")


def parse(src):
    return Parser(src).parse_program()


# ---------------------------------------------------------------------------
# Runtime values

class GMLError(Exception):
    """A runtime error, catchable by Catspeak's catch."""


class MeowThrow(Exception):
    def __init__(self, value):
        super().__init__(repr(value))
        self.value = value


class _Return(Exception):
    def __init__(self, value):
        self.value = value


class _Break(Exception):
    def __init__(self, value):
        self.value = value


class _Continue(Exception):
    pass


class Struct(dict):
    """A GML struct. Compared by identity, like GML."""

    __hash__ = object.__hash__

    def __eq__(self, other):
        return self is other

    def __ne__(self, other):
        return self is not other


class Function:
    def __init__(self, interp, params, body, line):
        self.interp = interp
        self.params = params
        self.body = body
        self.line = line

    def __call__(self, *args):
        return self.interp.call(self, list(args))

    def __repr__(self):
        return f"<meow fun line {self.line}>"


def is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) or isinstance(v, bool)


def truthy(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v > 0.5
    if v is None:
        return False
    raise GMLError(f"cannot convert {type_name(v)} to bool")


def type_name(v):
    if v is None:
        return "undefined"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    if isinstance(v, Struct):
        return "struct"
    if callable(v):
        return "method"
    return type(v).__name__


def num(v, what="operand"):
    if isinstance(v, (int, float)):
        return v
    raise GMLError(f"expected number for {what}, got {type_name(v)} ({v!r})")


def gml_equal(a, b):
    if isinstance(a, (list, Struct)) or isinstance(b, (list, Struct)):
        return a is b
    if isinstance(a, str) != isinstance(b, str):
        return False
    if a is None or b is None:
        return a is b
    if callable(a) or callable(b):
        return a is b
    return a == b


# ---------------------------------------------------------------------------
# Interpreter

class Interpreter:
    def __init__(self, builtins=None):
        self.builtins = dict(builtins or {})
        self.dyn = {}
        self.scopes = []        # stack of local scopes for the current call
        self.caught = []        # exceptions swallowed by catch expressions
        self.call_depth = 0

    # public -------------------------------------------------------------
    def run_file(self, path):
        with open(path, encoding="utf-8") as f:
            return self.run_source(f.read())

    def run_source(self, src):
        tree = parse(src)
        self.scopes = [{}]
        try:
            return self.eval_block_inline(tree)
        except _Return as r:
            return r.value

    def call(self, fn, args):
        if isinstance(fn, Function):
            saved = self.scopes
            frame = {}
            for i, p in enumerate(fn.params):
                frame[p] = args[i] if i < len(args) else None
            self.scopes = [frame]
            self.call_depth += 1
            if self.call_depth > 200:
                raise GMLError("stack overflow")
            try:
                return self.eval_block_inline(fn.body)
            except _Return as r:
                return r.value
            finally:
                self.call_depth -= 1
                self.scopes = saved
        if callable(fn):
            return fn(*args)
        raise GMLError(f"attempt to call a {type_name(fn)}")

    # scopes -------------------------------------------------------------
    def lookup(self, name, line):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        if name in self.dyn:
            return self.dyn[name]
        if name in self.builtins:
            return self.builtins[name]
        raise GMLError(f"line {line}: unknown identifier '{name}'")

    def assign_name(self, name, value):
        for scope in reversed(self.scopes):
            if name in scope:
                scope[name] = value
                return
        self.dyn[name] = value

    # evaluation ---------------------------------------------------------
    def eval_block_inline(self, block):
        self.scopes.append({})
        try:
            result = None
            for stmt in block[2]:
                result = self.eval(stmt)
            return result
        finally:
            self.scopes.pop()

    def eval(self, node):
        kind = node[0]
        m = getattr(self, "ev_" + kind)
        return m(node)

    def ev_block(self, n):
        return self.eval_block_inline(n)

    def ev_let(self, n):
        _, line, name, init = n
        value = self.eval(init) if init is not None else None
        self.scopes[-1][name] = value
        return None

    def ev_lit(self, n):
        return n[2]

    def ev_ident(self, n):
        return self.lookup(n[2], n[1])

    def ev_self(self, n):
        return None

    def ev_array(self, n):
        return [self.eval(e) for e in n[2]]

    def ev_struct(self, n):
        s = Struct()
        for k, v in n[2]:
            key = self.eval(k)
            s[key if isinstance(key, str) else gml_string(key)] = self.eval(v)
        return s

    def ev_fun(self, n):
        return Function(self, n[2], n[3], n[1])

    def ev_if(self, n):
        _, line, cond, then, els = n
        if truthy(self.eval(cond)):
            return self.eval(then)
        if els is not None:
            return self.eval(els)
        return None

    def ev_while(self, n):
        _, line, cond, body = n
        guard = 0
        while truthy(self.eval(cond)):
            guard += 1
            if guard > 1_000_000:
                raise GMLError(f"line {line}: runaway loop")
            try:
                self.eval(body)
            except _Break as b:
                return b.value
            except _Continue:
                continue
        return None

    def ev_return(self, n):
        raise _Return(self.eval(n[2]) if n[2] is not None else None)

    def ev_break(self, n):
        raise _Break(self.eval(n[2]) if n[2] is not None else None)

    def ev_continue(self, n):
        raise _Continue()

    def ev_throw(self, n):
        raise MeowThrow(self.eval(n[2]))

    def ev_catch(self, n):
        _, line, body, name, handler = n
        depth = len(self.scopes)
        try:
            return self.eval(body)
        except (GMLError, MeowThrow, ZeroDivisionError, TypeError, KeyError, IndexError) as e:
            del self.scopes[depth:]
            self.caught.append((line, e))
            self.scopes.append({name: e.value if isinstance(e, MeowThrow) else Struct(message=str(e))} if name else {})
            try:
                return self.eval_block_inline(handler)
            finally:
                self.scopes.pop()

    def ev_call(self, n):
        _, line, callee, args = n
        fn = self.eval(callee)
        vals = [self.eval(a) for a in args]
        if not (isinstance(fn, Function) or callable(fn)):
            raise GMLError(f"line {line}: attempt to call {type_name(fn)}")
        return self.call(fn, vals)

    def ev_member(self, n):
        _, line, obj, name = n
        return self.get_index(self.eval(obj), name, line)

    def ev_index(self, n):
        _, line, obj, idx = n
        return self.get_index(self.eval(obj), self.eval(idx), line)

    def get_index(self, obj, key, line):
        if isinstance(obj, Struct):
            if not isinstance(key, str):
                key = gml_string(key)
            if key not in obj:
                raise GMLError(f"line {line}: struct has no member '{key}'")
            return obj[key]
        if isinstance(obj, list):
            if not isinstance(key, (int, float)) or isinstance(key, bool):
                raise GMLError(f"line {line}: array index must be a number")
            i = int(key)
            if i < 0 or i >= len(obj):
                raise GMLError(f"line {line}: array index {i} out of range ({len(obj)})")
            return obj[i]
        if hasattr(obj, "meow_get"):
            return obj.meow_get(key, line)
        raise GMLError(f"line {line}: cannot index {type_name(obj)}")

    def set_index(self, obj, key, value, line):
        if isinstance(obj, Struct):
            if not isinstance(key, str):
                key = gml_string(key)
            obj[key] = value
            return
        if isinstance(obj, list):
            i = int(num(key, "array index"))
            if i < 0:
                raise GMLError(f"line {line}: negative array index")
            while len(obj) <= i:
                obj.append(0)
            obj[i] = value
            return
        if hasattr(obj, "meow_set"):
            obj.meow_set(key, value, line)
            return
        raise GMLError(f"line {line}: cannot assign into {type_name(obj)}")

    def ev_assign(self, n):
        _, line, op, target, rhs = n
        value = self.eval(rhs)
        if op != "=":
            current = self.eval(target)
            value = binop(op[0], current, value, line)
        tk = target[0]
        if tk == "ident":
            self.assign_name(target[2], value)
        elif tk == "member":
            self.set_index(self.eval(target[2]), target[3], value, line)
        else:
            self.set_index(self.eval(target[2]), self.eval(target[3]), value, line)
        return None

    def ev_unop(self, n):
        _, line, op, e = n
        v = self.eval(e)
        if op == "!":
            return not truthy(v)
        if op == "-":
            return -num(v)
        if op == "+":
            return num(v)
        if op == "~":
            return ~int(num(v))
        raise GMLError(f"line {line}: bad unary {op}")

    def ev_binop(self, n):
        _, line, op, a, b = n
        if op == "and":
            left = self.eval(a)
            return self.eval(b) if truthy(left) else left
        if op == "or":
            left = self.eval(a)
            return left if truthy(left) else self.eval(b)
        if op == "xor":
            return truthy(self.eval(a)) != truthy(self.eval(b))
        if op == "|>":
            return self.call(self.eval(b), [self.eval(a)])
        if op == "<|":
            return self.call(self.eval(a), [self.eval(b)])
        return binop(op, self.eval(a), self.eval(b), line)


def binop(op, x, y, line):
    if op == "==":
        return gml_equal(x, y)
    if op == "!=":
        return not gml_equal(x, y)
    if op == "+":
        if isinstance(x, str) and isinstance(y, str):
            return x + y
        if isinstance(x, str) or isinstance(y, str):
            raise GMLError(f"line {line}: cannot add {type_name(x)} and {type_name(y)}")
    if op in ("<", "<=", ">", ">="):
        if isinstance(x, str) and isinstance(y, str):
            pass
        else:
            num(x, f"'{op}' at line {line}")
            num(y, f"'{op}' at line {line}")
        return {"<": x < y, "<=": x <= y, ">": x > y, ">=": x >= y}[op]
    a = num(x, f"'{op}' at line {line}")
    b = num(y, f"'{op}' at line {line}")
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        if b == 0:
            raise GMLError(f"line {line}: divide by zero")
        return a / b
    if op == "//":
        if int(b) == 0:
            raise GMLError(f"line {line}: divide by zero")
        q = int(a) / int(b)
        return int(q)
    if op == "%":
        if b == 0:
            raise GMLError(f"line {line}: divide by zero")
        return math.fmod(a, b)
    if op == "&":
        return int(a) & int(b)
    if op == "|":
        return int(a) | int(b)
    if op == "^":
        return int(a) ^ int(b)
    if op == "<<":
        return int(a) << int(b)
    if op == ">>":
        return int(a) >> int(b)
    raise GMLError(f"line {line}: unknown operator {op}")


def gml_string(v):
    """GML's string(): integers print bare, other reals with 2 decimals."""
    if v is None:
        return "undefined"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if math.isnan(v):
            return "NaN"
        if math.isinf(v):
            return "inf" if v > 0 else "-inf"
        if v == int(v):
            return str(int(v))
        return f"{v:.2f}"
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "[ " + ",".join(gml_string(x) for x in v) + " ]"
    if isinstance(v, Struct):
        return "{ " + ", ".join(f"{k} : {gml_string(x)}" for k, x in v.items()) + " }"
    return repr(v)


if __name__ == "__main__":
    import sys
    for path in sys.argv[1:]:
        with open(path, encoding="utf-8") as f:
            parse(f.read())
        print(f"ok  {path}")
