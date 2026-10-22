"""Brasões dos entes no cadastro único (mesmo acervo e mesmas miniaturas do painel Fundeb 2027).

Insumos (pasta `insumos/brasoes/`):
  * `brasoes_catalogo.csv`  — catálogo do acervo de brasões da Tech Play Edu (uma linha por município IBGE), com
    arquivo, página de origem, Wikidata, autor, licença, crédito, observações e SHA-256 da imagem original;
  * `pacote_<UF>.json`      — miniaturas (160 px, data URL) por UF, chave = código IBGE de 7 dígitos. São os mesmos
    pacotes publicados no painel Fundeb 2027, gerados pelo `pidemanda` a partir do acervo.

Política de publicação (config `brasoes.publicar`):
  * "todos"                 — publica toda imagem do acervo, com a licença declarada ao lado;
  * "licenca_identificada"  — publica só imagens com licença livre identificada (domínio público, CC0, CC BY, CC BY-SA);
  * "nenhum"                — não publica imagens; o cartão mostra apenas a procedência.
Nenhuma imagem é gerada ou inventada: sem registro no acervo, o portal mostra um espaço reservado identificado.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

LICENCAS_LIVRES = ("public domain", "cc0", "cc by-sa", "cc by ")
CAMPOS = ["arquivo", "fonte", "wikidata", "autor", "licenca", "licenca_url", "credito", "observacoes", "sha256", "coleta"]


class ErroBrasoes(RuntimeError):
    """Inconsistência entre catálogo, pacotes e cadastro: a publicação não deve prosseguir."""


def licenca_livre(lic: str) -> bool:
    l = (lic or "").strip().lower() + " "
    return any(l.startswith(x) for x in LICENCAS_LIVRES)


def ler_catalogo(caminho: Path) -> dict[str, dict]:
    txt = caminho.read_bytes().decode("utf-8-sig")
    linhas = list(csv.DictReader(io.StringIO(txt), delimiter=";"))
    if not linhas or "codigo_ibge" not in linhas[0] or "licenca" not in linhas[0]:
        raise ErroBrasoes(f"{caminho.name}: colunas esperadas (codigo_ibge, licenca, ...) não encontradas.")
    return {r["codigo_ibge"].strip(): r for r in linhas}


def montar(pasta: Path, cadastro: list[dict], politica: str, destino: Path) -> dict:
    """Valida catálogo × pacotes × cadastro, grava `destino/indice_<UF>.json` e os pacotes publicados. Devolve o resumo."""
    if politica not in ("todos", "licenca_identificada", "nenhum"):
        raise ErroBrasoes(f"Política de brasões desconhecida: {politica!r}")
    cat_arq = pasta / "brasoes_catalogo.csv"
    cat = ler_catalogo(cat_arq)
    ibge = {e["ibge7"]: e for e in cadastro if e.get("ibge7")}
    erros = []
    fora = sorted(set(cat) - set(ibge))
    if fora:
        erros.append(f"catálogo com códigos fora do IBGE: {fora[:10]}")
    baixados = {c for c, r in cat.items() if r.get("status") == "baixado"}

    pacotes: dict[str, dict] = {}
    sha_pacotes = {}
    for p in sorted(pasta.glob("pacote_*.json")):
        b = p.read_bytes()
        try:
            pacotes[p.stem.split("_", 1)[1]] = json.loads(b)
        except ValueError as e:
            raise ErroBrasoes(f"{p.name} não é JSON válido: {e}") from e
        sha_pacotes[p.name] = hashlib.sha256(b).hexdigest()
    no_pacote = {}
    for uf, d in pacotes.items():
        for cod, url in d.items():
            if cod in no_pacote:
                erros.append(f"código {cod} em mais de um pacote")
            if not str(url).startswith("data:image/"):
                erros.append(f"{cod}: miniatura não é data URL de imagem")
            if cod in ibge and ibge[cod]["uf"] != uf:
                erros.append(f"{cod} no pacote {uf}, mas o IBGE diz {ibge[cod]['uf']}")
            no_pacote[cod] = uf
    # Os pacotes de insumo contêm só o que a política permite publicar (o repositório é público):
    # "todos" exige todas as imagens baixadas; "licenca_identificada" exige exatamente as de licença livre.
    sem_registro = set(no_pacote) - baixados
    if sem_registro:
        erros.append(f"pacotes × catálogo divergentes: {len(sem_registro)} miniaturas sem registro 'baixado' ({sorted(sem_registro)[:5]})")
    if politica == "todos":
        esperado = baixados
    elif politica == "licenca_identificada":
        esperado = {c for c in baixados if licenca_livre(cat[c].get("licenca", ""))}
    else:
        esperado = set()
    if politica != "nenhum" and set(no_pacote) != esperado:
        erros.append(f"pacotes × catálogo divergentes para a política {politica!r}: {len(esperado - set(no_pacote))} imagens "
                     f"esperadas sem miniatura e {len(set(no_pacote) - esperado)} miniaturas que a política não permite")
    if erros:
        raise ErroBrasoes("Acervo de brasões inconsistente:\n  - " + "\n  - ".join(erros[:30]))

    def publicar(cod: str) -> bool:
        if politica == "nenhum" or cod not in no_pacote:
            return False
        return politica == "todos" or licenca_livre(cat[cod].get("licenca", ""))

    destino.mkdir(parents=True, exist_ok=True)
    indice = {}
    for cod, r in cat.items():
        reg = {k: (r.get(k) or "").strip() for k in CAMPOS}
        reg["status"] = r.get("status", "")
        reg["livre"] = licenca_livre(reg["licenca"])
        reg["publicado"] = publicar(cod)
        reg["pacote"] = no_pacote.get(cod) if reg["publicado"] else None
        indice[cod] = reg
    # o governo do Distrito Federal usa o registro de Brasília (5300108), único brasão do DF no acervo
    if "5300108" in indice:
        indice["UF-DF"] = dict(indice["5300108"], imagem="5300108", observacoes=("Imagem do registro Brasília (5300108) do acervo. " +
                                                               indice["5300108"]["observacoes"]).strip())
    publicados = {uf: {c: u for c, u in d.items() if publicar(c)} for uf, d in pacotes.items()}
    sha_pub = {}
    for uf, d in publicados.items():
        if not d:
            continue
        b = json.dumps(d, separators=(",", ":")).encode("utf-8")
        (destino / f"pacote_{uf}.json").write_bytes(b)
        sha_pub[f"pacote_{uf}.json"] = hashlib.sha256(b).hexdigest()
    # índice de procedência por UF (carregado sob demanda, junto com o pacote de miniaturas da UF)
    por_uf: dict[str, dict] = {}
    for cod, reg in indice.items():
        uf = "DF" if cod == "UF-DF" else (ibge[cod]["uf"] if cod in ibge else None)
        if uf:
            por_uf.setdefault(uf, {})[cod] = reg
    sha_ind = {}
    for uf, d in sorted(por_uf.items()):
        b = json.dumps(d, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        (destino / f"indice_{uf}.json").write_bytes(b)
        sha_ind[f"indice_{uf}.json"] = hashlib.sha256(b).hexdigest()
    contagem_lic = {"livre": sum(1 for c in baixados if licenca_livre(cat[c]["licenca"]))}
    contagem_lic["a_verificar"] = len(baixados) - contagem_lic["livre"]
    return {
        "politica": politica,
        "catalogo": {"arquivo": "insumos/brasoes/brasoes_catalogo.csv", "sha256": hashlib.sha256(cat_arq.read_bytes()).hexdigest(),
                     "registros": len(cat), "com_imagem": len(baixados)},
        "licencas_das_imagens": contagem_lic,
        "pacotes_insumo_sha256": sha_pacotes,
        "publicados": sum(len(d) for d in publicados.values()),
        "indices_sha256": sha_ind,
        "pacotes_publicados_sha256": sha_pub,
    }
