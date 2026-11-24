import hashlib
import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures  # noqa: E402
from placards_cd import importar  # noqa: E402

ORIGEM = "https://desenhos.empresa.example"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture(scope="session")
def ambiente(tmp_path_factory):
    d = tmp_path_factory.mktemp("placards")
    planilha = fixtures.gerar_planilha(d / "PLANILHA_PLACARD CD.xlsx")
    pdf_a = fixtures.gerar_pdf(d / "desenho-sintetico-A.pdf", "A")
    pdf_b = fixtures.gerar_pdf(d / "desenho-sintetico-B.pdf", "B")
    manifesto = d / "manifesto.json"
    manifesto.write_text(json.dumps(fixtures.manifesto_sintetico(sha(pdf_a), sha(pdf_b)), ensure_ascii=False), encoding="utf-8")
    hash_antes = sha(planilha)
    saida = d / "dist"
    rc = importar.main(["--planilha", str(planilha), "--saida", str(saida), "--manifesto", str(manifesto),
                        "--origem-autorizada", ORIGEM])
    assert rc == 0
    base = json.loads((saida / "base_placards_cd.json").read_text(encoding="utf-8"))
    return {"dir": d, "planilha": planilha, "hash_antes": hash_antes, "pdf_a": pdf_a, "pdf_b": pdf_b,
            "manifesto": manifesto, "saida": saida, "base": base, "html": saida / "consulta-placards-cd.html"}


@pytest.fixture(scope="session")
def registros(ambiente):
    return ambiente["base"]["registros"]
