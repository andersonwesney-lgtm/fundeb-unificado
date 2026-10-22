# Fundeb integrado — nova aba de unificação

Portal que unifica o acompanhamento do Fundeb (Lei nº 14.113/2020) **sem alterar** os sistemas existentes:

* **Painel SIOPE e Fundeb** — <https://andersonwesney-lgtm.github.io/painel-siope-fundeb/> (repositório `painel-siope-fundeb`);
* **Fundeb 2027 em números** e **Demanda reprimida 0 a 5 anos** — painel publicado no claude.ai.

Publicado em <https://andersonwesney-lgtm.github.io/fundeb-unificado/>.

## Fase 1 (esta versão): portal

* **Cadastro único de entes** (`dados/entes.json`): chave canônica = código IBGE de 7 dígitos (municípios) ou `UF-<sigla>` (governos estaduais e distrital), com o identificador usado em cada sistema:

  | Sistema | Município | Estado/DF |
  |---|---|---|
  | IBGE | 7 dígitos (`2700300`) | — |
  | SIOPE / painel SIOPE e Fundeb | 6 dígitos (`270030`) | `UF-AL` |
  | Painel Fundeb 2027 / demanda reprimida | 7 dígitos (`2700300`) | código da UF (`27`) |

  Casos especiais, conferidos contra as três fontes em 21/10/2026:
  * **Brasília (5300108)** aponta para `UF-DF`: o DF é um único ente no Fundeb e no SIOPE (CF, art. 32, § 1º).
  * **Fernando de Noronha (2605459)** é distrito estadual: tem declarações próprias no SIOPE (`260545`) e não tem rede própria no painel Fundeb 2027.
* **Brasão de cada município**, com a procedência ao lado. Vem do mesmo acervo e tem as mesmas miniaturas de 160 px do painel Fundeb 2027 (`insumos/brasoes/`: `brasoes_catalogo.csv` e `pacote_<UF>.json`).
  * **Cobertura:** 5.487 municípios com imagem no acervo. Este portal publica 1.094 delas (política `licenca_identificada`, escolhida em 22/10/2026).
  * **Licença:** 1.094 imagens têm licença livre identificada (domínio público, CC0, CC BY, CC BY-SA). As outras 4.393 estão como "Consultar a página de origem" ou "Não informada". Para esses municípios, o portal mostra só a procedência e o aviso. Como o repositório é público, os pacotes em `insumos/brasoes/` também trazem só as imagens de licença livre.
  * **O que o portal mostra:** arquivo, página de origem, licença, autor e crédito, Wikidata, SHA-256 da imagem original e data de coleta.
  * **Sem brasão:** municípios fora do acervo e governos estaduais mostram um espaço reservado identificado; nenhuma imagem é gerada.
  * **DF:** o governo do DF usa o registro de Brasília (5300108), e isso fica indicado no cartão.
  * **Política de publicação**, em `config/sistemas.json` → `brasoes.publicar`:
    * `todos`: toda imagem, com a licença ao lado;
    * `licenca_identificada`: só as imagens com licença livre;
    * `nenhum`: só a procedência, sem imagens.
  * **Conferência no build:** o build confere catálogo × miniaturas × cadastro (mesmos códigos, mesma UF, imagens como data URL) e falha se houver divergência.
* **Menu comum** e **parâmetro de URL comum**: `?ente=<IBGE 7, SIOPE 6, sigla ou código da UF>&ano=<exercício>`.
* **Ligações entre os sistemas**:
  * para o painel SIOPE, o link já abre o ente e o exercício (`?ano=2026&bim=todos&ente=270030`);
  * o painel Fundeb 2027 não aceita o ente no endereço, e alterá-lo está fora do escopo. Por isso, o cartão diz qual UF e qual município escolher.
* **Período e fonte** de cada sistema visíveis no cartão.

**O que esta versão não faz:**
* Nenhum valor financeiro (VAAF, VAAT, VAAR, coeficientes, situação de obrigações) é calculado ou republicado nesta fase.
* A aba "Oportunidades de consultoria" não é publicada aqui.

## Publicação

Pelo workflow `.github/workflows/publicar.yml`:
1. coleta a lista de municípios do IBGE e o cadastro e o manifesto publicados pelo painel SIOPE, guardando cada arquivo bruto com SHA-256;
2. gera o site;
3. roda os testes;
4. publica.

Se qualquer passo falhar (fonte fora do ar, formato mudado, cadastro inconsistente), nada é publicado e o site anterior continua no ar.

O workflow roda a cada envio ao `main`, pelo botão "Run workflow" e toda segunda-feira às 10:30 UTC, depois da atualização semanal do painel SIOPE.

Os arquivos podem ser enviados pelo navegador mantendo as pastas, ou soltos na raiz. Nesse caso, o primeiro passo do workflow os organiza em `fundeb_core/`, `web/`, `config/`, `insumos/`, `insumos/brasoes/` e `tests/`, como no repositório `painel-siope-fundeb`.

## Executar localmente

```bash
pip install pytest
python -m fundeb_core coletar   # brutos/: IBGE e painel SIOPE, com SHA-256
python -m fundeb_core gerar     # site/
python -m pytest -q
python -m fundeb_core servir    # http://localhost:8000
```

## Próximas fases (desenho aprovado)

* **Fase 2:** levar o cálculo para o `fundeb_core`, com:
  * normas por exercício;
  * testes contra os valores oficiais;
  * comparação ente a ente com o que está publicado;
  * publicação apenas nesta aba.
* **Fase 3:** simulador.
* **Fase 4:** fluxo único de publicação. Qualquer passo que tocasse o painel existente será submetido antes à aprovação.
