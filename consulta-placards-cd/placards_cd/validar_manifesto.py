"""Valida um manifesto de desenhos 2D e, opcionalmente, os PDFs locais.

Uso:
    python -m placards_cd.validar_manifesto desenhos/manifesto.json \
        [--base dist/base_placards_cd.json] [--pasta-pdf "Z:/desenhos liberados"]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .manifesto import carregar_manifesto, verificar_pdfs


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("manifesto")
    p.add_argument("--base", help="base_placards_cd.json para conferir os topos")
    p.add_argument("--pasta-pdf", help="pasta autorizada com os PDFs locais (confere hash e páginas)")
    a = p.parse_args(argv)
    topos = None
    if a.base:
        base = json.loads(Path(a.base).read_text(encoding="utf-8"))
        topos = {r["topo_normalizado"] for r in base.get("registros", [])}
    res = carregar_manifesto(Path(a.manifesto), topos)
    problemas = list(res["erros"])
    if a.pasta_pdf and res["manifesto"] and not res["erros"]:
        problemas += verificar_pdfs(res["manifesto"], Path(a.pasta_pdf))
    for av in res["avisos"]:
        print(f"AVISO {av['codigo']} {av['caminho']}: {av['mensagem']}")
    for e in problemas:
        print(f"ERRO  {e['codigo']} {e['caminho']}: {e['mensagem']}")
    if problemas:
        return 1
    n = len(res["manifesto"]["desenhos"])
    conferidos = sum(1 for d in res["manifesto"]["desenhos"] if d["vinculo_conferido"])
    print(f"Manifesto válido: {n} desenho(s), {conferidos} com vínculo conferido.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
