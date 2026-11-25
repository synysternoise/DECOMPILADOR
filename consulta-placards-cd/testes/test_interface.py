"""Consulta publicada aberta no Chromium (dados e PDFs SINTÉTICOS)."""
import json
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest

from conftest import montar_pasta
from placards_cd import publicar

sync_api = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def navegador():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"Chromium indisponível: {exc}")
        yield b
        b.close()


@pytest.fixture
def pg(navegador, pasta):
    page = navegador.new_page(viewport={"width": 1440, "height": 900})
    rede, erros = [], []
    page.on("request", lambda r: rede.append(r.url) if not r.url.startswith(("file:", "data:", "about:")) else None)
    page.on("pageerror", lambda e: erros.append(str(e)))
    page.goto(pasta["html"].as_uri())
    yield page
    assert rede == [] and erros == []
    page.close()


def buscar(pg, q):
    pg.fill("#q", q)
    pg.wait_for_timeout(200)


def cards(pg):
    return pg.locator("#grade .card")


def test_abre_com_todos_os_placards(pg):
    assert "261 placards · 3 desenhos 2D" in pg.inner_text("#meta")
    assert cards(pg).count() == 261
    assert pg.evaluate("document.activeElement.id") == "q"


def test_busca_pn_com_e_sem_hifen(pg):
    for q in ["171-50557-021", "17150557021", "cdpl569-1-16", " CDPL 569 1 16 "]:
        buscar(pg, q)
        c = cards(pg).first
        assert "171-50557-021" in c.inner_text() and "Correspondência exata" in c.inner_text(), q
        assert "00122" in c.inner_text() and "F204" in c.inner_text() and "171-60473-401" in c.inner_text()
        assert "SH20" in c.inner_text()


def test_metalico_e_sem_pn(pg):
    buscar(pg, "171-60555-001")
    c = cards(pg).first
    assert "Metálico" in c.inner_text()
    assert [s.inner_text().replace("\n", " ") for s in c.locator(".sh").all()] == ["SH06× 1", "SH07× 1", "SH09× 1", "SH11× 1"]
    buscar(pg, "CDPL568-201")
    c = cards(pg).first
    assert "Sem PN novo" in c.inner_text() and "Título não informado" in c.inner_text()


def test_link_do_desenho_aponta_para_pdf_existente(pg, pasta):
    for q in ["171-50557-021", "171-60555-001", "CDPL568-201"]:
        buscar(pg, q)
        a = cards(pg).first.locator("a.abrir")
        assert a.get_attribute("target") == "_blank"
        alvo = Path(unquote(urlparse(a.evaluate("el => el.href")).path))
        assert alvo.is_file() and alvo.suffix == ".pdf", alvo
    buscar(pg, "171-50550-005")
    assert cards(pg).first.locator(".abrir.off").inner_text() == "Sem desenho 2D"


def test_filtro_de_idioma(pg):
    botoes = [b.inner_text() for b in pg.locator("#idiomas button").all()]
    assert botoes[0] == "Todos"
    pg.click("#idiomas button[data-l='Francês']") if "Francês" in botoes else None
    # a planilha sintética não tem siglas de idioma: só "Todos"
    assert botoes == ["Todos"]


def test_sem_resultado_e_texto_seguro(pg):
    buscar(pg, "XYZ-NAO-EXISTE")
    assert "Nenhum placard encontrado para “XYZ-NAO-EXISTE”" in pg.inner_text("#grade")
    assert pg.inner_text("#contagem").replace("\n", "") == "0placards"
    buscar(pg, "nao fumar")
    assert 'PLACA "NÃO FUMAR" – AÇÃO <img src=x onerror="window.__xss=1">' in cards(pg).first.inner_text()
    assert pg.evaluate("window.__xss") is None and pg.locator("#grade img").count() == 0


def test_idiomas_e_rodape_com_dados_proprios(navegador, tmp_path):
    p = montar_pasta(tmp_path / "i", com_desenhos=False)
    import openpyxl
    wb = openpyxl.load_workbook(p / "PLANILHA_PLACARD CD.xlsx")
    ws = wb["PLACARD, KIT PLASTIC"]
    ws["G2"], ws["G3"], ws["G4"] = "EXIT PLACARD, FRA, ING, PLST", "LAVATORY PLACARD, PICTORIAL, PLST", "AVISO, POR"
    wb.save(p / "PLANILHA_PLACARD CD.xlsx")
    cfg_path = p / "_adm" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["desenvolvedor"] = {"nome": "Fulano de Tal", "contato": "ramal 1234", "iniciais": "FT"}
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    assert publicar.main(["--config", str(cfg_path)]) == 0
    page = navegador.new_page()
    page.goto((p / "Consulta de Placards.html").as_uri())
    assert [b.inner_text() for b in page.locator("#idiomas button").all()] == ["Todos", "Francês", "Inglês", "Pictórico", "Português"]
    page.click("#idiomas button[data-l='Francês']")
    assert page.locator("#grade .card").count() == 1 and "EXIT PLACARD" in page.inner_text("#grade")
    page.fill("#q", "171-59003")
    page.wait_for_timeout(200)
    assert "Nenhum placard" in page.inner_text("#grade")  # linha 3 é Pictórico, não Francês
    page.click("#idiomas button[data-l='']")
    assert "LAVATORY" in page.inner_text("#grade")
    assert "Desenvolvido por Fulano de Tal" in page.inner_text("footer") and "ramal 1234" in page.inner_text("footer")
    assert page.inner_text("#dev-sig") == "FT"
    page.close()


def test_consulta_nao_publicada(navegador, tmp_path):
    p = montar_pasta(tmp_path / "n", com_desenhos=False)
    publicar.main(["--config", str(p / "_adm" / "config.json"), "--sem-base"])
    page = navegador.new_page()
    page.goto((p / "Consulta de Placards.html").as_uri())
    assert "Consulta ainda não publicada" in page.inner_text("#meta")
    assert page.is_disabled("#q")
    page.close()
