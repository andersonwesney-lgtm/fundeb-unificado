"""Monta o site da nova aba (pasta `site/`) a partir dos arquivos brutos já coletados.

A pasta só é publicada pelo workflow se este passo e os testes terminarem sem erro (publicação atômica do GitHub Pages).
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from . import __version__
from .coleta import agora
from .brasoes import montar as montar_brasoes
from .entes import colunar, construir

RAIZ = Path(__file__).resolve().parent.parent


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def gerar(brutos: Path, saida: Path, raiz: Path = RAIZ) -> dict:
    config = json.loads((raiz / "config" / "sistemas.json").read_text(encoding="utf-8"))
    ibge = json.loads((brutos / "ibge_municipios.json").read_bytes())
    siope_entes = json.loads((brutos / "siope_entes.json").read_bytes())
    siope_manifest = json.loads((brutos / "siope_manifest.json").read_bytes())
    painel = json.loads((raiz / "insumos" / "painel_fundeb2027_codigos.json").read_text(encoding="utf-8"))

    cad = construir(ibge, siope_entes, painel)

    if saida.exists():
        shutil.rmtree(saida)
    (saida / "dados").mkdir(parents=True)
    for f in ("index.html", "portal.js", "estilo.css"):
        shutil.copy2(raiz / "web" / f, saida / f)

    bcfg = config["brasoes"]
    resumo_brasoes = montar_brasoes(raiz / bcfg["pasta"], cad, bcfg["publicar"], saida / "dados" / "brasoes")
    resumo_brasoes["descricao"] = bcfg["descricao"]
    resumo_brasoes["aviso_licenca"] = bcfg["aviso_licenca"]

    entes_b = json.dumps(colunar(cad), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    (saida / "dados" / "entes.json").write_bytes(entes_b)

    fontes = []
    for nome in ("ibge_municipios", "siope_entes", "siope_manifest"):
        m = json.loads((brutos / f"{nome}.meta.json").read_text(encoding="utf-8"))
        m["descricao"] = config["fontes"][nome]["descricao"]
        fontes.append(m)
    fontes.append({"nome": "painel_fundeb2027_codigos", "descricao": painel["descricao"],
                   "sha256": painel["sha256"], "verificado_em": painel["verificado_em"],
                   "arquivo": "insumos/painel_fundeb2027_codigos.json"})

    exercicios = [e["ano"] for e in siope_manifest["exercicios"]]
    sistemas = json.loads(json.dumps(config["sistemas"], ensure_ascii=False).replace("{exercicios}", " e ".join(map(str, exercicios))))
    contagem = {}
    for e in cad:
        contagem[e["tipo"]] = contagem.get(e["tipo"], 0) + 1
    manifest = {
        "gerado_em": agora(), "versao": __version__, "portal": config["portal"], "sistemas": sistemas,
        "siope": {"exercicios": exercicios, "gerado_em": siope_manifest.get("gerado_em"),
                  "data_referencia": siope_manifest.get("data_referencia")},
        "entes": {"arquivo": "dados/entes.json", "sha256": _sha(entes_b), "total": len(cad), "por_tipo": contagem},
        "fontes": fontes,
        "brasoes": resumo_brasoes,
    }
    (saida / "dados" / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    (saida / ".nojekyll").write_text("", encoding="utf-8")
    return manifest
