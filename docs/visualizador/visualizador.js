/* Visualizador do BELUGA: lê v1/manifest.json e mostra os setores de uma UF.
   JS puro, sem build, como o dashboard do ORCA. Funciona servido por HTTP
   (scripts/rodar_visualizador.sh ou GitHub Pages); aberto como file://, o
   navegador bloqueia o fetch e só o "Abrir um GeoJSON local" funciona. */
(function () {
  "use strict";

  const BASE = "v1/";
  const ID_CPRM = "br-sgb-setorizacao";
  const GRAUS = ["Muito alto", "Alto", "Médio", "Baixo", "sem grau"];
  const COR_GRAU = {
    "Muito alto": "#b2182b", "Alto": "#ef6548", "Médio": "#fdae61", "Baixo": "#fee08b", "sem grau": "#9ca3af",
  };
  // CPRM em azul (cor do logo); fontes externas em cores bem distintas dela.
  const PALETA = ["#f28c28", "#1b9e77", "#7570b3", "#e7298a", "#66a61e", "#e6ab02", "#a6761d"];
  const COR_CPRM = "#1f4e8c";

  const estado = {
    manifest: null, fontes: {}, cores: {}, camada: null, setores: [], porNum: new Map(),
    filtroFontes: new Set(), filtroGraus: new Set(GRAUS), sob: "todos", cor: "fonte",
  };

  const $ = (id) => document.getElementById(id);
  const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (n) => Number(n).toLocaleString("pt-BR");

  const mapa = L.map("mapa", { preferCanvas: true, zoomControl: true }).setView([-15.8, -50], 4);
  const ruas = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, attribution: "&copy; colaboradores do OpenStreetMap",
  }).addTo(mapa);
  const satelite = L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 19, attribution: "Imagens &copy; Esri" });
  L.control.layers({ "Ruas (OSM)": ruas, "Satélite (Esri)": satelite }, {}, { position: "topright" }).addTo(mapa);
  L.control.scale({ imperial: false }).addTo(mapa);

  const legenda = L.control({ position: "bottomright" });
  legenda.onAdd = () => L.DomUtil.create("div", "legenda");
  legenda.addTo(mapa);

  function avisar(texto, erro) {
    const el = $("estado");
    el.textContent = texto;
    el.classList.toggle("erro", Boolean(erro));
  }

  function grauDe(p) { return p.grau_risco || "sem grau"; }

  function corDe(p) {
    if (estado.cor === "grau") return COR_GRAU[grauDe(p)];
    return estado.cores[p.bl_fonte] || "#888";
  }

  function estilo(feature) {
    const p = feature.properties;
    const cprm = p.bl_fonte === ID_CPRM;
    return {
      color: estado.cor === "fonte" ? corDe(p) : (cprm ? COR_CPRM : "#333"),
      weight: cprm ? 1 : 2,
      dashArray: cprm && estado.cor === "grau" ? "4 3" : null,
      fillColor: corDe(p),
      fillOpacity: cprm ? 0.25 : 0.45,
    };
  }

  function visivel(p) {
    if (!estado.filtroFontes.has(p.bl_fonte)) return false;
    if (!estado.filtroGraus.has(grauDe(p))) return false;
    if (estado.sob === "sim" && p.bl_sob_cp !== true) return false;
    if (estado.sob === "nao" && p.bl_sob_cp !== false) return false;
    return true;
  }

  const GRUPOS = [
    ["Setor", ["num_setor", "bl_num_or", "munic", "cd_geocmu", "uf", "local", "data_setor"]],
    ["Risco", ["grau_risco", "bl_grau_or", "grau_vulne", "tipolo_g1", "tipolo_e1", "tipolo_g2", "tipolo_e2",
      "tipolo_g3", "tipolo_e3", "cobrade_01", "bl_tipo_or", "descricao", "num_edif", "num_domi", "num_pess",
      "sug_interv"]],
    ["Relação com a CPRM", ["bl_sob_cp", "bl_cp_frac", "bl_cp_set"]],
    ["Proveniência", ["bl_fonte", "orgao_exec", "bl_id_orig", "bl_produto", "bl_licenca", "bl_coleta",
      "bl_geom_or", "bl_crs_or", "bl_sha256"]],
  ];
  const ROTULO = {
    num_setor: "código", bl_num_or: "código na fonte", munic: "município", local: "local", descricao: "descrição", cd_geocmu: "cód. IBGE", data_setor: "data do setor",
    grau_risco: "grau", bl_grau_or: "grau na fonte", grau_vulne: "vulnerabilidade",
    tipolo_g1: "tipologia", tipolo_e1: "específica", tipolo_g2: "tipologia 2", tipolo_e2: "específica 2",
    tipolo_g3: "tipologia 3", tipolo_e3: "específica 3", cobrade_01: "COBRADE", bl_tipo_or: "tipologia na fonte",
    num_edif: "edificações", num_domi: "domicílios", num_pess: "pessoas", sug_interv: "intervenção sugerida",
    bl_sob_cp: "sobrepõe CPRM", bl_cp_frac: "fração coberta", bl_cp_set: "setores CPRM",
    bl_fonte: "fonte", orgao_exec: "órgão", bl_id_orig: "id na fonte", bl_produto: "produto",
    bl_licenca: "licença", bl_coleta: "coletado em", bl_geom_or: "geometria na fonte", bl_crs_or: "CRS na fonte",
    bl_sha256: "sha256 do bruto",
  };

  function valor(chave, v) {
    if (chave === "bl_sob_cp") return v === true ? "sim" : v === false ? "não" : "não se aplica";
    if (chave === "bl_cp_frac") return v == null ? "" : `${Math.round(v * 100)}%`;
    if (chave === "bl_cp_set") {
      return String(v).split(",").map((s) => `<button class="ir" data-setor="${esc(s)}">${esc(s)}</button>`).join("");
    }
    if (chave === "bl_fonte") return esc(estado.fontes[v]?.nome ? `${estado.fontes[v].nome} (${v})` : v);
    if (chave === "bl_sha256") return `<code>${esc(String(v).slice(0, 12))}…</code>`;
    return esc(v);
  }

  function popup(p) {
    let html = `<div class="popup"><h4>${esc(p.num_setor)}</h4><table>`;
    for (const [titulo, chaves] of GRUPOS) {
      const linhas = chaves.filter((k) => p[k] !== null && p[k] !== undefined && p[k] !== "")
        .filter((k) => !(k === "bl_num_or" && p.bl_num_or === p.num_setor));
      if (titulo === "Relação com a CPRM" && p.bl_fonte !== ID_CPRM && !linhas.includes("bl_sob_cp")) {
        linhas.unshift("bl_sob_cp");
      }
      if (!linhas.length) continue;
      html += `<tr class="grupo"><th colspan="2">${esc(titulo)}</th></tr>`;
      for (const k of linhas) html += `<tr><th>${esc(ROTULO[k] || k)}</th><td>${valor(k, p[k])}</td></tr>`;
    }
    return html + "</table></div>";
  }

  mapa.on("popupopen", (e) => {
    e.popup.getElement().querySelectorAll("button.ir").forEach((b) => {
      b.addEventListener("click", () => irParaSetor(b.dataset.setor));
    });
  });

  function irParaSetor(num) {
    const camada = estado.porNum.get(num);
    if (!camada) { avisar(`Setor ${num} não está carregado (outra UF ou filtrado).`, true); return; }
    if (camada.getBounds) mapa.fitBounds(camada.getBounds(), { maxZoom: 17 });
    else mapa.setView(camada.getLatLng(), 17);
    camada.openPopup();
  }

  function desenhar(ajustar) {
    if (estado.camada) mapa.removeLayer(estado.camada);
    estado.porNum.clear();
    const visiveis = estado.setores.filter((f) => visivel(f.properties));
    estado.camada = L.geoJSON(visiveis, {
      style: estilo,
      pointToLayer: (f, latlng) => L.circleMarker(latlng, {
        radius: 5, weight: 1, color: "#222", fillColor: corDe(f.properties), fillOpacity: 0.9,
      }),
      onEachFeature: (f, camada) => {
        estado.porNum.set(f.properties.num_setor, camada);
        camada.bindPopup(() => popup(f.properties), { maxWidth: 380 });
      },
    }).addTo(mapa);
    $("contagem").textContent = `${fmt(visiveis.length)} de ${fmt(estado.setores.length)} setores no mapa`;
    // Sem o invalidateSize, o primeiro fitBounds pode rodar antes do layout e
    // cair no zoom máximo.
    mapa.invalidateSize();
    if (ajustar && visiveis.length) {
      const limites = estado.camada.getBounds();
      requestAnimationFrame(() => { mapa.invalidateSize(); mapa.fitBounds(limites, { padding: [20, 20] }); });
    }
    atualizarLegenda();
  }

  function atualizarLegenda() {
    const el = document.querySelector(".legenda");
    const itens = estado.cor === "grau"
      ? GRAUS.map((g) => [COR_GRAU[g], g])
      : [...estado.filtroFontes].map((id) => [estado.cores[id], estado.fontes[id]?.nome || id]);
    el.innerHTML = itens.map(([c, t]) => `<div><span class="amostra" style="background:${c}"></span>${esc(t)}</div>`).join("");
  }

  function montarFiltros() {
    const presentes = new Map();
    const graus = new Map();
    for (const f of estado.setores) {
      const p = f.properties;
      presentes.set(p.bl_fonte, (presentes.get(p.bl_fonte) || 0) + 1);
      graus.set(grauDe(p), (graus.get(grauDe(p)) || 0) + 1);
    }
    estado.filtroFontes = new Set(presentes.keys());
    $("filtro-fontes").innerHTML = [...presentes].sort().map(([id, n]) => `
      <label><input type="checkbox" data-fonte="${esc(id)}" checked>
        <span class="amostra" style="background:${estado.cores[id]}"></span>
        <span>${esc(estado.fontes[id]?.nome || id)}</span><span class="n">${fmt(n)}</span></label>`).join("");
    $("filtro-graus").innerHTML = GRAUS.filter((g) => graus.has(g)).map((g) => `
      <label><input type="checkbox" data-grau="${esc(g)}" ${estado.filtroGraus.has(g) ? "checked" : ""}>
        <span class="amostra" style="background:${COR_GRAU[g]}"></span>
        <span>${esc(g)}</span><span class="n">${fmt(graus.get(g))}</span></label>`).join("");

    const municipios = [...new Set(estado.setores.map((f) => f.properties.munic).filter(Boolean))].sort();
    $("lista-municipios").innerHTML = municipios.map((m) => `<option value="${esc(m)}">`).join("");
    $("municipio").value = "";
  }

  async function carregarUf(uf) {
    const info = estado.manifest.ufs[uf];
    avisar(`Carregando ${uf.toUpperCase()} (${fmt(info.setores)} setores, ${(info.bytes / 1e6).toFixed(1)} MB)…`);
    try {
      const resp = await fetch(BASE + info.arquivo);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const dados = await resp.json();
      estado.setores = dados.features || [];
    } catch (err) {
      avisar(`Falha ao carregar ${info.arquivo}: ${err.message}`, true);
      return;
    }
    montarFiltros();
    desenhar(true);
    avisar(`Publicação de ${new Date(estado.manifest.gerado_em).toLocaleString("pt-BR")} · ` +
      `${fmt(estado.manifest.total_setores)} setores em ${Object.keys(estado.manifest.ufs).length} UF(s)`);
    try { localStorage.setItem("beluga.uf", uf); } catch (_) { /* sem armazenamento: tudo bem */ }
  }

  function renderCatalogo() {
    const fontes = estado.manifest.fontes;
    $("catalogo").innerHTML = fontes.map((f) => {
      const cls = f.status === "ativa" ? "ativa" : "inativa";
      const muns = (f.municipios || []).map((m) => `${m.nome} (${m.cd_ibge})`).join(", ") || (f.uf === "BR" ? "nacional" : f.uf);
      const link = f.acesso.pagina || f.acesso.url;
      return `<div class="fonte">
        <h3>${esc(f.nome)}</h3>
        <p><span class="selo ${cls}">${esc(f.status)}</span>
           <span class="selo">${f.publicada ? "publicada" : "não publicada"}</span>
           <span class="selo">${esc(f.produto)}</span></p>
        <p>${esc(f.orgao)}</p>
        <p>${esc(muns)}</p>
        <p>Licença: ${esc(f.licenca.nome)} · ${fmt(f.setores_publicados)} setores publicados
           ${f.coletado_em ? ` · coletado em ${esc(f.coletado_em.slice(0, 10))}` : ""}</p>
        <p>Acesso: ${esc(f.acesso.tipo)}${link ? ` · <a href="${esc(link)}" rel="noopener" target="_blank">abrir</a>` : ""}
           · verificado em ${esc(f.ultima_verificacao)}</p>
        ${f.notas ? `<p>${esc(f.notas)}</p>` : ""}
      </div>`;
    }).join("");
  }

  async function renderValidacao() {
    try {
      const resp = await fetch(BASE + "relatorio_validacao.json");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const r = await resp.json();
      let html = `<p>${fmt(r.total_publicado)} de ${fmt(r.total_entrada)} setores publicados.</p>`;
      if (r.avisos_globais?.length) html += `<p>${r.avisos_globais.map(esc).join("<br>")}</p>`;
      for (const [fonte, d] of Object.entries(r.por_fonte)) {
        html += `<h3>${esc(estado.fontes[fonte]?.nome || fonte)}</h3><table class="relatorio">
          <tr><th>entrada</th><td class="n">${fmt(d.entrada)}</td></tr>
          <tr><th>publicados</th><td class="n">${fmt(d.publicados)}</td></tr>`;
        for (const [m, n] of Object.entries(d.erros)) {
          html += `<tr><th>erro: ${esc(m)}</th><td class="n">${fmt(n)}</td></tr>`;
        }
        for (const [m, n] of Object.entries(d.avisos)) {
          const ex = (d.exemplos[m] || []).slice(0, 5).map((s) => `<button class="ir" data-setor="${esc(s)}">${esc(s)}</button>`).join("");
          html += `<tr><th>aviso: ${esc(m)}<br>${ex}</th><td class="n">${fmt(n)}</td></tr>`;
        }
        html += "</table>";
      }
      $("validacao").innerHTML = html;
      $("validacao").querySelectorAll("button.ir").forEach((b) => b.addEventListener("click", () => irParaSetor(b.dataset.setor)));
    } catch (err) {
      $("validacao").textContent = `Relatório indisponível: ${err.message}`;
    }
  }

  function definirCores() {
    let i = 0;
    for (const f of estado.manifest.fontes) {
      estado.fontes[f.id] = f;
      estado.cores[f.id] = f.id === ID_CPRM ? COR_CPRM : PALETA[i++ % PALETA.length];
    }
  }

  async function iniciar() {
    try {
      const resp = await fetch(BASE + "manifest.json");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      estado.manifest = await resp.json();
    } catch (err) {
      const arquivo = location.protocol === "file:";
      avisar(arquivo
        ? "Aberto como arquivo: o navegador bloqueia a leitura de v1/. Rode scripts/rodar_visualizador.sh, ou use \"Abrir um GeoJSON local\"."
        : `Sem publicação em ${BASE}manifest.json (${err.message}). Rode \`python -m src.cli exportar\`.`, true);
      return;
    }
    definirCores();
    const ufs = Object.keys(estado.manifest.ufs).sort();
    $("uf").innerHTML = ufs.map((u) => `<option value="${u}">${u.toUpperCase()} · ${fmt(estado.manifest.ufs[u].setores)} setores</option>`).join("");
    let inicial = null;
    try { inicial = localStorage.getItem("beluga.uf"); } catch (_) { /* ignora */ }
    const uf = ufs.includes(inicial) ? inicial : (ufs.includes("mg") ? "mg" : ufs[0]);
    $("uf").value = uf;
    renderCatalogo();
    renderValidacao();
    await carregarUf(uf);
  }

  // ---------------------------------------------------------------- eventos
  $("uf").addEventListener("change", (e) => carregarUf(e.target.value));
  $("filtro-fontes").addEventListener("change", (e) => {
    const id = e.target.dataset.fonte;
    if (e.target.checked) estado.filtroFontes.add(id); else estado.filtroFontes.delete(id);
    desenhar(false);
  });
  $("filtro-graus").addEventListener("change", (e) => {
    const g = e.target.dataset.grau;
    if (e.target.checked) estado.filtroGraus.add(g); else estado.filtroGraus.delete(g);
    desenhar(false);
  });
  document.querySelectorAll('input[name="cor"]').forEach((r) => r.addEventListener("change", (e) => {
    estado.cor = e.target.value; desenhar(false);
  }));
  document.querySelectorAll('input[name="sob"]').forEach((r) => r.addEventListener("change", (e) => {
    estado.sob = e.target.value; desenhar(false);
  }));
  $("municipio").addEventListener("change", (e) => {
    const nome = e.target.value.trim().toUpperCase();
    const doMunicipio = estado.setores.filter((f) => f.properties.munic === nome);
    if (!doMunicipio.length) return;
    mapa.fitBounds(L.geoJSON(doMunicipio).getBounds(), { padding: [20, 20], maxZoom: 16 });
  });
  document.querySelectorAll(".abas button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".abas button").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
    document.querySelectorAll(".aba").forEach((a) => { a.hidden = a.id !== b.dataset.aba; });
  }));
  $("recolher").addEventListener("click", (e) => {
    const painel = $("painel");
    painel.classList.toggle("recolhido");
    e.target.setAttribute("aria-expanded", String(!painel.classList.contains("recolhido")));
    setTimeout(() => mapa.invalidateSize(), 50);
  });
  $("arquivo-local").addEventListener("change", async (e) => {
    const arq = e.target.files[0];
    if (!arq) return;
    try {
      const dados = JSON.parse(await arq.text());
      estado.setores = dados.features || [];
      if (!estado.manifest) {
        for (const f of estado.setores) {
          const id = f.properties.bl_fonte || "arquivo";
          f.properties.bl_fonte = id;
          if (!estado.cores[id]) estado.cores[id] = id === ID_CPRM ? COR_CPRM : PALETA[Object.keys(estado.cores).length % PALETA.length];
        }
      }
      montarFiltros();
      desenhar(true);
      avisar(`Arquivo local: ${arq.name} (${fmt(estado.setores.length)} feições)`);
    } catch (err) {
      avisar(`Não deu para ler ${arq.name}: ${err.message}`, true);
    }
  });

  // Exposto para depuração no console do navegador.
  window.BELUGA = { mapa, estado };
  iniciar();
})();
