"""Regras dos dados (critérios 1–4) sobre a planilha SINTÉTICA."""
import shutil
import subprocess

import pytest

from conftest import montar_pasta, sha
from placards_cd import importacao as imp
from placards_cd import publicar
from placards_cd.leitores import formatar_valor


def achar(regs, **kw):
    return [r for r in regs if all(r.get(k) == v for k, v in kw.items())]


def codigos(r):
    return [a["codigo"] for a in r["avisos"]]


def test_criterio1_contagens(pasta):
    res = pasta["res"]
    assert res["resumo"]["PLASTICO"]["registros"] == 189
    assert res["resumo"]["METALICO"]["registros"] == 72 and res["resumo"]["METALICO"]["sem_pn_novo"] == 60
    assert res["comparacao"] == []


def test_criterio2(registros):
    r = achar(registros, pn_novo="171-50557-021")
    assert len(r) == 1
    r = r[0]
    assert (r["pn_antigo"], r["pos"], r["zona"], r["topo_normalizado"]) == ("CDPL569-1-16", "00122", "F204", "171-60473-401/CD")
    assert [(f["folha"], f["numero"]) for f in r["folhas"]] == [(20, 1)]


def test_criterio3(registros):
    r = achar(registros, pn_novo="171-60555-001")[0]
    assert r["topo_normalizado"] == "171-60474-401/CD"
    assert [(f["folha"], f["numero"]) for f in r["folhas"]] == [(6, 1), (7, 1), (9, 1), (11, 1)]
    s = achar(registros, pn_antigo="CDPL568-201")[0]
    assert s["pn_novo"] is None and s["descricao"] is None


def test_criterio4_e_planilha_intacta(pasta, registros):
    r = achar(registros, kit="PLASTICO", linha=130)[0]
    assert (r["qty"], r["soma_folhas"], r["total_registrado"]) == ("3", 2, "4")
    assert {"QTY_DIF_SOMA", "TOTAL_DIF_SOMA", "QTY_DIF_TOTAL"} <= set(codigos(r))
    assert sha(pasta["dir"] / "PLANILHA_PLACARD CD.xlsx") == pasta["hash_antes"]


def test_nao_deduplica_nao_herda_zeros_e_vazios(registros):
    assert [r["linha"] for r in achar(registros, pn_novo="171-50550-005")] == [35, 36]
    r37 = achar(registros, kit="PLASTICO", linha=37)[0]
    assert r37["pn_novo"] is None and r37["descricao"] is None and r37["zona"] is None
    r31 = achar(registros, kit="PLASTICO", linha=31)[0]
    assert r31["pos"] == "00029" and [(f["folha"], f["aparece"]) for f in r31["folhas"]] == [(3, False), (4, True)]
    assert achar(registros, kit="PLASTICO", linha=38)[0]["pn_novo"] == "171-50550-041"


def test_exclusoes_e_abas(pasta):
    ex = {(e["aba"], e["linha"]): e["motivo"] for e in pasta["res"]["exclusoes"]}
    assert "LX" in ex[("PLACARD, KIT PLASTIC", 191)] and "AL" in ex[("PLACARD, KIT PLASTIC", 192)]
    assert {a["aba"] for a in pasta["res"]["ignoradas"]} == {"NON ELECTRICAL EXIT SIGNS", "ELECTRICAL EXIT SIGNS", "Controle de Folhas"}
    assert all(r["configuracao"] == "CD" for r in pasta["res"]["registros"])


def test_layout_invalido(tmp_path, capsys):
    p = montar_pasta(tmp_path / "x", com_desenhos=False)
    import fixtures
    fixtures.gerar_planilha(p / "PLANILHA_PLACARD CD.xlsx", layout_invalido=True)
    assert publicar.main(["--config", str(p / "_adm" / "config.json")]) == 2
    err = capsys.readouterr().err
    assert "PLACARD, KIT METALLIC" in err and "SH12" in err
    assert not (p / "Consulta de Placards.html").exists()


def test_planilha_ausente(tmp_path, capsys):
    p = montar_pasta(tmp_path / "y", com_desenhos=False)
    (p / "PLANILHA_PLACARD CD.xlsx").rename(p / "outra.xlsx")
    assert publicar.main(["--config", str(p / "_adm" / "config.json")]) == 2
    assert "Planilha não encontrada" in capsys.readouterr().err


@pytest.mark.parametrize("valor,fmt,esperado", [(122, "00000", "00122"), ("00122", None, "00122"), (5, '"P"0000', "P0005"),
                                                (1.5, "General", "1.5"), (None, None, None)])
def test_formatar_valor(valor, fmt, esperado):
    assert formatar_valor(valor, fmt) == esperado


def test_xls_legado(tmp_path):
    soffice = shutil.which("soffice")
    if not soffice:
        pytest.skip("LibreOffice ausente")
    p = montar_pasta(tmp_path / "z", com_desenhos=False)
    subprocess.run([soffice, "--headless", "--convert-to", "xls", "--outdir", str(p), str(p / "PLANILHA_PLACARD CD.xlsx")],
                   check=True, capture_output=True, timeout=180)
    cfg, base = publicar.carregar_config(p / "_adm" / "config.json")
    cfg["planilha"] = "../PLANILHA_PLACARD CD.xls"
    res = publicar.publicar(cfg, base)
    assert res["resumo"]["PLASTICO"]["registros"] == 189 and res["resumo"]["METALICO"]["sem_pn_novo"] == 60
    assert achar(res["registros"], pn_novo="171-50557-021")[0]["pos"] == "00122"
