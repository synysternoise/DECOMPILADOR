"""Dados SINTÉTICOS para testes. Nunca são publicados nem usados na base real.

A planilha imita o layout da PLANILHA_PLACARD CD (cabeçalho na linha 1,
colunas A:AH) e reproduz os casos dos critérios de aceitação. Descrições e
códigos genéricos são inventados.
"""
from __future__ import annotations

from pathlib import Path

TOPO_PLAST = "171-60473-401/ CD"
TOPO_METAL = "171-60474-401/ CD"
FMT_POS = "00000"


def _cabecalho(kit: str) -> list:
    cab = ["PART NUMBER", "E2 REFERENCIA", "CDPL (REF)" if kit == "P" else "PART NUMBER", "POS", "ZONE", "QTY",
           "FORMATO", "CONJUNTO" if kit == "P" else "MATERIAL", "ECODE", "ACTION", "LIBERADO"]
    cab += [f"SH{n}" for n in range(1, 21)]
    cab += ["Total", "Check", "OBS"]
    return cab


def _linha(a=None, b=None, c=None, pos=None, zona=None, qty=None, g=None, h=TOPO_PLAST, ecode=None,
           action="SIM", liberado="OK", folhas=None, total=None, check="ok", obs=None) -> dict:
    return {"a": a, "b": b, "c": c, "pos": pos, "zona": zona, "qty": qty, "g": g, "h": h, "ecode": ecode,
            "action": action, "liberado": liberado, "folhas": folhas or {}, "total": total, "check": check, "obs": obs}


def linhas_plastico() -> dict[int, dict | str | None]:
    zonas = ["A101", "B202", "C303", "E204"]
    rows: dict[int, dict | str | None] = {}
    for r in range(2, 191):  # 189 registros CD
        n = r % 20 + 1
        rows[r] = _linha(a=f"171-59{r:03d}-001", b=f"196-LEX9{r:05d}", c=f"CDPL9{r}-1", pos=r + 100,
                         zona=zonas[r % 4], qty=1, g=f"PLACARD SINTETICO {r}, PLST", ecode=2300000 + r,
                         folhas={n: 1}, total=1)
    # Critério 2
    rows[12] = _linha(a="171-50557-021", b="196-LEX003131", c="CDPL569-1-16", pos=122, zona="F204", qty=1,
                      g="SEAT ROW 16 SINTETICO, PLST", ecode=2307529, folhas={20: 1}, total=1)
    # Sem PN novo, com CDPL
    rows[20] = _linha(a=None, b="196-LEX002446", c="CDPL561-27", pos=6, zona="B034", qty=4,
                      g="DO NOT TOUCH SINTETICO, PLST", folhas={3: 2, 4: 2}, total=4)
    # Referência provisória
    rows[25] = _linha(a="171-50550-019", b="196-LEX003763", c="CDPLXXX-XX", pos=35, zona="B086", qty=1,
                      g="PROVISORIO SINTETICO", folhas={10: 1}, total=1)
    # Aspas, acentos e HTML que não pode ser executado
    rows[30] = _linha(a="171-50550-029", b="196-LEX002423", c="CDPL563-129", pos=42, zona="C051", qty=2,
                      g='PLACA "NÃO FUMAR" – AÇÃO <img src=x onerror="window.__xss=1">',
                      folhas={6: 1, 7: 1}, total=2, obs='</script><b id="injetado">x</b>')
    # POS como texto, zero registrado numa folha
    rows[31] = _linha(a="171-50550-031", b="196-LEX002438", c="CDPL563-3", pos="00029", zona="C061", qty=2,
                      g="PBE SINTETICO, PLST", folhas={3: 0, 4: 2}, total=2)
    # Valor não numérico numa folha
    rows[32] = _linha(a="171-50550-033", b="196-LEX002428", c="CDPL563-57", pos=54, zona="C104", qty=1,
                      g="ARROW SINTETICO", folhas={5: "X"}, total=1)
    # Erro do Excel no total
    rows[33] = _linha(a="171-50550-035", b="196-LEX000506", c="CDPL563-5", pos=55, zona="D106", qty=1,
                      g="OXIGEN SINTETICO", folhas={10: 1}, total="#N/A")
    # Fórmula sem valor em cache no total
    rows[34] = _linha(a="171-50550-037", b="171-50550-033", c="CDPL563-9", pos=56, zona="D103", qty=2,
                      g="FIRST AID SINTETICO", folhas={10: 2}, total="=SUM(L34:AE34)")
    # PN repetido em duas linhas (não deduplicar) + linha seguinte sem PN (não herdar)
    rows[35] = _linha(a="171-50550-005", b="171-50550-005", c="CDPL562-25", pos=30, zona="C064", qty=2,
                      g="ABSORBENT SINTETICO", folhas={6: 1, 7: 1}, total=2)
    rows[36] = _linha(a="171-50550-005", b="171-50550-005", c="CDPL562-23", pos=36, zona="D061", qty=2,
                      g="PAPER SINTETICO", folhas={6: 1, 7: 1}, total=2)
    rows[37] = _linha(a=None, b=None, c="CDPL562-19", pos=37, zona=None, qty=None, g=None, action=None,
                      liberado=None, folhas={}, total=None, check=None)
    # Espaços nas pontas dos identificadores
    rows[38] = _linha(a="  171-50550-041 ", b=" 196-LEX003764", c="CDPL563-11 ", pos=65, zona="D103", qty=1,
                      g="MEDICAL KIT SINTETICO", folhas={11: 1}, total=1)
    # Topo sem barra antes da configuração
    rows[40] = _linha(a="171-50550-045", b="196-LEX003752", c="CDPL602-57", pos=79, zona="F141", qty=1,
                      g="ELT SINTETICO", h="171-60473-401 CD", folhas={6: 1}, total=1)
    # Critério 4: divergência QTY x distribuição x Total
    rows[130] = _linha(a="171-59130-001", b="196-LEX900130", c="CDPL9130-1", pos=230, zona="C303", qty=3,
                       g="DIVERGENTE SINTETICO", folhas={6: 1, 7: 1}, total=4, check="ok",
                       obs="FALTA PASSAR PARA INCLUIR NA OE")
    # Exclusões (fora do escopo CD ou sem identificação)
    rows[191] = _linha(a="171-50557-021", c="CDPL569-1-16", pos=122, zona="F204", qty=1, g="LX SINTETICO",
                       h="171-60473-401/ LX", folhas={20: 1}, total=1)
    rows[192] = _linha(a="171-50999-001", c="CDPL999-1", pos=1, zona="A001", qty=1, g="AL SINTETICO",
                       h="171-60473-401/ AL", folhas={1: 1}, total=1)
    rows[193] = None
    rows[194] = _linha(a="171-50999-003", c="CDPL999-3", pos=3, qty=1, g="SEM H", h=None, folhas={1: 1}, total=1)
    rows[195] = _linha(qty=5, total=5, g=None, check=None)
    rows[196] = "CABECALHO"
    rows[197] = _linha(a="171-50999-005", c="CDPL999-5", pos=5, qty=1, g="H TEXTO", h="VER DESENHO", total=1)
    rows[198] = None
    return rows


def linhas_metalico() -> dict[int, dict | str | None]:
    rows: dict[int, dict | str | None] = {}
    com_pn = set(range(2, 9)) | set(range(10, 15))  # 12 com PN novo; 60 sem
    for r in range(2, 74):  # 72 registros CD
        n = r % 20 + 1
        rows[r] = _linha(a=f"171-69{r:03d}-001" if r in com_pn else None, b=f"196-LEM8{r:05d}",
                         c=f"CDPL568-{r:03d}", pos=r + 500, zona="M" + str(100 + r), qty=1,
                         g=f"PLACARD METALICO SINTETICO {r}", h=TOPO_METAL, folhas={n: 1}, total=1)
    rows[5] = _linha(a="171-60555-001", b="196-LEM800005", c="CDPL568-005", pos=505, zona="M105", qty=4,
                     g="PLACARD METALICO SINTETICO 5", h=TOPO_METAL, folhas={6: 1, 7: 1, 9: 1, 11: 1}, total=4)
    rows[9] = _linha(a=None, b=None, c="CDPL568-201", pos=509, zona="M109", qty=1, g=None, h=TOPO_METAL,
                     folhas={2: 1}, total=1)
    rows[74] = _linha(a="171-69900-001", c="CDPL568-900", pos=900, qty=1, g="LX METAL", h="171-60474-401/ LX",
                      folhas={1: 1}, total=1)
    rows[75] = _linha(a="171-69901-001", c="CDPL568-901", pos=901, qty=1, g="AL METAL", h="171-60474-401/AL",
                      folhas={1: 1}, total=1)
    return rows


def _escrever_aba(ws, kit: str, rows: dict, cabecalho: list | None = None):
    cab = cabecalho or _cabecalho(kit)
    for k, v in enumerate(cab, start=1):
        ws.cell(row=1, column=k, value=v)
    ws.auto_filter.ref = "A1:AH1"
    for r, d in sorted(rows.items()):
        if d is None:
            continue
        if d == "CABECALHO":
            for k, v in enumerate(cab, start=1):
                ws.cell(row=r, column=k, value=v)
            continue
        valores = [d["a"], d["b"], d["c"], d["pos"], d["zona"], d["qty"], d["g"], d["h"], d["ecode"],
                   d["action"], d["liberado"]]
        for k, v in enumerate(valores, start=1):
            if v is not None:
                ws.cell(row=r, column=k, value=v)
        if isinstance(d["pos"], int):
            ws.cell(row=r, column=4).number_format = FMT_POS
        for n, q in d["folhas"].items():
            ws.cell(row=r, column=11 + n, value=q)
        for col, v in ((32, d["total"]), (33, d["check"]), (34, d["obs"])):
            if v is not None:
                ws.cell(row=r, column=col, value=v)


def gerar_planilha(caminho: Path, layout_invalido: bool = False) -> Path:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "PLACARD, KIT PLASTIC"
    _escrever_aba(ws, "P", linhas_plastico())
    wm = wb.create_sheet("PLACARD, KIT METALLIC")
    cab_m = None
    if layout_invalido:
        cab_m = _cabecalho("P")  # metálico com cabeçalho de plástico em C/H
        cab_m[11 + 11] = "OBS"  # SH12 ausente
    _escrever_aba(wm, "M", linhas_metalico(), cab_m)
    for nome in ("NON ELECTRICAL EXIT SIGNS", "ELECTRICAL EXIT SIGNS"):
        we = wb.create_sheet(nome)
        _escrever_aba(we, "P", {2: _linha(a="171-77777-001", c="CDPL777-1", pos=1, qty=1, g="EXIT SIGN SINTETICO",
                                          folhas={1: 1}, total=1)})
    wc = wb.create_sheet("Controle de Folhas")
    wc["A1"], wc["B1"] = "FOLHA", "STATUS"
    wc["A2"], wc["B2"] = "SH1", "OK"
    wb.save(caminho)
    return caminho


def gerar_pdf(caminho: Path, revisao: str = "A") -> Path:
    """PDF sintético de 24 páginas: capa, índice, folhas 1–20 (págs. 3–22), notas."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(caminho), pagesize=landscape(A4))
    paginas = ["CAPA (sintética) rev " + revisao, "ÍNDICE (sintético)"] + \
              [f"FOLHA {n} — desenho sintético 171-60473-401 rev {revisao}" for n in range(1, 21)] + ["NOTAS 1", "NOTAS 2"]
    for i, titulo in enumerate(paginas, start=1):
        c.setFont("Helvetica-Bold", 28)
        c.drawString(60, 400, titulo)
        c.setFont("Helvetica", 14)
        c.drawString(60, 360, f"Página {i} do PDF")
        c.showPage()
    c.save()
    return caminho


def manifesto_sintetico(sha_a: str = "", sha_b: str = "") -> dict:
    mapa_a = {str(n): n + 2 for n in range(1, 21) if n != 19}   # folha 19 sem página
    mapa_b = {str(n): n + 3 for n in range(1, 21)}
    return {
        "formato": "manifesto-desenhos-placards",
        "versao_formato": 1,
        "atualizado_em": "2026-11-24",
        "desenhos": [
            {"configuracao": "CD", "topo": "171-60473-401/CD", "revisao": "A", "ativa": True,
             "origem": {"tipo": "local", "nome_arquivo": "desenho-sintetico-A.pdf", "sha256": sha_a},
             "total_paginas": 24, "mapa_folhas": mapa_a, "vinculo_conferido": False,
             "observacoes": "SINTÉTICO — somente testes"},
            {"configuracao": "CD", "topo": "171-60473-401/CD", "revisao": "B", "ativa": False,
             "origem": {"tipo": "local", "nome_arquivo": "desenho-sintetico-B.pdf", "sha256": sha_b},
             "total_paginas": 24, "mapa_folhas": mapa_b, "vinculo_conferido": False},
        ],
    }
