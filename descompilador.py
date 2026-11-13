#!/usr/bin/env python3
"""Descompilador simples de arquivos .pyc (bytecode Python) para código-fonte.

Uso:
    python descompilador.py programa.pyc            # mostra o código na tela
    python descompilador.py programa.pyc -o saida.py
    python descompilador.py programa.pyc --dis      # mostra só o bytecode

O arquivo .pyc precisa ter sido gerado pela MESMA versão do Python que está
executando este script (feito e testado no Python 3.13).
"""
import argparse
import ast
import dis
import importlib.util
import marshal
import re
import sys
import types

CO_VARARGS, CO_VARKEYWORDS = 0x04, 0x08


class Unsupported(Exception):
    """Trecho de bytecode que este descompilador não sabe reconstruir."""


# --------------------------------------------------------------------------
# Expressões: um texto + a precedência do operador principal
# --------------------------------------------------------------------------
class E(str):
    def __new__(cls, text, prec=16, **kw):
        self = super().__new__(cls, text)
        self.prec = prec
        self.__dict__.update(kw)
        return self


def par(e, prec):
    """Coloca parênteses se a precedência da expressão for menor que a exigida."""
    return f"({e})" if getattr(e, "prec", 16) < prec else str(e)


BINOPS = {"**": 14, "*": 12, "/": 12, "//": 12, "%": 12, "@": 12, "+": 11,
          "-": 11, "<<": 10, ">>": 10, "&": 9, "^": 8, "|": 7}
INVERT = {"==": "!=", "!=": "==", "is": "is not", "is not": "is",
          "in": "not in", "not in": "in"}


def compare(left, op, right):
    return E(f"{par(left, 7)} {op} {par(right, 7)}", 6, cmp=(left, op, right))


def neg(e):
    """Negação lógica de uma condição."""
    if hasattr(e, "notof"):
        return e.notof
    if hasattr(e, "cmp") and e.cmp[1] in INVERT:
        left, op, right = e.cmp
        return compare(left, INVERT[op], right)
    return E(f"not {par(e, 5)}", 5, notof=e)


def boolop(left, op, right):
    prec = 3 if op == "or" else 4
    return E(f"{par(left, prec)} {op} {par(right, prec + 1)}", prec)


def const(value):
    if value is Ellipsis:
        return E("...")
    if isinstance(value, tuple):
        items = [str(const(v)) for v in value]
        text = "(" + ", ".join(items) + ("," if len(items) == 1 else "") + ")"
        return E(text, kind="tuple", items=items)
    if isinstance(value, frozenset):
        items = sorted(str(const(v)) for v in value)
        return E("{" + ", ".join(items) + "}", kind="set", items=items)
    if isinstance(value, (int, float, complex)) and str(value).startswith("-"):
        return E(repr(value), 13)
    if isinstance(value, str):
        return E(repr(value), strval=value)
    return E(repr(value))


def seq(kind, items):
    if kind == "tuple":
        text = "(" + ", ".join(items) + ("," if len(items) == 1 else "") + ")"
    elif kind == "list":
        text = "[" + ", ".join(items) + "]"
    elif kind == "set":
        text = "{" + ", ".join(items) + "}" if items else "set()"
    else:  # dict: items são pares (chave, valor); chave None significa **valor
        text = "{" + ", ".join(f"**{v}" if k is None else f"{k}: {v}"
                               for k, v in items) + "}"
    return E(text, kind=kind, items=list(items))


def fstr_escape(text):
    for a, b in (("\\", "\\\\"), ('"', '\\"'), ("\n", "\\n"), ("\r", "\\r"),
                 ("\t", "\\t"), ("{", "{{"), ("}", "}}")):
        text = text.replace(a, b)
    return text


def fstr(inner):
    return E(f'f"{inner}"', fs=inner)


class Null:
    """Marcador do NULL que o Python empilha antes de chamadas."""


class BuildClass:
    """Marcador do LOAD_BUILD_CLASS."""


class Func:
    def __init__(self, code):
        self.code = code
        self.defaults = []
        self.kwdefaults = {}
        self.decorators = []

    @property
    def is_lambda(self):
        return self.code.co_name == "<lambda>"

    def signature(self):
        c = self.code
        n, k, names = c.co_argcount, c.co_kwonlyargcount, c.co_varnames
        parts = []
        first_default = n - len(self.defaults)
        for i, name in enumerate(names[:n]):
            if i >= first_default:
                name += "=" + self.defaults[i - first_default]
            parts.append(name)
            if c.co_posonlyargcount and i == c.co_posonlyargcount - 1:
                parts.append("/")
        j = n + k
        if c.co_flags & CO_VARARGS:
            parts.append("*" + names[j])
            j += 1
        elif k:
            parts.append("*")
        for name in names[n:n + k]:
            if name in self.kwdefaults:
                name += "=" + self.kwdefaults[name]
            parts.append(name)
        if c.co_flags & CO_VARKEYWORDS:
            parts.append("**" + names[j])
        return ", ".join(parts)

    def as_lambda(self):
        body = Decompiler(self.code).body()
        if len(body) != 1 or body[0][0] != "return":
            raise Unsupported("lambda complexa")
        sig = self.signature()
        return E(f"lambda{' ' + sig if sig else ''}: {par(body[0][1], 2)}", 1)


class Class:
    def __init__(self, code, name, bases):
        self.code, self.name, self.bases = code, name, bases
        self.decorators = []


class Loop:
    def __init__(self, head, exit, alias=None):
        # alias: destino de um salto que fica logo depois do laço (um `break`
        # pode ir direto para lá)
        self.head, self.exit, self.alias, self.breaks = head, exit, alias, set()


CJ = {"POP_JUMP_IF_FALSE", "POP_JUMP_IF_TRUE", "POP_JUMP_IF_NONE",
      "POP_JUMP_IF_NOT_NONE"}
STORES = {"STORE_NAME", "STORE_FAST", "STORE_GLOBAL", "STORE_DEREF"}
LOADS = {"LOAD_NAME", "LOAD_FAST", "LOAD_FAST_CHECK", "LOAD_DEREF",
         "LOAD_CLOSURE", "LOAD_CLASSDEREF"}
SKIP = {"RESUME", "NOP", "CACHE", "TO_BOOL", "GET_ITER", "COPY_FREE_VARS",
        "MAKE_CELL", "SETUP_ANNOTATIONS", "EXTENDED_ARG"}
STOP = {"JUMP_FORWARD", "JUMP_BACKWARD", "JUMP_BACKWARD_NO_INTERRUPT",
        "FOR_ITER", "RETURN_VALUE", "RETURN_CONST", "RAISE_VARARGS"}


# --------------------------------------------------------------------------
# Descompilador de um objeto de código (módulo, função ou classe)
# --------------------------------------------------------------------------
class Decompiler:
    def __init__(self, code):
        self.code = code
        self.ins = list(dis.get_instructions(code))
        self.idx = {ins.offset: i for i, ins in enumerate(self.ins)}
        self.idx[self.ins[-1].offset + 1000000] = len(self.ins)
        self.jump = {i: ins.jump_target for i, ins in enumerate(self.ins)
                     if ins.jump_target is not None}
        self.skip = set()
        self.declared = []  # nomes "global"/"nonlocal"
        self.normalize_whiles()
        # cabeça de laço while -> índice do último salto para trás até ela
        self.whiles = {}
        for i, ins in enumerate(self.ins):
            if ins.opname.startswith("JUMP_BACKWARD") and i not in self.skip:
                head = self.idx[self.jump[i]]
                if self.ins[head].opname != "FOR_ITER":
                    self.whiles[head] = max(i, self.whiles.get(head, 0))

    def off(self, i):
        """Offset da instrução de índice i (ou um valor enorme, se for o fim)."""
        return self.ins[i].offset if i < len(self.ins) else self.ins[-1].offset + 1000000

    def alias(self, i):
        if i < len(self.ins) and i not in self.skip and self.ins[i].opname in (
                "JUMP_FORWARD", "JUMP_BACKWARD"):
            return self.jump[i]
        return None

    def normalize_whiles(self):
        """O Python 3.13 repete a condição do `while` no fim do laço.
        Aqui a cópia é descartada e o salto final volta para a condição do topo."""
        last = {}  # início do corpo -> último salto para trás até ele
        for i, ins in enumerate(self.ins):
            if ins.opname == "JUMP_BACKWARD":
                last[self.idx[self.jump[i]]] = i
        for body, jb in last.items():
            line = self.ins[jb].positions.lineno
            lo = jb  # cópia da condição: instruções da linha do `while` no fim
            while lo - 1 > body and self.ins[lo - 1].positions.lineno == line:
                lo -= 1
            top = body  # condição original, logo antes do corpo
            while top > 0 and self.ins[top - 1].positions.lineno == line:
                top -= 1
            key = lambda r: [(x.opname, x.argval) for x in (self.ins[n] for n in r)
                             if x.opname not in CJ and x.opname != "JUMP_BACKWARD"]
            if lo < jb and top < body and key(range(lo, jb)) == key(range(top, body)):
                self.skip.update(range(lo, jb))
                self.jump[jb] = self.ins[top].offset

    # ---------------------------------------------------------------- blocos
    def body(self):
        if self.code.co_exceptiontable:
            raise Unsupported("try/except, with ou compreensão de lista")
        stack = []
        out = self.block(0, len(self.ins), stack, None, None)
        return out

    def block(self, i, end, stack, follow, loop, nowhile=-1):
        out = []
        while i < end:
            i = self.step(i, end, stack, out, follow, loop, nowhile)
        return out

    def resolve(self, target, follow, loop):
        """Traduz um salto para fora do bloco atual: nada, continue ou break."""
        if target == follow:
            return None
        if loop and target == loop.head:
            return "continue"
        if loop and target == loop.alias:
            loop.breaks.add(loop.exit)
            return "break"
        if loop and target >= loop.exit:
            loop.breaks.add(target)
            return "break"
        raise Unsupported("fluxo de controle não reconhecido")

    def pop(self, stack):
        if not stack:
            raise Unsupported("pilha vazia")
        value = stack.pop()
        if isinstance(value, Func):
            if value.is_lambda:
                return value.as_lambda()
            raise Unsupported("função usada como expressão")
        if not isinstance(value, E):
            raise Unsupported("valor inesperado na pilha")
        return value

    def popn(self, stack, n):
        if n == 0:
            return []
        if len(stack) < n:
            raise Unsupported("pilha vazia")
        values = stack[-n:]
        del stack[-n:]
        return values

    def exprs(self, values):
        stack = list(values)
        return [self.pop(stack[:i + 1]) for i in range(len(stack))]

    # ------------------------------------------------------------ atribuição
    def targets(self, i, n):
        """Lê n alvos de atribuição a partir da instrução i."""
        result = []
        while len(result) < n:
            ins = self.ins[i]
            if ins.opname in STORES:
                self.declare(ins)
                result.append(ins.argval)
            elif ins.opname == "STORE_FAST_STORE_FAST" and n - len(result) >= 2:
                result.extend(ins.argval)
            elif ins.opname == "UNPACK_SEQUENCE":
                inner, i = self.targets(i + 1, ins.arg)
                result.append("(" + ", ".join(inner) + ("," if len(inner) == 1 else "") + ")")
                continue
            else:
                raise Unsupported("alvo de atribuição complexo")
            i += 1
        return result, i

    def declare(self, ins):
        name = ins.argval
        is_function = self.code.co_name not in ("<module>",) and self.code.co_flags & 0x02
        if ins.opname in ("STORE_GLOBAL", "DELETE_GLOBAL") and is_function:
            decl = f"global {name}"
        elif ins.opname in ("STORE_DEREF", "DELETE_DEREF") and name in self.code.co_freevars:
            decl = f"nonlocal {name}"
        else:
            return
        if decl not in self.declared:
            self.declared.append(decl)

    def assign(self, target, value, out):
        if isinstance(value, Func) and not value.is_lambda:
            if value.code.co_name != target:
                raise Unsupported("função com nome diferente")
            out.append(("def", value))
        elif isinstance(value, Class):
            if value.name != target:
                raise Unsupported("classe com nome diferente")
            out.append(("class", value))
        else:
            if isinstance(value, Func):
                value = value.as_lambda()
            if not isinstance(value, E):
                raise Unsupported("valor inesperado na pilha")
            aug = getattr(value, "aug", None)
            if aug and aug[0] == target:
                out.append(f"{target} {aug[1]} {aug[2]}")
            else:
                out.append(f"{target} = {value}")

    # ------------------------------------------------------------- condições
    def one_cond(self, i, stack):
        """Condição de um salto condicional: (expressão, salta_se_verdadeiro)."""
        op = self.ins[i].opname
        value = self.pop(stack)
        if op == "POP_JUMP_IF_TRUE":
            return value, True
        if op == "POP_JUMP_IF_FALSE":
            return value, False
        if op == "POP_JUMP_IF_NONE":
            return compare(value, "is not", E("None")), False
        return compare(value, "is", E("None")), False

    def cond(self, i, end, stack):
        """Lê um salto condicional, juntando sequências de `and` / `or`."""
        c, sense = self.one_cond(i, stack)
        target = self.jump[i]
        while True:
            trial, tmp, j = list(stack), [], i + 1
            try:
                while (j < end and not tmp and j not in self.whiles
                       and self.ins[j].opname not in CJ
                       and self.ins[j].opname not in STOP):
                    j = self.step(j, end, trial, tmp, None, None, -1)
            except Unsupported:
                break
            if (tmp or j >= end or self.ins[j].opname not in CJ
                    or len(trial) != len(stack) + 1):
                break
            try:
                c2, sense2 = self.one_cond(j, trial)
            except Unsupported:
                break
            target2 = self.jump[j]
            if target2 == target:
                if sense2 != sense:
                    c2 = neg(c2)
                c = boolop(c, "or" if sense else "and", c2)
            elif target == self.off(j + 1):
                if sense == sense2:
                    c, sense = neg(c), not sense
                c = boolop(c, "or" if sense else "and", c2)
                sense, target = sense2, target2
            else:
                break
            i = j
            stack[:] = trial
        return c, sense, target, i

    def do_if(self, fc, a, target, end, stack, out, follow, loop):
        """`fc` é a condição para executar o trecho que começa em `a`."""
        ti = self.idx[target]
        if ti > end:
            jump = self.resolve(target, follow, loop)
            if jump is None:
                out.append(("if", fc, self.block(a, end, list(stack), follow, loop), []))
                return end
            out.append(("if", neg(fc), [jump], []))
            return a
        last = ti - 1
        if last >= a and self.ins[last].opname == "JUMP_FORWARD":
            x = self.jump[last]
            is_break = loop and x >= loop.exit and x != follow
            if x > target and not is_break and (self.idx[x] <= end or x == follow):
                xi = min(self.idx[x], end)
                s1, s2 = list(stack), list(stack)
                b1 = self.block(a, last, s1, x, loop)
                b2 = self.block(ti, xi, s2, x, loop)
                if not b1 and not b2 and len(s1) == len(s2) == len(stack) + 1:
                    v1, v2 = self.pop(s1), self.pop(s2)
                    stack.append(E(f"{par(v1, 3)} if {par(fc, 3)} else {par(v2, 2)}", 2))
                    return xi
                if len(s1) != len(stack) or len(s2) != len(stack):
                    raise Unsupported("expressão condicional complexa")
                out.append(("if", fc, b1, b2))
                return xi
        s1 = list(stack)
        b1 = self.block(a, ti, s1, target, loop)
        if len(s1) != len(stack):
            raise Unsupported("expressão condicional complexa")
        out.append(("if", fc, b1, []))
        return ti

    # ----------------------------------------------------------------- laços
    def loop_else(self, loop, after, end, stack, follow, outer):
        """Trata o `else` de um laço; devolve (bloco_else, próximo_índice)."""
        targets = {t for t in loop.breaks if t != self.off(after)}
        if not targets:
            return [], after
        if len(targets) > 1:
            raise Unsupported("break com destinos diferentes")
        b = targets.pop()
        bi = min(self.idx[b], end)
        if self.idx[b] > end and b != follow:
            raise Unsupported("break com destino não reconhecido")
        return self.block(after, bi, list(stack), b, outer), bi

    def do_for(self, i, end, stack, out, follow, outer):
        iterable = self.pop(stack)
        endi = self.idx[self.jump[i]]  # END_FOR
        (target,), start = self.targets(i + 1, 1)
        if target.startswith("("):
            target = target[1:-1]
        after = endi + 2  # pula END_FOR e POP_TOP
        loop = Loop(self.ins[i].offset, self.off(after), self.alias(after))
        body = self.block(start, endi, [], loop.head, loop)
        orelse, nxt = self.loop_else(loop, after, end, stack, follow, outer)
        out.append(("for", target, iterable, tailfix(body), orelse))
        return nxt

    def do_while(self, i, end, stack, out, follow, outer):
        jb = self.whiles[i]
        after = jb + 1
        loop = Loop(self.ins[i].offset, self.off(after), self.alias(after))
        condition, start = E("True"), i
        # tenta ler a condição do cabeçalho: `while cond:`
        trial, tmp, j = [], [], i
        try:
            while (j < jb and not tmp and self.ins[j].opname not in CJ
                   and self.ins[j].opname not in STOP):
                j = self.step(j, jb, trial, tmp, None, None, i)
            if not tmp and j < jb and self.ins[j].opname in CJ and len(trial) == 1:
                c, sense, target, last = self.cond(j, jb, trial)
                if target == loop.exit and not trial:
                    condition, start = (neg(c) if sense else c), last + 1
        except Unsupported:
            pass
        body = self.block(start, jb + 1, [], loop.head, loop, nowhile=i)
        orelse, nxt = self.loop_else(loop, after, end, stack, follow, outer)
        out.append(("while", condition, tailfix(body), orelse))
        return nxt

    # ------------------------------------------------------- uma instrução
    def step(self, i, end, stack, out, follow, loop, nowhile):
        ins = self.ins[i]
        op, arg, val = ins.opname, ins.arg, ins.argval
        push = stack.append
        if i in self.skip or op in SKIP:
            return i + 1
        if i in self.whiles and i != nowhile:
            return self.do_while(i, end, stack, out, follow, loop)

        # ---- cargas
        if op == "LOAD_CONST":
            push(Func(val) if isinstance(val, types.CodeType) else const(val))
        elif op in LOADS:
            push(E(val))
        elif op == "LOAD_GLOBAL":
            push(E(val))
            if arg & 1:
                push(Null())
        elif op == "LOAD_FAST_LOAD_FAST":
            push(E(val[0]))
            push(E(val[1]))
        elif op == "PUSH_NULL":
            push(Null())
        elif op == "LOAD_ATTR":
            push(E(f"{par(self.pop(stack), 16)}.{val}"))
            if arg & 1:
                push(Null())
        elif op == "LOAD_SUPER_ATTR":
            self.popn(stack, 3)
            push(E(f"super().{val}"))
            if arg & 1:
                push(Null())
        elif op == "LOAD_BUILD_CLASS":
            push(BuildClass())
        elif op == "LOAD_ASSERTION_ERROR":
            push(E("AssertionError"))

        # ---- atribuições
        elif op in STORES:
            if val == "__classcell__":
                stack.pop()
            else:
                self.declare(ins)
                self.assign(val, stack.pop() if stack else self.pop(stack), out)
        elif op == "STORE_FAST_STORE_FAST":
            a, b = self.pop(stack), self.pop(stack)
            out.append(f"{val[0]}, {val[1]} = {a}, {b}")
        elif op == "STORE_FAST_LOAD_FAST":
            self.assign(val[0], stack.pop() if stack else self.pop(stack), out)
            push(E(val[1]))
        elif op == "STORE_ATTR":
            obj = self.pop(stack)
            self.assign(f"{par(obj, 16)}.{val}", self.pop(stack), out)
        elif op == "STORE_SUBSCR":
            key, obj = self.pop(stack), self.pop(stack)
            self.assign(f"{par(obj, 16)}[{key}]", self.pop(stack), out)
        elif op == "STORE_SLICE":
            hi, lo, obj = self.pop(stack), self.pop(stack), self.pop(stack)
            self.assign(f"{par(obj, 16)}[{slice_text(lo, hi)}]", self.pop(stack), out)
        elif op == "UNPACK_SEQUENCE":
            value = self.pop(stack)
            names, nxt = self.targets(i + 1, arg)
            out.append(f"{', '.join(names)}{',' if len(names) == 1 else ''} = {value}")
            return nxt
        elif op in ("DELETE_NAME", "DELETE_FAST", "DELETE_GLOBAL", "DELETE_DEREF"):
            self.declare(ins)
            out.append(f"del {val}")
        elif op == "DELETE_ATTR":
            out.append(f"del {par(self.pop(stack), 16)}.{val}")
        elif op == "DELETE_SUBSCR":
            key, obj = self.pop(stack), self.pop(stack)
            out.append(f"del {par(obj, 16)}[{key}]")

        # ---- operadores
        elif op == "BINARY_OP":
            right, left = self.pop(stack), self.pop(stack)
            sym = ins.argrepr
            if sym.endswith("=") and sym not in ("==",):
                base = sym[:-1]
                prec = BINOPS[base]
                push(E(f"{par(left, prec)} {base} {par(right, prec + 1)}", prec,
                       aug=(str(left), sym, str(right))))
            else:
                prec = BINOPS[sym]
                if sym == "**":
                    push(E(f"{par(left, 15)} ** {par(right, 14)}", prec))
                else:
                    push(E(f"{par(left, prec)} {sym} {par(right, prec + 1)}", prec))
        elif op == "UNARY_NEGATIVE":
            push(E(f"-{par(self.pop(stack), 13)}", 13))
        elif op == "UNARY_INVERT":
            push(E(f"~{par(self.pop(stack), 13)}", 13))
        elif op == "UNARY_NOT":
            push(E(f"not {par(self.pop(stack), 5)}", 5))
        elif op == "COMPARE_OP":
            right, left = self.pop(stack), self.pop(stack)
            push(compare(left, val, right))
        elif op == "IS_OP":
            right, left = self.pop(stack), self.pop(stack)
            push(compare(left, "is not" if arg else "is", right))
        elif op == "CONTAINS_OP":
            right, left = self.pop(stack), self.pop(stack)
            push(compare(left, "not in" if arg else "in", right))
        elif op == "BINARY_SUBSCR":
            key, obj = self.pop(stack), self.pop(stack)
            push(E(f"{par(obj, 16)}[{key}]"))
        elif op == "BINARY_SLICE":
            hi, lo, obj = self.pop(stack), self.pop(stack), self.pop(stack)
            push(E(f"{par(obj, 16)}[{slice_text(lo, hi)}]"))
        elif op == "BUILD_SLICE":
            parts = self.exprs(self.popn(stack, arg))
            push(E(":".join("" if p == "None" else par(p, 3) for p in parts), 0))

        # ---- coleções
        elif op in ("BUILD_TUPLE", "BUILD_LIST", "BUILD_SET"):
            items = [par(e, 2) for e in self.exprs(self.popn(stack, arg))]
            push(seq(op[6:].lower(), items))
        elif op == "BUILD_MAP":
            flat = [par(e, 2) for e in self.exprs(self.popn(stack, 2 * arg))]
            push(seq("dict", list(zip(flat[::2], flat[1::2]))))
        elif op == "BUILD_CONST_KEY_MAP":
            keys = self.pop(stack).items
            values = [par(e, 2) for e in self.exprs(self.popn(stack, arg))]
            push(seq("dict", list(zip(keys, values))))
        elif op in ("LIST_EXTEND", "SET_UPDATE") and arg == 1:
            extra, base = self.pop(stack), self.pop(stack)
            more = extra.items if getattr(extra, "kind", "") in ("tuple", "set", "list") \
                else [f"*{par(extra, 7)}"]
            push(seq(base.kind, base.items + more))
        elif op in ("LIST_APPEND", "SET_ADD") and arg == 1:
            value, base = self.pop(stack), self.pop(stack)
            push(seq(base.kind, base.items + [par(value, 2)]))
        elif op in ("DICT_UPDATE", "DICT_MERGE") and arg == 1:
            extra, base = self.pop(stack), self.pop(stack)
            more = extra.items if getattr(extra, "kind", "") == "dict" \
                else [(None, par(extra, 7))]
            push(seq("dict", base.items + more))

        # ---- f-strings
        elif op == "CONVERT_VALUE":
            value = self.pop(stack)
            push(E(str(value), value.prec, conv="!" + "sra"[arg - 1]))
        elif op == "FORMAT_SIMPLE":
            value = self.pop(stack)
            push(fstr("{" + fexpr(value) + getattr(value, "conv", "") + "}"))
        elif op == "FORMAT_WITH_SPEC":
            spec, value = self.pop(stack), self.pop(stack)
            spec = spec.fs if hasattr(spec, "fs") else fstr_escape(spec.strval)
            push(fstr("{" + fexpr(value) + getattr(value, "conv", "") + ":" + spec + "}"))
        elif op == "BUILD_STRING":
            parts = self.exprs(self.popn(stack, arg))
            push(fstr("".join(p.fs if hasattr(p, "fs") else fstr_escape(p.strval)
                              for p in parts)))

        # ---- chamadas
        elif op in ("CALL", "CALL_KW"):
            names = self.pop(stack).items if op == "CALL_KW" else []
            args = self.popn(stack, arg)
            slot = self.popn(stack, 1)[0]  # NULL ou self
            if not isinstance(slot, Null):
                args.insert(0, slot)
            func = stack.pop() if stack else self.pop(stack)
            if isinstance(func, BuildClass):
                rest = self.exprs(args[2:])
                npos = len(rest) - len(names)
                bases = [str(e) for e in rest[:npos]] + [
                    f"{ast.literal_eval(k)}={v}" for k, v in zip(names, rest[npos:])]
                push(Class(args[0].code, ast.literal_eval(self.exprs(args[1:2])[0]), bases))
            elif (len(args) == 1 and not names and isinstance(args[0], (Func, Class))
                  and not getattr(args[0], "is_lambda", False)):
                stack.append(func)
                args[0].decorators.insert(0, str(self.pop(stack)))
                push(args[0])
            else:
                stack.append(func)
                func = self.pop(stack)
                args = [par(e, 2) for e in self.exprs(args)]
                npos = len(args) - len(names)
                text = args[:npos] + [f"{ast.literal_eval(k)}={v}"
                                      for k, v in zip(names, args[npos:])]
                push(E(f"{par(func, 16)}({', '.join(text)})"))
        elif op == "CALL_FUNCTION_EX":
            kwargs = self.pop(stack) if arg & 1 else None
            args = self.pop(stack)
            self.popn(stack, 1)
            func = self.pop(stack)
            text = list(args.items) if getattr(args, "kind", "") in ("tuple", "list") \
                else [f"*{par(args, 7)}"]
            if kwargs is not None:
                if getattr(kwargs, "kind", "") == "dict":
                    for k, v in kwargs.items:
                        text.append(f"**{v}" if k is None else f"{ast.literal_eval(k)}={v}")
                else:
                    text.append(f"**{par(kwargs, 7)}")
            push(E(f"{par(func, 16)}({', '.join(text)})"))
        elif op == "CALL_INTRINSIC_1":
            value = self.pop(stack)
            if ins.argrepr == "INTRINSIC_LIST_TO_TUPLE":
                push(seq("tuple", value.items))
            elif ins.argrepr == "INTRINSIC_UNARY_POSITIVE":
                push(E(f"+{par(value, 13)}", 13))
            else:
                raise Unsupported(ins.argrepr)

        # ---- funções e classes
        elif op == "MAKE_FUNCTION":
            if not isinstance(stack[-1], Func):
                raise Unsupported("MAKE_FUNCTION")
            if stack[-1].code.co_name in ("<genexpr>", "<listcomp>", "<dictcomp>", "<setcomp>"):
                raise Unsupported("expressão geradora / compreensão")
        elif op == "SET_FUNCTION_ATTRIBUTE":
            func = stack.pop()
            value = self.pop(stack)
            if arg == 1:
                func.defaults = list(value.items)
            elif arg == 2:
                func.kwdefaults = {ast.literal_eval(k): v for k, v in value.items}
            push(func)  # anotações (4) e closures (8) são ignoradas

        # ---- importações
        elif op == "IMPORT_NAME":
            return self.do_import(i, stack, out)

        # ---- pilha
        elif op == "POP_TOP":
            if stack:
                if isinstance(stack[-1], (Null, BuildClass)):
                    stack.pop()
                else:
                    out.append(str(self.pop(stack)))
        elif op == "COPY":
            nxt = self.do_copy(i, end, stack, out, loop)
            if nxt is not None:
                return nxt
            if len(stack) < arg:
                raise Unsupported("COPY")
            push(stack[-arg])
        elif op == "SWAP":
            if len(stack) < arg:
                raise Unsupported("SWAP")
            stack[-1], stack[-arg] = stack[-arg], stack[-1]

        # ---- fluxo de controle
        elif op == "RETURN_VALUE":
            out.append(("return", self.pop(stack)))
        elif op == "RETURN_CONST":
            out.append(("return", const(val)))
        elif op == "RAISE_VARARGS":
            parts = self.exprs(self.popn(stack, arg))
            out.append("raise" + (f" {parts[0]}" if parts else "")
                       + (f" from {parts[1]}" if arg == 2 else ""))
        elif op in CJ:
            c, sense, target, last = self.cond(i, end, stack)
            return self.do_if(neg(c) if sense else c, last + 1, target, end,
                              stack, out, follow, loop)
        elif op in ("JUMP_FORWARD", "JUMP_BACKWARD", "JUMP_BACKWARD_NO_INTERRUPT"):
            jump = self.resolve(self.jump[i], follow, loop)
            if jump:
                out.append(jump)
        elif op == "FOR_ITER":
            return self.do_for(i, end, stack, out, follow, loop)
        else:
            raise Unsupported(f"instrução {op}")
        return i + 1

    def do_copy(self, i, end, stack, out, loop):
        """Casos especiais de COPY 1: `a or b`, `a and b` e `a = b = valor`."""
        if self.ins[i].arg != 1:
            return None
        k = i + 1
        if self.ins[k].opname == "TO_BOOL":
            k += 1
        name = self.ins[k].opname
        if name in ("POP_JUMP_IF_TRUE", "POP_JUMP_IF_FALSE") and self.ins[k + 1].opname == "POP_TOP":
            ti = self.idx[self.jump[k]]
            left, sub = self.pop(stack), []
            if self.block(k + 2, ti, sub, None, loop) or len(sub) != 1:
                raise Unsupported("expressão and/or complexa")
            stack.append(boolop(left, "or" if name.endswith("TRUE") else "and", self.pop(sub)))
            return ti
        if self.ins[i + 1].opname == "STORE_FAST_STORE_FAST" and isinstance(stack[-1], E):
            a, b = self.ins[i + 1].argval
            out.append(f"{a} = {b} = {self.pop(stack)}")
            return i + 2
        if self.ins[i + 1].opname in STORES:
            names, j = [], i
            while (self.ins[j].opname == "COPY" and self.ins[j].arg == 1
                   and self.ins[j + 1].opname in STORES):
                self.declare(self.ins[j + 1])
                names.append(self.ins[j + 1].argval)
                j += 2
            if self.ins[j].opname in STORES and isinstance(stack[-1], E):
                self.declare(self.ins[j])
                names.append(self.ins[j].argval)
                out.append(" = ".join(names) + f" = {self.pop(stack)}")
                return j + 1
        return None

    def do_import(self, i, stack, out):
        module = self.ins[i].argval
        fromlist, level = self.pop(stack), self.pop(stack)
        dots = "." * int(level)
        i += 1
        if fromlist == "None":
            if self.ins[i].opname in STORES:
                name = self.ins[i].argval
                out.append(f"import {module}" if name == module.split(".")[0]
                           else f"import {module} as {name}")
                return i + 1
            while self.ins[i].opname not in STORES:  # import a.b.c as nome
                if self.ins[i].opname not in ("IMPORT_FROM", "SWAP", "POP_TOP"):
                    raise Unsupported("import")
                i += 1
            out.append(f"import {module} as {self.ins[i].argval}")
            return i + 2
        if self.ins[i].opname == "CALL_INTRINSIC_1":
            out.append(f"from {dots}{module} import *")
            return i + 2
        names = []
        while self.ins[i].opname == "IMPORT_FROM":
            attr, store = self.ins[i].argval, self.ins[i + 1]
            if store.opname not in STORES:
                raise Unsupported("import")
            names.append(attr if attr == store.argval else f"{attr} as {store.argval}")
            i += 2
        out.append(f"from {dots}{module} import {', '.join(names)}")
        return i + 1


def slice_text(lo, hi):
    return f"{'' if lo == 'None' else lo}:{'' if hi == 'None' else hi}"


def fexpr(value):
    text = par(value, 3)
    return " " + text if text.startswith("{") else text


def tailfix(stmts, end="continue"):
    """Remove o salto final implícito (`continue` num laço, `return` num módulo).
    Deixa o corpo de um laço mais legível: troca `if c: ...; continue`
    seguido de mais código por `if c: ... else: ...`."""
    stmts = list(stmts)
    if stmts and stmts[-1] == end:
        stmts.pop()
    for n, s in enumerate(stmts):
        if isinstance(s, tuple) and s[0] == "if" and not s[3] and s[2] and s[2][-1] == end:
            rest = tailfix(stmts[n + 1:], end)
            then = tailfix(s[2], end)
            if not then:
                return stmts[:n] + [("if", neg(s[1]), rest, [])] if rest else stmts[:n]
            return stmts[:n] + [("if", s[1], then, rest)]
    if stmts and isinstance(stmts[-1], tuple) and stmts[-1][0] == "if":
        s = stmts[-1]
        stmts[-1] = ("if", s[1], tailfix(s[2], end), tailfix(s[3], end))
    return stmts


# --------------------------------------------------------------------------
# Geração do texto final
# --------------------------------------------------------------------------
def render(stmts, indent=0):
    pad = "    " * indent
    lines = []
    for s in stmts:
        if isinstance(s, str):
            lines.append(pad + s)
        elif s[0] == "return":
            lines.append(pad + ("return" if s[1] == "None" else f"return {s[1]}"))
        elif s[0] == "if" and not s[3] and len(s[2]) == 1 and isinstance(s[2][0], str) \
                and re.fullmatch(r"raise AssertionError(\(.*\))?", s[2][0]):
            message = s[2][0][len("raise AssertionError("):-1]
            lines.append(f"{pad}assert {par(neg(s[1]), 3)}" + (f", {message}" if message else ""))
        elif s[0] == "if":
            word = "if"
            while True:
                lines.append(f"{pad}{word} {s[1]}:")
                lines += render(s[2], indent + 1) or [pad + "    pass"]
                orelse = s[3]
                if len(orelse) == 1 and isinstance(orelse[0], tuple) and orelse[0][0] == "if":
                    s, word = orelse[0], "elif"
                    continue
                if orelse:
                    lines.append(pad + "else:")
                    lines += render(orelse, indent + 1)
                break
        elif s[0] in ("while", "for"):
            head = f"while {s[1]}:" if s[0] == "while" else f"for {s[1]} in {s[2]}:"
            lines.append(pad + head)
            lines += render(s[-2], indent + 1) or [pad + "    pass"]
            if s[-1]:
                lines.append(pad + "else:")
                lines += render(s[-1], indent + 1)
        elif s[0] in ("def", "class"):
            if lines:
                lines.append("")
            lines += (render_def if s[0] == "def" else render_class)(s[1], indent)
            lines.append("")
    while lines and not lines[-1]:
        lines.pop()
    return [a for a, b in zip(lines, [None] + lines) if a or b]  # sem linhas vazias duplas


def fallback(code, error, indent):
    """Quando não dá para descompilar, mostra o bytecode como comentário."""
    pad = "    " * indent
    lines = [f"{pad}# NÃO DESCOMPILADO ({error}). Bytecode:"]
    lines += [f"{pad}#   {line}" for line in dis.Bytecode(code).dis().splitlines() if line.strip()]
    return lines


def render_def(func, indent):
    pad = "    " * indent
    code = func.code
    lines = [f"{pad}@{d}" for d in func.decorators]
    lines.append(f"{pad}def {code.co_name}({func.signature()}):")
    body = []
    doc = code.co_consts[0] if code.co_consts else None
    if isinstance(doc, str):  # no Python 3.13 a docstring é a primeira constante
        body.append(repr(doc))
    try:
        d = Decompiler(code)
        stmts = d.body()
        if stmts and stmts[-1] == ("return", "None"):
            stmts.pop()
        lines += render(body + d.declared + stmts, indent + 1) or [pad + "    pass"]
    except Exception as error:  # noqa: BLE001 - qualquer falha vira comentário
        lines += fallback(code, error, indent + 1) + [pad + "    pass"]
    return lines


CLASS_NOISE = ("__module__ = ", "__qualname__ = ", "__firstlineno__ = ",
               "__static_attributes__ = ")


def render_class(cls, indent):
    pad = "    " * indent
    lines = [f"{pad}@{d}" for d in cls.decorators]
    bases = f"({', '.join(cls.bases)})" if cls.bases else ""
    lines.append(f"{pad}class {cls.name}{bases}:")
    try:
        stmts = [s for s in Decompiler(cls.code).body()
                 if not (isinstance(s, str) and s.startswith(CLASS_NOISE))
                 and not (isinstance(s, tuple) and s[0] == "return")]
        stmts = [s[len("__doc__ = "):] if isinstance(s, str) and s.startswith("__doc__ = ")
                 else s for s in stmts]
        lines += render(stmts, indent + 1) or [pad + "    pass"]
    except Exception as error:  # noqa: BLE001 - qualquer falha vira comentário
        lines += fallback(cls.code, error, indent + 1) + [pad + "    pass"]
    return lines


def decompile(code):
    """Recebe o objeto de código de um módulo e devolve o código-fonte."""
    try:
        stmts = Decompiler(code).body()
    except Exception as error:  # noqa: BLE001 - qualquer falha vira comentário
        return "\n".join(fallback(code, error, 0)) + "\n"
    stmts = tailfix(stmts, ("return", "None"))
    if stmts and isinstance(stmts[0], str) and stmts[0].startswith("__doc__ = "):
        stmts[0] = stmts[0][len("__doc__ = "):]
    return "\n".join(render(stmts)) + "\n"


def load_pyc(path):
    """Lê um arquivo .pyc e devolve o objeto de código."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != importlib.util.MAGIC_NUMBER:
        raise SystemExit(
            f"Erro: '{path}' foi compilado por outra versão do Python (ou não é um .pyc).\n"
            f"Execute este script com a mesma versão que gerou o arquivo "
            f"(você está usando o Python {sys.version.split()[0]}).")
    return marshal.loads(data[16:])  # 16 bytes de cabeçalho


def main():
    parser = argparse.ArgumentParser(description="Descompilador simples de arquivos .pyc")
    parser.add_argument("arquivo", help="arquivo .pyc a descompilar")
    parser.add_argument("-o", "--saida", help="arquivo .py de saída (padrão: tela)")
    parser.add_argument("--dis", action="store_true", help="mostra o bytecode em vez do código")
    args = parser.parse_args()
    code = load_pyc(args.arquivo)
    if args.dis:
        dis.dis(code)
        return
    source = decompile(code)
    if args.saida:
        with open(args.saida, "w", encoding="utf-8") as f:
            f.write(source)
        print(f"Código salvo em {args.saida}")
    else:
        sys.stdout.write(source)


if __name__ == "__main__":
    main()
