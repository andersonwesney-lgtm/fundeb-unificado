/* Fundeb integrado — Fase 1 (portal). Só lê dados/manifest.json e dados/entes.json; não calcula valores. */
"use strict";
const S = { man: null, entes: [], porId: new Map(), porSiope: new Map(), sel: null, ano: "", brasoes: {} };
const $ = (s) => document.querySelector(s);
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const sem = (t) => String(t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const preencher = (t, o) => String(t || "").replace(/\{(\w+)\}/g, (_, k) => (o[k] ?? ""));

async function getJSON(u) {
  const r = await fetch(u, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${u}: HTTP ${r.status}`);
  return r.json();
}

async function iniciar() {
  try {
    const [man, ent] = await Promise.all([getJSON("dados/manifest.json"), getJSON("dados/entes.json")]);
    S.man = man;
    S.entes = ent.linhas.map((l) => Object.fromEntries(ent.colunas.map((c, i) => [c, l[i]])));
    for (const e of S.entes) {
      S.porId.set(e.id, e);
      if (e.id_siope && e.tipo !== "referencia_df") S.porSiope.set(e.id_siope, e);
    }
  } catch (e) {
    $("#fase").textContent = "Não foi possível carregar os dados do portal (" + e.message + "). Recarregue a página.";
    return;
  }
  $("#titulo").textContent = S.man.portal.titulo;
  $("#subtitulo").textContent = S.man.portal.subtitulo;
  $("#fase").textContent = S.man.portal.fase;
  $("#menuSistemas").innerHTML = S.man.sistemas
    .map((s) => `<a href="${esc(s.url)}" rel="noopener">${esc(s.nome)}</a>`).join("");
  const ufs = [...new Set(S.entes.map((e) => e.uf))].sort();
  $("#uf").insertAdjacentHTML("beforeend", ufs.map((u) => `<option>${u}</option>`).join(""));
  S.ano = String(S.man.siope.exercicios[S.man.siope.exercicios.length - 1]);
  $("#q").addEventListener("input", buscar);
  $("#uf").addEventListener("change", buscar);
  window.addEventListener("popstate", lerURL);
  rodape();
  lerURL();
}

function normalizar(v) {
  v = String(v || "").trim().toUpperCase();
  if (!v) return null;
  if (S.porId.has(v)) return v;
  if (/^[A-Z]{2}$/.test(v) && S.porId.has("UF-" + v)) return "UF-" + v;
  if (/^\d{2}$/.test(v)) { const e = S.entes.find((x) => x.cod_uf === v && x.ibge7 === null); return e ? e.id : null; }
  if (/^\d{6}$/.test(v) && S.porSiope.has(v)) return S.porSiope.get(v).id;
  return null;
}

function lerURL() {
  const p = new URLSearchParams(location.search);
  const ano = p.get("ano");
  if (ano && S.man.siope.exercicios.map(String).includes(ano)) S.ano = ano;
  const id = normalizar(p.get("ente"));
  if (p.get("ente") && !id) {
    $("#ficha").hidden = false;
    $("#ficha").innerHTML = `<p class="alerta">O ente “${esc(p.get("ente"))}” não foi encontrado no cadastro. Use o código IBGE de 7 dígitos, o código do SIOPE (6 dígitos) ou a sigla da UF.</p>`;
    return;
  }
  if (id) mostrar(id, false);
}

function escreverURL() {
  const p = new URLSearchParams();
  if (S.sel) p.set("ente", S.sel.id);
  if (S.ano) p.set("ano", S.ano);
  try { history.pushState(null, "", "?" + p.toString()); } catch (e) { /* visualizadores sem history */ }
}

function buscar() {
  const q = sem($("#q").value.trim()), uf = $("#uf").value;
  const ul = $("#resultados");
  if (!q && !uf) { ul.innerHTML = ""; return; }
  const direto = normalizar($("#q").value);
  let lista = S.entes.filter((e) => (!uf || e.uf === uf) &&
    (!q || sem(e.nome).includes(q) || (e.ibge7 || "").startsWith(q) || (e.id_siope || "").toLowerCase().startsWith(q) || e.id.toLowerCase() === q));
  if (direto && !lista.some((e) => e.id === direto)) lista.unshift(S.porId.get(direto));
  lista.sort((a, b) => (a.ibge7 === null) - (b.ibge7 === null) || sem(a.nome).localeCompare(sem(b.nome)));
  const total = lista.length;
  lista = lista.slice(0, 40);
  ul.innerHTML = lista.map((e) => `<li><button type="button" data-id="${esc(e.id)}">${esc(e.nome)} <span class="uf">${esc(e.uf)}</span> <span class="cod">${esc(e.ibge7 || e.id)}</span></button></li>`).join("") +
    (total > 40 ? `<li class="mais">${total - 40} outros resultados; refine a busca.</li>` : "") +
    (total === 0 ? `<li class="mais">Nenhum ente encontrado.</li>` : "");
  ul.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => mostrar(b.dataset.id, true)));
}

function linkSistema(s, e, alvo) {
  const ctx = { ano: S.ano, id_siope: alvo.id_siope || "", id_fundeb: alvo.id_fundeb || "", uf: alvo.uf, nome_painel: alvo.ibge7 ? `${alvo.nome} - ${alvo.uf}` : alvo.nome };
  const indisponivel = (s.id === "siope" && !alvo.id_siope) || (s.id !== "siope" && !alvo.id_fundeb);
  if (indisponivel) {
    return `<p class="alerta">Este ente não aparece neste sistema. ${esc(e.obs || "")}</p>`;
  }
  const url = s.aceita_ente_no_link ? preencher(s.link_ente, ctx) : s.link_ente;
  const instr = s.aceita_ente_no_link ? "" :
    `<p class="instr">${esc(preencher(alvo.ibge7 ? s.instrucao : s.instrucao_estadual, ctx))}</p>`;
  const acesso = s.acesso ? `<p class="nota">Acesso: ${esc(s.acesso)}.</p>` : "";
  const rot = s.aceita_ente_no_link ? (s.id === "siope" ? `Abrir ${esc(alvo.nome)} no SIOPE (${esc(S.ano)})` : "Abrir") : `Abrir ${esc(s.nome)}`;
  return `${instr}<p><a class="botao" href="${esc(url)}" rel="noopener">${rot}</a></p>${acesso}`;
}

function mostrar(id, empilhar) {
  const e = S.porId.get(id);
  if (!e) return;
  S.sel = e;
  const alvo = e.aponta_para ? S.porId.get(e.aponta_para) : e;
  const f = $("#ficha");
  f.hidden = false;
  const tipo = { municipal: "Município", estadual: "Governo estadual", distrital: "Governo do Distrito Federal",
    referencia_df: "Município do IBGE (Distrito Federal)", distrito_estadual: "Distrito estadual" }[e.tipo] || e.tipo;
  const anos = S.man.siope.exercicios.map((a) => `<option ${String(a) === S.ano ? "selected" : ""}>${a}</option>`).join("");
  f.innerHTML = `
    <div class="cab-ente"><div id="brasao" class="brasao"><div class="ph">Carregando brasão…</div></div><div>
    <h2>${esc(e.nome)} <span class="uf">${esc(e.uf)}</span></h2>
    <p class="meta">${esc(tipo)} · região ${esc(e.regiao)}${e.aponta_para ? ` · no Fundeb e no SIOPE: <a href="?ente=${esc(e.aponta_para)}&ano=${esc(S.ano)}" data-ir="${esc(e.aponta_para)}">${esc(alvo.nome)}</a>` : ""}</p>
    ${e.obs ? `<p class="alerta">${esc(e.obs)}</p>` : ""}
    <div id="fonteBrasao" class="fonte-brasao"></div></div></div>
    <table class="ids">
      <caption>Identificador do ente em cada sistema</caption>
      <thead><tr><th scope="col">Sistema</th><th scope="col">Código</th></tr></thead>
      <tbody>
        <tr><td>IBGE (município)</td><td>${esc(e.ibge7 || "—")}</td></tr>
        <tr><td>Cadastro único (esta aba)</td><td>${esc(e.id)}</td></tr>
        <tr><td>SIOPE / painel SIOPE e Fundeb</td><td>${esc(alvo.id_siope || "—")}</td></tr>
        <tr><td>Painel Fundeb 2027 em números e demanda reprimida</td><td>${esc(alvo.id_fundeb || "—")}</td></tr>
      </tbody>
    </table>
    <label class="ano">Exercício para o SIOPE <select id="ano">${anos}</select></label>
    <div class="cartoes">
      ${S.man.sistemas.map((s) => `
        <article class="cartao">
          <h3>${esc(s.nome)}</h3>
          <p class="perg">${esc(s.pergunta)}</p>
          <dl>
            <dt>Período de referência</dt><dd>${esc(s.periodo)}</dd>
            <dt>Fontes e normas</dt><dd>${esc(s.referencia)}</dd>
            <dt>Atualização</dt><dd>${esc(s.atualizacao)}</dd>
          </dl>
          ${linkSistema(s, e, alvo)}
        </article>`).join("")}
    </div>`;
  f.querySelector("#ano").addEventListener("change", (ev) => { S.ano = ev.target.value; mostrar(S.sel.id, true); });
  f.querySelectorAll("[data-ir]").forEach((a) => a.addEventListener("click", (ev) => { ev.preventDefault(); mostrar(a.dataset.ir, true); }));
  mostrarBrasao(e);
  if (empilhar) escreverURL();
  f.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function brasoesUF(uf) {
  if (!S.brasoes[uf]) {
    S.brasoes[uf] = Promise.all([
      getJSON(`dados/brasoes/indice_${uf}.json`).catch(() => ({})),
      getJSON(`dados/brasoes/pacote_${uf}.json`).catch(() => ({})),
    ]);
  }
  return S.brasoes[uf];
}

async function mostrarBrasao(e) {
  const chave = e.ibge7 || (e.id === "UF-DF" ? "UF-DF" : null);
  const caixa = $("#brasao"), fonte = $("#fonteBrasao");
  if (!caixa) return;
  if (!chave) {
    caixa.innerHTML = `<div class="ph">Brasão estadual<br>não disponível</div>`;
    fonte.innerHTML = `<p class="nota">O acervo de brasões cobre os municípios; brasões dos estados não fazem parte dele. Nenhuma imagem é gerada.</p>`;
    return;
  }
  const [ind, pac] = await brasoesUF(e.uf);
  if (S.sel !== e) return;               // o usuário já escolheu outro ente
  const r = ind[chave];
  if (!r || r.status !== "baixado") {
    caixa.innerHTML = `<div class="ph">Brasão não<br>disponível</div>`;
    fonte.innerHTML = `<p class="nota">Sem imagem no acervo de brasões${r ? ` (situação: ${esc(r.status.replace(/_/g, " "))})` : ""}. Nenhuma imagem é gerada ou inventada.</p>`;
    return;
  }
  const img = r.publicado ? pac[r.imagem || chave] : null;
  caixa.innerHTML = img ? `<img src="${img}" alt="Brasão de ${esc(e.nome)}">` :
    `<div class="ph">Imagem não publicada<br>neste portal</div>`;
  const qid = (r.wikidata || "").split("/").pop();
  const lic = r.licenca_url ? `<a href="${esc(r.licenca_url)}" rel="noopener">${esc(r.licenca)}</a>` : esc(r.licenca || "não informada");
  const partes = [
    r.fonte ? `origem: <a href="${esc(r.fonte)}" rel="noopener">página de origem</a>` : "",
    `licença: ${lic}`,
    r.autor ? `autor: ${esc(r.autor)}` : "", r.credito ? `crédito: ${esc(r.credito)}` : "",
    qid ? `Wikidata <a href="${esc(r.wikidata)}" rel="noopener">${esc(qid)}</a>` : "",
    r.sha256 ? `SHA-256 da imagem original <code>${esc(r.sha256.slice(0, 12))}…</code>` : "",
    r.coleta ? `coletado em ${esc(r.coleta)}` : "",
  ].filter(Boolean).join(" · ");
  fonte.innerHTML = `<p class="nota"><b>Fonte do brasão:</b> acervo de brasões da Tech Play Edu, arquivo <code>${esc(r.arquivo)}</code>; ${partes}.` +
    `${r.observacoes ? ` ${esc(r.observacoes)}` : ""}</p>` +
    (!r.livre ? `<p class="nota aviso-lic">${esc(S.man.brasoes.aviso_licenca)}</p>` : "") +
    (!r.publicado ? `<p class="nota">A política de publicação deste portal não inclui imagens com esta licença; a procedência fica registrada.</p>` : "");
}

function rodape() {
  const m = S.man;
  const fontes = m.fontes.map((f) => `<li>${esc(f.descricao)}${f.url ? ` — <a href="${esc(f.url)}" rel="noopener">${esc(f.url)}</a>` : ""}; ${f.coletado_em ? "coletado em " + esc(f.coletado_em) : "verificado em " + esc(f.verificado_em)}; SHA-256 <code>${esc(String(f.sha256).slice(0, 16))}…</code></li>`).join("");
  $("#rodape").innerHTML = `
    <p>Cadastro com ${m.entes.total.toLocaleString("pt-BR")} registros (SHA-256 <code>${esc(m.entes.sha256.slice(0, 16))}…</code>), gerado em ${esc(m.gerado_em)} · versão ${esc(m.versao)}.
    Painel SIOPE: manifesto de ${esc(m.siope.gerado_em || "")}, exercícios ${esc(m.siope.exercicios.join(" e "))}.</p>
    <details><summary>Fontes do cadastro</summary><ul>${fontes}<li>${esc(m.brasoes.descricao)}: catálogo <code>${esc(m.brasoes.catalogo.sha256.slice(0, 16))}…</code>, ${m.brasoes.catalogo.com_imagem.toLocaleString("pt-BR")} municípios com imagem (${m.brasoes.licencas_das_imagens.livre.toLocaleString("pt-BR")} com licença livre identificada, ${m.brasoes.licencas_das_imagens.a_verificar.toLocaleString("pt-BR")} a verificar); ${m.brasoes.publicados.toLocaleString("pt-BR")} imagens publicadas (política: ${esc(m.brasoes.politica)}).</li></ul></details>
    <p>Tech Play Edu · Lei nº 14.113/2020 · <a href="dados/manifest.json">manifesto</a> · <a href="dados/entes.json">cadastro (JSON)</a></p>`;
}

iniciar();
