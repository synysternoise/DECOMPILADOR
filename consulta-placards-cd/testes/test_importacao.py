"""Importador: critérios de aceitação 1–5 sobre a planilha SINTÉTICA."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import RAIZ, sha
import fixtures
from placards_cd import importacao as imp
from placards_cd import importar
from placards_cd.leitores import formatar_valor


def por_kit(regs, kit):
    return [r for r in regs if r["kit"] == kit]


def achar(regs, **kw):
    return [r for r in regs if all(r.get(k) == v for k, v in kw.items())]


def codigos(r):
    return [a["codigo"] for a in r["avisos"]]


# ---------------------------------------------------------------- critério 1
def test_contagens_derivadas_da_fonte(ambiente, registros):
    resumo = ambiente["base"]["resumo"]
    assert len(por_kit(registros, "PLASTICO")) == resumo["PLASTICO"]["registros"] == 189
    assert len(por_kit(registros, "METALICO")) == resumo["METALICO"]["registros"] == 72
    assert resumo["METALICO"]["sem_pn_novo"] == sum(1 for r in por_kit(registros, "METALICO") if not r["pn_novo"]) == 60
    assert ambiente["base"]["comparacao_snapshot"]["diferencas"] == []


def test_diferenca_do_snapshot_e_reportada_sem_forcar(ambiente, tmp_path):
    ref = tmp_path / "ref.json"
    ref.write_text(json.dumps({"kits": {"PLASTICO": {"registros": 190}, "METALICO": {"registros": 72, "sem_pn_novo": 61}}}))
    importar.main(["--planilha", str(ambiente["planilha"]), "--saida", str(tmp_path / "out"), "--referencia", str(ref)])
    rel = json.loads((tmp_path / "out" / "relatorio_importacao.json").read_text(encoding="utf-8"))
    assert rel["resumo"]["PLASTICO"]["registros"] == 189  # não forçado
    assert "PLASTICO.registros: esperado 190, obtido 189." in rel["comparacao_snapshot"]["diferencas"]
    assert "METALICO.sem_pn_novo: esperado 61, obtido 60." in rel["comparacao_snapshot"]["diferencas"]


def test_topos_por_kit(registros):
    assert {r["topo_normalizado"] for r in por_kit(registros, "PLASTICO")} == {"171-60473-401/CD"}
    assert {r["topo_normalizado"] for r in por_kit(registros, "METALICO")} == {"171-60474-401/CD"}
    r = achar(registros, kit="PLASTICO", linha=40)[0]
    assert r["topo"] == "171-60473-401 CD" and r["topo_normalizado"] == "171-60473-401/CD"


# ---------------------------------------------------------------- critério 2
def test_criterio2_pn_cdpl(registros):
    r = achar(registros, pn_novo="171-50557-021")
    assert len(r) == 1, "a linha LX com o mesmo PN não pode entrar"
    r = r[0]
    assert r["pn_antigo"] == "CDPL569-1-16"
    assert r["pos"] == "00122"
    assert r["zona"] == "F204"
    assert r["topo"] == "171-60473-401/ CD" and r["topo_normalizado"] == "171-60473-401/CD"
    assert [(f["folha"], f["numero"]) for f in r["folhas"]] == [(20, 1)]
    assert (r["aba"], r["linha"]) == ("PLACARD, KIT PLASTIC", 12)


# ---------------------------------------------------------------- critério 3
def test_criterio3_metalico(registros):
    r = achar(registros, pn_novo="171-60555-001")[0]
    assert r["kit"] == "METALICO" and r["topo_normalizado"] == "171-60474-401/CD"
    assert [(f["folha"], f["numero"]) for f in r["folhas"]] == [(6, 1), (7, 1), (9, 1), (11, 1)]
    assert r["rotulo_c"] == "PART NUMBER"
    s = achar(registros, pn_antigo="CDPL568-201")[0]
    assert s["pn_novo"] is None and s["descricao"] is None
    assert "SEM_PN_NOVO" in codigos(s) and "SEM_DESCRICAO" in codigos(s)


# ---------------------------------------------------------------- critério 4
def test_criterio4_divergencia_linha_130(ambiente, registros):
    r = achar(registros, kit="PLASTICO", linha=130)[0]
    assert (r["qty"], r["soma_folhas"], r["total_registrado"]) == ("3", 2, "4")
    assert {"QTY_DIF_SOMA", "TOTAL_DIF_SOMA", "QTY_DIF_TOTAL"} <= set(codigos(r))
    assert r["check_qtd"] == "ok"  # preservado, sem significar liberação
    assert sha(ambiente["planilha"]) == ambiente["hash_antes"]


def test_fonte_nao_e_alterada(ambiente):
    rel = json.loads((ambiente["saida"] / "relatorio_importacao.json").read_text(encoding="utf-8"))
    assert rel["fonte_inalterada"] is True
    assert rel["fonte"]["sha256"] == ambiente["hash_antes"] == sha(ambiente["planilha"])


# ---------------------------------------------------------------- regras dos dados
def test_nao_deduplica_e_nao_herda(registros):
    dup = achar(registros, pn_novo="171-50550-005")
    assert [r["linha"] for r in dup] == [35, 36]
    r37 = achar(registros, kit="PLASTICO", linha=37)[0]
    assert r37["pn_novo"] is None and r37["descricao"] is None and r37["liberado"] is None and r37["zona"] is None
    assert r37["pn_antigo"] == "CDPL562-19"


def test_sem_pn_mantido_quando_c_preenchido(registros):
    r = achar(registros, kit="PLASTICO", linha=20)[0]
    assert r["pn_novo"] is None and r["pn_antigo"] == "CDPL561-27"


def test_zeros_a_esquerda_e_texto(registros):
    assert achar(registros, kit="PLASTICO", linha=31)[0]["pos"] == "00029"   # texto
    assert achar(registros, kit="PLASTICO", linha=2)[0]["pos"] == "00102"    # número formatado 00000
    assert achar(registros, kit="PLASTICO", linha=2)[0]["ecode"] == "2300002"


def test_vazio_diferente_de_zero(registros):
    r = achar(registros, kit="PLASTICO", linha=31)[0]
    assert [(f["folha"], f["texto"], f["aparece"]) for f in r["folhas"]] == [(3, "0", False), (4, "2", True)]
    assert r["soma_folhas"] == 2 and "QTY_DIF_SOMA" not in codigos(r)


def test_aspas_acentos_html_preservados(registros):
    r = achar(registros, kit="PLASTICO", linha=30)[0]
    assert r["descricao"] == 'PLACA "NÃO FUMAR" – AÇÃO <img src=x onerror="window.__xss=1">'
    assert r["observacoes"] == '</script><b id="injetado">x</b>'


def test_html_escapa_dados(ambiente):
    html = ambiente["html"].read_text(encoding="utf-8")
    dados = html.split('id="dados-base">', 1)[1].split("</script>", 1)[0]
    assert "<" not in dados and ">" not in dados
    assert "\\u003c/script\\u003e" in dados


def test_provisorio_e_valores_especiais(registros):
    assert "CDPL_PROVISORIO" in codigos(achar(registros, kit="PLASTICO", linha=25)[0])
    assert "FOLHA_NAO_NUMERICA" in codigos(achar(registros, kit="PLASTICO", linha=32)[0])
    r33 = achar(registros, kit="PLASTICO", linha=33)[0]
    assert r33["total_registrado"] == "#N/A" and "ERRO_EXCEL" in codigos(r33)
    assert "FORMULA_SEM_CACHE" in codigos(achar(registros, kit="PLASTICO", linha=34)[0])


def test_espacos_nas_pontas(registros):
    r = achar(registros, kit="PLASTICO", linha=38)[0]
    assert (r["pn_novo"], r["ref_e2"], r["pn_antigo"]) == ("171-50550-041", "196-LEX003764", "CDPL563-11")


def test_exclusoes_registradas(ambiente):
    ex = {(e["aba"], e["linha"]): e["motivo"] for e in ambiente["base"]["exclusoes"]}
    p = "PLACARD, KIT PLASTIC"
    assert "LX" in ex[(p, 191)] and "AL" in ex[(p, 192)]
    assert ex[(p, 194)].startswith("coluna H vazia")
    assert ex[(p, 195)].startswith("sem PN novo")
    assert ex[(p, 196)] == "cabeçalho repetido"
    assert ex[(p, 197)] == "configuração não identificada na coluna H"
    assert ("PLACARD, KIT METALLIC", 74) in ex
    ignoradas = {a["aba"] for a in ambiente["base"]["abas_ignoradas"]}
    assert ignoradas == {"NON ELECTRICAL EXIT SIGNS", "ELECTRICAL EXIT SIGNS", "Controle de Folhas"}
    assert all(r["configuracao"] == "CD" for r in ambiente["base"]["registros"])


def test_layout_invalido_falha(tmp_path, capsys):
    p = fixtures.gerar_planilha(tmp_path / "ruim.xlsx", layout_invalido=True)
    rc = importar.main(["--planilha", str(p), "--saida", str(tmp_path / "o")])
    err = capsys.readouterr().err
    assert rc == 2 and "PLACARD, KIT METALLIC" in err and "Coluna C" in err and "Coluna H" in err and "SH12" in err
    assert not (tmp_path / "o" / "consulta-placards-cd.html").exists()


def test_sem_base_rotula_nao_carregada(tmp_path):
    assert importar.main(["--sem-base", "--saida", str(tmp_path)]) == 0
    html = (tmp_path / "consulta-placards-cd.html").read_text(encoding="utf-8")
    assert 'id="dados-base">null<' in html


def test_html_sem_recursos_externos(ambiente):
    html = ambiente["html"].read_text(encoding="utf-8")
    assert "<script src" not in html and "<link" not in html
    assert "connect-src 'none'" in html
    externos = [u for u in __import__("re").findall(r"https?://[^\s\"'<>)]+", html)
                if not u.startswith("https://desenhos.empresa.example")]
    assert externos == [], externos


@pytest.mark.parametrize("valor,fmt,esperado", [
    (122, "00000", "00122"), (122.0, "00000", "00122"), ("00122", None, "00122"), (0, "General", "0"),
    (1.5, "General", "1.5"), (2307529, "0", "2307529"), (5, '"P"0000', "P0005"), (7, "[Blue]000", "007"), (-3, "00000", "-3"), (None, None, None), ("  ", None, None)])
def test_formatar_valor(valor, fmt, esperado):
    assert formatar_valor(valor, fmt) == esperado


@pytest.mark.parametrize("h,esperado", [
    ("171-60473-401/ CD", ("CD", "171-60473-401/CD")), ("171-60473-401/CD", ("CD", "171-60473-401/CD")),
    ("171-60473-401 CD", ("CD", "171-60473-401/CD")), ("171-60473-401/ lx", ("LX", "171-60473-401/LX")),
    ("VER DESENHO", (None, None)), ("", (None, None)), ("/CD", (None, None))])
def test_extrair_configuracao(h, esperado):
    assert imp.extrair_configuracao(h) == esperado


def test_xls_legado(ambiente, tmp_path):
    soffice = shutil.which("soffice")
    if not soffice:
        pytest.skip("LibreOffice ausente para gerar .xls de teste")
    copia = tmp_path / "PLANILHA_PLACARD CD.xlsx"
    shutil.copy(ambiente["planilha"], copia)
    subprocess.run([soffice, "--headless", "--convert-to", "xls", "--outdir", str(tmp_path), str(copia)],
                   check=True, capture_output=True, timeout=180)
    xls = tmp_path / "PLANILHA_PLACARD CD.xls"
    assert importar.main(["--planilha", str(xls), "--saida", str(tmp_path / "o")]) == 0
    base = json.loads((tmp_path / "o" / "base_placards_cd.json").read_text(encoding="utf-8"))
    regs = base["registros"]
    assert base["resumo"]["PLASTICO"]["registros"] == 189 and base["resumo"]["METALICO"]["sem_pn_novo"] == 60
    r = achar(regs, pn_novo="171-50557-021")[0]
    assert r["pos"] == "00122" and r["zona"] == "F204"
    assert achar(regs, kit="PLASTICO", linha=31)[0]["pos"] == "00029"


def exportar_csv(planilha: Path, aba: str, destino: Path, delim: str):
    """Exporta a aba como o Excel faria (valores exibidos)."""
    import csv
    from placards_cd.leitores import ler_xlsx
    _, dados = ler_xlsx(planilha, [aba])
    with open(destino, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=delim)
        for linha in dados[aba]:
            w.writerow([c.texto or "" for c in linha])


def test_csv_python_e_paridade_com_js(ambiente, tmp_path):
    pcsv, mtsv = tmp_path / "plastico.csv", tmp_path / "metalico.tsv"
    exportar_csv(ambiente["planilha"], "PLACARD, KIT PLASTIC", pcsv, ";")
    exportar_csv(ambiente["planilha"], "PLACARD, KIT METALLIC", mtsv, "\t")
    assert importar.main(["--csv", str(pcsv), "--csv", str(mtsv), "--saida", str(tmp_path / "o"), "--sem-referencia"]) == 0
    py = json.loads((tmp_path / "o" / "base_placards_cd.json").read_text(encoding="utf-8"))["registros"]
    node = shutil.which("node")
    if not node:
        pytest.skip("node ausente")
    script = tmp_path / "rodar.js"
    script.write_text(
        "const N=require(process.argv[2]);const fs=require('fs');let regs=[];"
        "for(const f of process.argv.slice(3)){regs=regs.concat(N.importarCSV(fs.readFileSync(f,'utf8'),require('path').basename(f)).registros);}"
        "process.stdout.write(JSON.stringify(regs));")
    out = subprocess.run([node, str(script), str(RAIZ / "web" / "nucleo.js"), str(pcsv), str(mtsv)],
                         check=True, capture_output=True, text=True).stdout
    js = json.loads(out)
    assert len(js) == len(py) == 261
    for a, b in zip(py, js):
        assert a == b, (a["id"], {k: (a[k], b.get(k)) for k in a if a[k] != b.get(k)})
    # A planilha e o CSV produzem os mesmos registros (exceto fórmula sem cache e nome da aba)
    xl = {r["id"]: r for r in ambiente["base"]["registros"]}
    for r in py:
        x = dict(xl[r["id"]])
        x["avisos"] = [a for a in x["avisos"] if a["codigo"] != "FORMULA_SEM_CACHE"]
        assert {k: v for k, v in x.items() if k != "aba"} == {k: v for k, v in r.items() if k != "aba"}, r["id"]
