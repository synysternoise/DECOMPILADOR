"""Importador reproduzível: planilha (ou CSV/TSV) -> base JSON + relatório + HTML.

Uso:
    python -m placards_cd.importar --planilha "PLANILHA_PLACARD CD.xlsx" --saida dist
    python -m placards_cd.importar --csv plastico.csv --csv metalico.csv --saida dist
    python -m placards_cd.importar --sem-base --saida dist
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

from . import importacao as imp
from .construir_html import montar_html
from .leitores import ler_csv, ler_xls, ler_xlsx, nomes_abas_xlsx
from .manifesto import carregar_manifesto, url_https_valida

FORMATO_BASE = "base-placards-cd"
VERSAO_BASE = 1
RAIZ = Path(__file__).resolve().parent.parent
REFERENCIA_PADRAO = RAIZ / "config" / "snapshot_conferido.json"


def sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def metadados_fonte(caminho: Path, formato: str) -> dict:
    info = caminho.stat()
    return {
        "arquivo": caminho.name,  # só o nome; o caminho local não é publicado
        "formato": formato,
        "sha256": sha256_arquivo(caminho),
        "tamanho_bytes": info.st_size,
        "modificado_em": dt.datetime.fromtimestamp(info.st_mtime).isoformat(timespec="seconds"),
    }


def resolver_abas(nomes: list[str]) -> tuple[dict[str, str], list[dict]]:
    """Encontra as abas do escopo; as demais são registradas como ignoradas."""
    por_norma = {imp.normalizar_nome_aba(n): n for n in nomes}
    encontradas: dict[str, str] = {}
    for kit, esperado in imp.ABAS_ESCOPO.items():
        if esperado in nomes:
            encontradas[kit] = esperado
        elif imp.normalizar_nome_aba(esperado) in por_norma:
            encontradas[kit] = por_norma[imp.normalizar_nome_aba(esperado)]
    faltando = [imp.ABAS_ESCOPO[k] for k in imp.ABAS_ESCOPO if k not in encontradas]
    if faltando:
        raise imp.ErroLayout(f"Aba(s) não encontrada(s): {faltando}. Abas do arquivo: {nomes}")
    usadas = set(encontradas.values())
    ignoradas = [{"aba": n, "motivo": "fora do escopo (somente PLACARD, KIT PLASTIC/METALLIC)"}
                 for n in nomes if n not in usadas]
    return encontradas, ignoradas


def importar_planilha(caminho: Path) -> tuple[list[dict], dict, list[dict]]:
    sufixo = caminho.suffix.lower()
    if sufixo in (".xlsx", ".xlsm"):
        nomes = nomes_abas_xlsx(caminho)
        abas, ignoradas = resolver_abas(nomes)
        _, dados = ler_xlsx(caminho, list(abas.values()))
        formato = sufixo[1:]
    elif sufixo == ".xls":
        import xlrd  # noqa: F401 - erro claro se ausente
        livro = xlrd.open_workbook(file_contents=caminho.read_bytes(), on_demand=True)
        nomes = livro.sheet_names()
        livro.release_resources()
        abas, ignoradas = resolver_abas(nomes)
        _, dados = ler_xls(caminho, list(abas.values()))
        formato = "xls"
    else:
        raise SystemExit(f"Formato não suportado: {sufixo}. Use .xlsx, .xlsm, .xls ou --csv.")
    resultados = [imp.importar_aba(kit, aba, dados[aba]) for kit, aba in abas.items()]
    return resultados, metadados_fonte(caminho, formato), ignoradas


def importar_csvs(caminhos: list[Path]) -> tuple[list[dict], dict, list[dict]]:
    resultados = []
    kits_vistos = set()
    for caminho in caminhos:
        linhas = ler_csv(caminho)
        textos = [imp._textos(l) for l in linhas[: imp.MAX_LINHA_CABECALHO]]
        cab = next((t for t in textos if imp.eh_linha_cabecalho(t)), None)
        kit = imp.detectar_kit(cab) if cab else None
        if kit is None:
            raise imp.ErroLayout(f"{caminho.name}: não foi possível identificar o kit pelo cabeçalho "
                                 "(C=CDPL (REF) e H=CONJUNTO para plástico; C=PART NUMBER e H=MATERIAL para metálico).")
        if kit in kits_vistos:
            raise imp.ErroLayout(f"{caminho.name}: kit {kit} informado em mais de um arquivo.")
        kits_vistos.add(kit)
        resultados.append(imp.importar_aba(kit, f"{imp.ABAS_ESCOPO[kit]} [CSV {caminho.name}]", linhas))
    fonte = {"arquivos": [metadados_fonte(c, "csv") for c in caminhos], "formato": "csv",
             "arquivo": ", ".join(c.name for c in caminhos)}
    return resultados, fonte, []


def relatorio_markdown(rel: dict) -> str:
    linhas = ["# Relatório de importação — placards configuração CD", "",
              f"- Fonte: `{rel['fonte'].get('arquivo')}` ({rel['fonte'].get('formato')})",
              f"- SHA-256: `{rel['fonte'].get('sha256', '—')}`",
              f"- Gerado em: {rel['gerado_em']}",
              f"- Fonte inalterada após a leitura: {'sim' if rel['fonte_inalterada'] else 'NÃO'}", ""]
    linhas += ["## Contagens por kit", "", "| Kit | Aba | Registros CD | Sem PN novo | Sem descrição | "
               "Provisórios | Divergência de quantidade | Exclusões | Topos |", "|---|---|---|---|---|---|---|---|---|"]
    for kit, r in rel["resumo"].items():
        topos = "; ".join(f"{t} ({n})" for t, n in r["topos"].items())
        linhas.append(f"| {imp.ROTULO_KIT[kit]} | {r['aba']} | {r['registros']} | {r['sem_pn_novo']} | "
                      f"{r['sem_descricao']} | {r['provisorios']} | {r['com_divergencia_quantidade']} | "
                      f"{r['exclusoes']} | {topos} |")
    linhas += ["", "## Comparação com o snapshot conferido", ""]
    comp = rel.get("comparacao_snapshot")
    if comp is None:
        linhas.append("Sem arquivo de referência.")
    elif not comp["diferencas"]:
        linhas.append("Contagens iguais às do snapshot conferido.")
    else:
        linhas.append("**Diferenças (reportadas, não corrigidas):**")
        linhas += [f"- {d}" for d in comp["diferencas"]]
    linhas += ["", "## Abas ignoradas", ""] + [f"- {a['aba']}: {a['motivo']}" for a in rel["abas_ignoradas"]]
    linhas += ["", f"## Linhas excluídas ({len(rel['exclusoes'])})", "", "| Aba | Linha | Motivo | A | C | H |",
               "|---|---|---|---|---|---|"]
    esc = lambda s: (s or "").replace("|", "\\|")  # noqa: E731
    for e in rel["exclusoes"]:
        linhas.append(f"| {esc(e['aba'])} | {e['linha']} | {esc(e['motivo'])} | {esc(e['a'])} | {esc(e['c'])} | {esc(e['h'])} |")
    linhas += ["", "## Registros com divergência de quantidade", "", "| Kit | Linha | PN novo | C | QTY | Soma folhas | Total |",
               "|---|---|---|---|---|---|---|"]
    for r in rel["divergencias"]:
        linhas.append(f"| {imp.ROTULO_KIT[r['kit']]} | {r['linha']} | {esc(r['pn_novo'])} | {esc(r['pn_antigo'])} | "
                      f"{esc(r['qty'])} | {imp.fmt_num(r['soma_folhas'])} | {esc(r['total_registrado'])} |")
    return "\n".join(linhas) + "\n"


def executar(args: argparse.Namespace) -> int:
    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)

    for origem in args.origem_autorizada:
        if not url_https_valida(origem):
            raise SystemExit(f"--origem-autorizada deve ser uma origem HTTPS: {origem!r}")
    origens = sorted({o.rstrip("/") for o in args.origem_autorizada})

    base = None
    topos_base = None
    if not args.sem_base:
        if args.planilha:
            caminho = Path(args.planilha)
            hash_antes = sha256_arquivo(caminho)
            resultados, fonte, ignoradas = importar_planilha(caminho)
            inalterada = sha256_arquivo(caminho) == hash_antes
        else:
            caminhos = [Path(c) for c in args.csv]
            hashes = [sha256_arquivo(c) for c in caminhos]
            resultados, fonte, ignoradas = importar_csvs(caminhos)
            inalterada = hashes == [sha256_arquivo(c) for c in caminhos]
        registros = [r for res in resultados for r in res["registros"]]
        resumo = {res["kit"]: imp.resumo_kit(res) for res in resultados}
        exclusoes = [e for res in resultados for e in res["exclusoes"]]
        gerado = dt.datetime.now().isoformat(timespec="seconds")
        topos_base = {r["topo_normalizado"] for r in registros}
        rel = {
            "fonte": fonte, "gerado_em": gerado, "fonte_inalterada": inalterada,
            "configuracao": imp.CONFIGURACAO_ALVO, "resumo": resumo,
            "abas_ignoradas": ignoradas, "exclusoes": exclusoes,
            "divergencias": [r for r in registros if {a["codigo"] for a in r["avisos"]}
                             & {"QTY_DIF_SOMA", "TOTAL_DIF_SOMA", "QTY_DIF_TOTAL"}],
        }
        ref_caminho = Path(args.referencia) if args.referencia else REFERENCIA_PADRAO
        if ref_caminho.is_file() and not args.sem_referencia:
            ref = json.loads(ref_caminho.read_text(encoding="utf-8"))
            rel["comparacao_snapshot"] = {"referencia": ref_caminho.name, "esperado": ref.get("kits", {}),
                                          "diferencas": imp.comparar_com_referencia(resumo, ref)}
        else:
            rel["comparacao_snapshot"] = None
        base = {
            "formato": FORMATO_BASE, "versao_formato": VERSAO_BASE, "configuracao": imp.CONFIGURACAO_ALVO,
            "fonte": fonte, "gerado_em": gerado, "resumo": resumo, "abas_ignoradas": ignoradas,
            "exclusoes": exclusoes, "comparacao_snapshot": rel["comparacao_snapshot"], "registros": registros,
        }
        (saida / "base_placards_cd.json").write_text(json.dumps(base, ensure_ascii=False, indent=1), encoding="utf-8")
        rel_json = {k: v for k, v in rel.items() if k != "divergencias"}
        rel_json["divergencias"] = [{k: r[k] for k in ("kit", "aba", "linha", "pn_novo", "pn_antigo", "qty",
                                                        "soma_folhas", "total_registrado")} for r in rel["divergencias"]]
        (saida / "relatorio_importacao.json").write_text(json.dumps(rel_json, ensure_ascii=False, indent=1),
                                                         encoding="utf-8")
        (saida / "relatorio_importacao.md").write_text(relatorio_markdown(rel), encoding="utf-8")

        print(f"Fonte: {fonte.get('arquivo')}  (inalterada: {'sim' if inalterada else 'NÃO'})")
        for kit, r in resumo.items():
            print(f"  {imp.ROTULO_KIT[kit]:9} {r['registros']:4} registros CD | sem PN novo: {r['sem_pn_novo']} | "
                  f"exclusões: {r['exclusoes']} | topos: {', '.join(r['topos'])}")
        comp = rel["comparacao_snapshot"]
        if comp and comp["diferencas"]:
            print("  Diferenças em relação ao snapshot conferido (não corrigidas):")
            for d in comp["diferencas"]:
                print(f"    - {d}")
        elif comp:
            print("  Contagens conferem com o snapshot de referência.")

    manifesto = None
    if args.manifesto:
        res = carregar_manifesto(Path(args.manifesto), topos_base)
        for a in res["avisos"]:
            print(f"  Manifesto (aviso) {a['caminho']}: {a['mensagem']}")
        if res["erros"]:
            for e in res["erros"]:
                print(f"  Manifesto (ERRO) {e['caminho']}: {e['mensagem']}", file=sys.stderr)
            raise SystemExit("Manifesto inválido; HTML não gerado.")
        manifesto = res["manifesto"]

    config = {"origens_pdf_autorizadas": origens, "gerado_em": dt.datetime.now().isoformat(timespec="seconds")}
    ref_cfg = Path(args.referencia) if args.referencia else REFERENCIA_PADRAO
    if ref_cfg.is_file() and not args.sem_referencia:
        # Para a página comparar quando a planilha é carregada direto no navegador
        config["referencia_snapshot"] = json.loads(ref_cfg.read_text(encoding="utf-8"))
    html = montar_html(base, manifesto, config)
    destino = saida / args.nome_html
    destino.write_text(html, encoding="utf-8")
    print(f"HTML: {destino}" + ("  (base NÃO carregada)" if base is None else ""))
    return 0


def criar_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    fonte = p.add_mutually_exclusive_group(required=True)
    fonte.add_argument("--planilha", help="PLANILHA_PLACARD CD.xlsx (.xlsx, .xlsm ou .xls)")
    fonte.add_argument("--csv", action="append", help="aba exportada como CSV/TSV (repita para cada kit)")
    fonte.add_argument("--sem-base", action="store_true", help="gera o HTML com a base marcada como não carregada")
    p.add_argument("--saida", default="dist", help="pasta de saída (padrão: dist)")
    p.add_argument("--nome-html", default="consulta-placards-cd.html")
    p.add_argument("--manifesto", help="manifesto de desenhos 2D a incorporar (JSON)")
    p.add_argument("--origem-autorizada", action="append", default=[],
                   help="origem HTTPS corporativa autorizada para PDFs (repita se preciso)")
    p.add_argument("--referencia", help=f"contagens do snapshot conferido (padrão: {REFERENCIA_PADRAO.name})")
    p.add_argument("--sem-referencia", action="store_true", help="não comparar com o snapshot conferido")
    return p


def main(argv=None) -> int:
    args = criar_parser().parse_args(argv)
    try:
        return executar(args)
    except imp.ErroLayout as exc:
        print(f"ERRO DE LAYOUT: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
