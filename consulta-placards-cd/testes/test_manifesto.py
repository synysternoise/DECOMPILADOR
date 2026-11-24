"""Validação do manifesto (Python) e conferência com PDF sintético."""
import json
from pathlib import Path

import pytest

from conftest import sha
from placards_cd.manifesto import carregar_manifesto, validar_manifesto, verificar_pdfs
from placards_cd import validar_manifesto as cli

CASOS = json.loads((Path(__file__).parent / "casos_manifesto.json").read_text(encoding="utf-8"))["casos"]


@pytest.mark.parametrize("caso", CASOS, ids=[c["nome"] for c in CASOS])
def test_casos_compartilhados(caso):
    topos = set(caso["topos_base"]) if caso["topos_base"] is not None else None
    res = validar_manifesto(caso["manifesto"], topos)
    assert sorted({e["codigo"] for e in res["erros"]}) == caso["erros"]
    assert sorted({a["codigo"] for a in res["avisos"]}) == caso["avisos"]


def test_normaliza_topo_e_mapa():
    caso = next(c for c in CASOS if c["nome"] == "topo com espacos e minusculas normaliza")
    m = validar_manifesto(caso["manifesto"])["manifesto"]
    assert m["desenhos"][0]["topo"] == "171-60473-401/CD"
    assert m["desenhos"][0]["mapa_folhas"] == {"1": 3, "20": 22}


def test_chave_json_duplicada(tmp_path):
    p = tmp_path / "m.json"
    p.write_text('{"formato":"manifesto-desenhos-placards","versao_formato":1,"desenhos":[{"configuracao":"CD",'
                 '"topo":"171-60473-401/CD","revisao":"A","ativa":true,"origem":{"tipo":"local","nome_arquivo":"a.pdf"},'
                 '"mapa_folhas":{"20":22,"20":21}}]}')
    res = carregar_manifesto(p)
    assert [e["codigo"] for e in res["erros"]] == ["CHAVE_DUPLICADA_JSON"]


def test_folha20_pagina22_no_pdf_sintetico(ambiente):
    from pypdf import PdfReader
    res = carregar_manifesto(ambiente["manifesto"])
    assert res["erros"] == []
    rev_a = next(d for d in res["manifesto"]["desenhos"] if d["revisao"] == "A")
    assert rev_a["mapa_folhas"]["20"] == 22 and "19" not in rev_a["mapa_folhas"]
    pagina = PdfReader(ambiente["pdf_a"]).pages[22 - 1].extract_text()
    assert "FOLHA 20" in pagina and "Página 22" in pagina
    assert verificar_pdfs(res["manifesto"], ambiente["dir"]) == []


def test_verificar_pdfs_detecta_problemas(ambiente, tmp_path):
    res = carregar_manifesto(ambiente["manifesto"])
    m = json.loads(json.dumps(res["manifesto"]))
    m["desenhos"][0]["origem"]["sha256"] = "0" * 64
    m["desenhos"][0]["mapa_folhas"]["20"] = 30
    m["desenhos"][1]["origem"]["nome_arquivo"] = "nao-existe.pdf"
    codigos = sorted(p["codigo"] for p in verificar_pdfs(m, ambiente["dir"]))
    assert codigos == ["PAGINA_FORA_DO_PDF", "PDF_HASH_DIVERGENTE", "PDF_NAO_ENCONTRADO"]


def test_cli_validar(ambiente, capsys):
    rc = cli.main([str(ambiente["manifesto"]), "--base", str(ambiente["saida"] / "base_placards_cd.json"),
                   "--pasta-pdf", str(ambiente["dir"])])
    out = capsys.readouterr().out
    assert rc == 0 and "0 com vínculo conferido" in out


def test_importador_recusa_manifesto_invalido(ambiente, tmp_path):
    from placards_cd import importar
    m = json.loads(ambiente["manifesto"].read_text(encoding="utf-8"))
    m["desenhos"][1]["ativa"] = True
    p = tmp_path / "m.json"
    p.write_text(json.dumps(m))
    with pytest.raises(SystemExit):
        importar.main(["--sem-base", "--saida", str(tmp_path / "o"), "--manifesto", str(p)])
