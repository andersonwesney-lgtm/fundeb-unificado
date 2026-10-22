"""Cadastro único de entes do Fundeb (Fase 1).

Chave canônica (`id`):
  * município: código IBGE de 7 dígitos (ex.: "2700300");
  * governo estadual e Distrito Federal: "UF-<sigla>" (ex.: "UF-AL", "UF-DF"), como no SIOPE.

Para cada ente o cadastro guarda o identificador usado em cada sistema:
  * `id_siope`  : SIOPE / painel SIOPE e Fundeb — município com 6 dígitos (IBGE sem o dígito verificador); estado "UF-XX";
  * `id_fundeb` : painel "Fundeb 2027 em números" — município com 7 dígitos; rede estadual com o código IBGE da UF (2 dígitos).

Casos especiais conferidos em 21/10/2026 contra as três fontes:
  * Brasília (5300108): o DF acumula competências estaduais e municipais (CF, art. 32, § 1º). No Fundeb e no SIOPE ele é um
    único ente, "UF-DF"; o código 5300108 fica no cadastro como município do IBGE apontando para "UF-DF".
  * Fernando de Noronha (2605459): distrito estadual de Pernambuco que o IBGE lista entre os municípios. O SIOPE o traz como
    ente municipal (260545); o painel Fundeb 2027 não o tem como rede própria.

Nenhum valor financeiro é calculado neste módulo.
"""
from __future__ import annotations

UFS = {  # código IBGE da UF: (sigla, nome, região)
    "11": ("RO", "Rondônia", "Norte"), "12": ("AC", "Acre", "Norte"), "13": ("AM", "Amazonas", "Norte"),
    "14": ("RR", "Roraima", "Norte"), "15": ("PA", "Pará", "Norte"), "16": ("AP", "Amapá", "Norte"),
    "17": ("TO", "Tocantins", "Norte"), "21": ("MA", "Maranhão", "Nordeste"), "22": ("PI", "Piauí", "Nordeste"),
    "23": ("CE", "Ceará", "Nordeste"), "24": ("RN", "Rio Grande do Norte", "Nordeste"), "25": ("PB", "Paraíba", "Nordeste"),
    "26": ("PE", "Pernambuco", "Nordeste"), "27": ("AL", "Alagoas", "Nordeste"), "28": ("SE", "Sergipe", "Nordeste"),
    "29": ("BA", "Bahia", "Nordeste"), "31": ("MG", "Minas Gerais", "Sudeste"), "32": ("ES", "Espírito Santo", "Sudeste"),
    "33": ("RJ", "Rio de Janeiro", "Sudeste"), "35": ("SP", "São Paulo", "Sudeste"), "41": ("PR", "Paraná", "Sul"),
    "42": ("SC", "Santa Catarina", "Sul"), "43": ("RS", "Rio Grande do Sul", "Sul"),
    "50": ("MS", "Mato Grosso do Sul", "Centro-Oeste"), "51": ("MT", "Mato Grosso", "Centro-Oeste"),
    "52": ("GO", "Goiás", "Centro-Oeste"), "53": ("DF", "Distrito Federal", "Centro-Oeste"),
}
SIGLA_PARA_COD = {v[0]: k for k, v in UFS.items()}
BRASILIA = "5300108"
NORONHA = "2605459"


class ErroCadastro(RuntimeError):
    """Falha de consistência do cadastro: a publicação não deve prosseguir."""


def _uf_do_municipio_ibge(m: dict) -> str:
    """Sigla da UF de um registro da API de Localidades do IBGE (há municípios novos sem microrregião, ex. 5101837)."""
    for caminho in (("microrregiao", "mesorregiao", "UF"), ("regiao-imediata", "regiao-intermediaria", "UF")):
        x = m
        for k in caminho:
            x = (x or {}).get(k)
        if x and x.get("sigla"):
            return x["sigla"]
    raise ErroCadastro(f"Município IBGE {m.get('id')} sem UF identificável no arquivo do IBGE.")


def construir(ibge: list[dict], siope_entes: dict, painel_fundeb: dict) -> list[dict]:
    """Monta o cadastro a partir das três fontes e valida a correspondência. Levanta ErroCadastro em qualquer divergência."""
    erros: list[str] = []
    mun_ibge: dict[str, tuple[str, str]] = {}
    for m in ibge:
        cod = str(m["id"])
        if len(cod) != 7 or not cod.isdigit():
            erros.append(f"IBGE: código de município inválido {cod!r}")
            continue
        uf = _uf_do_municipio_ibge(m)
        if SIGLA_PARA_COD.get(uf) != cod[:2]:
            erros.append(f"IBGE: {cod} ({m.get('nome')}) com UF {uf} incompatível com o prefixo {cod[:2]}")
        mun_ibge[cod] = (m["nome"], uf)
    seis = {c[:6]: c for c in mun_ibge}
    if len(seis) != len(mun_ibge):
        erros.append("IBGE: há municípios com os mesmos 6 primeiros dígitos; o identificador do SIOPE ficaria ambíguo")

    col = siope_entes["colunas"]
    i_id, i_nome, i_uf, i_esf = (col.index(x) for x in ("id", "nome", "uf", "esfera"))
    siope_mun: dict[str, str] = {}
    siope_est: set[str] = set()
    for r in siope_entes["linhas"]:
        sid = str(r[i_id])
        if r[i_esf] == "estadual":
            siope_est.add(sid)
            if sid != f"UF-{r[i_uf]}":
                erros.append(f"SIOPE: ente estadual com identificador inesperado {sid!r}")
            continue
        cod7 = seis.get(sid)
        if cod7 is None:
            erros.append(f"SIOPE: ente municipal {sid} ({r[i_nome]}/{r[i_uf]}) não encontrado no IBGE")
            continue
        if mun_ibge[cod7][1] != r[i_uf]:
            erros.append(f"SIOPE: {sid} na UF {r[i_uf]}, IBGE diz {mun_ibge[cod7][1]}")
        if mun_ibge[cod7][0] != r[i_nome]:
            erros.append(f"SIOPE: nome divergente para {sid}: {r[i_nome]!r} × IBGE {mun_ibge[cod7][0]!r}")
        siope_mun[cod7] = sid
    if siope_est != {f"UF-{v[0]}" for v in UFS.values()}:
        erros.append(f"SIOPE: governos estaduais divergentes das 27 UFs: {sorted(siope_est ^ {f'UF-{v[0]}' for v in UFS.values()})}")

    pf_ausentes = set(painel_fundeb["ibge_ausentes_no_painel"])
    if painel_fundeb.get("painel_fora_do_ibge"):
        erros.append(f"Painel Fundeb 2027: códigos fora do IBGE {painel_fundeb['painel_fora_do_ibge']}")
    if sorted(painel_fundeb["codigos_estaduais"]) != sorted(UFS):
        erros.append("Painel Fundeb 2027: códigos das redes estaduais diferentes dos 27 códigos de UF")
    if painel_fundeb["municipios"] != len(mun_ibge) - len(pf_ausentes):
        erros.append(f"Painel Fundeb 2027: {painel_fundeb['municipios']} municípios, mas o IBGE atual tem {len(mun_ibge)} "
                     f"menos {len(pf_ausentes)} ausentes conhecidos (a lista do IBGE mudou: rever a verificação do painel)")

    if erros:
        raise ErroCadastro("Cadastro de entes inconsistente:\n  - " + "\n  - ".join(erros[:50]))

    cad: list[dict] = []
    for cuf, (sg, nome_uf, reg) in sorted(UFS.items()):
        cad.append({"id": f"UF-{sg}", "tipo": "estadual" if sg != "DF" else "distrital", "nome": f"{nome_uf} (governo {'distrital' if sg == 'DF' else 'estadual'})",
                    "uf": sg, "cod_uf": cuf, "regiao": reg, "ibge7": None,
                    "id_siope": f"UF-{sg}", "id_fundeb": cuf, "obs": ""})
    for cod7, (nome, sg) in sorted(mun_ibge.items()):
        obs = ""
        if cod7 == BRASILIA:
            obs = ("O Distrito Federal é um único ente no Fundeb e no SIOPE (CF, art. 32, § 1º): use o governo distrital (UF-DF).")
        elif cod7 == NORONHA:
            obs = ("Distrito estadual de Pernambuco. O SIOPE traz declarações próprias (260545); no painel Fundeb 2027 as "
                   "matrículas estão na rede estadual de PE.")
        cad.append({"id": cod7, "tipo": "municipal" if cod7 not in (BRASILIA, NORONHA) else
                    ("referencia_df" if cod7 == BRASILIA else "distrito_estadual"),
                    "nome": nome, "uf": sg, "cod_uf": cod7[:2], "regiao": UFS[cod7[:2]][2], "ibge7": cod7,
                    "id_siope": siope_mun.get(cod7) or ("UF-DF" if cod7 == BRASILIA else None),
                    "id_fundeb": None if cod7 in pf_ausentes else cod7,
                    "obs": obs, "aponta_para": "UF-DF" if cod7 == BRASILIA else None})
    validar(cad)
    return cad


def validar(cad: list[dict]) -> None:
    """Invariantes do cadastro publicado."""
    ids = [e["id"] for e in cad]
    if len(ids) != len(set(ids)):
        raise ErroCadastro("Cadastro com identificadores repetidos.")
    sio = [e["id_siope"] for e in cad if e["id_siope"] and e["tipo"] != "referencia_df"]
    if len(sio) != len(set(sio)):
        raise ErroCadastro("Dois entes do cadastro apontam para o mesmo identificador do SIOPE.")
    fun = [e["id_fundeb"] for e in cad if e["id_fundeb"]]
    if len(fun) != len(set(fun)):
        raise ErroCadastro("Dois entes do cadastro apontam para o mesmo código do painel Fundeb 2027.")
    for e in cad:
        if e["tipo"] == "municipal" and (not e["id_siope"] or not e["id_fundeb"]):
            raise ErroCadastro(f"Município {e['id']} ({e['nome']}/{e['uf']}) sem correspondência em algum sistema.")


def normalizar_parametro(valor: str, cad_por_id: dict[str, dict]) -> str | None:
    """Converte o que vier em ?ente= (id canônico, IBGE 7, SIOPE 6, sigla ou código de UF) para o id canônico."""
    v = (valor or "").strip().upper()
    if not v:
        return None
    if v in cad_por_id:
        return v
    if v.startswith("UF-") and v in cad_por_id:
        return v
    if len(v) == 2 and v in SIGLA_PARA_COD:
        return f"UF-{v}"
    if len(v) == 2 and v in UFS:
        return f"UF-{UFS[v][0]}"
    if len(v) == 6 and v.isdigit():
        for e in cad_por_id.values():
            if e.get("id_siope") == v:
                return e["id"]
    return None


def colunar(cad: list[dict]) -> dict:
    """Formato colunar (como o do painel SIOPE) para o arquivo publicado."""
    colunas = ["id", "tipo", "nome", "uf", "cod_uf", "regiao", "ibge7", "id_siope", "id_fundeb", "aponta_para", "obs"]
    return {"colunas": colunas, "linhas": [[e.get(c) for c in colunas] for e in cad]}
