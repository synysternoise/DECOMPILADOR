"""Desenhos por nome de arquivo, HTML publicado e relatório do ADM."""
import json
import re
from pathlib import Path
from urllib.parse import unquote

from conftest import montar_pasta
from placards_cd import publicar


def dados_do_html(html: Path):
    t = html.read_text(encoding="utf-8")
    return json.loads(t.split('id="dados">', 1)[1].split("</script>", 1)[0]), t


def pub(pasta, **kw):
    return [p for p in pasta["res"]["publicos"] if all(p.get(k) == v for k, v in kw.items())]


def test_desenhos_por_pn_cdpl_e_subpasta(pasta):
    assert pub(pasta, pn_novo="171-50557-021")[0]["desenho"] == "desenhos/171-50557-021.pdf"
    assert pub(pasta, pn_novo="171-60555-001")[0]["desenho"] == "desenhos/met%C3%A1lico/171-60555-001.pdf"
    assert pub(pasta, pn_antigo="CDPL568-201")[0]["desenho"] == "desenhos/CDPL568-201.pdf"
    assert pub(pasta, pn_novo="171-50550-005")[0]["desenho"] is None
    for p in pasta["res"]["publicos"]:
        if p["desenho"]:
            assert (pasta["dir"] / unquote(p["desenho"])).is_file()
    assert pasta["res"]["pdfs_sem_placard"] == ["999-ORFAO-001.pdf"]


def test_links_absolutos(tmp_path):
    p = montar_pasta(tmp_path / "Pasta Com Espaço")
    cfg, base = publicar.carregar_config(p / "_adm" / "config.json")
    cfg["links_absolutos"] = True
    res = publicar.publicar(cfg, base)
    link = [x for x in res["publicos"] if x["pn_novo"] == "171-50557-021"][0]["desenho"]
    assert link.startswith("file:///") and "Pasta%20Com%20Espa%C3%A7o" in link


def test_html_publicado(pasta):
    dados, html = dados_do_html(pasta["html"])
    assert len(dados["registros"]) == 261 and dados["total_desenhos"] == 3
    assert dados["fonte"]["arquivo"] == "PLANILHA_PLACARD CD.xlsx"
    # Só os campos necessários vão para o arquivo público
    assert set(dados["registros"][0]) == set(publicar.CAMPOS_PUBLICOS) | {"folhas", "desenho"}
    bruto = html.split('id="dados">', 1)[1].split("</script>", 1)[0]
    assert "<" not in bruto and "\\u003cimg" in bruto
    assert "<script src" not in html and "<link" not in html and "connect-src 'none'" in html
    assert re.findall(r"https?://[^\s\"'<>)]+", html) == []


def test_relatorio_do_adm(pasta):
    rel = pasta["res"]["relatorio"].read_text(encoding="utf-8")
    assert "Contagens iguais às do snapshot conferido" in rel
    assert "PDFs em desenhos/ que não correspondem a nenhum placard (1)" in rel and "999-ORFAO-001.pdf" in rel
    assert "Placards sem desenho 2D (258)" in rel
    assert "| Plástico | 130 | 171-59130-001 |" in rel
    assert pasta["res"]["relatorio"].parent.name == "_adm"


def test_consulta_vazia(tmp_path):
    p = montar_pasta(tmp_path / "v", com_desenhos=False)
    assert publicar.main(["--config", str(p / "_adm" / "config.json"), "--sem-base"]) == 0
    dados, _ = dados_do_html(p / "Consulta de Placards.html")
    assert dados["registros"] is None


def test_bat_do_adm():
    bat = (Path(publicar.__file__).parent.parent / "ATUALIZAR CONSULTA.bat").read_bytes()
    assert b"\r\n" in bat and b"placards_cd.publicar --config config.json" in bat
    cfg = json.loads((Path(publicar.__file__).parent.parent / "config.json").read_text(encoding="utf-8"))
    assert cfg["planilha"] == "../PLANILHA_PLACARD CD.xlsx" and cfg["arquivo_consulta"] == "../Consulta de Placards.html"
