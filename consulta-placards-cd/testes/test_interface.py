"""Interface no Chromium (Playwright), com base e PDFs SINTÉTICOS."""
import json
import re

import pytest

from conftest import ORIGEM
from placards_cd import importar

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
def pagina(navegador, ambiente):
    ctx = navegador.new_context(accept_downloads=True)
    pg = ctx.new_page()
    externas, erros = [], []
    pg.on("request", lambda r: externas.append(r.url) if not r.url.startswith(("file:", "blob:", "data:", "about:")) else None)
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.goto(ambiente["html"].as_uri())
    yield pg
    assert externas == [], f"requisições de rede: {externas}"
    assert erros == [], erros
    ctx.close()


def buscar(pg, q):
    pg.fill("#busca", q)
    pg.wait_for_timeout(250)


def abrir_filtros(pg):
    if not pg.evaluate("document.getElementById('filtros-det').open"):
        pg.click("#filtros-det summary")


def abrir_primeiro(pg):
    pg.focus("#busca")
    pg.keyboard.press("ArrowDown")
    pg.keyboard.press("Enter")
    return pg.locator("#ficha-corpo")


def linha_folha(pg, n):
    return pg.locator("#ficha-corpo tbody tr", has=pg.locator(f"th:text-is('Folha {n}'), th:text-is('Folha {n} (filtrada)')"))


def selecionar_pdf(pg, botao, arquivo):
    with pg.expect_file_chooser() as fc:
        botao.click()
    fc.value.set_files(str(arquivo))
    pg.wait_for_timeout(300)


def test_criterio2_busca_ficha_e_teclado(pagina):
    pg = pagina
    assert "PLANILHA_PLACARD CD.xlsx" in pg.inner_text("#estado-base")
    assert "189 registros plásticos" in pg.inner_text("#estado-base")
    for q in ["17150557021", "cdpl569-1-16"]:
        buscar(pg, q)
        primeiro = pg.locator("#lista .item").first
        assert "171-50557-021" in primeiro.inner_text() and "exato" in primeiro.inner_text()
    ficha = abrir_primeiro(pg)
    assert pg.evaluate("document.activeElement.id") == "ficha-titulo"
    txt = ficha.inner_text()
    for esperado in ["00122", "F204", "171-60473-401/ CD", "CDPL569-1-16", "Zona da linha"]:
        assert esperado in txt
    assert linha_folha(pg, 20).locator("td").first.inner_text() == "1"
    assert pg.locator("#ficha-corpo tbody tr").count() == 1
    resumo = pg.inner_text("#ficha-corpo .resumo")
    assert "171-60473-401/CD" in resumo and "00122" in resumo and "F204" in resumo and "SH20: 1" in resumo


def test_criterio3_metalico_sem_pn(pagina):
    pg = pagina
    buscar(pg, "171-60555-001")
    ficha = abrir_primeiro(pg)
    assert "171-60474-401/CD" in ficha.inner_text()
    assert [linha_folha(pg, n).locator("td").first.inner_text() for n in (6, 7, 9, 11)] == ["1"] * 4
    assert "PDF não associado" in ficha.inner_text()
    buscar(pg, "CDPL568-201")
    ficha = abrir_primeiro(pg)
    assert ficha.locator("dd .nao-inf").count() >= 2  # PN novo e descrição não informados
    assert "Sem PN novo" in ficha.inner_text() and "Descrição (coluna G) não informada" in ficha.inner_text()


def test_criterio4_quantidades_separadas(pagina):
    pg = pagina
    buscar(pg, "171-59130-001")
    ficha = abrir_primeiro(pg)
    caixas = ficha.locator(".qtd")
    assert [caixas.nth(i).locator(".val").inner_text() for i in range(3)] == ["3", "2", "4"]
    assert ficha.locator(".qtd.divergente").count() == 3
    assert "não significa liberação" in ficha.inner_text()


def test_filtros_combinados_e_folha_nao_esconde(pagina):
    pg = pagina
    assert "Digite um PN novo ou CDPL" in pg.inner_text("#contagem")
    assert pg.locator("#lista .item").count() == 0
    abrir_filtros(pg)
    pg.select_option("#f-kit", "METALICO")
    pg.select_option("#f-folha", "9")
    pg.select_option("#f-topo", "171-60474-401/CD")
    assert pg.inner_text("#filtros-ativos") == "3 ativos"
    assert re.search(r"^\d+ registros?", pg.inner_text("#contagem"))
    buscar(pg, "171-60555-001")
    abrir_primeiro(pg)
    assert pg.locator("#ficha-corpo tbody tr").count() == 4
    assert pg.locator("#ficha-corpo tr.filtrada").inner_text().startswith("Folha 9 (filtrada)")
    pg.select_option("#f-kit", "PLASTICO")
    assert "Nenhum registro encontrado" in pg.inner_text("#contagem")
    pg.click("#limpar")
    assert pg.input_value("#busca") == "" and "Base com 261 registros" in pg.inner_text("#contagem")
    assert pg.is_hidden("#filtros-ativos")


def test_correspondencia_exata_unica_abre_ficha_sozinha(pagina):
    buscar(pagina, "CDPL568-201")
    assert pagina.inner_text("#ficha-titulo") == "CDPL568-201"
    assert pagina.evaluate("document.activeElement.id") == "busca"  # foco continua na busca
    buscar(pagina, "171-50550-005")  # PN repetido em duas linhas: não abre sozinho
    assert pagina.locator("#lista .item").count() == 2
    assert pagina.inner_text("#ficha-titulo") == "CDPL568-201"


def test_sem_resultados(pagina):
    buscar(pagina, "XYZ-NAO-EXISTE")
    assert "Nenhum registro encontrado para “XYZ-NAO-EXISTE”" in pagina.inner_text("#contagem")


def test_dados_como_texto_nunca_html(pagina):
    pg = pagina
    buscar(pg, "nao fumar")
    abrir_primeiro(pg)
    assert 'PLACA "NÃO FUMAR" – AÇÃO <img src=x onerror="window.__xss=1">' in pg.inner_text("#ficha-corpo")
    assert '</script><b id="injetado">x</b>' in pg.inner_text("#ficha-corpo")
    assert pg.evaluate("window.__xss") is None
    assert pg.locator("#injetado").count() == 0 and pg.locator("#ficha-corpo img").count() == 0


def test_pdf_sintetico_folha20_pagina22_revisao_e_documento(pagina, ambiente):
    pg = pagina
    buscar(pg, "171-50557-021")
    abrir_primeiro(pg)
    celula = linha_folha(pg, 20).locator("td").nth(2)
    assert "PDF local precisa ser selecionado novamente (folha 20 → página 22)" in celula.inner_text()
    # PDF errado (rev. B) para a rev. A é recusado pelo SHA-256
    selecionar_pdf(pg, celula.get_by_role("button", name="Selecionar PDF…"), ambiente["pdf_b"])
    assert "SHA-256 não confere" in pg.inner_text("#aviso-global")
    selecionar_pdf(pg, linha_folha(pg, 20).get_by_role("button", name="Selecionar PDF…"), ambiente["pdf_a"])
    assert "PDF associado" in pg.inner_text("#aviso-global")
    linha_folha(pg, 20).get_by_role("button", name="Ver folha 20 (pág. 22)").click()
    src = pg.locator("#vis-quadro iframe").get_attribute("src")
    assert src.startswith("blob:") and src.endswith("#page=22")
    assert pg.get_attribute("#vis-nova-aba", "href") == src
    assert "Vínculo folha → página NÃO conferido" in pg.inner_text("#ficha-corpo")
    pg.get_by_role("button", name="Abrir documento inteiro").click()
    src_inteiro = pg.locator("#vis-quadro iframe").get_attribute("src")
    assert src_inteiro.startswith("blob:") and "#" not in src_inteiro
    assert "Folha 20 → página 22 do PDF" in pg.inner_text("#ficha-corpo")
    # Folha sem página mapeada (folha 19 não está no mapa da rev. A)
    buscar(pg, "171-59018-001")
    abrir_primeiro(pg)
    c19 = linha_folha(pg, 19).locator("td").nth(2)
    assert "Folha 19 sem página mapeada (rev. A)" in c19.inner_text()
    c19.get_by_role("button", name="Documento inteiro").click()
    assert "#" not in pg.locator("#vis-quadro iframe").get_attribute("src")
    # Troca da revisão ativa para B
    pg.locator("#painel-desenhos summary").click()
    pg.get_by_label("Revisão B ativa para 171-60473-401/CD").check()
    buscar(pg, "171-50557-021")
    abrir_primeiro(pg)
    celula = linha_folha(pg, 20).locator("td").nth(2)
    assert "precisa ser selecionado novamente (folha 20 → página 23)" in celula.inner_text()
    selecionar_pdf(pg, celula.get_by_role("button", name="Selecionar PDF…"), ambiente["pdf_b"])
    linha_folha(pg, 20).get_by_role("button", name="Ver folha 20 (pág. 23)").click()
    assert pg.locator("#vis-quadro iframe").get_attribute("src").endswith("#page=23")


def test_manifesto_exportar_e_importar_invalido(pagina, tmp_path):
    pg = pagina
    pg.locator("#painel-desenhos summary").click()
    with pg.expect_download() as dl:
        pg.click("#exportar-manifesto")
    caminho = tmp_path / "m.json"
    dl.value.save_as(caminho)
    m = json.loads(caminho.read_text(encoding="utf-8"))
    assert m["formato"] == "manifesto-desenhos-placards" and len(m["desenhos"]) == 2
    assert caminho.stat().st_size < 10_000  # só metadados, nenhum PDF
    m["desenhos"][1]["ativa"] = True
    m["desenhos"][0]["mapa_folhas"]["20"] = 0
    ruim = tmp_path / "ruim.json"
    ruim.write_text(json.dumps(m))
    pg.set_input_files("#importar-manifesto", str(ruim))
    pg.wait_for_timeout(200)
    txt = pg.inner_text("#desenhos-corpo")
    assert "Manifesto não aplicado" in txt and "revisões ativas" in txt and "Página inválida" in txt
    assert "2 desenho(s), incorporado no HTML" in txt


def test_editor_valida_e_associa_url_autorizada(pagina):
    pg = pagina
    pg.locator("#painel-desenhos summary").click()
    pg.locator("#desenhos-corpo tr", has_text="171-60474-401/CD").get_by_role("button", name="Associar…").click()
    pg.fill("#ed-rev", "A")
    pg.check("input[name=ed-tipo][value=url]")
    pg.fill("#ed-url", "http://inseguro.example/x.pdf")
    pg.fill("#ed-f6", "8")
    pg.get_by_role("button", name="Validar e salvar").click()
    assert "URL deve ser HTTPS" in pg.inner_text("#ed-msgs")
    pg.fill("#ed-url", ORIGEM + "/171-60474-401.pdf")
    pg.get_by_role("button", name="Validar e salvar").click()
    assert "salvo" in pg.inner_text("#aviso-global")
    buscar(pg, "171-60555-001")
    abrir_primeiro(pg)
    link = linha_folha(pg, 6).get_by_role("link")
    assert link.get_attribute("href") == ORIGEM + "/171-60474-401.pdf#page=8"
    assert link.get_attribute("target") == "_blank" and "noopener" in link.get_attribute("rel")
    assert "Folha 7 sem página mapeada" in linha_folha(pg, 7).inner_text()


def test_sem_base_e_importacao_csv(navegador, ambiente, tmp_path):
    from test_importacao import exportar_csv
    assert importar.main(["--sem-base", "--saida", str(tmp_path)]) == 0
    pcsv, mtsv = tmp_path / "p.csv", tmp_path / "m.tsv"
    exportar_csv(ambiente["planilha"], "PLACARD, KIT PLASTIC", pcsv, ";")
    exportar_csv(ambiente["planilha"], "PLACARD, KIT METALLIC", mtsv, "\t")
    pg = navegador.new_page()
    pg.goto((tmp_path / "consulta-placards-cd.html").as_uri())
    assert "Base não carregada" in pg.inner_text("#estado-base")
    assert pg.is_disabled("#busca")
    pg.locator("#painel-csv summary").click()
    pg.set_input_files("#arquivo-csv", [str(pcsv), str(mtsv)])
    pg.wait_for_timeout(400)
    assert "Base importada de CSV/TSV" in pg.inner_text("#estado-base")
    assert "Plástico 189 registros" in pg.inner_text("#csv-resultado")
    buscar(pg, "17150557021")
    abrir_primeiro(pg)
    assert "00122" in pg.inner_text("#ficha-corpo")
    pg.close()


# ---------------------------------------------------------------- planilha carregada direto na página
def _sem_base(tmp_path):
    assert importar.main(["--sem-base", "--saida", str(tmp_path)]) == 0
    return tmp_path / "consulta-placards-cd.html"


def _carregar(pg, arquivo):
    pg.set_input_files("#arquivo-planilha", str(arquivo))
    for _ in range(200):  # sem wait_for_function: a CSP da página bloqueia eval
        texto = pg.inner_text("#aviso-global")
        if texto and "Lendo" not in texto:
            return texto
        pg.wait_for_timeout(100)
    raise AssertionError("planilha não terminou de carregar")


def _comparar_com_python(base_js, base_py):
    for campo in ("resumo", "abas_ignoradas", "exclusoes"):
        assert base_js[campo] == base_py[campo], campo
    assert len(base_js["registros"]) == len(base_py["registros"])
    for a, b in zip(base_py["registros"], base_js["registros"]):
        assert a == b, (a["id"], {k: (a[k], b.get(k)) for k in a if a[k] != b.get(k)})


def test_planilha_carregada_no_navegador_igual_ao_importador(navegador, ambiente, tmp_path):
    pg = navegador.new_page()
    rede = []
    pg.on("request", lambda r: rede.append(r.url) if not r.url.startswith(("file:", "blob:", "data:")) else None)
    pg.goto(_sem_base(tmp_path).as_uri())
    assert "Carregar planilha" in pg.inner_text("#estado-base") and pg.is_disabled("#salvar-consulta")
    msg = _carregar(pg, ambiente["planilha"])
    assert "Planilha carregada: Plástico 189 · Metálico 72" in msg and "diferença" not in msg
    base_js = pg.evaluate("ConsultaPlacards.base()")
    _comparar_com_python(base_js, ambiente["base"])
    assert base_js["fonte"]["sha256"] == ambiente["hash_antes"]
    assert base_js["comparacao_snapshot"]["diferencas"] == []
    assert "nada foi enviado" in pg.inner_text("#estado-base")
    buscar(pg, "17150557021")
    assert "00122" in pg.inner_text("#ficha-corpo .resumo")
    assert rede == []
    pg.close()


def test_planilha_regravada_pelo_libreoffice(navegador, ambiente, tmp_path):
    import shutil
    import subprocess
    soffice = shutil.which("soffice")
    if not soffice:
        pytest.skip("LibreOffice ausente")
    origem = tmp_path / "orig"
    origem.mkdir()
    shutil.copy(ambiente["planilha"], origem / "lo.xlsx")
    subprocess.run([soffice, "--headless", "--convert-to", "xlsx:Calc MS Excel 2007 XML", "--outdir", str(tmp_path),
                    str(origem / "lo.xlsx")], check=True, capture_output=True, timeout=180)
    lo = tmp_path / "lo.xlsx"
    assert importar.main(["--planilha", str(lo), "--saida", str(tmp_path / "py")]) == 0
    base_py = json.loads((tmp_path / "py" / "base_placards_cd.json").read_text(encoding="utf-8"))
    pg = navegador.new_page()
    pg.goto(_sem_base(tmp_path / "html").as_uri())
    _carregar(pg, lo)
    _comparar_com_python(pg.evaluate("ConsultaPlacards.base()"), base_py)
    pg.close()


def test_planilha_com_layout_errado_ou_xls(navegador, ambiente, tmp_path):
    import fixtures
    ruim = fixtures.gerar_planilha(tmp_path / "ruim.xlsx", layout_invalido=True)
    xls = tmp_path / "velha.xls"
    xls.write_bytes(b"\xd0\xcf\x11\xe0")
    pg = navegador.new_page()
    pg.goto(_sem_base(tmp_path / "h").as_uri())
    msg = _carregar(pg, ruim)
    assert "Planilha não carregada" in msg and "PLACARD, KIT METALLIC" in msg and "Coluna C" in msg and "SH12" in msg
    assert "Base não carregada" in pg.inner_text("#estado-base")
    assert "salve como .xlsx" in _carregar(pg, xls).lower() or "Pasta de Trabalho do Excel (.xlsx)" in pg.inner_text("#aviso-global")
    pg.close()


def test_salvar_consulta_com_base_embutida(navegador, ambiente, tmp_path):
    ctx = navegador.new_context(accept_downloads=True)
    pg = ctx.new_page()
    pg.goto(_sem_base(tmp_path).as_uri())
    _carregar(pg, ambiente["planilha"])
    with pg.expect_download() as dl:
        pg.click("#salvar-consulta")
    salvo = tmp_path / "salva" / "consulta-placards-cd.html"
    salvo.parent.mkdir()
    dl.value.save_as(salvo)
    assert dl.value.suggested_filename == "consulta-placards-cd.html"
    html = salvo.read_text(encoding="utf-8")
    dados = html.split('id="dados-base">', 1)[1].split("</script>", 1)[0]
    assert "<" not in dados and "\\u003c/script\\u003e" in dados
    pg2 = ctx.new_page()
    erros = []
    pg2.on("pageerror", lambda e: erros.append(str(e)))
    pg2.goto(salvo.as_uri())
    assert "Base: PLANILHA_PLACARD CD.xlsx" in pg2.inner_text("#estado-base")
    buscar(pg2, "CDPL568-201")
    assert pg2.inner_text("#ficha-titulo") == "CDPL568-201"
    _comparar_com_python(pg2.evaluate("ConsultaPlacards.base()"), ambiente["base"])
    assert erros == []
    ctx.close()
