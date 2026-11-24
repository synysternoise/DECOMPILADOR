"""Leitores somente-leitura da planilha de placards.

Cada leitor devolve, por aba, uma lista de linhas; cada linha é uma lista de
``Celula``. Nenhum leitor executa macros nem grava no arquivo de origem.
"""
from __future__ import annotations

import csv
import datetime as _dt
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ERROS_EXCEL = {"#N/A", "#REF!", "#VALUE!", "#DIV/0!", "#NAME?", "#NUM!", "#NULL!", "#SPILL!", "#CALC!"}


@dataclass(frozen=True)
class Celula:
    """Valor de uma célula.

    texto   -- valor como exibido (formatado), já sem espaços nas pontas;
               ``None`` quando a célula está vazia.
    valor   -- valor bruto (str, int, float, bool, data) ou ``None``.
    formula -- a célula contém fórmula.
    erro    -- código de erro do Excel (ex.: ``#N/A``) ou ``None``.
    """

    texto: Optional[str] = None
    valor: object = None
    formula: bool = False
    erro: Optional[str] = None

    @property
    def vazia(self) -> bool:
        return self.texto is None or self.texto == ""


VAZIA = Celula()


_RE_LITERAL = r'(?:"[^"]*"|\\.)*'


def _formato_zeros(formato: str | None) -> Optional[tuple[str, int, str]]:
    """Formato só com zeros e literais (ex.: ``00000`` ou ``"P"0000``).

    Devolve (prefixo, largura, sufixo) ou ``None``.
    """
    if not formato:
        return None
    secao = re.sub(r"\[[^\]]*\]", "", formato.split(";")[0]).strip()  # [cor], [condição]
    m = re.fullmatch(f"({_RE_LITERAL})(0+)({_RE_LITERAL})", secao)
    if not m:
        return None

    def literal(t: str) -> str:
        return "".join(a[1:-1] if a.startswith('"') else a[1:] for a in re.findall(r'"[^"]*"|\\.', t))

    return literal(m.group(1)), len(m.group(2)), literal(m.group(3))


def _casas_decimais(formato: str | None) -> Optional[int]:
    if not formato:
        return None
    m = re.fullmatch(r"[#,]*0+\.(0+)", formato.split(";")[0].strip())
    return len(m.group(1)) if m else None


def formatar_valor(valor, formato: str | None = None) -> Optional[str]:
    """Converte um valor de célula em texto como o Excel o exibiria.

    Preserva zeros à esquerda quando o formato numérico é do tipo ``00000``.
    """
    if valor is None:
        return None
    if isinstance(valor, str):
        texto = valor.strip()
        return texto if texto != "" else None
    if isinstance(valor, bool):
        return "VERDADEIRO" if valor else "FALSO"
    if isinstance(valor, _dt.datetime):
        if valor.time() == _dt.time(0, 0):
            return valor.date().isoformat()
        return valor.isoformat(sep=" ")
    if isinstance(valor, _dt.date):
        return valor.isoformat()
    if isinstance(valor, _dt.time):
        return valor.isoformat()
    if isinstance(valor, (int, float)):
        numero = round(float(valor), 10)
        zeros = _formato_zeros(formato)
        if numero.is_integer():
            inteiro = int(numero)
            if zeros and inteiro >= 0:
                prefixo, largura, sufixo = zeros
                return f"{prefixo}{str(inteiro).zfill(largura)}{sufixo}"
            return str(inteiro)
        casas = _casas_decimais(formato)
        if casas is not None:
            return f"{numero:.{casas}f}"
        return repr(numero)
    return str(valor).strip() or None


# ---------------------------------------------------------------- xlsx / xlsm

def ler_xlsx(caminho: Path, abas: list[str]) -> tuple[list[str], dict[str, list[list[Celula]]]]:
    """Lê as abas pedidas de um .xlsx/.xlsm (valores em cache; macros nunca rodam)."""
    import openpyxl

    with open(caminho, "rb") as fh:
        conteudo = fh.read()  # lê uma vez; o arquivo de origem não é tocado de novo
    wb_valores = openpyxl.load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True, keep_vba=False)
    wb_formulas = openpyxl.load_workbook(io.BytesIO(conteudo), read_only=True, data_only=False, keep_vba=False)
    try:
        nomes = list(wb_valores.sheetnames)
        resultado: dict[str, list[list[Celula]]] = {}
        for aba in abas:
            ws_v = wb_valores[aba]
            ws_f = wb_formulas[aba]
            linhas: list[list[Celula]] = []
            for linha_v, linha_f in zip(ws_v.iter_rows(), ws_f.iter_rows()):
                celulas = []
                for cv, cf in zip(linha_v, linha_f):
                    valor = getattr(cv, "value", None)
                    tipo = getattr(cv, "data_type", None)
                    bruto_f = getattr(cf, "value", None)
                    eh_formula = isinstance(bruto_f, str) and bruto_f.startswith("=")
                    if tipo == "e" or (isinstance(valor, str) and valor.strip() in ERROS_EXCEL):
                        texto = str(valor).strip() if valor is not None else "#ERRO"
                        celulas.append(Celula(texto=texto, valor=valor, formula=eh_formula, erro=texto))
                        continue
                    formato = getattr(cv, "number_format", None)
                    texto = formatar_valor(valor, formato)
                    celulas.append(Celula(texto=texto, valor=valor, formula=eh_formula))
                linhas.append(celulas)
            resultado[aba] = linhas
        return nomes, resultado
    finally:
        wb_valores.close()
        wb_formulas.close()


def nomes_abas_xlsx(caminho: Path) -> list[str]:
    import openpyxl

    with open(caminho, "rb") as fh:
        wb = openpyxl.load_workbook(io.BytesIO(fh.read()), read_only=True)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


# ----------------------------------------------------------------------- xls

def ler_xls(caminho: Path, abas: list[str]) -> tuple[list[str], dict[str, list[list[Celula]]]]:
    """Lê .xls legado com xlrd (valores em cache; macros nunca rodam)."""
    try:
        import xlrd
    except ImportError as exc:  # pragma: no cover - depende do ambiente
        raise RuntimeError(
            "Leitura de .xls requer o pacote xlrd (pip install xlrd). "
            "Alternativa: abra no Excel e salve como .xlsx (veja README)."
        ) from exc

    with open(caminho, "rb") as fh:
        conteudo = fh.read()
    livro = xlrd.open_workbook(file_contents=conteudo, formatting_info=True, on_demand=True)
    try:
        nomes = livro.sheet_names()
        resultado: dict[str, list[list[Celula]]] = {}
        for aba in abas:
            folha = livro.sheet_by_name(aba)
            linhas = []
            for r in range(folha.nrows):
                celulas = []
                for c in range(folha.ncols):
                    cel = folha.cell(r, c)
                    tipo = cel.ctype
                    if tipo in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                        celulas.append(VAZIA)
                        continue
                    if tipo == xlrd.XL_CELL_ERROR:
                        codigo = xlrd.error_text_from_code.get(cel.value, "#ERRO")
                        celulas.append(Celula(texto=codigo, valor=codigo, erro=codigo))
                        continue
                    formato = None
                    try:
                        xf = livro.xf_list[cel.xf_index]
                        formato = livro.format_map[xf.format_key].format_str
                    except Exception:
                        formato = None
                    valor = cel.value
                    if tipo == xlrd.XL_CELL_DATE:
                        try:
                            valor = xlrd.xldate.xldate_as_datetime(cel.value, livro.datemode)
                        except Exception:
                            pass
                    elif tipo == xlrd.XL_CELL_BOOLEAN:
                        valor = bool(cel.value)
                    celulas.append(Celula(texto=formatar_valor(valor, formato), valor=valor))
                linhas.append(celulas)
            resultado[aba] = linhas
        return nomes, resultado
    finally:
        livro.release_resources()


# ----------------------------------------------------------------------- csv

def _decodificar(conteudo: bytes) -> str:
    for codificacao in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return conteudo.decode(codificacao)
        except UnicodeDecodeError:
            continue
    return conteudo.decode("utf-8", errors="replace")


def detectar_delimitador(primeira_linha: str) -> str:
    contagens = {d: primeira_linha.count(d) for d in ("\t", ";", ",")}
    melhor = max(contagens, key=lambda d: contagens[d])
    return melhor if contagens[melhor] > 0 else ","


def ler_csv(caminho: Path) -> list[list[Celula]]:
    """Lê uma aba exportada como CSV/TSV (valores já como exibidos)."""
    texto = _decodificar(Path(caminho).read_bytes())
    primeira = texto.split("\n", 1)[0]
    leitor = csv.reader(io.StringIO(texto, newline=""), delimiter=detectar_delimitador(primeira))
    linhas = []
    for linha in leitor:
        celulas = []
        for valor in linha:
            t = valor.strip()
            if t == "":
                celulas.append(VAZIA)
            elif t in ERROS_EXCEL:
                celulas.append(Celula(texto=t, valor=t, erro=t))
            else:
                celulas.append(Celula(texto=t, valor=t))
        linhas.append(celulas)
    return linhas
