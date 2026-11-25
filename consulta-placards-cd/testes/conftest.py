import hashlib
import shutil
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
ADM = RAIZ / "pasta-modelo" / "_adm"
sys.path.insert(0, str(ADM))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures  # noqa: E402
from placards_cd import publicar  # noqa: E402


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def montar_pasta(destino: Path, com_desenhos=True) -> Path:
    """Simula a pasta compartilhada: planilha, desenhos/ e _adm/ (cópia da pasta modelo)."""
    shutil.copytree(ADM, destino / "_adm", ignore=shutil.ignore_patterns("__pycache__"))
    fixtures.gerar_planilha(destino / "PLANILHA_PLACARD CD.xlsx")
    d = destino / "desenhos"
    (d / "metálico").mkdir(parents=True)
    if com_desenhos:
        fixtures.gerar_pdf(d / "171-50557-021.pdf")
        fixtures.gerar_pdf(d / "metálico" / "171-60555-001.pdf")
        fixtures.gerar_pdf(d / "CDPL568-201.pdf")          # placard sem PN novo: PDF pelo CDPL
        fixtures.gerar_pdf(d / "999-ORFAO-001.pdf")        # PDF sem placard
    return destino


@pytest.fixture(scope="session")
def pasta(tmp_path_factory):
    p = montar_pasta(tmp_path_factory.mktemp("rede") / "Placards CD")
    hash_antes = sha(p / "PLANILHA_PLACARD CD.xlsx")
    cfg, base = publicar.carregar_config(p / "_adm" / "config.json")
    res = publicar.publicar(cfg, base)
    return {"dir": p, "res": res, "hash_antes": hash_antes, "html": p / "Consulta de Placards.html"}


@pytest.fixture(scope="session")
def registros(pasta):
    return pasta["res"]["registros"]
