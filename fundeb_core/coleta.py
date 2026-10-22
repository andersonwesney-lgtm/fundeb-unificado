"""Coleta das fontes externas: grava o arquivo bruto, o SHA-256 e os metadados; falha com mensagem clara.

Nada é publicado a partir de um arquivo incompleto: o JSON é validado antes de ser gravado em `brutos/`.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = "fundeb-unificado/1.0 (portal de acompanhamento do Fundeb; github.com/andersonwesney-lgtm)"


class ErroColeta(RuntimeError):
    """A fonte não respondeu ou respondeu algo inválido. A publicação deve parar."""


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def baixar(url: str, tentativas: int = 4, timeout: int = 60) -> bytes:
    if url.startswith("file:"):
        tentativas = 1
    ultimo = None
    for i in range(1, tentativas + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if getattr(r, "status", None) not in (200, None):  # file:// (testes) não tem status
                    raise ErroColeta(f"HTTP {r.status}")
                b = r.read()
            # alguns servidores (ex.: API do IBGE) mandam gzip mesmo sem pedido; o bruto gravado é o conteúdo descomprimido
            if b[:2] == b"\x1f\x8b":
                b = gzip.decompress(b)
            return b
        except Exception as e:  # noqa: BLE001
            ultimo = e
            if i < tentativas:
                time.sleep(5 * i)
    raise ErroColeta(f"Falha ao baixar {url} após {tentativas} tentativas: {ultimo}")


def coletar_json(nome: str, url: str, pasta: Path, checar=None) -> dict:
    """Baixa, valida (JSON e, se houver, `checar(obj)`), grava bruto + metadados e devolve os metadados."""
    b = baixar(url)
    try:
        obj = json.loads(b)
    except ValueError as e:
        raise ErroColeta(f"{nome}: a resposta de {url} não é JSON válido ({e}). Início: {b[:200]!r}") from e
    if checar:
        problema = checar(obj)
        if problema:
            raise ErroColeta(f"{nome}: conteúdo inesperado em {url}: {problema}")
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / f"{nome}.json").write_bytes(b)
    meta = {"nome": nome, "url": url, "coletado_em": agora(), "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
    (pasta / f"{nome}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


def _checar_ibge(o):
    if not isinstance(o, list) or len(o) < 5500:
        return f"esperada lista com ~5.570 municípios, veio {type(o).__name__} com {len(o) if hasattr(o, '__len__') else '?'} itens"
    return None


def _checar_siope_entes(o):
    if not isinstance(o, dict) or o.get("colunas", [])[:5] != ["id", "nome", "uf", "regiao", "esfera"]:
        return "formato do entes.json do painel SIOPE mudou (colunas id, nome, uf, regiao, esfera)"
    if len(o.get("linhas", [])) < 5500:
        return f"poucas linhas ({len(o.get('linhas', []))})"
    return None


def _checar_siope_manifest(o):
    if not isinstance(o, dict) or not isinstance(o.get("exercicios"), list) or not o["exercicios"]:
        return "manifesto do painel SIOPE sem a lista de exercícios"
    return None


CHECAGENS = {"ibge_municipios": _checar_ibge, "siope_entes": _checar_siope_entes, "siope_manifest": _checar_siope_manifest}


def coletar_tudo(config: dict, pasta: Path) -> list[dict]:
    metas = []
    for nome, f in config["fontes"].items():
        metas.append(coletar_json(nome, f["url"], pasta, CHECAGENS.get(nome)))
    return metas
