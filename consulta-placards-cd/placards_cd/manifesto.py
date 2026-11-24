"""Validação do manifesto de desenhos 2D (mapa folha -> página do PDF).

Espelhado em ``web/nucleo.js`` (``validarManifesto``). Os dois validadores
são testados contra os mesmos casos em ``testes/casos_manifesto.json``.
O manifesto guarda apenas metadados; o PDF nunca é incorporado.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

FORMATO = "manifesto-desenhos-placards"
VERSAO_FORMATO = 1
CONFIGURACAO = "CD"
NUM_FOLHAS = 20

RE_TOPO = re.compile(r"[A-Z0-9][A-Z0-9-]*/[A-Z]{2,3}")
RE_REVISAO = re.compile(r"[A-Z0-9][A-Z0-9._-]{0,9}")
RE_SHA256 = re.compile(r"[0-9a-f]{64}")


def normalizar_topo(topo: str) -> str:
    return re.sub(r"\s+", "", topo).upper()


def _eh_inteiro(v: Any) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return True
    return isinstance(v, float) and v.is_integer()


def url_https_valida(url: str) -> bool:
    try:
        partes = urlsplit(url)
    except ValueError:
        return False
    return partes.scheme == "https" and bool(partes.hostname)


def carregar_json_sem_duplicatas(texto: str) -> tuple[Any, list[dict]]:
    """Carrega JSON registrando chaves duplicadas (o JSON.parse descartaria)."""
    duplicadas: list[dict] = []

    def gancho(pares):
        obj = {}
        for chave, valor in pares:
            if chave in obj:
                duplicadas.append({"codigo": "CHAVE_DUPLICADA_JSON", "caminho": chave,
                                   "mensagem": f"Chave JSON duplicada: {chave!r}."})
            obj[chave] = valor
        return obj

    return json.loads(texto, object_pairs_hook=gancho), duplicadas


def validar_manifesto(obj: Any, topos_base: Optional[set[str]] = None) -> dict:
    erros: list[dict] = []
    avisos: list[dict] = []

    def erro(codigo, caminho, mensagem):
        erros.append({"codigo": codigo, "caminho": caminho, "mensagem": mensagem})

    def aviso(codigo, caminho, mensagem):
        avisos.append({"codigo": codigo, "caminho": caminho, "mensagem": mensagem})

    if not isinstance(obj, dict) or obj.get("formato") != FORMATO:
        erro("FORMATO_INVALIDO", "formato", f"O arquivo não é um manifesto ({FORMATO}).")
        return {"erros": erros, "avisos": avisos, "manifesto": None}
    if obj.get("versao_formato") != VERSAO_FORMATO:
        erro("FORMATO_INVALIDO", "versao_formato", f"Versão de formato não suportada: {obj.get('versao_formato')!r}.")
        return {"erros": erros, "avisos": avisos, "manifesto": None}
    desenhos = obj.get("desenhos")
    if not isinstance(desenhos, list):
        erro("DESENHOS_AUSENTE", "desenhos", "Lista 'desenhos' ausente.")
        return {"erros": erros, "avisos": avisos, "manifesto": None}

    normalizados = []
    vistos: dict[tuple[str, str], int] = {}
    for i, d in enumerate(desenhos):
        cam = f"desenhos[{i}]"
        if not isinstance(d, dict):
            erro("TIPO_INVALIDO", cam, "Entrada deve ser um objeto.")
            continue
        n: dict[str, Any] = {}

        cfg = d.get("configuracao")
        if not isinstance(cfg, str) or not cfg.strip():
            erro("CAMPO_OBRIGATORIO", f"{cam}.configuracao", "Configuração obrigatória.")
            cfg_n = None
        else:
            cfg_n = cfg.strip().upper()
            if cfg_n != CONFIGURACAO:
                erro("CONFIGURACAO_INVALIDA", f"{cam}.configuracao",
                     f"Configuração {cfg!r} fora do escopo ({CONFIGURACAO}).")
        n["configuracao"] = cfg_n

        topo = d.get("topo")
        topo_n = None
        if not isinstance(topo, str) or not topo.strip():
            erro("CAMPO_OBRIGATORIO", f"{cam}.topo", "Topo obrigatório.")
        else:
            topo_n = normalizar_topo(topo)
            if not RE_TOPO.fullmatch(topo_n):
                erro("TOPO_INVALIDO", f"{cam}.topo", f"Topo inválido: {topo!r} (esperado ex.: 171-60473-401/CD).")
            elif cfg_n and topo_n.rsplit("/", 1)[1] != cfg_n:
                erro("TOPO_CONFIG_DIVERGENTE", f"{cam}.topo",
                     f"Topo {topo_n} não corresponde à configuração {cfg_n}.")
            elif topos_base is not None and topo_n not in topos_base:
                aviso("TOPO_FORA_DA_BASE", f"{cam}.topo", f"Topo {topo_n} não aparece na base carregada.")
        n["topo"] = topo_n

        rev = d.get("revisao")
        rev_n = None
        if not isinstance(rev, str) or not rev.strip():
            erro("CAMPO_OBRIGATORIO", f"{cam}.revisao", "Revisão obrigatória.")
        else:
            rev_n = rev.strip().upper()
            if not RE_REVISAO.fullmatch(rev_n):
                erro("REVISAO_INVALIDA", f"{cam}.revisao", f"Revisão inválida: {rev!r}.")
        n["revisao"] = rev_n

        for campo in ("ativa", "vinculo_conferido"):
            v = d.get(campo, False)
            if not isinstance(v, bool):
                erro("TIPO_INVALIDO", f"{cam}.{campo}", f"{campo} deve ser true/false.")
                v = False
            n[campo] = v
        for campo in ("conferido_por", "conferido_em", "observacoes"):
            v = d.get(campo, "")
            if v is None:
                v = ""
            if not isinstance(v, str):
                erro("TIPO_INVALIDO", f"{cam}.{campo}", f"{campo} deve ser texto.")
                v = ""
            n[campo] = v

        origem = d.get("origem")
        if not isinstance(origem, dict):
            erro("ORIGEM_INVALIDA", f"{cam}.origem", "Origem do PDF obrigatória (local ou url).")
            n["origem"] = None
        elif origem.get("tipo") == "local":
            nome = origem.get("nome_arquivo")
            sha = origem.get("sha256", "")
            if not isinstance(nome, str) or not nome.strip().lower().endswith(".pdf"):
                erro("ORIGEM_INVALIDA", f"{cam}.origem.nome_arquivo", "Nome do arquivo PDF obrigatório (.pdf).")
            if sha not in ("", None) and (not isinstance(sha, str) or not RE_SHA256.fullmatch(sha.lower())):
                erro("ORIGEM_INVALIDA", f"{cam}.origem.sha256", "sha256 deve ter 64 caracteres hexadecimais.")
            n["origem"] = {"tipo": "local", "nome_arquivo": nome.strip() if isinstance(nome, str) else None,
                           "sha256": sha.lower() if isinstance(sha, str) and sha else ""}
        elif origem.get("tipo") == "url":
            url = origem.get("url")
            if not isinstance(url, str) or not url_https_valida(url.strip()):
                erro("ORIGEM_INVALIDA", f"{cam}.origem.url", "URL deve ser HTTPS.")
            n["origem"] = {"tipo": "url", "url": url.strip() if isinstance(url, str) else None}
        else:
            erro("ORIGEM_INVALIDA", f"{cam}.origem.tipo", "Tipo de origem deve ser 'local' ou 'url'.")
            n["origem"] = None

        total = d.get("total_paginas")
        if total is not None and (not _eh_inteiro(total) or total < 1):
            erro("PAGINA_INVALIDA", f"{cam}.total_paginas", "total_paginas deve ser inteiro positivo.")
            total = None
        n["total_paginas"] = int(total) if total is not None else None

        mapa = d.get("mapa_folhas")
        mapa_n: dict[str, int] = {}
        if not isinstance(mapa, dict):
            erro("CAMPO_OBRIGATORIO", f"{cam}.mapa_folhas", "mapa_folhas obrigatório (objeto {folha: página}).")
        else:
            paginas_vistas: dict[int, int] = {}
            for chave, pagina in mapa.items():
                cam_f = f"{cam}.mapa_folhas[{chave}]"
                if not isinstance(chave, str) or not re.fullmatch(r"\d+", chave.strip()) \
                        or not 1 <= int(chave) <= NUM_FOLHAS:
                    erro("FOLHA_INVALIDA", cam_f, f"Folha inválida: {chave!r} (1 a {NUM_FOLHAS}).")
                    continue
                folha = str(int(chave))
                if folha in mapa_n:
                    erro("FOLHA_DUPLICADA", cam_f, f"Folha {folha} mapeada mais de uma vez.")
                    continue
                if not _eh_inteiro(pagina) or pagina < 1:
                    erro("PAGINA_INVALIDA", cam_f, f"Página inválida para a folha {folha}: {pagina!r}.")
                    continue
                pagina = int(pagina)
                if n["total_paginas"] and pagina > n["total_paginas"]:
                    erro("PAGINA_INVALIDA", cam_f,
                         f"Página {pagina} da folha {folha} excede o total de {n['total_paginas']} páginas.")
                    continue
                if pagina in paginas_vistas:
                    aviso("PAGINA_REPETIDA", cam_f,
                          f"Página {pagina} usada pelas folhas {paginas_vistas[pagina]} e {folha}.")
                else:
                    paginas_vistas[pagina] = int(folha)
                mapa_n[folha] = pagina
            if not mapa:
                aviso("MAPA_VAZIO", f"{cam}.mapa_folhas", "Nenhuma folha mapeada.")
        n["mapa_folhas"] = dict(sorted(mapa_n.items(), key=lambda kv: int(kv[0])))

        if topo_n and rev_n:
            chave = (topo_n, rev_n)
            if chave in vistos:
                erro("DUPLICADO", cam, f"Topo {topo_n} revisão {rev_n} repetido (já em desenhos[{vistos[chave]}]).")
            else:
                vistos[chave] = i
        normalizados.append(n)

    por_topo: dict[str, list[dict]] = {}
    for n in normalizados:
        if n.get("topo"):
            por_topo.setdefault(n["topo"], []).append(n)
    for topo, lista in por_topo.items():
        ativas = [x for x in lista if x["ativa"]]
        if len(ativas) > 1:
            erro("MULTIPLAS_ATIVAS", topo, f"Topo {topo} tem {len(ativas)} revisões ativas; escolha uma.")
        elif not ativas:
            aviso("SEM_ATIVA", topo, f"Topo {topo} não tem revisão ativa.")

    manifesto = {"formato": FORMATO, "versao_formato": VERSAO_FORMATO,
                 "atualizado_em": obj.get("atualizado_em", "") if isinstance(obj.get("atualizado_em"), str) else "",
                 "desenhos": normalizados}
    return {"erros": erros, "avisos": avisos, "manifesto": manifesto}


def carregar_manifesto(caminho: Path, topos_base: Optional[set[str]] = None) -> dict:
    texto = Path(caminho).read_text(encoding="utf-8")
    obj, duplicadas = carregar_json_sem_duplicatas(texto)
    resultado = validar_manifesto(obj, topos_base)
    resultado["erros"] = duplicadas + resultado["erros"]
    return resultado


def verificar_pdfs(manifesto: dict, pasta: Path) -> list[dict]:
    """Confere PDFs locais (hash e número de páginas) numa pasta autorizada."""
    from pypdf import PdfReader

    problemas = []
    for i, d in enumerate(manifesto.get("desenhos", [])):
        origem = d.get("origem") or {}
        if origem.get("tipo") != "local" or not origem.get("nome_arquivo"):
            continue
        cam = f"desenhos[{i}]"
        arquivo = Path(pasta) / origem["nome_arquivo"]
        if not arquivo.is_file():
            problemas.append({"codigo": "PDF_NAO_ENCONTRADO", "caminho": cam,
                              "mensagem": f"{origem['nome_arquivo']} não encontrado em {pasta}."})
            continue
        conteudo = arquivo.read_bytes()
        sha = hashlib.sha256(conteudo).hexdigest()
        if origem.get("sha256") and origem["sha256"] != sha:
            problemas.append({"codigo": "PDF_HASH_DIVERGENTE", "caminho": cam,
                              "mensagem": f"{origem['nome_arquivo']}: sha256 diferente do manifesto."})
        paginas = len(PdfReader(arquivo).pages)
        if d.get("total_paginas") and d["total_paginas"] != paginas:
            problemas.append({"codigo": "TOTAL_PAGINAS_DIVERGENTE", "caminho": cam,
                              "mensagem": f"Manifesto diz {d['total_paginas']} páginas; PDF tem {paginas}."})
        for folha, pagina in d.get("mapa_folhas", {}).items():
            if pagina > paginas:
                problemas.append({"codigo": "PAGINA_FORA_DO_PDF", "caminho": f"{cam}.mapa_folhas[{folha}]",
                                  "mensagem": f"Folha {folha} -> página {pagina}, mas o PDF tem {paginas}."})
    return problemas
