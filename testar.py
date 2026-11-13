"""Teste: compila cada exemplo, descompila e confere se o resultado
descompilado se comporta igual ao programa original."""
import contextlib
import glob
import io
import py_compile
import sys
import tempfile

import descompilador


def executar(codigo):
    saida = io.StringIO()
    with contextlib.redirect_stdout(saida):
        exec(codigo, {"__name__": "__main__"})
    return saida.getvalue()


falhas = 0
for arquivo in sorted(glob.glob("exemplos/*.py")):
    with tempfile.TemporaryDirectory() as pasta:
        pyc = py_compile.compile(arquivo, cfile=f"{pasta}/x.pyc", doraise=True)
        fonte = descompilador.decompile(descompilador.load_pyc(pyc))
    original = executar(compile(open(arquivo, encoding="utf-8").read(), arquivo, "exec"))
    try:
        ok = "NÃO DESCOMPILADO" not in fonte and executar(compile(fonte, "descompilado", "exec")) == original
    except Exception as erro:
        print("  erro:", repr(erro))
        ok = False
    print("OK   " if ok else "FALHA", arquivo)
    if not ok:
        falhas += 1
        print("\n".join(fonte.splitlines()[:40]))
sys.exit(1 if falhas else 0)
