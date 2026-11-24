"""Regras de importação dos placards da configuração CD.

A lógica aqui é espelhada em ``web/nucleo.js`` (importação CSV/TSV pela
interface). O teste ``test_paridade_python_js`` garante que as duas
implementações produzem os mesmos registros.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from .leitores import Celula, ERROS_EXCEL

CONFIGURACAO_ALVO = "CD"
NUM_FOLHAS = 20
MAX_LINHA_CABECALHO = 15

ABAS_ESCOPO = {
    "PLASTICO": "PLACARD, KIT PLASTIC",
    "METALICO": "PLACARD, KIT METALLIC",
}
ROTULO_KIT = {"PLASTICO": "Plástico", "METALICO": "Metálico"}

# Índices de coluna (base 0)
A, B, C, D, E, F, G, H, I, J, K = range(11)
SH1 = 11                      # L
SH20 = SH1 + NUM_FOLHAS - 1   # AE
AF, AG, AH = 31, 32, 33
NUM_COLUNAS = 34


def letra_coluna(indice: int) -> str:
    n = indice + 1
    letras = ""
    while n:
        n, resto = divmod(n - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


def normalizar_cabecalho(texto: Optional[str]) -> str:
    if not texto:
        return ""
    sem_acento = "".join(ch for ch in unicodedata.normalize("NFD", texto) if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", sem_acento).strip().upper()


def normalizar_nome_aba(nome: str) -> str:
    return re.sub(r"[\s,]+", "", normalizar_cabecalho(nome))


def extrair_configuracao(h: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Devolve (configuração, topo_normalizado) a partir da coluna H.

    ``171-60473-401/ CD`` -> (``CD``, ``171-60473-401/CD``).
    """
    if not h:
        return None, None
    s = h.strip().upper()
    if "/" in s:
        base, cfg = s.rsplit("/", 1)
        cfg = cfg.strip()
        if not re.fullmatch(r"[A-Z]{2,3}", cfg):
            return None, None
    else:
        m = re.fullmatch(r"(.+?)\s+([A-Z]{2,3})", s)
        if not m:
            return None, None
        base, cfg = m.group(1), m.group(2)
    base = re.sub(r"\s+", "", base)
    if not base:
        return None, None
    return cfg, f"{base}/{cfg}"


RE_PROVISORIO = re.compile(r"CDPL\s*X{2,}", re.IGNORECASE)
RE_NUMERO = re.compile(r"[+-]?\d+(?:[.,]\d+)?")


def eh_provisorio(texto: Optional[str]) -> bool:
    return bool(texto and RE_PROVISORIO.search(texto))


def numero(texto: Optional[str]) -> Optional[float]:
    if texto is None:
        return None
    t = texto.strip()
    if not RE_NUMERO.fullmatch(t):
        return None
    return float(t.replace(",", "."))


def fmt_num(valor: Optional[float]) -> str:
    if valor is None:
        return ""
    if float(valor).is_integer():
        return str(int(valor))
    return repr(round(valor, 10))


def iguais(a: float, b: float) -> bool:
    return abs(a - b) < 1e-9


# ------------------------------------------------------------------ layout

def eh_linha_cabecalho(textos: list[Optional[str]]) -> bool:
    return normalizar_cabecalho(textos[D]) == "POS" and normalizar_cabecalho(textos[E]).startswith("ZON")


def detectar_kit(cabecalho: list[Optional[str]]) -> Optional[str]:
    c = normalizar_cabecalho(cabecalho[C])
    h = normalizar_cabecalho(cabecalho[H])
    if "CDPL" in c and "CONJUNTO" in h:
        return "PLASTICO"
    if "PART NUMBER" in c and "MATERIAL" in h:
        return "METALICO"
    return None


def validar_layout(cabecalho: list[Optional[str]], kit: str) -> tuple[list[str], list[str]]:
    """Valida o cabeçalho por posição. Devolve (erros, avisos)."""
    n = [normalizar_cabecalho(x) for x in cabecalho]
    erros: list[str] = []
    avisos: list[str] = []

    def exigir(cond: bool, col: int, esperado: str):
        if not cond:
            erros.append(f"Coluna {letra_coluna(col)}: esperado {esperado}, encontrado {cabecalho[col]!r}.")

    def recomendar(cond: bool, col: int, esperado: str):
        if not cond:
            avisos.append(f"Coluna {letra_coluna(col)}: esperado {esperado}, encontrado {cabecalho[col]!r}.")

    exigir("PART NUMBER" in n[A] or re.search(r"\bPN\b", n[A]) is not None, A, "PART NUMBER (PN novo)")
    exigir("E2" in n[B] or "REFER" in n[B], B, "E2 REFERENCIA")
    if kit == "PLASTICO":
        exigir("CDPL" in n[C], C, "CDPL (REF)")
        exigir("CONJUNTO" in n[H], H, "CONJUNTO")
    else:
        exigir("PART NUMBER" in n[C] and "CDPL" not in n[C], C, "segundo PART NUMBER")
        exigir("MATERIAL" in n[H], H, "MATERIAL")
    exigir(n[D] == "POS", D, "POS")
    exigir(n[E].startswith("ZON"), E, "ZONE")
    exigir("QTY" in n[F] or "QTD" in n[F], F, "QTY")
    exigir("FORMATO" in n[G] or "DESCRI" in n[G], G, "FORMATO")
    for k in range(NUM_FOLHAS):
        col = SH1 + k
        m = re.fullmatch(r"SH\s*0*(\d+)", n[col])
        exigir(bool(m) and int(m.group(1)) == k + 1, col, f"SH{k + 1}")
    exigir("TOTAL" in n[AF], AF, "Total")
    recomendar(n[I].startswith("ECOD"), I, "ECODE")
    recomendar(n[J].startswith("ACTIO") or n[J].startswith("ACAO"), J, "ACTION")
    recomendar(n[K].startswith("LIBERA"), K, "LIBERADO")
    recomendar("CHECK" in n[AG], AG, "Check")
    return erros, avisos


class ErroLayout(Exception):
    pass


# ------------------------------------------------------------------ registros

def calcular_avisos(reg: dict, erros_colunas: list[tuple[int, str]], formulas_sem_cache: list[int]) -> list[dict]:
    avisos: list[dict] = []

    def add(codigo: str, mensagem: str):
        avisos.append({"codigo": codigo, "mensagem": mensagem})

    if not reg["pn_novo"]:
        add("SEM_PN_NOVO", "Sem PN novo (coluna A vazia).")
    if eh_provisorio(reg["pn_antigo"]):
        add("CDPL_PROVISORIO", "Referência provisória (CDPLXXX-XX) na coluna C.")
    if not reg["descricao"]:
        add("SEM_DESCRICAO", "Descrição (coluna G) não informada.")
    for col, codigo in erros_colunas:
        add("ERRO_EXCEL", f"Erro do Excel na coluna {letra_coluna(col)}: {codigo}.")
    if not reg["qty"]:
        add("QTY_NAO_INFORMADA", "QTY prevista (coluna F) não informada.")
    elif reg["qty_numero"] is None and reg["qty"] not in ERROS_EXCEL:
        add("QTY_NAO_NUMERICA", f"QTY prevista não numérica: \"{reg['qty']}\".")
    if not any(f["aparece"] for f in reg["folhas"]):
        add("SEM_FOLHAS", "Nenhuma folha (SH1–SH20) com quantidade.")
    for f in reg["folhas"]:
        if f["numero"] is None and f["texto"] not in ERROS_EXCEL:
            add("FOLHA_NAO_NUMERICA", f"Folha {f['folha']}: valor não numérico \"{f['texto']}\".")
    qty, soma, total = reg["qty_numero"], reg["soma_folhas"], reg["total_numero"]
    if qty is not None and soma is not None and not iguais(qty, soma):
        add("QTY_DIF_SOMA", f"QTY prevista ({fmt_num(qty)}) difere da soma das folhas ({fmt_num(soma)}).")
    if not reg["total_registrado"]:
        add("TOTAL_NAO_INFORMADO", "Total registrado (coluna AF) não informado.")
    elif total is not None and soma is not None and not iguais(total, soma):
        add("TOTAL_DIF_SOMA", f"Total registrado ({fmt_num(total)}) difere da soma das folhas ({fmt_num(soma)}).")
    if qty is not None and total is not None and not iguais(qty, total):
        add("QTY_DIF_TOTAL", f"QTY prevista ({fmt_num(qty)}) difere do Total registrado ({fmt_num(total)}).")
    for col in formulas_sem_cache:
        add("FORMULA_SEM_CACHE",
            f"Coluna {letra_coluna(col)} tem fórmula sem valor calculado salvo; abra e salve a planilha no Excel.")
    return avisos


def montar_registro(kit: str, aba: str, linha: int, textos: list[Optional[str]], rotulo_c: Optional[str],
                    topo_normalizado: str, configuracao: str,
                    erros_colunas: list[tuple[int, str]] | None = None,
                    formulas_sem_cache: list[int] | None = None) -> dict:
    folhas = []
    for k in range(NUM_FOLHAS):
        texto = textos[SH1 + k]
        if texto:
            num = numero(texto)
            folhas.append({
                "folha": k + 1,
                "texto": texto,
                "numero": num,
                "aparece": (num is not None and num > 0) or (num is None and texto not in ERROS_EXCEL),
            })
    numeros = [f["numero"] for f in folhas if f["numero"] is not None]
    reg = {
        "id": f"{kit}-{linha}",
        "kit": kit,
        "aba": aba,
        "linha": linha,
        "pn_novo": textos[A],
        "ref_e2": textos[B],
        "pn_antigo": textos[C],
        "rotulo_c": rotulo_c,
        "pos": textos[D],
        "zona": textos[E],
        "qty": textos[F],
        "descricao": textos[G],
        "topo": textos[H],
        "topo_normalizado": topo_normalizado,
        "configuracao": configuracao,
        "ecode": textos[I],
        "action": textos[J],
        "liberado": textos[K],
        "folhas": folhas,
        "total_registrado": textos[AF],
        "check_qtd": textos[AG],
        "observacoes": textos[AH],
        "qty_numero": numero(textos[F]),
        "soma_folhas": sum(numeros) if numeros else None,
        "total_numero": numero(textos[AF]),
        "provisorio": eh_provisorio(textos[C]),
    }
    reg["avisos"] = calcular_avisos(reg, erros_colunas or [], formulas_sem_cache or [])
    return reg


def _textos(celulas: list[Celula]) -> list[Optional[str]]:
    t = [c.texto if c.texto not in ("",) else None for c in celulas[:NUM_COLUNAS]]
    return t + [None] * (NUM_COLUNAS - len(t))


def importar_aba(kit: str, aba: str, linhas: list[list[Celula]]) -> dict:
    """Converte as linhas de uma aba em registros CD + exclusões."""
    textos_linhas = [_textos(l) for l in linhas]
    idx_cab = next((i for i, t in enumerate(textos_linhas[:MAX_LINHA_CABECALHO]) if eh_linha_cabecalho(t)), None)
    if idx_cab is None:
        raise ErroLayout(f"Aba {aba!r}: cabeçalho com POS em D e ZONE em E não encontrado nas "
                         f"{MAX_LINHA_CABECALHO} primeiras linhas.")
    cabecalho = textos_linhas[idx_cab]
    erros, avisos_layout = validar_layout(cabecalho, kit)
    if erros:
        raise ErroLayout(f"Aba {aba!r}, linha de cabeçalho {idx_cab + 1}: layout não confere.\n  - "
                         + "\n  - ".join(erros))

    registros, exclusoes = [], []
    linhas_vazias = 0
    for i in range(idx_cab + 1, len(linhas)):
        numero_linha = i + 1
        celulas = linhas[i]
        textos = textos_linhas[i]
        if all(c.vazia for c in celulas):
            linhas_vazias += 1
            continue

        def excluir(motivo: str):
            exclusoes.append({"aba": aba, "linha": numero_linha, "motivo": motivo,
                              "a": textos[A], "c": textos[C], "h": textos[H]})

        if all(t is None for t in textos):
            excluir("conteúdo apenas além da coluna AH")
            continue
        if eh_linha_cabecalho(textos):
            excluir("cabeçalho repetido")
            continue
        cfg, topo_norm = extrair_configuracao(textos[H])
        if not textos[H]:
            excluir("coluna H vazia (sem configuração)")
            continue
        if cfg is None:
            excluir("configuração não identificada na coluna H")
            continue
        if cfg != CONFIGURACAO_ALVO:
            excluir(f"configuração {cfg} na coluna H (fora do escopo {CONFIGURACAO_ALVO})")
            continue
        if not textos[A] and not textos[C]:
            excluir("sem PN novo (A) e sem PN antigo/CDPL (C)")
            continue
        celulas_pad = list(celulas[:NUM_COLUNAS]) + [Celula()] * max(0, NUM_COLUNAS - len(celulas))
        erros_colunas = [(k, c.erro) for k, c in enumerate(celulas_pad) if c.erro]
        sem_cache = [k for k, c in enumerate(celulas_pad) if c.formula and c.valor is None]
        registros.append(montar_registro(kit, aba, numero_linha, textos, cabecalho[C], topo_norm, cfg,
                                         erros_colunas, sem_cache))
    return {
        "kit": kit,
        "aba": aba,
        "linha_cabecalho": idx_cab + 1,
        "avisos_layout": avisos_layout,
        "registros": registros,
        "exclusoes": exclusoes,
        "linhas_vazias": linhas_vazias,
    }


def resumo_kit(resultado: dict) -> dict:
    regs = resultado["registros"]
    topos: dict[str, int] = {}
    for r in regs:
        topos[r["topo_normalizado"]] = topos.get(r["topo_normalizado"], 0) + 1
    codigos = lambda r: {a["codigo"] for a in r["avisos"]}  # noqa: E731
    return {
        "aba": resultado["aba"],
        "linha_cabecalho": resultado["linha_cabecalho"],
        "registros": len(regs),
        "sem_pn_novo": sum(1 for r in regs if not r["pn_novo"]),
        "sem_descricao": sum(1 for r in regs if not r["descricao"]),
        "provisorios": sum(1 for r in regs if r["provisorio"]),
        "com_divergencia_quantidade": sum(
            1 for r in regs if codigos(r) & {"QTY_DIF_SOMA", "TOTAL_DIF_SOMA", "QTY_DIF_TOTAL"}),
        "topos": topos,
        "exclusoes": len(resultado["exclusoes"]),
        "linhas_vazias": resultado["linhas_vazias"],
        "avisos_layout": resultado["avisos_layout"],
    }


def comparar_com_referencia(resumo: dict, referencia: dict) -> list[str]:
    """Compara contagens obtidas com o snapshot conferido. Só reporta."""
    diferencas = []
    for kit, esperado in referencia.get("kits", {}).items():
        obtido = resumo.get(kit)
        if obtido is None:
            diferencas.append(f"{kit}: aba não importada.")
            continue
        for campo in ("registros", "sem_pn_novo"):
            if campo in esperado and esperado[campo] != obtido.get(campo):
                diferencas.append(f"{kit}.{campo}: esperado {esperado[campo]}, obtido {obtido.get(campo)}.")
        if "topo" in esperado:
            topos = set(obtido.get("topos", {}))
            if topos != {esperado["topo"]}:
                diferencas.append(f"{kit}.topo: esperado só {esperado['topo']}, obtido {sorted(topos)}.")
    return diferencas
