"""Publica a Consulta de Placards a partir da pasta compartilhada.

O ADM roda isto (pelo ATUALIZAR CONSULTA.bat) sempre que a planilha mudar
ou entrarem desenhos novos. Lê a planilha (sem alterá-la), procura os PDFs
em desenhos/ pelo PN novo (ou pelo CDPL, se não houver PDF com o PN) e
regrava o HTML que todos abrem.

Uso:  python -m placards_cd.publicar [--config config.json]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

from . import importacao as imp
from .leitores import ler_xls, ler_xlsx

ADM = Path(__file__).resolve().parent.parent
WEB = ADM / "web"
VERSAO_APP = "1.0"

CONFIG_PADRAO = {
    "planilha": "../PLANILHA_PLACARD CD.xlsx",
    "pasta_desenhos": "../desenhos",
    "arquivo_consulta": "../Consulta de Placards.html",
    "links_absolutos": False,
    "desenvolvedor": {"nome": "", "contato": "", "iniciais": ""},
    "snapshot_referencia": "snapshot_conferido.json",
}


class ErroPublicacao(Exception):
    pass


# ------------------------------------------------------------------ planilha

def sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def resolver_abas(nomes: list[str]) -> tuple[dict[str, str], list[dict]]:
    por_norma = {imp.normalizar_nome_aba(n): n for n in nomes}
    encontradas = {}
    for kit, esperado in imp.ABAS_ESCOPO.items():
        if esperado in nomes:
            encontradas[kit] = esperado
        elif imp.normalizar_nome_aba(esperado) in por_norma:
            encontradas[kit] = por_norma[imp.normalizar_nome_aba(esperado)]
    faltando = [imp.ABAS_ESCOPO[k] for k in imp.ABAS_ESCOPO if k not in encontradas]
    if faltando:
        raise imp.ErroLayout(f"Aba(s) não encontrada(s): {faltando}. Abas do arquivo: {nomes}")
    usadas = set(encontradas.values())
    return encontradas, [{"aba": n, "motivo": "fora do escopo"} for n in nomes if n not in usadas]


def ler_planilha(caminho: Path) -> tuple[list[dict], list[dict]]:
    sufixo = caminho.suffix.lower()
    if sufixo in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(caminho.read_bytes()), read_only=True)
        nomes = list(wb.sheetnames)
        wb.close()
        abas, ignoradas = resolver_abas(nomes)
        _, dados = ler_xlsx(caminho, list(abas.values()))
    elif sufixo == ".xls":
        import xlrd
        livro = xlrd.open_workbook(file_contents=caminho.read_bytes(), on_demand=True)
        nomes = livro.sheet_names()
        livro.release_resources()
        abas, ignoradas = resolver_abas(nomes)
        _, dados = ler_xls(caminho, list(abas.values()))
    else:
        raise ErroPublicacao(f"Formato não suportado: {caminho.name}. Use .xlsx (ou .xls).")
    return [imp.importar_aba(kit, aba, dados[aba]) for kit, aba in abas.items()], ignoradas


# ------------------------------------------------------------------ desenhos

def chave_desenho(nome: str) -> str:
    return re.sub(r"\s+", "", nome).upper()


def listar_desenhos(pasta: Path) -> tuple[dict[str, Path], list[str]]:
    """PDFs da pasta (e subpastas), indexados pelo nome sem extensão."""
    mapa: dict[str, Path] = {}
    repetidos: list[str] = []
    if not pasta.is_dir():
        return mapa, repetidos
    for pdf in sorted(pasta.rglob("*")):
        if pdf.is_file() and pdf.suffix.lower() == ".pdf":
            k = chave_desenho(pdf.stem)
            if k in mapa:
                repetidos.append(str(pdf.relative_to(pasta)))
            else:
                mapa[k] = pdf
    return mapa, repetidos


def link_para(pdf: Path, saida: Path, absoluto: bool) -> str:
    if absoluto:
        return pdf.resolve().as_uri()
    rel = os.path.relpath(pdf.resolve(), saida.resolve().parent)
    return "/".join(quote(parte) for parte in Path(rel).as_posix().split("/"))


# ------------------------------------------------------------------ HTML

def json_para_script(dados) -> str:
    texto = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
    return (texto.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def montar_html(dados: dict | None) -> str:
    modelo = (WEB / "template.html").read_text(encoding="utf-8")
    trocas = {
        "/*__CSS__*/": (WEB / "estilo.css").read_text(encoding="utf-8"),
        "/*__AVIAO__*/": (WEB / "aviao.js").read_text(encoding="utf-8"),
        "/*__BUSCA__*/": (WEB / "busca.js").read_text(encoding="utf-8"),
        "/*__APP__*/": (WEB / "app.js").read_text(encoding="utf-8"),
        "__DADOS__": json_para_script(dados),
    }
    for m in trocas:
        if modelo.count(m) != 1:
            raise RuntimeError(f"Marcador {m} deve aparecer uma vez em template.html")
    padrao = re.compile("|".join(re.escape(m) for m in trocas))
    return padrao.sub(lambda m: trocas[m.group(0)], modelo)


def gravar_atomico(destino: Path, texto: str):
    """Grava em arquivo temporário e troca, para ninguém abrir um HTML pela metade."""
    tmp = destino.with_name(destino.name + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    os.replace(tmp, destino)


CAMPOS_PUBLICOS = ("kit", "linha", "pn_novo", "ref_e2", "pn_antigo", "descricao", "pos", "zona", "topo_normalizado")


def registro_publico(r: dict, desenho: str | None) -> dict:
    p = {k: r[k] for k in CAMPOS_PUBLICOS}
    p["folhas"] = [{"folha": f["folha"], "texto": f["texto"], "numero": f["numero"], "aparece": f["aparece"]}
                   for f in r["folhas"]]
    p["desenho"] = desenho
    return p


# ------------------------------------------------------------------ relatório

def relatorio(fonte: dict, resumo: dict, ignoradas, exclusoes, divergencias, sem_desenho, pdfs_sem_placard,
              repetidos, comparacao, gerado: str) -> str:
    esc = lambda s: (s or "").replace("|", "\\|")  # noqa: E731
    L = [f"# Publicação da Consulta de Placards — {gerado}", "",
         f"- Planilha: `{fonte['arquivo']}` (SHA-256 `{fonte['sha256'][:16]}…`, não alterada)", ""]
    L += ["| Kit | Registros CD | Sem PN novo | Divergência de quantidade | Linhas excluídas |", "|---|---|---|---|---|"]
    for kit, r in resumo.items():
        L.append(f"| {imp.ROTULO_KIT[kit]} | {r['registros']} | {r['sem_pn_novo']} | "
                 f"{r['com_divergencia_quantidade']} | {r['exclusoes']} |")
    L += ["", "## Comparação com o snapshot conferido", ""]
    if comparacao is None:
        L.append("Sem referência.")
    elif comparacao:
        L += ["**Diferenças (reportadas, nada foi alterado):**"] + [f"- {d}" for d in comparacao]
    else:
        L.append("Contagens iguais às do snapshot conferido.")
    L += ["", f"## Placards sem desenho 2D ({len(sem_desenho)})", ""]
    L += [f"- {esc(r['pn_novo'] or '(sem PN novo)')} / {esc(r['pn_antigo'])} — {esc(r['descricao'])}" for r in sem_desenho]
    L += ["", f"## PDFs em desenhos/ que não correspondem a nenhum placard ({len(pdfs_sem_placard)})", ""]
    L += [f"- {p}" for p in pdfs_sem_placard]
    if repetidos:
        L += ["", "## PDFs com nome repetido (ignorados)", ""] + [f"- {p}" for p in repetidos]
    L += ["", f"## Divergências de quantidade ({len(divergencias)})", "",
          "| Kit | Linha | PN novo | CDPL | QTY | Soma das folhas | Total |", "|---|---|---|---|---|---|---|"]
    for r in divergencias:
        L.append(f"| {imp.ROTULO_KIT[r['kit']]} | {r['linha']} | {esc(r['pn_novo'])} | {esc(r['pn_antigo'])} | "
                 f"{esc(r['qty'])} | {imp.fmt_num(r['soma_folhas'])} | {esc(r['total_registrado'])} |")
    L += ["", "## Abas ignoradas", ""] + [f"- {a['aba']}" for a in ignoradas]
    L += ["", f"## Linhas excluídas ({len(exclusoes)})", "", "| Aba | Linha | Motivo | A | C | H |", "|---|---|---|---|---|---|"]
    for e in exclusoes:
        L.append(f"| {esc(e['aba'])} | {e['linha']} | {esc(e['motivo'])} | {esc(e['a'])} | {esc(e['c'])} | {esc(e['h'])} |")
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------ principal

def carregar_config(caminho: Path) -> tuple[dict, Path]:
    cfg = json.loads(json.dumps(CONFIG_PADRAO))
    base = ADM
    if caminho.is_file():
        lido = json.loads(caminho.read_text(encoding="utf-8"))
        dev = {**cfg["desenvolvedor"], **lido.get("desenvolvedor", {})}
        cfg.update(lido)
        cfg["desenvolvedor"] = dev
        base = caminho.resolve().parent
    return cfg, base


def publicar(cfg: dict, base: Path, sem_base: bool = False) -> dict:
    saida = (base / cfg["arquivo_consulta"]).resolve()
    dev = {k: str(cfg["desenvolvedor"].get(k, "") or "") for k in ("nome", "contato", "iniciais")}
    if sem_base:
        gravar_atomico(saida, montar_html({"desenvolvedor": dev, "versao_app": VERSAO_APP, "registros": None}))
        return {"saida": saida}

    planilha = (base / cfg["planilha"]).resolve()
    if not planilha.is_file():
        raise ErroPublicacao(f"Planilha não encontrada: {planilha}\nConfira o nome em _adm/config.json.")
    hash_antes = sha256_arquivo(planilha)
    resultados, ignoradas = ler_planilha(planilha)
    if sha256_arquivo(planilha) != hash_antes:
        raise ErroPublicacao("A planilha mudou durante a leitura (alguém salvou?). Rode de novo.")
    fonte = {"arquivo": planilha.name, "sha256": hash_antes}

    registros = [r for res in resultados for r in res["registros"]]
    resumo = {res["kit"]: imp.resumo_kit(res) for res in resultados}
    exclusoes = [e for res in resultados for e in res["exclusoes"]]
    divergencias = [r for r in registros if {a["codigo"] for a in r["avisos"]}
                    & {"QTY_DIF_SOMA", "TOTAL_DIF_SOMA", "QTY_DIF_TOTAL"}]

    pasta = (base / cfg["pasta_desenhos"]).resolve()
    pdfs, repetidos = listar_desenhos(pasta)
    usados, publicos, sem_desenho = set(), [], []
    for r in registros:
        achado = None
        for ident in (r["pn_novo"], r["pn_antigo"]):
            if ident and chave_desenho(ident) in pdfs:
                achado = chave_desenho(ident)
                break
        if achado:
            usados.add(achado)
            publicos.append(registro_publico(r, link_para(pdfs[achado], saida, bool(cfg.get("links_absolutos")))))
        else:
            sem_desenho.append(r)
            publicos.append(registro_publico(r, None))
    pdfs_sem_placard = [str(p.relative_to(pasta)) for k, p in pdfs.items() if k not in usados]

    comparacao = None
    ref = (base / cfg["snapshot_referencia"]) if cfg.get("snapshot_referencia") else None
    if ref and ref.is_file():
        comparacao = imp.comparar_com_referencia(resumo, json.loads(ref.read_text(encoding="utf-8")))

    gerado = dt.datetime.now().isoformat(timespec="seconds")
    dados = {"versao_formato": 1, "versao_app": VERSAO_APP, "gerado_em": gerado, "fonte": fonte,
             "desenvolvedor": dev, "total_desenhos": len(usados), "registros": publicos}
    gravar_atomico(saida, montar_html(dados))
    rel = base / "relatorio_ultima_publicacao.md"
    rel.write_text(relatorio(fonte, resumo, ignoradas, exclusoes, divergencias, sem_desenho, pdfs_sem_placard,
                             repetidos, comparacao, gerado), encoding="utf-8")
    return {"saida": saida, "relatorio": rel, "resumo": resumo, "registros": registros, "publicos": publicos,
            "exclusoes": exclusoes, "sem_desenho": sem_desenho, "pdfs_sem_placard": pdfs_sem_placard,
            "comparacao": comparacao, "fonte": fonte, "ignoradas": ignoradas}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default=str(ADM / "config.json"))
    p.add_argument("--sem-base", action="store_true", help="gera a consulta vazia (\"ainda não publicada\")")
    a = p.parse_args(argv)
    try:
        cfg, base = carregar_config(Path(a.config))
        res = publicar(cfg, base, a.sem_base)
    except (ErroPublicacao, imp.ErroLayout) as exc:
        print(f"\nERRO: {exc}\n", file=sys.stderr)
        return 2
    if a.sem_base:
        print(f"Consulta vazia gravada em: {res['saida']}")
        return 0
    print(f"\nPlanilha: {res['fonte']['arquivo']} (não alterada)")
    for kit, r in res["resumo"].items():
        print(f"  {imp.ROTULO_KIT[kit]:9} {r['registros']:4} placards | sem PN novo: {r['sem_pn_novo']} | "
              f"linhas excluídas: {r['exclusoes']}")
    print(f"  Desenhos 2D encontrados: {sum(1 for x in res['publicos'] if x['desenho'])} placards com PDF, "
          f"{len(res['sem_desenho'])} sem PDF, {len(res['pdfs_sem_placard'])} PDFs sem placard")
    if res["comparacao"]:
        print("  ATENÇÃO — diferenças em relação ao snapshot conferido (nada foi alterado):")
        for d in res["comparacao"]:
            print(f"    - {d}")
    print(f"\nConsulta publicada: {res['saida']}")
    print(f"Relatório: {res['relatorio']}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
