"""Monta o HTML autônomo a partir de ``web/`` com os dados incorporados."""
from __future__ import annotations

import json
import re
from pathlib import Path

RAIZ_WEB = Path(__file__).resolve().parent.parent / "web"


def json_para_script(dados) -> str:
    """Serializa JSON para dentro de <script type="application/json">.

    Escapa <, >, & e separadores de linha para que nenhum texto vindo do Excel
    ou do manifesto consiga fechar a tag ou ser interpretado como HTML.
    """
    texto = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
    return (texto.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def montar_html(base: dict | None, manifesto: dict | None, config: dict) -> str:
    modelo = (RAIZ_WEB / "template.html").read_text(encoding="utf-8")
    trocas = {
        "/*__CSS__*/": (RAIZ_WEB / "estilo.css").read_text(encoding="utf-8"),
        "/*__NUCLEO__*/": (RAIZ_WEB / "nucleo.js").read_text(encoding="utf-8"),
        "/*__APP__*/": (RAIZ_WEB / "app.js").read_text(encoding="utf-8"),
        "__DADOS_BASE__": json_para_script(base),
        "__DADOS_MANIFESTO__": json_para_script(manifesto),
        "__DADOS_CONFIG__": json_para_script(config),
    }
    for marcador in trocas:
        if modelo.count(marcador) != 1:
            raise RuntimeError(f"Marcador {marcador} deve aparecer uma vez em template.html")
    # Substituição em passada única: o conteúdo inserido (que pode vir do
    # Excel) nunca é reprocessado em busca de outros marcadores.
    padrao = re.compile("|".join(re.escape(m) for m in trocas))
    return padrao.sub(lambda m: trocas[m.group(0)], modelo)
