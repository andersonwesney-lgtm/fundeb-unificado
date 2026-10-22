"""Testes do cadastro único de entes e do site da Fase 1.

Os testes sintéticos reproduzem a estrutura das três fontes; os testes com dados reais rodam quando `brutos/` existe
(no GitHub Actions, depois do passo de coleta).
"""
import copy
import json
import re
from pathlib import Path

import pytest

from fundeb_core import entes
from fundeb_core.gerar import gerar

RAIZ = Path(__file__).resolve().parent.parent
BRUTOS = RAIZ / "brutos"


def _ibge(cod, nome, uf, com_micro=True):
    ufj = {"sigla": uf}
    r = {"id": int(cod), "nome": nome, "regiao-imediata": {"regiao-intermediaria": {"UF": ufj}}}
    r["microrregiao"] = {"mesorregiao": {"UF": ufj}} if com_micro else None
    return r


def _sintetico():
    ibge = [_ibge("2700300", "Arapiraca", "AL"), _ibge("2704302", "Maceió", "AL"),
            _ibge("5300108", "Brasília", "DF"), _ibge("2605459", "Fernando de Noronha", "PE"),
            _ibge("5101837", "Boa Esperança do Norte", "MT", com_micro=False)]
    siope = {"colunas": ["id", "nome", "uf", "regiao", "esfera", "pop"],
             "linhas": [[f"UF-{v[0]}", v[1], v[0], v[2], "estadual", 1] for v in entes.UFS.values()] +
                       [["270030", "Arapiraca", "AL", "Nordeste", "municipal", 1], ["270430", "Maceió", "AL", "Nordeste", "municipal", 1],
                        ["260545", "Fernando de Noronha", "PE", "Nordeste", "municipal", 1],
                        ["510183", "Boa Esperança do Norte", "MT", "Centro-Oeste", "municipal", 1]]}
    painel = {"municipios": 3, "ibge_ausentes_no_painel": ["2605459", "5300108"], "painel_fora_do_ibge": [],
              "codigos_estaduais": sorted(entes.UFS)}
    return ibge, siope, painel


def test_cadastro_sintetico_e_casos_especiais():
    cad = entes.construir(*_sintetico())
    por = {e["id"]: e for e in cad}
    assert len(cad) == 27 + 5
    assert por["2700300"]["id_siope"] == "270030" and por["2700300"]["id_fundeb"] == "2700300"
    assert por["UF-AL"]["id_siope"] == "UF-AL" and por["UF-AL"]["id_fundeb"] == "27"
    assert por["UF-DF"]["tipo"] == "distrital" and por["UF-DF"]["id_fundeb"] == "53"
    # Brasília aponta para o governo distrital; não vira um ente próprio do Fundeb
    assert por["5300108"]["tipo"] == "referencia_df" and por["5300108"]["aponta_para"] == "UF-DF"
    assert por["5300108"]["id_fundeb"] is None
    # Fernando de Noronha: tem SIOPE próprio, não tem rede no painel Fundeb 2027
    assert por["2605459"]["tipo"] == "distrito_estadual"
    assert por["2605459"]["id_siope"] == "260545" and por["2605459"]["id_fundeb"] is None
    assert por["5101837"]["uf"] == "MT"   # município novo sem microrregião no IBGE


def test_falha_quando_siope_tem_ente_fora_do_ibge():
    ibge, siope, painel = _sintetico()
    siope = copy.deepcopy(siope)
    siope["linhas"].append(["999999", "Inexistente", "AL", "Nordeste", "municipal", 1])
    with pytest.raises(entes.ErroCadastro, match="999999"):
        entes.construir(ibge, siope, painel)


def test_falha_quando_nome_diverge():
    ibge, siope, painel = _sintetico()
    siope = copy.deepcopy(siope)
    siope["linhas"][-1][1] = "Boa Esperanca"
    with pytest.raises(entes.ErroCadastro, match="nome divergente"):
        entes.construir(ibge, siope, painel)


def test_falha_quando_municipio_novo_nao_esta_nos_sistemas():
    ibge, siope, painel = _sintetico()
    ibge = ibge + [_ibge("2799999", "Novo Município", "AL")]
    with pytest.raises(entes.ErroCadastro):
        entes.construir(ibge, siope, painel)


def test_normalizar_parametro():
    cad = entes.construir(*_sintetico())
    por = {e["id"]: e for e in cad}
    assert entes.normalizar_parametro("2700300", por) == "2700300"
    assert entes.normalizar_parametro("270030", por) == "2700300"
    assert entes.normalizar_parametro("al", por) == "UF-AL"
    assert entes.normalizar_parametro("27", por) == "UF-AL"
    assert entes.normalizar_parametro("uf-df", por) == "UF-DF"
    assert entes.normalizar_parametro("123", por) is None


@pytest.mark.skipif(not (BRUTOS / "ibge_municipios.json").exists(), reason="sem dados coletados")
def test_dados_reais_e_site(tmp_path):
    m = gerar(BRUTOS, tmp_path / "site")
    assert m["entes"]["por_tipo"]["municipal"] == 5569
    assert m["entes"]["por_tipo"]["estadual"] == 26 and m["entes"]["por_tipo"]["distrital"] == 1
    cad = json.loads((tmp_path / "site" / "dados" / "entes.json").read_text(encoding="utf-8"))
    linhas = [dict(zip(cad["colunas"], l)) for l in cad["linhas"]]
    # bijeção com o SIOPE: 5.570 municipais + 27 estaduais = 5.597 entes, como no painel SIOPE
    ids_siope = {e["id_siope"] for e in linhas if e["id_siope"] and e["tipo"] != "referencia_df"}
    assert len(ids_siope) == 5597
    # bijeção com o painel Fundeb 2027: 5.569 municípios + 27 redes estaduais
    assert len({e["id_fundeb"] for e in linhas if e["id_fundeb"]}) == 5596
    # o site não carrega nada de fora (scripts, folhas de estilo, fontes)
    for f in ("index.html", "portal.js", "estilo.css"):
        txt = (tmp_path / "site" / f).read_text(encoding="utf-8")
        assert not re.search(r'(src|href)\s*=\s*"https?://', txt), f
        assert "@import" not in txt and "fonts.googleapis" not in txt
    # brasões: mesmas 5.487 imagens do acervo e do painel Fundeb 2027, cada uma com procedência
    assert m["brasoes"]["catalogo"]["com_imagem"] == 5487
    if m["brasoes"]["politica"] == "licenca_identificada":
        assert m["brasoes"]["publicados"] == m["brasoes"]["licencas_das_imagens"]["livre"]
    al = json.loads((tmp_path / "site" / "dados" / "brasoes" / "indice_AL.json").read_text(encoding="utf-8"))
    assert al["2700300"]["status"] == "baixado" and al["2700300"]["licenca"]
    assert "UF-DF" in json.loads((tmp_path / "site" / "dados" / "brasoes" / "indice_DF.json").read_text(encoding="utf-8"))
    # nenhum conteúdo de consultoria/oportunidades na nova aba
    tudo = " ".join(p.read_text(encoding="utf-8", errors="ignore") for p in (tmp_path / "site").rglob("*")
                    if p.is_file() and not p.name.startswith("pacote_"))
    # (marcadores da aba do painel Fundeb 2027; "consultoria" pode aparecer legitimamente como autor de um brasão)
    for marca in ("consultoria.json", "oportunidades de consultoria", "oportunidades_fundeb", "t-cons"):
        assert marca not in tudo.lower(), marca


def test_config_sistemas_tem_fonte_e_periodo():
    cfg = json.loads((RAIZ / "config" / "sistemas.json").read_text(encoding="utf-8"))
    for s in cfg["sistemas"]:
        for k in ("nome", "pergunta", "url", "referencia", "periodo", "atualizacao"):
            assert s.get(k), (s["id"], k)


def test_coleta_grava_bruto_com_hash_e_falha_com_mensagem(tmp_path):
    import hashlib
    from fundeb_core import coleta
    ok = tmp_path / "ok.json"
    ok.write_text(json.dumps({"exercicios": [{"ano": 2026}]}), encoding="utf-8")
    meta = coleta.coletar_json("siope_manifest", ok.as_uri(), tmp_path / "brutos", coleta.CHECAGENS["siope_manifest"])
    assert meta["sha256"] == hashlib.sha256(ok.read_bytes()).hexdigest()
    assert (tmp_path / "brutos" / "siope_manifest.json").read_bytes() == ok.read_bytes()
    ruim = tmp_path / "ruim.json"
    ruim.write_text("<html>manutenção</html>", encoding="utf-8")
    with pytest.raises(coleta.ErroColeta, match="não é JSON"):
        coleta.coletar_json("x", ruim.as_uri(), tmp_path / "b2")
    formato = tmp_path / "formato.json"
    formato.write_text(json.dumps({"colunas": ["codigo"], "linhas": []}), encoding="utf-8")
    with pytest.raises(coleta.ErroColeta, match="formato"):
        coleta.coletar_json("siope_entes", formato.as_uri(), tmp_path / "b3", coleta.CHECAGENS["siope_entes"])
    assert not (tmp_path / "b3" / "siope_entes.json").exists()   # nada é gravado quando a validação falha
    # resposta em gzip sem ter sido pedida (caso real da API do IBGE): descomprime e grava o JSON
    import gzip
    gz = tmp_path / "gz.json"
    gz.write_bytes(gzip.compress(ok.read_bytes()))
    meta = coleta.coletar_json("siope_manifest", gz.as_uri(), tmp_path / "b4", coleta.CHECAGENS["siope_manifest"])
    assert (tmp_path / "b4" / "siope_manifest.json").read_bytes() == ok.read_bytes()
    assert meta["sha256"] == hashlib.sha256(ok.read_bytes()).hexdigest()


# ---------------------------------------------------------------- brasões
def _acervo(pasta, licenca_arapiraca="Public domain"):
    from fundeb_core import brasoes  # noqa: F401
    pasta.mkdir(parents=True, exist_ok=True)
    cab = ["codigo_ibge", "municipio", "uf", "estado", "arquivo", "url", "fonte", "wikidata", "status", "pasta",
           "fonte_repositorio", "autor", "licenca", "licenca_url", "credito", "observacoes", "sha256", "coleta", "largura", "altura"]
    def lin(cod, nome, uf, status, lic):
        d = dict.fromkeys(cab, "")
        d.update(codigo_ibge=cod, municipio=nome, uf=uf, status=status, licenca=lic, arquivo=f"imagens/{uf}/{nome}/b.png",
                 fonte="https://commons.wikimedia.org/wiki/File:X.svg", sha256="ab" * 32, coleta="2026-10-20")
        return ";".join(f'"{d[c]}"' for c in cab)
    linhas = [";".join(f'"{c}"' for c in cab),
              lin("2700300", "Arapiraca", "AL", "baixado", licenca_arapiraca),
              lin("2704302", "Maceió", "AL", "baixado", "Consultar a página de origem"),
              lin("5300108", "Brasília", "DF", "baixado", "CC BY-SA 4.0"),
              lin("2605459", "Fernando de Noronha", "PE", "sem_imagem_na_fonte", ""),
              lin("5101837", "Boa Esperança do Norte", "MT", "sem_imagem_na_fonte", "")]
    (pasta / "brasoes_catalogo.csv").write_text("﻿" + "\n".join(linhas), encoding="utf-8")
    png = "data:image/png;base64,iVBORw0KGgo="
    (pasta / "pacote_AL.json").write_text(json.dumps({"2700300": png, "2704302": png}), encoding="utf-8")
    (pasta / "pacote_DF.json").write_text(json.dumps({"5300108": png}), encoding="utf-8")


def test_brasoes_politicas_e_df(tmp_path):
    from fundeb_core import brasoes
    cad = entes.construir(*_sintetico())
    _acervo(tmp_path / "in")
    r = brasoes.montar(tmp_path / "in", cad, "todos", tmp_path / "out")
    assert r["publicados"] == 3 and r["licencas_das_imagens"] == {"livre": 2, "a_verificar": 1}
    al = json.loads((tmp_path / "out" / "indice_AL.json").read_text(encoding="utf-8"))
    assert al["2704302"]["publicado"] and not al["2704302"]["livre"]
    df = json.loads((tmp_path / "out" / "indice_DF.json").read_text(encoding="utf-8"))
    assert df["UF-DF"]["publicado"] and "5300108" in df["UF-DF"]["observacoes"] and df["UF-DF"]["imagem"] == "5300108"
    # com "licenca_identificada", os pacotes de insumo precisam trazer só as imagens de licença livre
    with pytest.raises(brasoes.ErroBrasoes, match="não permite"):
        brasoes.montar(tmp_path / "in", cad, "licenca_identificada", tmp_path / "x")
    (tmp_path / "in" / "pacote_AL.json").write_text(json.dumps({"2700300": "data:image/png;base64,AA=="}), encoding="utf-8")
    r2 = brasoes.montar(tmp_path / "in", cad, "licenca_identificada", tmp_path / "out2")
    pac = json.loads((tmp_path / "out2" / "pacote_AL.json").read_text(encoding="utf-8"))
    assert set(pac) == {"2700300"} and r2["publicados"] == 2      # Maceió (licença a verificar) fica de fora
    al2 = json.loads((tmp_path / "out2" / "indice_AL.json").read_text(encoding="utf-8"))
    assert not al2["2704302"]["publicado"] and al2["2704302"]["licenca"]   # procedência continua registrada
    r3 = brasoes.montar(tmp_path / "in", cad, "nenhum", tmp_path / "out3")
    assert r3["publicados"] == 0 and not list((tmp_path / "out3").glob("pacote_*.json"))


def test_brasoes_falham_quando_pacote_e_catalogo_divergem(tmp_path):
    from fundeb_core import brasoes
    cad = entes.construir(*_sintetico())
    _acervo(tmp_path / "in")
    (tmp_path / "in" / "pacote_AL.json").write_text(json.dumps({"2700300": "data:image/png;base64,AA=="}), encoding="utf-8")
    with pytest.raises(brasoes.ErroBrasoes, match="divergentes"):
        brasoes.montar(tmp_path / "in", cad, "todos", tmp_path / "out")
    _acervo(tmp_path / "in2")
    (tmp_path / "in2" / "pacote_DF.json").write_text(json.dumps({"5300108": "http://externo/x.png"}), encoding="utf-8")
    with pytest.raises(brasoes.ErroBrasoes, match="data URL"):
        brasoes.montar(tmp_path / "in2", cad, "todos", tmp_path / "out2")


def test_licenca_livre():
    from fundeb_core.brasoes import licenca_livre
    assert licenca_livre("Public domain") and licenca_livre("CC0") and licenca_livre("CC BY-SA 3.0") and licenca_livre("CC BY 4.0")
    assert not licenca_livre("Consultar a página de origem") and not licenca_livre("Não informada pelo acervo")
