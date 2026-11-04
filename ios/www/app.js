(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (v, digits = 1) => (v == null || Number.isNaN(Number(v)) ? "—" : Number(v).toFixed(digits));
  const pct = (v) => (v == null ? "—" : `${Math.round(Number(v) * 100)}%`);
  const titleCase = (s) => String(s || "").replace(/(^|[-_ ])\w/g, (m) => m.toUpperCase()).replace(/[-_]/g, " ");
  const localizedText = (v) => {
    const raw = String(v == null ? "" : v);
    if (state.lang !== "en") return raw;
    return translateText(raw, "en") || raw;
  };
  const clipLocalized = (v, zhLimit, enLimit) => {
    const text = localizedText(v);
    return text.slice(0, state.lang === "en" ? enLimit : zhLimit);
  };

  const state = {
    me: null,
    design: null,
    selected: 0,
    cases: [],
    systems: [],
    page: "design",
    mode: "auto",
    caseSystem: null,
    caseTitle: null,
    computeDesign: null,
    evidence: null,
    graph: null,
    graphView: false,
    graphAnim: null,
    poll: null,
    loading: false,
    computeCaps: [],
    tools: null,
    litStats: null,
    litTopics: null,
    jobs: [],
    resources: null,
    knowledge: null,
    resourceFilter: "all",
    resourceQuery: "",
    theme: "aurora",
    themeMode: "auto",
  };

  const pages = {
    design: ["DESIGN", "设计工作台"],
    cases: ["CASE LIBRARY", "案例库"],
    evidence: ["FEDERATED EVIDENCE", "在线证据"],
    resources: ["RESOURCE DIRECTORY", "资源库"],
    compute: ["LOCAL MECHANISM", "机制计算"],
    lab: ["MODEL LAB", "模型实验室"],
    guide: ["FIELD MANUAL", "使用指南"],
    settings: ["SETTINGS", "设置"],
  };

  function toast(message) {
    const el = $("#toast");
    el.textContent = message;
    el.classList.add("show");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => el.classList.remove("show"), 3200);
  }

  function showLogin(message = "") {
    $("#login-gate").classList.remove("hidden");
    $("#app").classList.add("hidden");
    $("#login-error").textContent = message;
    $("#login-pass").value = "";
    setTimeout(() => $("#login-pass").focus(), 60);
  }

  function refreshNativeServer() {
    const bridge = window.AndroidBridge;
    const card = $("#android-server-card");
    const loginBtn = $("#native-server-btn");
    if (!bridge) {
      if (card) card.hidden = true;
      if (loginBtn) loginBtn.hidden = true;
      return;
    }
    if (loginBtn) loginBtn.hidden = false;
    if (card) {
      card.hidden = false;
      const url = $("#settings-server-url");
      try { if (url) url.textContent = bridge.getServerUrl() || "未设置"; } catch { if (url) url.textContent = "未设置"; }
    }
  }

  function showApp() {
    $("#login-gate").classList.add("hidden");
    $("#app").classList.remove("hidden");
    $("#account-btn").textContent = (state.me?.username || "A").slice(0, 1).toUpperCase();
    const s = $("#settings-user");
    if (s) s.textContent = state.me?.username || "—";
    refreshNativeServer();
  }

  async function api(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    const res = await fetch(path, { credentials: "same-origin", ...options, headers });
    let payload = null;
    const text = await res.text();
    try { payload = text ? JSON.parse(text) : null; } catch { payload = { detail: text }; }
    if (res.status === 401) {
      showLogin(state.me ? "登录已过期，请重新登录。" : "请输入用户名和密码。");
      throw new Error("unauthorized");
    }
    if (!res.ok) {
      const detail = payload?.detail;
      throw new Error(typeof detail === "string" ? detail : `请求失败 (${res.status})`);
    }
    return payload;
  }

  function setPage(page) {
    if (!pages[page]) return;
    if (page === state.page) {
      if (page === "lab") window.BioForgeLab?.enter();
      return;
    }
    state.page = page;
    $$(".view").forEach((v) => v.classList.remove("active"));
    const view = $(`#view-${page}`);
    if (view) view.classList.add("active");
    $$(".nav-item, .mobile-tabs button").forEach((b) => b.classList.toggle("active", b.dataset.page === page));
    $("#page-kicker").textContent = pages[page][0];
    $("#page-title").textContent = pages[page][1];
    $(".sidebar")?.classList.remove("open");
    window.scrollTo({ top: 0, behavior: "smooth" });
    if (page === "compute") { loadJobs(); loadCapabilities(); loadTools(); }
    if (page === "lab") window.BioForgeLab?.enter();
    if (page === "evidence") { loadLiteratureStats(); if (!state.evidence && !state.graphView) runEvidence("quercetin"); }
    if (page === "cases" && !state.cases.length) loadCases();
    if (page === "settings") { loadSourceCatalog(); loadKnowledgeStatus(); }
    if (page === "guide") { loadAssistantStatus(); loadNotes(); }
    if (page === "resources") loadResources();
  }

  function setConn(on) {
    const dot = $("#conn-dot"), label = $("#conn-label");
    if (dot) dot.className = `dot ${on ? "on" : "off"}`;
    if (label) label.textContent = on ? "服务器已连接" : "离线 / 未连接";
  }

  async function login(event) {
    event.preventDefault();
    const username = $("#login-user").value.trim();
    const password = $("#login-pass").value;
    const btn = $("#login-form button[type=submit]");
    btn.disabled = true;
    try {
      const res = await api("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
      state.me = res.user;
      $("#login-error").textContent = "";
      showApp();
      await bootData();
      toast("已登录，欢迎回来。");
    } catch (err) {
      $("#login-error").textContent = err.message === "unauthorized" ? "用户名或密码错误。" : err.message;
    } finally {
      btn.disabled = false;
    }
  }

  async function logout() {
    try { await api("/api/auth/logout", { method: "POST" }); } catch { /* ignore */ }
    state.me = null;
    state.design = null;
    showLogin("已安全退出。");
  }

  async function bootData() {
    loadCases();
    loadSystems();
    loadMeta();
    loadResources();
    setConn(true);
  }

  async function loadCases() {
    try {
      const res = await api("/api/v2/cases");
      state.cases = res.items || [];
      renderCases();
    } catch (err) { if (err.message !== "unauthorized") toast(err.message); }
  }

  async function loadSystems() {
    try {
      const res = await api("/api/v2/food/systems");
      state.systems = res.items || [];
      if (state.cases.length) renderCases();
    } catch { /* non-blocking */ }
  }

  async function loadMeta() {
    try {
      const meta = await api("/api/meta");
      const list = $("#dataset-list");
      if (list && meta.datasets) {
        list.innerHTML = Object.entries(meta.datasets).map(([name, info]) =>
          `<div class="dataset-row"><b>${esc(name)}</b><span>${info.items ?? "—"} 条 · ${info.schema_version || ""}</span></div>`
        ).join("");
      }
    } catch { /* non-blocking */ }
  }

  function renderCases() {
    const grid = $("#case-grid");
    if (!grid) return;
    const en = state.lang === "en";
    const systemCount = state.systems.length || new Set(state.cases.map((item) => item.system).filter(Boolean)).size;
    const title = $("#case-count-title");
    if (title) title.textContent = en
      ? `${systemCount || "—"} food systems · ${state.cases.length} end-to-end cases`
      : `${systemCount || "—"} 个食品体系 · ${state.cases.length} 个端到端案例`;
    grid.innerHTML = state.cases.map((c) => `
      <details class="case-card card" data-case="${esc(c.id)}">
        <summary>
          <span class="badge blue">${esc(c.system || "food")}</span>
          <h3>${esc(en ? (c.title_en || c.title) : c.title)}</h3>
          <span class="case-chevron" aria-hidden="true">▸</span>
        </summary>
        <div class="case-body">
          <p>${esc(en ? (c.query_en || c.query) : c.query)}</p>
          <span class="muted" style="font-size:11px">${esc((c.focus || []).join(" · "))}</span>
          <button class="btn ghost small case-load" type="button" data-load-case="${esc(c.id)}">${en ? "Open case" : "打开案例"}</button>
        </div>
      </details>`).join("");
    $$("[data-load-case]", grid).forEach((button) => button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const item = state.cases.find((c) => c.id === button.dataset.loadCase);
      if (!item) return;
      if (!item.system) {
        setPage("compute");
        const query = en ? (item.query_en || item.query) : item.query;
        const box = $("#compute-query");
        if (box) box.value = query;
        toast(en ? "Mechanism case loaded. Review the partners and start the job." : "机制案例已载入。请核对受体/配体后启动作业。");
        return;
      }
      setPage("design");
      setDesignMode("food");
      state.caseSystem = item.system;
      state.caseTitle = en ? (item.title_en || item.title) : item.title;
      $("#design-query").value = en ? (item.query_en || item.query) : item.query;
      submitDesign();
    }));
  }

  function setDesignMode(mode) {
    state.mode = mode;
    $$("#mode-seg button").forEach((x) => x.classList.toggle("active", x.dataset.mode === mode));
  }

  function modeButtons() {
    $$("#mode-seg button").forEach((b) => b.addEventListener("click", () => {
      state.caseSystem = null;
      state.caseTitle = null;
      setDesignMode(b.dataset.mode);
    }));
    $("#design-query")?.addEventListener("input", () => { state.caseSystem = null; state.caseTitle = null; });
  }

  async function submitDesign(event) {
    event?.preventDefault();
    if (state.loading) return;
    const query = $("#design-query").value.trim();
    if (!query) { toast("请先输入产品目标。"); $("#design-query").focus(); return; }
    state.loading = true;
    $("#design-loading").classList.remove("hidden");
    $("#design-result").classList.add("hidden");
    $("#design-empty").classList.add("hidden");
    $("#design-submit").disabled = true;
    try {
      const design = await api("/api/v2/design", {
        method: "POST",
        body: JSON.stringify({ query, options: { mode: state.mode, ...(state.caseSystem ? { system_id: state.caseSystem } : {}) } }),
      });
      state.design = design;
      state.selected = 0;
      state.graph = null;
      setPage("design");
      renderDesign();
      toast(`已生成 ${design.candidates?.length || design.portfolio?.length || 0} 个候选。`);
    } catch (err) {
      if (err.message !== "unauthorized") toast(err.message);
      if (!state.design) $("#design-empty").classList.remove("hidden");
    } finally {
      state.loading = false;
      $("#design-loading").classList.add("hidden");
      $("#design-submit").disabled = false;
    }
  }

  function scoreClass(v) {
    if (v == null) return "";
    return v >= 0.75 ? "good" : v >= 0.55 ? "" : "warn";
  }

  function rangeText(pair, unit = "") {
    if (!Array.isArray(pair) || pair.length < 2) return "—";
    return `${num(pair[0], 2)}–${num(pair[1], 2)}${unit}`;
  }

  function renderMetrics(m, intervals = {}) {
    const items = [
      ["综合评分", pct(m.overall_score), scoreClass(m.overall_score), ""],
      ["pH", num(m.ph, 2), "", rangeText(intervals.ph)],
      ["蛋白质", `${num(m.protein_pct, 1)}%`, "", rangeText(intervals.protein_pct, "%")],
      ["糖", `${num(m.sugar_pct, 1)}%`, "", rangeText(intervals.sugar_pct, "%")],
      ["钠", `${num(m.sodium_mg, 0)} mg`, m.sodium_mg > 600 ? "warn" : "", rangeText(intervals.sodium_mg, " mg")],
      ["脂肪", `${num(m.fat_pct, 1)}%`, "", rangeText(intervals.fat_pct, "%")],
    ];
    return items.map(([label, value, cls, interval]) =>
      `<div class="metric ${cls}" title="${esc(interval ? `筛选区间 ${interval}（假设值，非实验置信区间）` : "")}"><span>${label}</span><b>${value}</b>${interval ? `<small style="font-size:9.5px;color:var(--muted)">${esc(interval)}</small>` : ""}</div>`).join("");
  }

  function candidateBadges(c) {
    const m = c.metrics || {};
    const badges = [];
    const status = c.constraint_status || (c.constraint_met ? "pass" : "fail");
    if (status === "pass") badges.push('<span class="badge ok">约束通过</span>');
    else if (status === "at_risk") badges.push('<span class="badge warn">约束有风险</span>');
    else badges.push('<span class="badge no">约束未达标</span>');
    badges.push(`<span class="badge">证据 ${esc(c.evidence_grade || "—")}</span>`);
    if (m.allergens?.length) badges.push(`<span class="badge warn">${m.allergens.length} 过敏原</span>`);
    if (m.negative_interactions?.length) badges.push(`<span class="badge warn">${m.negative_interactions.length} 负向作用</span>`);
    return badges.join("");
  }

  function renderConstraintReport(sel) {
    const rows = sel.constraint_report || [];
    if (!rows.length) return '<p class="muted">未设置可计算的硬约束。</p>';
    const value = (x) => `${esc(Array.isArray(x.value) ? (x.value.length ? x.value.join("、") : "无") : x.value)}${esc(x.unit || "")}`;
    const limit = (x) => `${esc(Array.isArray(x.limit) ? x.limit.join("–") : x.limit)}${esc(x.unit || "")}`;
    const status = (x) => `<span class="badge ${x.status === "pass" ? "ok" : x.status === "at_risk" ? "warn" : "no"}">${esc(x.status)}</span>`;
    return `<div class="constraint-cards">${rows.map((x) => `<div class="constraint-card">
      <div style="display:flex;justify-content:space-between;gap:8px;align-items:flex-start"><b>${esc(x.label)}</b>${status(x)}</div>
      <p style="margin:6px 0 2px">估算 <b>${value(x)}</b> · 限制 ${limit(x)}</p>
      <p class="fineprint" style="margin:0">筛选区间 ${esc(Array.isArray(x.interval) ? rangeText(x.interval, x.unit || "") : "—")}</p>
    </div>`).join("")}</div>
    <div class="table-wrap constraint-table-wrap"><table class="constraint-table">
      <thead><tr><th>约束</th><th>估算</th><th>限制</th><th>筛选区间</th><th>状态</th></tr></thead>
      <tbody>${rows.map((x) => `<tr>
        <td><b>${esc(x.label)}</b></td>
        <td>${value(x)}</td>
        <td>${limit(x)}</td>
        <td>${esc(Array.isArray(x.interval) ? rangeText(x.interval, x.unit || "") : "—")}</td>
        <td>${status(x)}</td>
      </tr>`).join("")}</tbody>
    </table></div><p class="fineprint">${esc(rows[0]?.basis || "")}。区间是筛选假设，不是统计置信区间。</p>`;
  }

  function renderMetricProvenance(sel) {
    const rows = sel.metric_provenance || [];
    return rows.map((x) => `<div class="note" style="margin-top:8px"><b>${esc(x.metric)}</b> <span class="badge">${esc(x.evidence_tier)}</span><br>
      <span style="font-size:12px">${esc(x.method)}</span><br>
      <span class="muted" style="font-size:11.5px">${esc(x.source)} · ${esc(x.confidence)}</span>
      <p class="fineprint" style="margin-top:4px">${esc(x.note || "")}</p></div>`).join("");
  }

  function renderReasoning(d, sel) {
    const r = d.reasoning || {};
    const block = (title, rows) => (rows && rows.length) ? `<div class="section-head" style="margin:16px 0 8px"><h3 style="font-size:15px">${title}</h3></div><ul class="list">${rows.map((x) => `<li>${esc(x.statement || x)} ${x.source ? `<span class="muted">(${esc(x.source)})</span>` : ""}</li>`).join("")}</ul>` : "";
    const changes = (sel.recipe_changes || []).map((x) => `<li><b>${esc(x.action)}</b> ${esc(x.ingredient)}${x.from_pct != null ? ` ${num(x.from_pct, 2)}% → ${num(x.to_pct, 2)}%` : ""} · ${esc(x.because || "")}</li>`).join("");
    return `${block("已知事实", r.facts)}${block("显式规则", r.rules)}${block("关键假设", r.assumptions)}${block("必须验证", r.validation_required)}
      ${changes ? `<div class="section-head" style="margin:16px 0 8px"><h3 style="font-size:15px">相对基础模板的改动</h3></div><ul class="list">${changes}</ul>` : ""}`;
  }

  function renderExplainer(d, sel) {
    const box = $("#result-explainer");
    if (!box) return;
    const biologic = d.mode === "biologic" || (!Array.isArray(d.portfolio) && d.selected);
    const m = sel.metrics || {};
    if (biologic) {
      box.innerHTML = `<summary><b>这张结果怎么读？</b><span class="muted">评分、保留率与验证边界</span></summary>
        <div class="explainer-body">
          <p><b>综合评分 ${pct(sel.score)}</b>：稳定性、光谱、安全性、亮度与成本的加权决策指数，<b>不是成功概率</b>。候选满足目标时只代表模型规则通过。</p>
          <p><b>有效 Tm ${num(m.tm_eff_c)} °C</b>：加入保护剂后的模型估计；<b>工艺后保留 ${pct(m.process_retention)}</b> 与 <b>总保留 ${pct(m.overall_retention)}</b> 来自数字孪生，不是实测。</p>
          <p><b>光谱</b>：λem ${num(m.em_nm, 0)} nm，Δλem ${num(m.spectral?.delta_em_nm, 2)} nm，谱形余弦 ${num(m.spectral?.shape_cosine, 3)}；仍须用分光光度计按固定狭缝/温度复核。</p>
          <p><b>MD/QM</b>：当前结果只生成验证协议或小体系检查，未完成生产级模拟，不能写成“已通过 MD/QM 验证”。</p>
        </div>`;
    } else {
      box.innerHTML = `<summary><b>这张结果怎么读？</b><span class="muted">决策指数、筛选区间与实测边界</span></summary>
        <div class="explainer-body">
          <p><b>综合评分 ${pct(sel.score)}</b>：多目标加权排序，不是概率，也不是感官/法规结论。</p>
          <p><b>约束状态</b>：<b>通过</b>只表示模型估算落在阈值内；<b>at_risk</b> 表示筛选区间跨过边界，需优先实测。</p>
          <p><b>占比与组成</b>：来自 curated 配方模板和 USDA FDC 参考映射；供应商批次、加工损失与地区法规仍需核验。</p>
          <p><b>来源</b>：${d.provenance?.citations?.length ? "结果附来源列表；引用前核对原文" : "策展数据与规则先验；不是系统综述"}。</p>
        </div>`;
    }
  }

  function renderDesign() {
    const d = state.design;
    if (!d) return;
    const biologic = d.mode === "biologic" || !Array.isArray(d.portfolio);
    const sel = biologic
      ? { ...(d.selected || {}), ...((d.candidates || [])[state.selected] || {}) }
      : ((d.portfolio && d.portfolio[state.selected]) || d.selected || {});
    $("#design-result").classList.remove("hidden");
    $("#design-empty").classList.add("hidden");
    if (biologic) {
      renderExplainer(d, sel);
      renderBiologic(d, sel);
      translateSubtree($("#page-design"));
      return;
    }
    const systemTitle = state.lang === "en"
      ? (d.system?.name || localizedText(d.system?.cn_name) || sel.system_cn || "Formulation")
      : (d.system?.cn_name || sel.system_cn || "配方");
    $("#result-title").textContent = `${systemTitle} · ${state.lang === "en" ? (sel.strategy_en || localizedText(sel.strategy_cn)) : (sel.strategy_cn || "候选方案")}`;
    const cstatus = sel.constraint_status || (sel.constraint_met ? "pass" : "fail");
    const ctext = cstatus === "pass" ? "全部硬约束通过" : cstatus === "at_risk" ? "约束存在区间风险" : "存在未达标约束";
    $("#result-sub").innerHTML = `${esc(d.brief?.query || "")} <span class="badge ${cstatus === "pass" ? "ok" : "warn"}" style="margin-left:8px">${ctext}</span> <span class="badge blue" style="margin-left:6px">证据等级 ${esc(sel.evidence_grade || "—")}</span> <span class="muted" style="margin-left:8px">${esc(d.design_id)}</span>`;

    renderExplainer(d, sel);
    $("#metric-grid").innerHTML = renderMetrics(sel.metrics || {}, sel.intervals || {});
    const heading = $("#candidate-heading");
    if (heading) heading.textContent = state.lang === "en" ? `${(d.portfolio || []).length} comparable candidates` : `${(d.portfolio || []).length} 个可比较候选`;
    const rail = $("#portfolio-rail");
    rail.innerHTML = (d.portfolio || []).map((c, i) => `
      <button class="candidate ${i === state.selected ? "active" : ""}" data-index="${i}">
        <span class="rank">候选 ${String(i + 1).padStart(2, "0")}</span>
        <h4>${esc(state.lang === "en" ? (c.strategy_en || localizedText(c.strategy_cn || c.strategy)) : (c.strategy_cn || c.strategy))}</h4>
        <span class="muted" style="font-size:11.5px">${esc(state.lang === "en" ? (c.strategy_note_en || localizedText(c.strategy_note || "")) : clipLocalized(c.strategy_note || "", 58, 96))}</span>
        <div class="score">${pct(c.score)}<small>score</small></div>
        <div class="mini">${candidateBadges(c)}</div>
      </button>`).join("");
    $$("[data-index]", rail).forEach((btn) => btn.addEventListener("click", () => {
      state.selected = Number(btn.dataset.index);
      renderDesign();
      $("#candidate-detail")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }));

    renderCandidate(sel, d);
    translateSubtree($("#page-design"));
  }

  function spectrumPath(xs, ys, width = 620, height = 170, pad = 24) {
    if (!Array.isArray(xs) || !Array.isArray(ys) || !xs.length || xs.length !== ys.length) return "";
    let xmin = Math.min(...xs), xmax = Math.max(...xs);
    let ymin = 0, ymax = Math.max(...ys, 1e-9);
    if (xmax <= xmin) xmax = xmin + 1;
    if (ymax <= ymin) ymax = ymin + 1;
    return xs.map((x, i) => {
      const px = pad + ((x - xmin) / (xmax - xmin)) * (width - pad * 2);
      const py = height - pad - ((ys[i] - ymin) / (ymax - ymin)) * (height - pad * 2);
      return `${i ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`;
    }).join(" ");
  }

  function spectrumSvg(fluorescence) {
    if (!fluorescence) return "";
    const wave = fluorescence.wavelength_nm || [];
    const ref = fluorescence.emission_reference || [];
    const stressed = fluorescence.emission_stressed || [];
    const uvWave = fluorescence.uvvis_wavelength_nm || [];
    const uvRef = fluorescence.uvvis_reference || [];
    const uvStress = fluorescence.uvvis_stressed || [];
    const emPath = spectrumPath(wave, ref);
    if (!emPath) return "";
    const stressPath = spectrumPath(wave, stressed);
    const uvPath = spectrumPath(uvWave, uvRef);
    const uvStressPath = spectrumPath(uvWave, uvStress);
    return `<div class="spectrum-chart-wrap">
      <svg class="spectrum-chart" viewBox="0 0 620 170" role="img" aria-label="数字孪生荧光与 UV-Vis 参考曲线">
        <defs><linearGradient id="spectrumFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--blue)" stop-opacity=".24"/><stop offset="1" stop-color="var(--blue)" stop-opacity="0"/></linearGradient></defs>
        <g class="spectrum-axis"><line x1="24" y1="146" x2="596" y2="146"/><line x1="24" y1="24" x2="24" y2="146"/></g>
        <path class="spectrum-uv" d="${uvPath}" />
        <path class="spectrum-uv stressed" d="${uvStressPath}" />
        <path class="spectrum-ref" d="${emPath}" />
        <path class="spectrum-stressed" d="${stressPath}" />
      </svg>
      <div class="spectrum-legend"><span><i class="ref"></i>发射参考</span><span><i class="stress"></i>工艺后（数字孪生）</span><span><i class="uv"></i>UV-Vis 参考</span></div>
    </div>`;
  }

  function spectraEvidenceLinks(sel) {
    const name = sel?.name || sel?.id || "";
    const cidMatch = String((sel?.references || []).join(" ")).match(/PubChem CID\s+(\d+)/i);
    const links = [];
    if (cidMatch) links.push([`PubChem CID ${cidMatch[1]}`, `https://pubchem.ncbi.nlm.nih.gov/compound/${cidMatch[1]}`]);
    else if (name) links.push(["PubChem 检索", `https://pubchem.ncbi.nlm.nih.gov/#query=${encodeURIComponent(name)}`]);
    if (name) {
      links.push(["NIST WebBook", `https://webbook.nist.gov/cgi/cbook.cgi?Name=${encodeURIComponent(name)}&Units=SI`]);
      links.push(["MassBank Europe", `https://massbank.eu/MassBank/Search?search=${encodeURIComponent(name)}`]);
      links.push(["HMDB", `https://hmdb.ca/unearth/q?query=${encodeURIComponent(name)}`]);
      links.push(["SDBS", "https://sdbs.db.aist.go.jp/sdbs/cgi-bin/direct_frame_top.cgi"]);
      links.push(["UniProt", `https://www.uniprot.org/uniprotkb?query=${encodeURIComponent(name)}`]);
    }
    return links.map(([label, url]) => `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>`).join("");
  }

  function renderSpectraCard(d, sel) {
    const spectra = d.spectra || {};
    const peaks = spectra.reference_peaks || [];
    const inv = spectra.invariance || {};
    const refs = (sel.references || []).filter(Boolean);
    return `<div class="detail-card card spectrum-card">
      <div class="section-head" style="margin:0 0 8px"><div><span class="eyebrow">SPECTRA · EVIDENCE</span><h3>光谱与参考峰</h3></div><span class="badge ${inv.meets_spec ? "ok" : "warn"}">${inv.meets_spec ? "模型阈值通过" : "需复核"}</span></div>
      <p class="subtle">${esc(spectra.note || "曲线由数字孪生生成；参考峰为本地近似的文献/数据库先验，不是同条件实测。")}</p>
      ${spectrumSvg(spectra.fluorescence)}
      <div class="job-result" style="margin-top:10px"><span>目标保留 ${pct(inv.target_retention)}</span><span>模型保留 ${pct(inv.intensity_retention)}</span><span>Δλem ${num(inv.delta_em_nm, 2)} nm</span><span>谱形余弦 ${num(inv.shape_cosine, 3)}</span></div>
      ${peaks.length ? `<div class="table-wrap" style="margin-top:10px"><table><thead><tr><th>类型</th><th>溶剂/条件</th><th>参考峰</th><th>级别</th><th>说明</th></tr></thead><tbody>${peaks.slice(0, 8).map((spec) => `<tr><td><b>${esc(spec.type)}</b></td><td>${esc(spec.solvent || "—")}</td><td>${(spec.peaks || []).slice(0, 10).map((peak) => `<span class="peak">${esc(peak[0])}${peak[1] != null ? ` (${num(peak[1], 2)})` : ""}</span>`).join(" ")}</td><td>${esc(spec.evidence_level || "approximate_reference")}</td><td>${esc(spec.notes || "")}</td></tr>`).join("")}</tbody></table></div>` : `<p class="fineprint" style="margin-top:10px">该候选暂无匹配的本地参考峰；可在“在线证据”中检索 PubChem/NIST/MassBank/SDBS，并核对仪器条件。</p>`}
      <div class="spectra-links" style="margin-top:10px">${spectraEvidenceLinks(sel)}</div>
      ${refs.length ? `<p class="fineprint"><b>候选来源：</b>${refs.map((ref) => esc(ref)).join(" · ")}。参考谱/文献条目需回到原始记录核对，不能当作同条件实测。</p>` : ""}
      <p class="fineprint">MS 需注明离子模式/碰撞能量，NMR 需注明溶剂/频率，IR 需注明样品制备；谱图证据必须能追溯到原始记录。</p>
    </div>`;
  }

  function renderBiologic(d, sel) {
    const m = sel.metrics || {};
    const candidates = d.candidates || [sel];
    const isCurrent = !candidates[state.selected] || sel.id === d.selected?.id;
    const f = isCurrent ? (d.formulation || {}) : { ...(d.formulation || {}), ingredients: (sel.blend || []).map((b) => ({
      name: b.name, cn_name: b.cn_name, pct: b.pct, role: b.role, role_cn: b.role_cn,
      food_safe: b.food_safe, note: b.notes_cn || b.notes,
    })) };
    const rows = f.ingredients || [];
    const candidateTitle = state.lang === "en" ? (sel.name || localizedText(sel.cn_name) || "Candidate") : (sel.cn_name || sel.name || "候选");
    $("#result-title").textContent = `${candidateTitle} · ${sel.kind === "protein" ? (state.lang === "en" ? "protein design" : "蛋白设计") : (state.lang === "en" ? "small-molecule design" : "小分子设计")}`;
    $("#result-sub").innerHTML = `${esc(d.brief?.query || "")} <span class="badge ${sel.meets_spec ? "ok" : "warn"}" style="margin-left:8px">${sel.meets_spec ? "目标模型通过" : "需复核"}</span> <span class="badge blue" style="margin-left:6px">评分 ${pct(sel.score)}</span> <span class="muted" style="margin-left:8px">${esc(d.design_id)}</span>`;
    const metrics = [
      ["综合评分", pct(sel.score), scoreClass(sel.score)],
      ["有效 Tm", `${num(m.tm_eff_c)} °C`, ""],
      ["工艺后保留", pct(m.process_retention), ""],
      ["总保留", pct(m.overall_retention), ""],
      ["亮度", m.brightness == null ? "—" : `×${num(m.brightness, 2)}`, ""],
      ["λem", `${num(m.em_nm, 0)} nm`, ""],
    ];
    $("#metric-grid").innerHTML = metrics.map(([label, value, cls]) => `<div class="metric ${cls}"><span>${label}</span><b>${value}</b></div>`).join("");
    const heading = $("#candidate-heading");
    if (heading) heading.textContent = state.lang === "en" ? `${candidates.length} comparable candidates` : `${candidates.length} 个可比较候选`;
    const rail = $("#portfolio-rail");
    rail.innerHTML = candidates.map((c, i) => `
      <button class="candidate ${i === state.selected ? "active" : ""}" data-index="${i}">
        <span class="rank">${esc(c.kind === "protein" ? "蛋白" : c.kind === "compound" ? "小分子" : "候选")} ${String(i + 1).padStart(2, "0")}</span>
        <h4>${esc(state.lang === "en" ? (c.name || localizedText(c.cn_name) || c.id) : (c.cn_name || c.name || c.id))}</h4>
        <span class="muted" style="font-size:11.5px">${esc(clipLocalized((c.rationale || [""])[0] || "", 58, 96))}</span>
        <div class="score">${pct(c.score)}<small>score</small></div>
        <div class="mini"><span class="badge ${c.meets_spec ? "ok" : "warn"}">${c.meets_spec ? "模型通过" : "待复核"}</span></div>
      </button>`).join("");
    $$("[data-index]", rail).forEach((btn) => btn.addEventListener("click", () => {
      state.selected = Number(btn.dataset.index);
      renderDesign();
      $("#candidate-detail")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }));
    const metricRows = Object.entries(m).filter(([, value]) => typeof value === "number" || typeof value === "string").slice(0, 18);
    const warnings = [...(sel.warnings || []), ...(d.warnings || [])].filter((v, i, a) => a.indexOf(v) === i);
    const rationale = (sel.rationale || []).map((x) => `<li>${esc(x)}</li>`).join("");
    const breakdown = sel.score_breakdown || {};
    const breakdownRows = Object.entries(breakdown).filter(([, value]) => typeof value === "number").map(([key, value]) => `<span class="badge">${esc(titleCase(key))} ${pct(value)}</span>`).join("");
    const controls = isCurrent ? (f.controls || []).map((x) => `<tr><td><b>${esc(x.parameter)}</b></td><td>${esc(x.target)}</td><td>${esc(x.why)}</td></tr>`).join("") : "";
    const qc = isCurrent ? (f.qc || []).map((x) => `<tr><td><b>${esc(x.test)}</b></td><td>${esc(x.method)}</td><td>${esc(x.acceptance)}</td><td>${esc(x.stage)}</td></tr>`).join("") : "";
    const process = isCurrent ? (f.process || []) : [];
    const ve = d.virtual_experiment || {};
    const mc = ve.monte_carlo || {};
    const detail = $("#candidate-detail");
    detail.innerHTML = `
      <div class="detail-card card">
        <div style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start">
          <div><h3>${state.lang === "en" ? "Candidate" : "候选"} · ${esc(state.lang === "en" ? (sel.name || localizedText(sel.cn_name)) : (sel.cn_name || sel.name))}</h3><p class="subtle">${esc(sel.kind || "biologic")} · ${esc(sel.type || "")} · ${esc(sel.id || "")}</p></div>
          <div style="text-align:right"><span class="badge ${sel.meets_spec ? "ok" : "warn"}">${pct(sel.score)}</span><br><span class="fineprint">决策指数，不是概率</span></div>
        </div>
        <p class="subtle">${esc((sel.rationale || [])[0] || "候选由约束筛选与保护剂组合优化生成。")}</p>
        ${rationale ? `<ul class="list">${rationale}</ul>` : ""}
        <div class="meta" style="display:flex;gap:6px;flex-wrap:wrap;margin:10px 0">${breakdownRows}</div>
        <div class="table-wrap"><table><thead><tr><th>指标</th><th>模型值</th></tr></thead><tbody>${metricRows.map(([key, value]) => `<tr><td>${esc(titleCase(key))}</td><td>${typeof value === "number" ? num(value, 3) : esc(value)}</td></tr>`).join("")}</tbody></table></div>
        ${warnings.length ? `<div class="section-head" style="margin:18px 0 8px"><h3 style="font-size:16px">风险与待验证</h3></div><ul class="list">${warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}
      </div>
      <div class="detail-card card">
        <h3>${state.lang === "en" ? `Protectant blend · ${rows.length} items` : `保护剂组合 · ${rows.length} 项`}</h3>
        <p class="subtle">配方原型 ${esc(f.name || "")} · ${esc(f.serving_basis || "")}</p>
        <div class="table-wrap"><table><thead><tr><th>成分</th><th>占比</th><th>角色</th><th>食品级</th><th>说明</th></tr></thead><tbody>${rows.map((x) => `<tr>
          <td><b>${esc(x.cn_name || x.name)}</b></td><td>${num(x.pct, 3)}%</td><td>${esc(x.role_cn || x.role || "")}</td><td>${x.food_safe ? "是" : x.food_safe === false ? "否" : "—"}</td><td>${esc(clipLocalized(x.note || "", 90, 150))}</td>
        </tr>`).join("")}</tbody></table></div>
        <div class="section-head" style="margin:18px 0 8px"><h3 style="font-size:16px">工艺</h3></div>
        <div class="steps">${process.map((p) => `<div class="step"><i>${p.step}</i><div><b>${esc(p.title)}</b><p>${esc(p.detail)}</p></div></div>`).join("") || '<p class="muted">该候选仅展示保护剂组合；完整工艺卡属于当前选中候选。</p>'}</div>
      </div>
      <div class="detail-card card">
        <h3>数字孪生与验证</h3>
        <div class="job-result"><span>工艺后保留 ${pct(m.process_retention)}</span><span>货架后保留 ${pct(m.storage_retention)}</span><span>总保留 ${pct(m.overall_retention)}</span>${mc.prob_meet_target != null ? `<span>模型达到目标概率 ${pct(mc.prob_meet_target)}</span>` : ""}</div>
        <p class="subtle" style="margin-top:10px">${esc(isCurrent ? (f.storage || "") : "")}</p>
        <p class="fineprint">${esc(f.cost_note || "")}</p>
        ${controls ? `<div class="section-head" style="margin:18px 0 8px"><h3 style="font-size:16px">控制点</h3></div><div class="table-wrap"><table><thead><tr><th>参数</th><th>目标</th><th>原因</th></tr></thead><tbody>${controls}</tbody></table></div>` : ""}
        ${qc ? `<div class="section-head" style="margin:18px 0 8px"><h3 style="font-size:16px">QC 与验收</h3></div><div class="table-wrap"><table><thead><tr><th>项目</th><th>方法</th><th>验收</th><th>阶段</th></tr></thead><tbody>${qc}</tbody></table></div>` : ""}
      </div>
      <div class="detail-card card">
        <h3>推理链与边界</h3>
        <ul class="list">${(d.decision_summary || []).slice(0, 7).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
        <div class="section-head" style="margin:18px 0 8px"><h3 style="font-size:16px">数据版本</h3></div>
        <p class="fineprint">${esc(d.provenance?.engine_version ? `生物引擎 ${d.provenance.engine_version} · 包 ${d.provenance.package_version}` : "")} · ${esc((d.provenance?.datasets ? Object.keys(d.provenance.datasets).length : 0))} 个策展数据集</p>
        <p class="fineprint">${esc((f.regulatory || []).join(" · ") || "研究用途；任何食品、临床或法规用途都需要有资质团队验证。")}</p>
      </div>`;
    if (isCurrent && d.spectra) detail.insertAdjacentHTML("beforeend", renderSpectraCard(d, sel));
  }

  function renderProcessing(processing) {
    if (!processing || !processing.effects?.length) return `<p class="muted">当前候选没有加工变化预测。</p>`;
    const conditions = processing.conditions || {};
    const levelNames = { high: "高影响", medium: "中影响", low: "低影响" };
    const macro = processing.macro || [];
    return `<div class="processing-block">
      <div class="job-result"><span>温度 ${num(conditions.temperature_c, 0)} °C</span><span>时间 ${num(conditions.time_min, 1)} min</span><span>pH ${num(conditions.ph, 2)}</span><span>aw ${num(conditions.aw, 2)}</span><span>热负荷 ${num(conditions.heat_load_c_min, 0)} °C·min</span></div>
      <p class="subtle">${esc(processing.summary || "")}</p>
      <div class="processing-effects">${processing.effects.map((effect) => `
        <div class="processing-effect ${esc(effect.level)}">
          <div class="processing-effect-head"><b>${esc(effect.component)}</b><span class="badge ${effect.level === "high" ? "warn" : ""}">${esc(levelNames[effect.level] || effect.level)}</span></div>
          <p><strong>${esc(effect.change)}</strong></p>
          <p>${esc(effect.mechanism)}</p>
          <p class="fineprint"><b>宏观：</b>${esc(effect.macro)}</p>
          <p class="fineprint"><b>验证：</b>${esc(effect.validation)}</p>
          <details><summary>证据 ${effect.evidence?.length || 0} 条</summary>${(effect.evidence || []).map((ref) => `<p class="fineprint">${ref.url ? `<a href="${esc(ref.url)}" target="_blank" rel="noopener noreferrer">${esc(ref.label)} ↗</a>` : esc(ref.label)}</p>`).join("")}</details>
        </div>`).join("")}</div>
      <div class="processing-macro">${macro.map((row) => `<div><span>${esc(row.quality)}</span><b>${esc(row.prediction)}</b><small>${esc(row.basis)}</small></div>`).join("")}</div>
      <p class="note">${esc(processing.boundary || "")}</p>
      <p class="fineprint">${esc(processing.evidence_note || "")}</p>
    </div>`;
  }

  function renderCandidate(sel, d) {
    const f = d.formulation || {};
    const ings = f.ingredients || sel.ingredients || [];
    const process = f.process || sel.process || [];
    const processing = sel.processing_effects || d.processing || {};
    const m = sel.metrics || {};
    const positive = m.positive_interactions || [];
    const negative = m.negative_interactions || [];
    const warnings = [...(f.warnings || []), ...(d.warnings || [])].filter((v, i, a) => a.indexOf(v) === i);
    const citations = d.provenance?.citations || [];
    const detail = $("#candidate-detail");
    detail.innerHTML = `
      <div class="detail-card card">
        <div style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start">
          <div><h3>${state.lang === "en" ? "Formulation" : "配方"} · ${esc(state.lang === "en" ? (sel.strategy_en || localizedText(sel.strategy_cn || "")) : (sel.strategy_cn || ""))}</h3><p class="subtle">${state.lang === "en" ? `Per 100 g / 100 mL · ${ings.length} ingredients` : `以 100 g / 100 mL 计 · ${ings.length} 项配料`}</p></div>
          <div style="text-align:right"><span class="badge ${sel.constraint_status === "pass" ? "ok" : "warn"}">${pct(sel.score)}</span><br><span class="fineprint">决策指数，不是概率</span></div>
        </div>
        <div class="table-wrap"><table>
          <thead><tr><th>配料</th><th>占比</th><th>角色</th><th>组成来源</th><th class="notes-col">说明</th></tr></thead>
          <tbody>${ings.map((x) => `<tr>
            <td><b>${esc(state.lang === "en" ? (x.name || localizedText(x.cn_name)) : (x.cn_name || x.name))}</b>${x.food_additive ? ' <span class="badge warn">添加剂</span>' : ""}${x.allergen ? ' <span class="badge no">过敏原</span>' : ""}</td>
            <td class="pct">${num(x.pct, 2)}%</td>
            <td class="role">${esc(localizedText(x.role_cn || x.role || ""))}</td>
            <td class="role">${x.fdc_id ? `FDC ${esc(x.fdc_id)}` : "estimate"}</td>
            <td class="role notes-col">${esc(clipLocalized(x.notes_cn || "", 64, 108))}</td>
          </tr>`).join("")}</tbody>
        </table></div>
        <p class="fineprint">组成：USDA FDC SR Legacy 覆盖 ${num(sel.composition?.mapped_mass_pct, 1)}% 配方质量；${esc(sel.composition?.estimated_ingredients || 0)} 个配料使用 curated estimate。FDC 是参考数据，不是供应商批次实测。</p>
        <div class="section-head" style="margin:20px 0 10px"><h3 style="font-size:16px">工艺</h3></div>
        <div class="steps">${process.map((p) => `<div class="step"><i>${p.step}</i><div><b>${esc(p.title)}</b><p>${esc(p.detail)}</p></div></div>`).join("") || '<p class="muted">该候选仅展示保护剂组合；完整工艺卡属于当前选中候选。</p>'}</div>
      </div>
      <div class="detail-card card">
        <div style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start"><div><h3>加工条件与分子变化</h3><p class="subtle">机理规则 + 文献先验的方向性预测；不是本配方实测。</p></div><span class="badge model">MODEL</span></div>
        ${renderProcessing(processing)}
      </div>
      <div class="detail-card card">
        <h3>为什么是这个组合</h3>
        <p class="subtle">${esc(state.lang === "en" ? (sel.strategy_note_en || localizedText(sel.strategy_note || "")) : (sel.strategy_note || ""))}</p>
        <ul class="list">${(d.decision_summary || []).slice(0, 6).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
        <div class="section-head" style="margin:20px 0 10px"><h3 style="font-size:16px">相互作用</h3></div>
        ${positive.length ? positive.map((x) => `<div class="note good"><b>+ ${esc(x.a_cn)} × ${esc(x.b_cn)}</b><br>${esc(x.mechanism_cn)} <span class="muted">(${esc(x.evidence || "")})</span></div>`).join("") : '<p class="muted">未检出显著正向作用。</p>'}
        ${negative.length ? negative.map((x) => `<div class="note bad"><b>− ${esc(x.a_cn)} × ${esc(x.b_cn)}</b><br>${esc(x.mechanism_cn)} <span class="muted">(${esc(x.evidence || "")})</span></div>`).join("") : ""}
        ${warnings.length ? `<div class="section-head" style="margin:20px 0 8px"><h3 style="font-size:16px">风险与待验证</h3></div><ul class="list">${warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}
        <div class="section-head" style="margin:20px 0 8px"><h3 style="font-size:16px">来源</h3></div>
        <p class="fineprint">${citations.length ? citations.map(esc).join(" · ") : "curated food system / ingredient / interaction priors"}</p>
        <p class="fineprint">${esc(d.provenance?.local?.[0]?.note || "配方为数字原型；法规、过敏原和微生物安全需实测与当地法规核验。")}</p>
      </div>
      <div class="detail-card card">
        <h3>约束审计</h3>
        <p class="subtle">硬约束逐项展示点估计、筛选区间和状态；<b>at_risk</b> 表示区间跨过边界，必须实测复核。</p>
        ${renderConstraintReport(sel)}
        <div class="section-head" style="margin:20px 0 8px"><h3 style="font-size:16px">指标是怎么来的</h3></div>
        ${renderMetricProvenance(sel)}
      </div>
      <div class="detail-card card">
        <h3>推理链与证据边界</h3>
        <p class="subtle">事实、规则、假设和待验证项分开记录；不使用随机数挑选配料。</p>
        ${renderReasoning(d, sel)}
      </div>`;
  }

  async function graphDesign() {
    if (!state.design) { toast("请先生成一个配方。"); return; }
    state.graphView = true;
    setPage("evidence");
    const box = $("#evidence-output");
    box.innerHTML = `<div class="card loading-card"><span class="spinner"></span><div><b>正在构建证据图谱</b><p class="muted">配料、相互作用、约束与来源。</p></div></div>`;
    try {
      const graph = await api("/api/v2/graph", { method: "POST", body: JSON.stringify({ design_id: state.design.design_id, online: state.evidence || undefined }) });
      state.graph = graph;
      renderGraph(graph);
    } catch (err) {
      if (err.message !== "unauthorized") box.innerHTML = `<div class="card detail-card"><p class="muted">${esc(err.message)}</p></div>`;
    }
  }

  const GRAPH_W = 980, GRAPH_H = 520;
  const GRAPH_EDGE_NAMES = {
    targets_system: "靶向体系", selects_candidate: "选择候选", selects_strategy: "选择策略",
    uses: "使用配料", formulates_with: "配伍", interaction: "相互作用", supported_by: "由证据支持",
    mechanism_note: "机制说明", starts: "起点", next: "下一步", completes: "完成", constraint: "约束",
    contains: "包含记录", candidate_evidence: "候选证据", exact_inchikey: "精确结构映射",
    uniprot_pdb_xref: "UniProt→PDB", spectrum_reference: "谱图参考", starts_process: "开始工艺",
    next_process: "下一步工艺", predicts_change: "预测变化", mentions: "提及", authored_by: "作者",
    published_in: "发表于",
  };
  const GRAPH_FIELD_NAMES = {
    pct: "占比", role: "角色", score: "评分", status: "状态", detail: "详情", source: "来源",
    license: "许可", note: "说明", name: "名称", meets_spec: "满足目标", mechanism: "机制",
    macro: "宏观影响", validation: "验证建议", level: "影响强度", relevance: "相关度",
    strength: "证据强度", retrieved_at: "检索时间", match_basis: "匹配依据", url: "原始链接",
    step: "步骤", caveat: "边界", confidence: "置信度", value: "值", query: "查询",
  };

  function graphKind(node) { return node.kind || node.type || "other"; }

  function graphVisible(node) {
    const kind = graphKind(node);
    if ((kind === "data_source" || kind === "online_source" || kind === "online_record") && state.graphShowSources === false) return false;
    if ((kind === "process" || kind === "processing" || kind === "processing_effect") && state.graphShowSteps === false) return false;
    return true;
  }

  function graphNodeRadius(kind, degree = 0) {
    if (kind === "design") return 21;
    if (["food_system", "system", "protein", "biologic_target"].includes(kind)) return 14;
    if (["candidate", "strategy", "processing_effect"].includes(kind)) return 11;
    if (kind === "process" || kind === "processing") return 8;
    return 7 + Math.min(3, degree * 0.25);
  }

  function graphLayout(graph) {
    const nodes = graph.nodes || [];
    const edges = graph.edges || [];
    const activeNodes = nodes.filter(graphVisible);
    const activeIds = new Set(activeNodes.map((node) => node.id));
    const activeEdges = edges.filter((edge) => activeIds.has(edge.from) && activeIds.has(edge.to));
    const degree = {};
    activeEdges.forEach((edge) => { degree[edge.from] = (degree[edge.from] || 0) + 1; degree[edge.to] = (degree[edge.to] || 0) + 1; });
    const cx = GRAPH_W / 2, cy = GRAPH_H / 2;
    const kindRadius = {
      design: 0, food_system: 100, system: 100, protein: 100, biologic_target: 100,
      candidate: 125, strategy: 125, ingredient: 175, excipient: 175, target: 195,
      process: 225, processing: 250, processing_effect: 290,
      mechanism: 220, literature: 230, data_source: 315, online_source: 315, online_record: 270,
    };
    const buckets = {};
    activeNodes.forEach((node) => { const kind = graphKind(node); (buckets[kind] = buckets[kind] || []).push(node); });
    const positions = new Map();
    const now = performance.now();
    let order = 0;
    Object.entries(buckets).forEach(([kind, items]) => {
      const radius = kindRadius[kind] ?? 235;
      items.forEach((node, index) => {
        const angle = (index / Math.max(1, items.length)) * Math.PI * 2 + (radius % 2 ? 0.35 : 0);
        const tx = cx + Math.cos(angle) * radius;
        const ty = cy + Math.sin(angle) * radius * 0.72;
        const jitter = kind === "design" ? 0 : 7;
        positions.set(node.id, {
          x: kind === "design" ? cx : cx + Math.cos(angle + index * 0.11) * 14 + jitter * Math.sin(index * 1.7),
          y: kind === "design" ? cy : cy + Math.sin(angle + index * 0.11) * 12 + jitter * Math.cos(index * 1.3),
          vx: 0, vy: 0, tx, ty,
          fixed: kind === "design",
          appear: now + order * 18,
        });
        order += 1;
      });
    });
    return { W: GRAPH_W, H: GRAPH_H, positions, activeNodes, activeEdges, degree, center: activeNodes.find((node) => graphKind(node) === "design") };
  }

  function openExternal(url, label) {
    if (typeof url !== "string" || !/^https?:\/\//i.test(url)) { toast(`${label || "该节点"}没有可打开的外部链接。`); return; }
    window.open(url, "_blank", "noopener,noreferrer");
  }

  function graphCitations(item) {
    if (Array.isArray(item.citations) && item.citations.length) return item.citations;
    if (Array.isArray(item.evidence)) return item.evidence.map((label) => ({ label }));
    if (typeof item.evidence === "string" && item.evidence) return [{ label: item.evidence }];
    return [];
  }

  function graphCitationMarkup(citations, fallback = "该节点/关系没有附带可公开链接的证据；请把它当作流程或待核对线索。") {
    if (!citations.length) return `<p class="graph-empty-evidence">${esc(fallback)}</p>`;
    return `<div class="graph-evidence-list">${citations.slice(0, 12).map((citation) => {
      const label = typeof citation === "string" ? citation : (citation.label || citation.source || "证据");
      const source = typeof citation === "string" ? "" : (citation.source || citation.verified_by || "");
      const meta = [source, citation.confidence, citation.retrieved_at ? `检索 ${String(citation.retrieved_at).slice(0, 10)}` : "", citation.match_basis].filter(Boolean).join(" · ");
      return `<div class="graph-evidence-item"><div><b>${esc(label)}</b>${meta ? `<span>${esc(meta)}</span>` : ""}</div>${citation.url ? `<a href="${esc(citation.url)}" target="_blank" rel="noopener noreferrer">打开来源 ↗</a>` : ""}</div>`;
    }).join("")}</div>`;
  }

  function graphFields(node) {
    const fields = ["pct", "role", "score", "status", "level", "confidence", "source", "license", "name", "meets_spec", "relevance", "strength", "retrieved_at", "match_basis", "step", "value", "detail", "mechanism", "macro", "validation", "note", "caveat"];
    return fields.filter((key) => node[key] != null && node[key] !== "" && !(Array.isArray(node[key]) && !node[key].length));
  }

  function graphRelatedMarkup(id, edges, nodeMap) {
    return edges.filter((edge) => edge.from === id || edge.to === id).slice(0, 18).map((edge) => {
      const other = nodeMap.get(edge.from === id ? edge.to : edge.from);
      const direction = edge.from === id ? "→" : "←";
      return `<button type="button" class="graph-relation" data-edge-id="${esc(edge.id)}"><span>${direction} ${esc(localizedText(other?.label || "?"))}</span><small>${esc(localizedText(edge.label || GRAPH_EDGE_NAMES[edge.type] || edge.type))}</small></button>`;
    }).join("");
  }

  function renderGraphDefaultInspector(graph) {
    const semantics = graph.semantics || {};
    const edgeTypes = semantics.edge_types || {};
    const confidenceNames = { workflow: "流程", curated: "策展", verified: "已验证", model: "模型", online: "在线", reference: "参考" };
    $("#graph-inspector").innerHTML = `<div class="graph-inspector-empty">
      <span class="eyebrow">READ THE NETWORK</span>
      <h4>节点和边分别是什么意思？</h4>
      <p>${esc(semantics.node || "节点是设计对象、配料、工艺步骤或证据记录。")}</p>
      <p>${esc(semantics.edge || "边是关系；点击边查看语义、来源和置信度。")}</p>
      <p class="fineprint">${esc(semantics.rule || "")}</p>
      <p class="fineprint">${esc(semantics.provenance || "")}</p>
      <div class="graph-confidence-legend">${Object.entries(confidenceNames).map(([key, label]) => `<span class="badge ${key}">${esc(label)}</span>`).join("")}</div>
      <p class="fineprint">双击节点打开右侧完整证据；点击“打开来源”才跳转到原始链接。</p>
    </div>`;
    translateSubtree($("#graph-inspector"));
  }

  function renderNodeInspector(node, graph, related, nodeMap) {
    const kind = graphKind(node);
    const fields = graphFields(node);
    const citations = graphCitations(node);
    const isProcess = kind === "process" || kind === "processing";
    $("#graph-inspector").innerHTML = `<div class="graph-inspector-head">
      <div><span class="eyebrow">节点详情</span><h4>${esc(localizedText(node.label))}</h4><p>${esc(localizedText(graphLabel(kind)))} · ${related.length} 条关系${node.confidence ? ` · 置信度 ${esc(localizedText(node.confidence))}` : ""}</p></div>
      <button type="button" class="btn ghost small" id="graph-inspector-close" aria-label="关闭详情">×</button>
    </div>
    <p class="graph-meaning">${esc(localizedText(node.meaning || ""))}</p>
    ${fields.length ? `<div class="graph-field-grid">${fields.map((key) => `<div><span>${esc(localizedText(GRAPH_FIELD_NAMES[key] || titleCase(key)))}</span><b>${esc(localizedText(String(node[key]).slice(0, 220)))}</b></div>`).join("")}</div>` : ""}
    ${isProcess ? `<p class="graph-caveat">这是流程/工艺步骤，不是外部实验证据；它的作用是把下一步和输入输出讲清楚。</p>` : ""}
    <div class="graph-inspector-section"><h5>证据与来源</h5>${graphCitationMarkup(citations, isProcess ? "该步骤由当前配方模板生成，没有独立外部证据；请用中试或 QC 验收。" : "该节点没有附带的公开证据链接；请核对本地策展来源。")}</div>
    ${related.length ? `<div class="graph-inspector-section"><h5>相连节点与关系</h5><div class="graph-related">${graphRelatedMarkup(node.id, related, nodeMap)}</div></div>` : ""}
    ${node.url ? `<div class="graph-inspector-actions"><a class="btn ghost small" href="${esc(node.url)}" target="_blank" rel="noopener noreferrer">打开原始记录 ↗</a></div>` : ""}`;
    translateSubtree($("#graph-inspector"));
  }

  function renderEdgeInspector(edge, nodeMap) {
    const from = nodeMap.get(edge.from), to = nodeMap.get(edge.to);
    const citations = graphCitations(edge);
    const statusNames = { workflow: "流程关系", curated: "本地策展", verified: "标识符级验证", online: "本次在线记录", reference: "参考记录", model: "模型预测", unknown: "来源未知" };
    const status = edge.evidence_status || edge.confidence || "unknown";
    $("#graph-inspector").innerHTML = `<div class="graph-inspector-head">
      <div><span class="eyebrow">关系详情</span><h4>${esc(localizedText(from?.label || edge.from))} → ${esc(localizedText(to?.label || edge.to))}</h4><p>${esc(localizedText(edge.label || GRAPH_EDGE_NAMES[edge.type] || edge.type))} · ${esc(localizedText(statusNames[status] || status))}</p></div>
      <button type="button" class="btn ghost small" id="graph-inspector-close" aria-label="关闭详情">×</button>
    </div>
    <p class="graph-meaning">${esc(localizedText(edge.meaning || GRAPH_EDGE_NAMES[edge.type] || "关系边。"))}</p>
    ${edge.basis ? `<p class="graph-caveat"><b>来源依据：</b>${esc(localizedText(edge.basis))}</p>` : ""}
    ${edge.mechanism ? `<p class="graph-caveat"><b>机制/说明：</b>${esc(localizedText(edge.mechanism))}</p>` : ""}
    ${edge.effect != null ? `<div class="graph-field-grid"><div><span>方向性权重</span><b>${esc(edge.effect)}</b></div><div><span>符号</span><b>${esc(edge.sign || "—")}</b></div></div>` : ""}
    ${edge.caveat ? `<p class="graph-caveat">${esc(localizedText(edge.caveat))}</p>` : ""}
    <div class="graph-inspector-section"><h5>这条边的证据</h5>${graphCitationMarkup(citations, edge.type === "next" || edge.type === "next_process" ? "这是顺序边，不自动证明因果；请查看相邻步骤的详情。" : (edge.caveat || "该关系没有附带公开链接；请核对本地策展依据。"))}</div>
    <div class="graph-inspector-section"><h5>两端节点</h5><div class="graph-related"><button type="button" class="graph-relation" data-node-jump="${esc(edge.from)}"><span>← ${esc(localizedText(from?.label || edge.from))}</span><small>${esc(localizedText(graphLabel(graphKind(from || {}))))}</small></button><button type="button" class="graph-relation" data-node-jump="${esc(edge.to)}"><span>${esc(localizedText(to?.label || edge.to))} →</span><small>${esc(localizedText(graphLabel(graphKind(to || {}))))}</small></button></div></div>`;
    translateSubtree($("#graph-inspector"));
  }

  function graphColor(kind, mode = "kind", degree = 0, node = {}) {
    if (mode === "degree") {
      const hue = Math.max(18, 210 - Math.min(190, degree * 14));
      return `hsl(${hue} 72% 54%)`;
    }
    if (mode === "status") {
      if (node.status === "planned") return "#8e8e93";
      if (node.status === "error") return "#d92c2c";
      if (node.status === "computed") return "#0071e3";
    }
    return ({
      design: "#0071e3", food_system: "#6e56cf", system: "#6e56cf", protein: "#6e56cf",
      compound: "#0a84ff", biologic_target: "#6e56cf", candidate: "#c46a00", strategy: "#c46a00",
      ingredient: "#1d9a52", excipient: "#30a46c", target: "#d92c2c", constraint: "#d92c2c",
      process: "#0a84ff", processing: "#5e5ce6", processing_effect: "#bf5af2",
      mechanism: "#8e44ad", data_source: "#86868b", online_source: "#0a84ff",
      literature: "#8e8e93", online_record: "#0a84ff",
    })[kind] || "#86868b";
  }

  function graphLabel(kind) {
    return ({
      design: "设计", food_system: "食品体系", system: "体系", protein: "蛋白", compound: "小分子",
      biologic_target: "生物靶点", candidate: "候选", strategy: "策略", ingredient: "配料",
      excipient: "保护剂", target: "约束", process: "推理步骤", processing: "工艺步骤",
      processing_effect: "加工变化预测", mechanism: "机制", source: "来源", data_source: "数据源",
      online_source: "在线源", literature: "文献", online_record: "在线记录", constraint: "约束",
    })[kind] || kind || "节点";
  }

  function renderGraph(graph) {
    cancelAnimationFrame(state.graphAnim);
    const nodes = graph.nodes || [];
    const edges = graph.edges || [];
    const sameDesign = state.graphPositions?.designId === graph.design_id;
    state.graphPositions = { designId: graph.design_id, ...graphLayout(graph) };
    state.graphShowSources = state.graphShowSources !== false;
    state.graphShowSteps = state.graphShowSteps !== false;
    state.graphColorMode = state.graphColorMode || "kind";
    state.graphLegendSignature = null;
    if (!sameDesign) { state.graphSelected = null; state.graphSelectedEdge = null; state.graphZoom = 1; state.graphPanX = 0; state.graphPanY = 0; }
    state.graphSelected = state.graphSelected && nodes.some((node) => node.id === state.graphSelected && graphVisible(node)) ? state.graphSelected : null;
    state.graphSelectedEdge = state.graphSelectedEdge && edges.some((edge) => edge.id === state.graphSelectedEdge) ? state.graphSelectedEdge : null;
    const summary = graph.summary || {};
    $("#evidence-output").innerHTML = `
      <div class="card detail-card graph-card" style="margin-top:16px">
        <div class="graph-toolbar"><div><span class="eyebrow">INTERACTIVE EVIDENCE GRAPH</span><h3 style="margin:3px 0 0">${esc(state.design?.system?.cn_name || state.design?.selected?.cn_name || state.design?.selected?.name || "设计")} 的证据网络</h3><p class="fineprint" style="margin:4px 0 0">拖拽节点会牵拉相连节点 · 滚轮/双指缩放 · 点击聚焦 · 双击打开证据 · 点击边看关系</p></div><div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap"><button type="button" id="graph-back" class="btn ghost small">返回在线检索</button><span class="badge blue">${nodes.length} 节点 · ${edges.length} 边</span></div></div>
        <div class="graph-controls">
          <label>着色<select id="graph-color-mode"><option value="kind">按类型</option><option value="degree">按连接度</option><option value="status">按计算状态</option></select></label>
          <label class="check"><input id="graph-show-sources" type="checkbox" ${state.graphShowSources ? "checked" : ""}> 数据源/在线记录</label>
          <label class="check"><input id="graph-show-steps" type="checkbox" ${state.graphShowSteps ? "checked" : ""}> 推理链/工艺</label>
          <span class="graph-view-actions"><button type="button" class="btn ghost small" id="graph-fit">适应视图</button><button type="button" class="btn ghost small" id="graph-relayout">重新布局</button></span>
        </div>
        <div class="graph-canvas" id="graph-stage">
          <svg id="graph-svg" viewBox="0 0 ${GRAPH_W} ${GRAPH_H}" role="img" aria-label="可缩放、可拖拽的证据图谱">
            <defs><marker id="graph-arrow" viewBox="0 0 10 10" refX="18" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#8e8e93" opacity=".6"/></marker></defs>
            <g id="graph-viewport"><g id="graph-edges"></g><g id="graph-nodes"></g></g>
          </svg>
          <div id="graph-tooltip" class="graph-tooltip hidden"></div>
        </div>
        <div class="graph-workbench">
          <div id="graph-detail" class="graph-detail"><p class="muted">点击节点聚焦并查看解释；双击节点打开完整证据；点击边查看关系语义。</p></div>
          <aside id="graph-inspector" class="graph-inspector" aria-live="polite"></aside>
        </div>
        <details class="graph-dictionary" open>
          <summary>节点 / 关系图例与定义 <span>点击展开，再点任一项查看含义</span></summary>
          <div class="graph-dictionary-body">
            <div class="graph-legend" id="graph-legend"></div>
            <div class="graph-legend graph-edge-legend" id="graph-edge-legend"></div>
            <div id="graph-type-panel" class="graph-type-panel"><p class="muted">点击节点类型或关系类型，查看定义、来源状态与当前数量。</p></div>
          </div>
        </details>
        <div class="graph-semantics"><b>怎么读：</b>${esc(graph.semantics?.rule || "流程边不是因果；模型边必须实测；在线记录需打开原始链接核对。")}</div>
        <div class="job-result">${Object.entries(summary).map(([key, value]) => `<span>${esc(titleCase(key))}: ${esc(value)}</span>`).join("")}</div>
        <p class="fineprint">节点颜色 = 类型；节点大小 = 连接度。图谱由当前设计结果和 curated 数据实时构图；在线记录只有在检索后才会出现。</p>
      </div>`;
    $("#graph-color-mode").value = state.graphColorMode;
    $("#graph-back")?.addEventListener("click", () => { state.graphView = false; state.graphAnim && cancelAnimationFrame(state.graphAnim); runEvidence($("#evidence-query")?.value || "quercetin"); });
    const provenanceNames = { workflow: "流程", curated: "策展", verified: "已验证", online: "在线", reference: "参考", model: "模型", unknown: "未知" };
    const edgeTypeInfo = graph.semantics?.edge_types || {};
    const edgeTypeCounts = {};
    edges.forEach((edge) => { edgeTypeCounts[edge.type] = (edgeTypeCounts[edge.type] || 0) + 1; });
    $("#graph-edge-legend").innerHTML = Object.keys(edgeTypeCounts).map((type) => {
      const info = edgeTypeInfo[type] || {};
      return `<button type="button" data-edge-type="${esc(type)}" title="${esc(localizedText(info.meaning || type))}">━ ${esc(localizedText(info.label || GRAPH_EDGE_NAMES[type] || type))} <b>${edgeTypeCounts[type]}</b></button>`;
    }).join("");
    translateSubtree($("#graph-edge-legend"));
    const showTypeInfo = (kind = null, type = null) => {
      const panel = $("#graph-type-panel");
      if (!panel) return;
      if (kind) {
        const count = nodes.filter((node) => graphKind(node) === kind).length;
        panel.innerHTML = `<p><b>${esc(localizedText(graphLabel(kind)))}</b> · ${count} 个节点<br>${esc(localizedText(graph.semantics?.node_types?.[kind] || "该类型节点表示设计对象或证据线索。"))}</p>`;
        translateSubtree(panel);
      } else if (type) {
        const info = edgeTypeInfo[type] || {};
        const count = edgeTypeCounts[type] || 0;
        const status = info.confidence || "unknown";
        panel.innerHTML = `<p><b>${esc(localizedText(info.label || GRAPH_EDGE_NAMES[type] || type))}</b> · ${count} 条边 · ${esc(localizedText(provenanceNames[status] || status))}<br>${esc(localizedText(info.meaning || "关系边。"))}<br><span class="fineprint">${esc(localizedText(graph.semantics?.provenance || "每条边都带来源状态；没有引用的边不能当作实验证据。"))}</span></p>`;
        translateSubtree(panel);
      }
    };
    $("#graph-legend").addEventListener("click", (event) => {
      const button = event.target.closest("[data-kind]");
      if (!button) return;
      $$("#graph-legend [data-kind]").forEach((item) => item.classList.toggle("active", item === button));
      showTypeInfo(button.dataset.kind, null);
    });
    $("#graph-edge-legend").addEventListener("click", (event) => {
      const button = event.target.closest("[data-edge-type]");
      if (!button) return;
      $$("#graph-edge-legend [data-edge-type]").forEach((item) => item.classList.toggle("active", item === button));
      showTypeInfo(null, button.dataset.edgeType);
    });
    const svg = $("#graph-svg"), viewport = $("#graph-viewport"), stage = $("#graph-stage");
    const nodeMap = new Map(nodes.map((node) => [node.id, node]));
    const edgeMap = new Map();
    edges.forEach((edge, index) => { if (!edge.id) edge.id = `edge:${index + 1}`; edgeMap.set(edge.id, edge); });
    const activeNodes = state.graphPositions.activeNodes;
    const activeEdges = state.graphPositions.activeEdges.map((edge) => edgeMap.get(edge.id) || { ...edge, id: `edge:local-${Math.random()}` });
    const activeIds = new Set(activeNodes.map((node) => node.id));
    const positions = state.graphPositions.positions;
    const degree = state.graphPositions.degree;
    const applyTransform = () => { viewport.setAttribute("transform", `translate(${state.graphPanX} ${state.graphPanY}) scale(${state.graphZoom})`); };
    const labelKinds = new Set(["design", "food_system", "system", "protein", "biologic_target", "candidate", "strategy", "process", "processing", "ingredient", "excipient", "processing_effect"]);

    const edgeMarkup = activeEdges.map((edge) => {
      const label = localizedText(edge.label || GRAPH_EDGE_NAMES[edge.type] || edge.type);
      return `<g class="graph-edge" data-edge-id="${esc(edge.id)}"><line class="graph-edge-hit" x1="0" y1="0" x2="0" y2="0" stroke="transparent" stroke-width="14"></line><line class="graph-edge-line" x1="0" y1="0" x2="0" y2="0" stroke="#8e8e93" stroke-width="1.2" marker-end="url(#graph-arrow)"><title>${esc(label)} · ${esc(localizedText("点击查看关系与证据"))}</title></line></g>`;
    }).join("");
    const nodeMarkup = activeNodes.map((node) => {
      const kind = graphKind(node);
      const radius = graphNodeRadius(kind, degree[node.id] || 0);
      const nodeLabel = localizedText(node.label);
      return `<g class="graph-node" data-node-id="${esc(node.id)}" tabindex="0" role="button" aria-label="${esc(nodeLabel)}">
        <circle cx="0" cy="0" r="${radius}" fill="${graphColor(kind, state.graphColorMode, degree[node.id] || 0, node)}" stroke="var(--bg)" stroke-width="2"><title>${esc(nodeLabel)} · ${esc(localizedText(graphLabel(kind)))}</title></circle>
        <text x="0" y="0" text-anchor="middle" font-size="10.5" fill="currentColor" display="none">${esc(String(nodeLabel).slice(0, 24))}</text>
      </g>`;
    }).join("");
    $("#graph-edges").innerHTML = edgeMarkup;
    $("#graph-nodes").innerHTML = nodeMarkup;
    const nodeEls = new Map();
    $$("#graph-nodes [data-node-id]").forEach((group) => nodeEls.set(group.dataset.nodeId, {
      group,
      circle: group.querySelector("circle"),
      text: group.querySelector("text"),
    }));
    const edgeEls = new Map();
    $$("#graph-edges [data-edge-id]").forEach((group) => edgeEls.set(group.dataset.edgeId, {
      group,
      line: group.querySelector(".graph-edge-line"),
      hit: group.querySelector(".graph-edge-hit"),
    }));

    function draw(now = performance.now()) {
      if (!stage?.isConnected) return;
      const selectedEdge = state.graphSelectedEdge ? edgeMap.get(state.graphSelectedEdge) : null;
      const focusIds = new Set();
      if (state.graphSelected) {
        focusIds.add(state.graphSelected);
        activeEdges.forEach((edge) => { if (edge.from === state.graphSelected || edge.to === state.graphSelected) { focusIds.add(edge.from); focusIds.add(edge.to); } });
      }
      if (selectedEdge) { focusIds.add(selectedEdge.from); focusIds.add(selectedEdge.to); }
      activeEdges.forEach((edge) => {
        const ref = edgeEls.get(edge.id);
        const a = positions.get(edge.from), b = positions.get(edge.to);
        if (!ref || !a || !b) return;
        const isSelected = selectedEdge?.id === edge.id;
        const touchesFocus = focusIds.has(edge.from) && focusIds.has(edge.to);
        const growA = Math.max(0, Math.min(1, (now - a.appear) / 650));
        const growB = Math.max(0, Math.min(1, (now - b.appear) / 650));
        const opacity = Math.min(growA, growB) * (isSelected ? .9 : (focusIds.size ? (touchesFocus ? .55 : .06) : .18));
        ref.line.setAttribute("x1", a.x.toFixed(1)); ref.line.setAttribute("y1", a.y.toFixed(1));
        ref.line.setAttribute("x2", b.x.toFixed(1)); ref.line.setAttribute("y2", b.y.toFixed(1));
        ref.hit.setAttribute("x1", a.x.toFixed(1)); ref.hit.setAttribute("y1", a.y.toFixed(1));
        ref.hit.setAttribute("x2", b.x.toFixed(1)); ref.hit.setAttribute("y2", b.y.toFixed(1));
        ref.line.setAttribute("stroke-opacity", opacity.toFixed(3));
        ref.line.setAttribute("stroke-width", isSelected ? "2.4" : (touchesFocus && focusIds.size ? "1.8" : "1.2"));
        ref.line.setAttribute("stroke", isSelected ? "#0071e3" : (focusIds.size && !touchesFocus ? "#8e8e93" : "#8e8e93"));
        ref.group.classList.toggle("selected", isSelected);
      });
      activeNodes.forEach((node) => {
        const ref = nodeEls.get(node.id), p = positions.get(node.id);
        if (!ref || !p) return;
        const grow = Math.max(0, Math.min(1, (now - p.appear) / 650));
        const kind = graphKind(node);
        const base = graphNodeRadius(kind, degree[node.id] || 0);
        const selected = state.graphSelected === node.id || selectedEdge?.from === node.id || selectedEdge?.to === node.id;
        const inFocus = !focusIds.size || focusIds.has(node.id);
        ref.group.style.display = grow > 0 ? "" : "none";
        ref.circle.setAttribute("cx", p.x.toFixed(1)); ref.circle.setAttribute("cy", p.y.toFixed(1));
        ref.circle.setAttribute("r", (base * (0.45 + 0.55 * grow) + (selected ? 4 : 0)).toFixed(1));
        ref.circle.setAttribute("stroke", selected ? "#0071e3" : "var(--bg)");
        ref.circle.setAttribute("stroke-width", selected ? "3.2" : "2");
        ref.group.style.opacity = String(inFocus ? 1 : .16);
        const showLabel = labelKinds.has(kind) || state.graphZoom > 1.15 || selected;
        ref.text.style.display = showLabel && grow > .55 ? "" : "none";
        ref.text.setAttribute("x", p.x.toFixed(1));
        ref.text.setAttribute("y", (p.y + base + 13).toFixed(1));
        ref.group.classList.toggle("selected", selected);
      });
      applyTransform();
      const legendKinds = [...new Set(activeNodes.map(graphKind))].sort();
      const signature = state.graphColorMode + ":" + legendKinds.join("|");
      if (state.graphLegendSignature !== signature) {
        state.graphLegendSignature = signature;
        $("#graph-legend").innerHTML = legendKinds.map((kind) => `<button type="button" data-kind="${esc(kind)}"><span style="color:${graphColor(kind, state.graphColorMode)}">●</span> ${esc(localizedText(graphLabel(kind)))} <b>${activeNodes.filter((node) => graphKind(node) === kind).length}</b></button>`).join("");
        translateSubtree($("#graph-legend"));
      }
    }

    function selectNode(id, full = false) {
      const node = nodeMap.get(id);
      if (!node || !activeIds.has(id)) return;
      state.graphSelected = id;
      state.graphSelectedEdge = null;
      const p = positions.get(id);
      if (p) {
        const targetZoom = Math.max(1.22, state.graphZoom);
        viewport.style.transition = "transform .32s ease";
        state.graphZoom = targetZoom;
        state.graphPanX = GRAPH_W / 2 - p.x * targetZoom;
        state.graphPanY = GRAPH_H / 2 - p.y * targetZoom;
        applyTransform();
        setTimeout(() => { viewport.style.transition = ""; }, 340);
      }
      const related = edges.filter((edge) => edge.from === id || edge.to === id);
      renderNodeInspector(node, graph, related, nodeMap);
      $("#graph-detail").innerHTML = state.lang === "en"
        ? `<p class="muted"><b>${esc(localizedText(node.label))}</b> focused. ${full ? "Full evidence and sources are on the right; " : "Double-click for full evidence; "}dragging this node pulls connected nodes.</p>`
        : `<p class="muted"><b>${esc(node.label)}</b> 已聚焦。${full ? "右侧是完整证据与来源；" : "双击可展开完整证据；"}拖拽该节点会牵拉相连节点。</p>`;
      draw();
      if (full) $("#graph-inspector")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    function selectEdge(id) {
      const edge = edgeMap.get(id);
      if (!edge) return;
      state.graphSelected = null;
      state.graphSelectedEdge = id;
      renderEdgeInspector(edge, nodeMap);
      $("#graph-detail").innerHTML = state.lang === "en"
        ? `<p class="muted">Viewing relationship <b>${esc(localizedText(edge.label || GRAPH_EDGE_NAMES[edge.type] || edge.type))}</b>. Evidence, meaning and both connected nodes are on the right.</p>`
        : `<p class="muted">正在查看关系 <b>${esc(edge.label || GRAPH_EDGE_NAMES[edge.type] || edge.type)}</b>。证据、含义和两端节点在右侧。</p>`;
      draw();
    }

    renderGraphDefaultInspector(graph);
    if (state.graphSelected) selectNode(state.graphSelected);
    else if (state.graphSelectedEdge) selectEdge(state.graphSelectedEdge);
    else draw();

    let simAlpha = 1.0, simRunning = true, lastFrame = performance.now(), settleUntil = performance.now() + 2600;
    const tick = () => {
      const active = activeNodes;
      active.forEach((a) => {
        const pa = positions.get(a.id);
        if (!pa || pa.fixed) return;
        active.forEach((b) => {
          if (a === b) return;
          const pb = positions.get(b.id);
          if (!pb) return;
          let dx = pa.x - pb.x, dy = pa.y - pb.y;
          const d2 = dx * dx + dy * dy || 1;
          if (d2 > 120000) return;
          const d = Math.sqrt(d2);
          const force = Math.min(2.6, 2400 / d2);
          pa.vx += (dx / d) * force; pa.vy += (dy / d) * force;
        });
      });
      activeEdges.forEach((edge) => {
        const pa = positions.get(edge.from), pb = positions.get(edge.to);
        if (!pa || !pb) return;
        const dx = pb.x - pa.x, dy = pb.y - pa.y;
        const d = Math.hypot(dx, dy) || 1;
        const target = ["next", "next_process", "uses", "formulates_with", "predicts_change"].includes(edge.type) ? 88 : 132;
        const force = (d - target) * 0.0045;
        if (!pa.fixed) { pa.vx += (dx / d) * force; pa.vy += (dy / d) * force; }
        if (!pb.fixed) { pb.vx -= (dx / d) * force; pb.vy -= (dy / d) * force; }
      });
      active.forEach((node) => {
        const p = positions.get(node.id);
        if (!p || p.fixed) return;
        p.vx += (p.tx - p.x) * 0.012; p.vy += (p.ty - p.y) * 0.012;
        p.vx *= 0.72; p.vy *= 0.72;
        p.x += Math.max(-24, Math.min(24, p.vx)); p.y += Math.max(-24, Math.min(24, p.vy));
        p.x = Math.max(30, Math.min(GRAPH_W - 30, p.x)); p.y = Math.max(26, Math.min(GRAPH_H - 26, p.y));
      });
      simAlpha *= 0.975;
    };
    const frame = (now) => {
      if (!stage?.isConnected) { simRunning = false; return; }
      if (now - lastFrame > 34) {
        lastFrame = now;
        if (now < settleUntil || simAlpha > 0.02) { tick(); simAlpha = Math.max(0.018, simAlpha); }
        draw(now);
        if (now > settleUntil && simAlpha <= 0.02) { simRunning = false; draw(now); return; }
      }
      state.graphAnim = requestAnimationFrame(frame);
    };
    const kick = () => {
      simAlpha = 1; settleUntil = performance.now() + 1000;
      if (!simRunning) { simRunning = true; lastFrame = performance.now(); state.graphAnim = requestAnimationFrame(frame); }
    };
    state.graphAnim = requestAnimationFrame(frame);

    let drag = null, dragNode = null, suppressClick = false, pointers = new Map(), pinch = 0;
    stage.addEventListener("wheel", (e) => {
      e.preventDefault();
      const rect = svg.getBoundingClientRect();
      const px = (e.clientX - rect.left) / rect.width * GRAPH_W;
      const py = (e.clientY - rect.top) / rect.height * GRAPH_H;
      applyZoom(Math.exp(-e.deltaY * 0.0012), px, py);
    }, { passive: false });
    const applyZoom = (factor, px = GRAPH_W / 2, py = GRAPH_H / 2) => {
      const next = Math.max(0.38, Math.min(3.8, state.graphZoom * factor));
      const ratio = next / state.graphZoom;
      state.graphPanX = px - (px - state.graphPanX) * ratio;
      state.graphPanY = py - (py - state.graphPanY) * ratio;
      state.graphZoom = next; applyTransform(); draw();
    };
    stage.addEventListener("pointerdown", (e) => {
      const nodeGroup = e.target.closest("[data-node-id]");
      if (nodeGroup) {
        e.preventDefault(); e.stopPropagation();
        nodeGroup.setPointerCapture(e.pointerId);
        const p = positions.get(nodeGroup.dataset.nodeId);
        if (p) {
          p.fixed = true;
          dragNode = { id: nodeGroup.dataset.nodeId, pointerId: e.pointerId, startX: e.clientX, startY: e.clientY, moved: false };
          kick();
        }
        return;
      }
      stage.setPointerCapture(e.pointerId);
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pointers.size === 1) drag = { x: e.clientX, y: e.clientY, panX: state.graphPanX, panY: state.graphPanY };
      if (pointers.size === 2) { const [a, b] = [...pointers.values()]; pinch = Math.hypot(a.x - b.x, a.y - b.y); }
    });
    stage.addEventListener("pointermove", (e) => {
      if (dragNode && dragNode.pointerId === e.pointerId) {
        const p = positions.get(dragNode.id);
        if (!p) return;
        const rect = svg.getBoundingClientRect();
        const gx = ((e.clientX - rect.left) / rect.width * GRAPH_W - state.graphPanX) / state.graphZoom;
        const gy = ((e.clientY - rect.top) / rect.height * GRAPH_H - state.graphPanY) / state.graphZoom;
        p.x = gx; p.y = gy; p.vx = 0; p.vy = 0; p.fixed = true;
        if (Math.hypot(e.clientX - dragNode.startX, e.clientY - dragNode.startY) > 4) dragNode.moved = true;
        kick(); draw();
        return;
      }
      if (!pointers.has(e.pointerId)) return;
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      const rect = svg.getBoundingClientRect();
      if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        const dist = Math.hypot(a.x - b.x, a.y - b.y);
        if (pinch > 0 && dist !== pinch) {
          const cx = (a.x + b.x) / 2, cy = (a.y + b.y) / 2;
          const px = (cx - rect.left) / rect.width * GRAPH_W;
          const py = (cy - rect.top) / rect.height * GRAPH_H;
          applyZoom(dist / pinch, px, py);
        }
        pinch = dist;
        return;
      }
      if (!drag) return;
      state.graphPanX = drag.panX + (e.clientX - drag.x) / rect.width * GRAPH_W;
      state.graphPanY = drag.panY + (e.clientY - drag.y) / rect.height * GRAPH_H;
      applyTransform();
    });
    const pointerUp = (e) => {
      if (dragNode && dragNode.pointerId === e.pointerId) {
        suppressClick = dragNode.moved;
        dragNode = null;
        kick();
      }
      pointers.delete(e.pointerId);
      if (!pointers.size) { drag = null; pinch = 0; }
    };
    stage.addEventListener("pointerup", pointerUp);
    stage.addEventListener("pointercancel", pointerUp);
    $("#graph-nodes").addEventListener("click", (e) => {
      const group = e.target.closest("[data-node-id]");
      if (!group) return;
      e.stopPropagation();
      if (suppressClick) { suppressClick = false; return; }
      selectNode(group.dataset.nodeId);
    });
    $("#graph-nodes").addEventListener("dblclick", (e) => {
      const group = e.target.closest("[data-node-id]");
      if (group) { e.preventDefault(); e.stopPropagation(); selectNode(group.dataset.nodeId, true); }
    });
    $("#graph-nodes").addEventListener("keydown", (e) => {
      const group = e.target.closest("[data-node-id]");
      if (group && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); selectNode(group.dataset.nodeId, true); }
    });
    $("#graph-edges").addEventListener("click", (e) => {
      const group = e.target.closest("[data-edge-id]");
      if (group) { e.stopPropagation(); selectEdge(group.dataset.edgeId); }
    });
    $("#graph-inspector").addEventListener("click", (e) => {
      if (e.target.closest("#graph-inspector-close")) { state.graphSelected = null; state.graphSelectedEdge = null; renderGraphDefaultInspector(graph); $("#graph-detail").innerHTML = `<p class="muted">点击节点聚焦并查看解释；双击节点打开完整证据；点击边查看关系语义。</p>`; translateSubtree($("#graph-detail")); draw(); return; }
      const edgeBtn = e.target.closest("[data-edge-id]");
      if (edgeBtn) { selectEdge(edgeBtn.dataset.edgeId); return; }
      const nodeBtn = e.target.closest("[data-node-jump]");
      if (nodeBtn) selectNode(nodeBtn.dataset.nodeJump, true);
    });
    $("#graph-fit").addEventListener("click", () => { state.graphZoom = 1; state.graphPanX = 0; state.graphPanY = 0; applyTransform(); draw(); });
    $("#graph-relayout").addEventListener("click", () => { state.graphPositions = { designId: graph.design_id, ...graphLayout(graph) }; renderGraph(graph); });
    $("#graph-color-mode").addEventListener("change", (e) => { state.graphColorMode = e.target.value; draw(); });
    $("#graph-show-sources").addEventListener("change", (e) => { state.graphShowSources = e.target.checked; renderGraph(graph); });
    $("#graph-show-steps").addEventListener("change", (e) => { state.graphShowSteps = e.target.checked; renderGraph(graph); });
    translateSubtree($("#evidence-output"));
  }

  async function runEvidence(query) {
    state.graphView = false;
    state.graphAnim && cancelAnimationFrame(state.graphAnim);
    const q = (query || $("#evidence-query").value || "").trim();
    if (!q) return;
    $("#evidence-query").value = q;
    const entity = $("#evidence-entity")?.value || "auto";
    const out = $("#evidence-output");
    out.innerHTML = `<div class="card loading-card"><span class="spinner"></span><div><b>正在规划并检索 ${esc(q)}</b><p class="muted">实体分类 → 选择数据库 → 标识符验证 → 相关性过滤</p></div></div>`;
    $("#source-status").innerHTML = "";
    try {
      const res = await api("/api/v2/db/search", { method: "POST", body: JSON.stringify({ query: q, entity }) });
      state.evidence = res;
      renderEvidence(res);
    } catch (err) {
      if (err.message !== "unauthorized") out.innerHTML = `<div class="card detail-card"><p class="muted">${esc(err.message)}</p></div>`;
    }
  }

  function sourcePill(id, info) {
    if (!info) return "";
    const status = info.status || "error";
    const label = { ok: "ok", degraded: "本地快照", link_only: "仅链接", empty: "0 条", skipped: "跳过", error: "错误" }[status] || status;
    const cls = status === "ok" ? "ok" : status === "degraded" ? "degraded" : status === "link_only" ? "link_only" : "error";
    return `<span class="source-pill ${cls}"><span class="dot ${status === "ok" ? "on" : "off"}"></span>${esc(info.source || id)} · ${esc(label)}${info.records?.length ? ` · ${info.records.length}` : ""}</span>`;
  }

  function entityLabel(entity) {
    return ({ compound: "小分子 / 化合物", protein: "蛋白 / 靶点", food: "食品 / 配方", complex: "化合物-蛋白复合" })[entity] || entity || "—";
  }

  function renderEvidencePlan(res) {
    const plan = res.plan || {};
    const rejected = plan.rejected_sources || [];
    const id = res.identity || {};
    const expansion = res.query_expansion || {};
    const matched = (expansion.matched || []).map((item) => `${item.term} → ${item.english}`);
    const mappingRows = Object.entries(id.mappings || {}).map(([db, ids]) => `<span class="badge">${esc(db)}: ${esc((ids || []).join(", "))}</span>`).join("");
    return `<div class="card detail-card" style="margin-top:12px">
      <div style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start">
        <div><span class="eyebrow">QUERY PLAN</span><h3 style="margin:4px 0 0">实体：${esc(entityLabel(res.entity))}</h3></div>
        <span class="badge blue">${(plan.selected_sources || []).length} 个来源</span>
      </div>
      <p class="subtle" style="margin-top:8px">${esc(plan.reason || "")}</p>
      <p style="font-size:12px;line-height:1.6"><b>查询扩展：</b>${esc(expansion.original || res.query || "")} → <b>${esc(expansion.expanded || plan.query_expanded || res.query || "")}</b>${matched.length ? `<br><span class="fineprint">中英文映射：${esc(matched.join("；"))}</span>` : ""}</p>
      <p style="font-size:12px;line-height:1.6"><b>执行来源：</b>${esc((plan.selected_sources || []).join(" · "))}</p>
      <p class="fineprint">${esc(plan.ranking || "相关度按词面覆盖与短语命中排序；不是统计显著性。")}</p>
      <p class="fineprint">${esc(plan.rule || "")}</p>
      ${rejected.length ? `<p class="fineprint"><b>已拒绝：</b>${rejected.map((x) => `${esc(x.source)}（${esc(x.reason)}）`).join("；")}</p>` : ""}
      ${id.inchikey ? `<p style="font-size:12px"><b>PubChem CID</b> ${esc(id.pubchem_cid)} · <b>InChIKey</b> <span style="font-family:ui-monospace,monospace">${esc(id.inchikey)}</span></p>` : ""}
      ${mappingRows ? `<div class="meta" style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px">${mappingRows}</div>` : ""}
    </div>`;
  }

  function renderEvidence(res) {
    $("#source-status").innerHTML = Object.entries(res.sources || {}).map(([id, info]) => sourcePill(id, info)).join("");
    const records = res.records || [];
    const grouped = {};
    records.forEach((r) => { (grouped[r.source] = grouped[r.source] || []).push(r); });
    const sourceNames = {};
    Object.entries(res.sources || {}).forEach(([id, info]) => { sourceNames[id] = info.source || id; });
    Object.values(grouped).forEach((items) => items.sort((a, b) => Number(b.relevance || 0) - Number(a.relevance || 0)));
    const strengthNames = { high: "高相关", medium: "中相关", low: "低相关" };
    const sections = Object.entries(grouped).map(([source, items]) => `
      <div class="card detail-card" style="margin-top:12px">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:10px"><h3 style="font-size:16px">${esc(sourceNames[source] || source)}</h3><span class="badge">${items.length} 条</span></div>
        <div class="record-grid">${items.slice(0, 6).map((r) => {
          const spectra = (r.data?.spectra || []).slice(0, 2);
          return `<div class="record" style="border:1px solid var(--line);border-radius:12px">
            <h4>${esc(r.title || r.id)}</h4>
            <div class="meta"><span>ID ${esc(r.id)}</span><span>${esc(r.match_basis || "record")}</span><span class="record-strength ${esc(r.strength || "low")}">${esc(strengthNames[r.strength] || "相关度")} ${num(r.relevance, 2)}</span><span>${esc((r.retrieved_at || "").slice(0, 10))}</span></div>
            <div class="meta"><span>${esc(r.license || "see source")}</span><span>排名 ${esc(r.rank || "—")}</span></div>
            ${(r.match_terms || []).length ? `<p class="fineprint">命中词：${esc((r.match_terms || []).join(" · "))}</p>` : ""}
            ${r.data?.formula ? `<p>${esc(r.data.formula)} · MW ${esc(r.data.mw || "—")}</p>` : ""}
            ${r.data?.description ? `<p>${esc(String(r.data.description).slice(0, 220))}</p>` : ""}
            ${r.data?.fdc_description ? `<p>${esc(String(r.data.fdc_description).slice(0, 220))}</p>` : ""}
            ${spectra.map((s) => `<p style="margin-top:7px"><b>${esc(s.type)}</b> ${s.instrument_type ? esc(s.instrument_type) : ""}</p><div class="peaks">${(s.peaks || []).slice(0, 8).map((p) => `<span class="peak">${esc(p.mz != null ? p.mz : p.mass)}${p.intensity != null ? ` (${num(p.intensity, 0)})` : ""}</span>`).join("")}</div>`).join("")}
            <a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">打开原始记录 ↗</a>
          </div>`;
        }).join("")}</div>
      </div>`).join("");
    const links = (res.cross_links || []).map((l) => `<div class="crosslink"><b>${esc(l.from)}</b> → <b>${esc(l.to)}</b> · ${esc(l.type)} <span class="muted">${esc(l.verified_by || "")} ${esc(l.note || "")}</span></div>`).join("");
    $("#evidence-output").innerHTML = renderEvidencePlan(res) + sections + (links ? `<div class="card detail-card" style="margin-top:12px"><h3 style="font-size:16px">已验证的跨库证据</h3><p class="subtle">只展示 InChIKey 精确映射、UniProt→PDB xref 或谱图参考；不再使用名称候选冒充身份验证。</p><div class="crosslinks">${links}</div></div>` : "") + `<p class="fineprint">${esc(res.notice || "记录来自各数据库公开接口；检索时间、记录号、匹配依据与许可已保留。")}</p>`;
  }

  async function loadLiteratureStats() {
    if (state.litStats) {
      $("#lit-stats").textContent = `${state.litStats.papers.toLocaleString()} 篇 · ${state.litStats.chunks.toLocaleString()} 块`;
      return;
    }
    try {
      const [stats, topics] = await Promise.all([
        api("/api/v3/literature/stats"),
        api("/api/v3/literature/topics").catch(() => null),
      ]);
      state.litStats = stats;
      state.litTopics = topics;
      if (!stats.available) {
        $("#lit-stats").textContent = "未建立";
        $("#lit-results").innerHTML = `<p class="note bad">${esc(stats.notice || "本地文献库不可用。")}</p>`;
        return;
      }
      $("#lit-stats").textContent = `${stats.papers.toLocaleString()} 篇 · ${stats.chunks.toLocaleString()} 块`;
      const topicKeys = Object.keys(topics?.topics || {});
      $("#lit-topics").innerHTML = topicKeys.map((key) => `<span class="badge">${esc(key)}</span>`).join("");
      $("#lit-results").innerHTML = `<div class="lit-summary"><span>OA ${stats.open_access.toLocaleString()}</span><span>全文 ${stats.with_fulltext}</span><span>实体 ${stats.entities.toLocaleString()}</span><span>关系 ${stats.edges.toLocaleString()}</span></div><p class="fineprint">${esc(stats.notice || "")}</p>`;
    } catch (err) {
      $("#lit-stats").textContent = "读取失败";
      if (err.message !== "unauthorized") $("#lit-stats").textContent = err.message;
    }
  }

  async function searchLiterature(event) {
    event?.preventDefault();
    const q = $("#lit-query").value.trim();
    if (!q) { toast("请输入文献检索词。"); return; }
    const out = $("#lit-results");
    out.innerHTML = `<div class="loading-card"><span class="spinner"></span><span>正在检索本地索引…</span></div>`;
    try {
      const res = await api(`/api/v3/literature/search?q=${encodeURIComponent(q)}&limit=8`);
      if (!res.items.length) {
        out.innerHTML = `<p class="muted">没有命中。尝试更短的关键词，例如 quercetin、whey protein、molecular dynamics。</p>`;
        return;
      }
      const expansion = res.query_expansion || {};
      const matched = (expansion.matched || []).map((item) => `${item.term} → ${item.english}`);
      out.innerHTML = `<p class="fineprint">${res.count} 条结果 · 查询扩展：${esc(expansion.expanded || q)}${matched.length ? ` · 中英文映射：${esc(matched.join("；"))}` : ""} · ${esc(res.notice || "")}</p>` + res.items.map((item) => {
        const snippet = esc(item.snippet || item.abstract || "").replace(/&lt;mark&gt;/g, "<mark>").replace(/&lt;\/mark&gt;/g, "</mark>");
        const tags = [...(item.tags || []), ...(item.mesh || []).slice(0, 3), ...(item.keywords || []).slice(0, 3)];
        return `<article class="lit-item">
          <div class="lit-meta"><span>${item.year || "—"}</span><span>${esc(item.category || "general")}</span><span>${esc(item.license || "see source")}</span><span class="record-strength ${esc(item.strength || "low")}">${esc(item.strength === "high" ? "高相关" : item.strength === "medium" ? "中相关" : "低相关")} ${num(item.relevance, 2)}</span>${item.pmcid ? `<span>${esc(item.pmcid)}</span>` : ""}</div>
          <h4>${esc(item.title)}</h4>
          <p>${snippet}</p>
          <div class="lit-tags">${tags.slice(0, 8).map((tag) => `<span>${esc(tag)}</span>`).join("")}</div>
          <a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">打开 Europe PMC / DOI ↗</a>
        </article>`;
      }).join("");
    } catch (err) {
      if (err.message !== "unauthorized") out.innerHTML = `<p class="note bad">${esc(err.message)}</p>`;
    }
  }

  async function loadKnowledgeStatus() {
    const box = $("#knowledge-status");
    if (!box) return;
    try {
      const res = await api("/api/v3/knowledge/status");
      const db = res.postgres || {};
      if (!db.available) {
        box.innerHTML = `<p class="note bad">PostgreSQL 不可用：${esc(db.reason || "unknown")}；文献检索回退 SQLite。</p>`;
        return;
      }
      const c = db.counts || {};
      const rows = [
        ["状态", db.database ? "已连接" : "—"],
        ["PostgreSQL", db.version || "—"],
        ["pgvector", db.pgvector || "—"],
        ["文献", formatNumber(c.literature_records)],
        ["文本块", formatNumber(c.literature_chunks)],
        ["图谱边", formatNumber(c.graph_edges)],
        ["向量", `${formatNumber(c.embeddings)} 已生成`],
        ["体积", c.size || "—"],
      ];
      box.innerHTML = rows.map(([k, v]) => `<div class="knowledge-row"><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join("");
      state.knowledge = db;
    } catch (err) {
      box.innerHTML = `<p class="note bad">${esc(err.message)}</p>`;
    }
  }

  async function loadSourceCatalog() {
    const box = $("#source-catalog");
    if (!box) return;
    box.innerHTML = `<div class="loading-card"><span class="spinner"></span><span>读取来源许可…</span></div>`;
    try {
      const res = await api("/api/v2/db/status");
      const live = (res.sources || []).map((source) => `<div class="source-row"><b>${esc(source.name)}</b><span>${esc(source.license)}</span><span class="badge ok">可查询</span></div>`).join("");
      const catalog = (res.catalog || []).map((source) => `<div class="source-row"><b>${esc(source.name)}</b><span>${esc(source.note || "")}</span><span class="badge warn">${esc(source.status === "license_required" ? "需许可" : source.status === "credentials_required" ? "需凭据" : "参考入口")}</span></div>`).join("");
      box.innerHTML = `<div class="source-row"><b>已登记公共源</b><span>${(res.sources || []).length} 个</span></div>${live}${catalog ? `<div class="source-row"><b>许可/机构来源</b><span>未授权前不抓取、不复制</span></div>${catalog}` : ""}`;
    } catch (err) {
      box.innerHTML = `<p class="note bad">${esc(err.message)}</p>`;
    }
  }

  const RESOURCE_STATUS = {
    live: ["可直接查询", "ok"],
    api_ready: ["API / 解析", "blue"],
    license_required: ["需许可", "warn"],
    institution_login: ["机构登录", "blue"],
    link_only: ["链接入口", ""],
    public_reference: ["公开参考", ""],
  };

  const THEMES = [
    { id: "aurora", name: "极光", a: "#0071e3", b: "#6e56cf" },
    { id: "ocean", name: "深海", a: "#087ea4", b: "#0f766e" },
    { id: "forest", name: "森林", a: "#1f7a4d", b: "#6a994e" },
    { id: "sunset", name: "日落", a: "#c2410c", b: "#c026d3" },
    { id: "berry", name: "莓果", a: "#b4235a", b: "#7c3aed" },
    { id: "mono", name: "石墨", a: "#4b5563", b: "#111827" },
    { id: "cyber", name: "赛博", a: "#00a8a8", b: "#ff2d95" },
    { id: "cartoon", name: "卡通", a: "#3a86ff", b: "#ffb703" },
    { id: "scroll", name: "国风", a: "#9a3412", b: "#b45309" },
    { id: "lab", name: "实验室", a: "#0b7285", b: "#5f3dc4" },
    { id: "candy", name: "糖果", a: "#d6336c", b: "#f59f00" },
    { id: "sand", name: "沙丘", a: "#a16207", b: "#0f766e" },
  ];

  function formatNumber(value) {
    return value == null ? "—" : Number(value).toLocaleString("zh-CN");
  }

  const THEME_EN = { aurora: "Aurora", ocean: "Ocean", forest: "Forest", sunset: "Sunset", berry: "Berry", mono: "Graphite", cyber: "Cyber", cartoon: "Cartoon", scroll: "Scroll", lab: "Lab", candy: "Candy", sand: "Sand" };
  function themeName(id) {
    const theme = THEMES.find((item) => item.id === id) || THEMES[0];
    return state.lang === "en" ? (THEME_EN[theme.id] || theme.name) : theme.name;
  }

  function updateThemeUi() {
    $$("#theme-grid .theme-choice").forEach((button) => button.classList.toggle("active", button.dataset.theme === state.theme));
    $$("#theme-mode button").forEach((button) => button.classList.toggle("active", button.dataset.mode === state.themeMode));
    const label = $("#theme-status");
    if (label) {
      const modeZh = state.themeMode === "auto" ? "跟随系统" : state.themeMode === "dark" ? "深色" : "浅色";
      const modeEn = state.themeMode === "auto" ? "System" : state.themeMode === "dark" ? "Dark" : "Light";
      label.textContent = state.lang === "en" ? `Current: ${modeEn} · ${themeName(state.theme)}` : `当前：${modeZh} · ${themeName(state.theme)}`;
    }
  }

  function applyTheme(theme, mode, persist = true) {
    if (!THEMES.some((item) => item.id === theme)) theme = "aurora";
    if (!["auto", "light", "dark"].includes(mode)) mode = "auto";
    state.theme = theme;
    state.themeMode = mode;
    document.documentElement.dataset.theme = theme;
    if (mode === "auto") delete document.documentElement.dataset.mode;
    else document.documentElement.dataset.mode = mode;
    const dark = mode === "dark" || (mode === "auto" && window.matchMedia?.("(prefers-color-scheme: dark)").matches);
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", dark ? "#0b0b0d" : "#f5f5f7");
    if (persist) {
      try {
        localStorage.setItem("bioforge-theme", theme);
        localStorage.setItem("bioforge-theme-mode", mode);
      } catch { /* storage can be disabled */ }
    }
    updateThemeUi();
  }

  function initTheme() {
    let theme = "aurora", mode = "auto";
    try {
      theme = localStorage.getItem("bioforge-theme") || theme;
      mode = localStorage.getItem("bioforge-theme-mode") || mode;
    } catch { /* storage can be disabled */ }
    const grid = $("#theme-grid");
    if (grid) {
      grid.innerHTML = THEMES.map((item) => `<button class="theme-choice" type="button" data-theme="${esc(item.id)}" aria-label="${esc(item.name)}主题" aria-pressed="false"><span class="theme-swatch" style="--swatch:${esc(item.a)};--swatch2:${esc(item.b)}"></span><span>${esc(item.name)}</span></button>`).join("");
      grid.addEventListener("click", (event) => {
        const button = event.target.closest("[data-theme]");
        if (button) applyTheme(button.dataset.theme, state.themeMode);
      });
    }
    $$("#theme-mode button").forEach((button) => button.addEventListener("click", () => applyTheme(state.theme, button.dataset.mode)));
    applyTheme(theme, mode, false);
  }

  function resourceBadge(status) {
    const [label, tone] = RESOURCE_STATUS[status] || [status || "入口", ""];
    return `<span class="badge ${tone}">${esc(label)}</span>`;
  }

  function renderResourceStats() {
    const box = $("#resource-stats");
    if (!box) return;
    const counts = state.resources?.counts || {};
    const db = state.knowledge?.counts || {};
    const cells = [
      [formatNumber(counts.items), "已登记来源"],
      [formatNumber(counts.live), "可直接查询"],
      [formatNumber(counts.institution), "机构入口"],
      [formatNumber(db.literature_records), "PostgreSQL 文献"],
      [formatNumber(db.literature_chunks), "文本块"],
      [formatNumber(db.graph_edges), "图谱边"],
    ];
    box.innerHTML = cells.map(([value, label]) => `<div class="resource-stat"><b>${esc(value)}</b><span>${esc(label)}</span></div>`).join("");
  }

  function renderResources() {
    const box = $("#resource-groups");
    if (!box || !state.resources) return;
    const en = state.lang === "en";
    const query = state.resourceQuery.toLowerCase();
    const filter = state.resourceFilter;
    const groups = (state.resources.groups || []).map((group) => {
      const items = (group.items || []).filter((item) => {
        if (filter !== "all" && item.status !== filter) return false;
        if (!query) return true;
        return [item.name, item.name_en, item.id, item.note, item.note_en, item.license, group.name, group.name_en].join(" ").toLowerCase().includes(query);
      });
      return { ...group, items };
    }).filter((group) => group.items.length);
    if (!groups.length) {
      box.innerHTML = `<div class="card"><p class="muted">${en ? "No matching resources. Clear the search or change the filter." : "没有匹配的资源。清空搜索或切换筛选。"}</p></div>`;
      return;
    }
    box.innerHTML = groups.map((group) => `<details class="resource-group" open><summary><h3>${esc(en ? (group.name_en || group.name) : group.name)}</h3><span class="resource-group-count">${group.items.length}</span></summary><div class="resource-grid">${group.items.map((item) => `
      <a class="resource-card" href="${esc(item.url || "#")}" target="_blank" rel="noopener noreferrer">
        <div class="resource-card-head"><h4>${esc(item.name)}</h4><span class="resource-arrow">↗</span></div>
        <p>${esc(en ? (item.note_en || item.note || "Official entry point") : (item.note || "官方入口"))}</p>
        <div class="resource-card-meta">${resourceBadge(item.status)}<span>${esc(item.license || (en ? "See site terms" : "查看站点条款"))}</span></div>
      </a>`).join("")}</div></details>`).join("");
    translateSubtree(box);
  }

  function renderResourcePopover() {
    const box = $("#resource-popover-links");
    if (!box) return;
    const wanted = ["pubchem", "uniprot", "europepmc", "openalex", "doi", "scut_library"];
    const items = (state.resources?.groups || []).flatMap((group) => group.items || []);
    const selected = wanted.map((id) => items.find((item) => item.id === id)).filter(Boolean);
    box.innerHTML = selected.map((item) => `<a class="popover-link" href="${esc(item.url)}" target="_blank" rel="noopener noreferrer"><b>${esc(item.name)}</b><span>${esc((RESOURCE_STATUS[item.status] || [item.status])[0])} · ${esc(item.license || "")}</span></a>`).join("");
    translateSubtree(box);
  }

  async function loadResources() {
    if (state.resources) {
      renderResourceStats();
      renderResources();
      renderResourcePopover();
      return;
    }
    try {
      const [catalog, knowledge] = await Promise.all([api("/api/v3/resources"), api("/api/v3/knowledge/status")]);
      state.resources = catalog;
      state.knowledge = knowledge.postgres || null;
      const sourceCount = $("#source-count");
      if (sourceCount && catalog.counts?.items) sourceCount.textContent = String(catalog.counts.items);
      renderResourceStats();
      loadKnowledgeStatus();
      renderResources();
      renderResourcePopover();
    } catch (err) {
      if (err.message !== "unauthorized") {
        const box = $("#resource-groups");
        if (box) box.innerHTML = `<div class="card"><p class="note bad">${esc(err.message)}</p></div>`;
      }
    }
  }

  function openResourcePopover() {
    const box = $("#resource-popover");
    if (!box) return;
    box.classList.remove("hidden");
    $("#resource-chip")?.setAttribute("aria-expanded", "true");
  }

  function closeResourcePopover() {
    const box = $("#resource-popover");
    if (!box) return;
    box.classList.add("hidden");
    $("#resource-chip")?.setAttribute("aria-expanded", "false");
  }

  async function resolveIdentifier(event) {
    event.preventDefault();
    const input = $("#identifier-input");
    const status = $("#identifier-status");
    const box = $("#identifier-result");
    const value = input.value.trim();
    if (!value) return;
    const old = status.textContent;
    status.textContent = "正在解析 DOI/PMID，并查询合法 OA 位置…";
    box.innerHTML = `<div class="loading-card"><span class="spinner"></span><span>解析中…</span></div>`;
    try {
      const data = await api(`/api/v3/library/resolve?q=${encodeURIComponent(value)}`);
      const links = (data.links || []).map((link) => `<a href="${esc(link.url)}" target="_blank" rel="noopener noreferrer">${esc(link.label)} ↗</a>`).join("");
      const locations = (data.unpaywall?.locations || []).map((loc) => `<div class="oa-location"><a href="${esc(loc.url)}" target="_blank" rel="noopener noreferrer">${esc(loc.host || "OA")} · ${esc(loc.version || "version")} · ${esc(loc.license || "see record")} ↗</a></div>`).join("");
      const meta = [data.journal, data.year, data.publisher].filter(Boolean).map(esc).join(" · ");
      const access = data.access === "open" ? "开放获取（仍请核对许可）" : "需机构/出版社授权";
      box.innerHTML = `<h4>${esc(data.title || data.identifier)}</h4><p class="muted">${meta || "元数据未返回"} · ${esc(access)}</p><div class="identifier-links">${links}</div>${locations ? `<div class="identifier-result">${locations}</div>` : `<p class="fineprint">未发现合法 OA 位置。可尝试学校图书馆/CARSI 入口；软件不会绕过付费墙。</p>`}`;
      status.textContent = "只返回公开元数据和合法 OA 入口；不会保存输入或账号密码。";
    } catch (err) {
      box.innerHTML = "";
      status.textContent = "解析失败：" + err.message;
      if (!err.message.includes("unauthorized")) setTimeout(() => { if (status.textContent.startsWith("解析失败")) status.textContent = old; }, 6000);
    }
  }

  async function loadCapabilities() {
    try {
      const res = await api("/api/v2/compute/capabilities");
      const tools = res.tools || [];
      state.computeCaps = tools;
      $("#compute-caps").innerHTML = tools.map((t) => `<div class="cap card"><b><span class="dot ${t.available ? "on" : "off"}"></span>${esc(t.name)}</b><span>${esc(t.available ? (t.version || "available") : "not available")}</span><span>${esc(t.note || "")}</span></div>`).join("");
    } catch { /* non-blocking */ }
  }

  const TOOL_LABELS = {
    gromacs: "GROMACS 可执行文件", gromacs_lib: "GROMACS 数据目录",
    cp2k: "CP2K 可执行文件", cp2k_data: "CP2K 数据目录",
    mk_prepare_receptor: "Meeko receptor", mk_prepare_ligand: "Meeko ligand",
    obabel: "Open Babel", haddock: "HADDOCK3",
  };

  async function loadTools() {
    try {
      const res = await api("/api/v3/tools");
      state.tools = res;
      const available = res.available || {};
      const detected = state.lang === "en" ? "Detected" : "已检测";
      const missing = state.lang === "en" ? "Not found" : "未找到";
      $("#tool-paths").innerHTML = (res.editable || []).map((key) => `<label class="tool-path-row"><span>${esc(localizedText(TOOL_LABELS[key] || key))} <b class="${available[key] ? "on" : "off"}">${available[key] ? detected : missing}</b></span><input data-tool-key="${esc(key)}" value="${esc(res.paths?.[key] || "")}" spellcheck="false"></label>`).join("");
      const hd = (state.computeCaps || []).find((t) => t.id === "haddock");
      const hdOk = res.available?.haddock || hd?.available;
      $("#tool-status").textContent = hdOk
        ? (state.lang === "en" ? `HADDOCK ${hd?.version || "detected"}; supports protein-protein, protein-ligand and protein-polysaccharide.` : `HADDOCK ${hd?.version || "已检测"}；支持蛋白-蛋白、蛋白-配体与蛋白-多糖。`)
        : (state.lang === "en" ? "HADDOCK not detected; enter the haddock3 path." : "HADDOCK 未检测到；可填写 haddock3 路径。");
    } catch (err) {
      $("#tool-paths").innerHTML = `<p class="note bad">${esc(err.message)}</p>`;
    }
  }

  async function saveTools() {
    const paths = {};
    $$("#tool-paths input[data-tool-key]").forEach((input) => { paths[input.dataset.toolKey] = input.value.trim(); });
    const btn = $("#tool-save");
    btn.disabled = true;
    $("#tool-status").textContent = "正在验证并保存…";
    try {
      const res = await api("/api/v3/tools", { method: "PUT", body: JSON.stringify({ paths }) });
      state.tools = res;
      toast(state.lang === "en" ? "Local tool paths saved." : "本地软件路径已保存。");
      await loadTools();
      await loadCapabilities();
    } catch (err) {
      $("#tool-status").textContent = err.message;
    } finally { btn.disabled = false; }
  }

  function resetParams() {
    const defaults = { "p-exhaustiveness": "8", "p-poses": "9", "p-box": "26", "p-md-mode": "complex", "p-em-steps": "5000", "p-md-steps": "1000", "p-dt": "0.002", "p-temp": "300", "p-threads": "8", "p-timeout-em": "900", "p-timeout-md": "1800", "p-qm-cutoff": "300", "p-qm-scf": "30", "p-advanced-scope": "representative" };
    Object.entries(defaults).forEach(([id, value]) => { const el = $("#" + id); if (el) el.value = value; });
    ["p-docking", "p-md", "p-qm"].forEach((id) => { const el = $("#" + id); if (el) el.checked = true; });
    const seed = $("#p-seed"); if (seed) seed.value = "";
  }

  const HADDOCK_DEFAULTS = {
    "haddock-restraint-radius": "6.5", "haddock-max-restraints": "200",
    "haddock-sampling": "20", "haddock-tolerance": "5", "haddock-select-top": "5",
    "haddock-min-population": "1", "haddock-top-models": "4", "haddock-clust-cutoff": "1.5",
    "haddock-ncores": "8", "haddock-seed": "917", "haddock-timeout": "1800",
    "haddock-w-vdw": "1", "haddock-w-elec": "1", "haddock-inter-rigid": "1",
    "haddock-epsilon": "10", "haddock-mdsteps-rigid": "500", "haddock-mdsteps-cool1": "500",
  };

  function updateHaddockHints() {
    const workflow = $("#haddock-workflow")?.value || "protein-protein";
    const partner = $("#haddock-partner");
    const chain = $("#haddock-partner-chain");
    const activePartner = $("#haddock-active-partner");
    if (!partner) return;
    if (workflow === "protein-ligand") {
      partner.placeholder = "例如 quercetin 或 SMILES";
      if (chain) { chain.value = "B"; chain.disabled = true; }
      if (activePartner) activePartner.placeholder = "例如 1（配体残基号）";
    } else if (workflow === "protein-polysaccharide") {
      partner.placeholder = "例如 1LMQ:B";
      if (chain) chain.disabled = false;
      if (activePartner) activePartner.placeholder = "例如 1,2,3（糖链残基）";
    } else {
      partner.placeholder = "例如 1GFL";
      if (chain) chain.disabled = false;
      if (activePartner) activePartner.placeholder = "例如 1,2,3";
    }
  }

  function resetHaddock() {
    Object.entries(HADDOCK_DEFAULTS).forEach(([id, value]) => { const el = $("#" + id); if (el) el.value = value; });
    const workflow = $("#haddock-workflow"); if (workflow) workflow.value = "protein-protein";
    ["haddock-flexref", "haddock-emref", "haddock-cluster", "haddock-cmrest"].forEach((id) => { const el = $("#" + id); if (el) el.checked = true; });
    const ranair = $("#haddock-ranair"); if (ranair) ranair.checked = false;
    ["haddock-receptor", "haddock-receptor-chain", "haddock-partner", "haddock-active-receptor", "haddock-active-partner", "haddock-query"].forEach((id) => { const el = $("#" + id); if (el) el.value = ""; });
    const chain = $("#haddock-partner-chain"); if (chain) chain.value = "";
    updateHaddockHints();
  }

  function haddockOptions() {
    const val = (id) => $(id)?.value.trim();
    const number = (id) => (val(id) === "" || val(id) == null ? undefined : Number(val(id)));
    const options = {
      haddock_enabled: true,
      haddock_workflow: val("#haddock-workflow") || "protein-protein",
      haddock_receptor: val("#haddock-receptor") || "",
      haddock_receptor_chain: val("#haddock-receptor-chain") || "",
      haddock_partner: val("#haddock-partner") || "",
      haddock_partner_chain: val("#haddock-partner-chain") || "",
      haddock_active_receptor: val("#haddock-active-receptor") || "",
      haddock_active_partner: val("#haddock-active-partner") || "",
      haddock_restraint_radius: number("#haddock-restraint-radius"),
      haddock_max_restraints: number("#haddock-max-restraints"),
      haddock_sampling: number("#haddock-sampling"),
      haddock_tolerance: number("#haddock-tolerance"),
      haddock_select_top: number("#haddock-select-top"),
      haddock_min_population: number("#haddock-min-population"),
      haddock_top_models: number("#haddock-top-models"),
      haddock_clust_cutoff: number("#haddock-clust-cutoff"),
      haddock_ncores: number("#haddock-ncores"),
      haddock_seed: number("#haddock-seed"),
      haddock_timeout: number("#haddock-timeout"),
      haddock_w_vdw: number("#haddock-w-vdw"),
      haddock_w_elec: number("#haddock-w-elec"),
      haddock_inter_rigid: number("#haddock-inter-rigid"),
      haddock_epsilon: number("#haddock-epsilon"),
      haddock_mdsteps_rigid: number("#haddock-mdsteps-rigid"),
      haddock_mdsteps_cool1: number("#haddock-mdsteps-cool1"),
      haddock_flexref: $("#haddock-flexref")?.checked ?? true,
      haddock_emref: $("#haddock-emref")?.checked ?? true,
      haddock_cluster: $("#haddock-cluster")?.checked ?? true,
      haddock_cmrest: $("#haddock-cmrest")?.checked ?? true,
      haddock_ranair: $("#haddock-ranair")?.checked ?? false,
    };
    Object.keys(options).forEach((key) => { if (options[key] === undefined) delete options[key]; });
    return options;
  }

  async function submitHaddock(event) {
    event.preventDefault();
    const query = $("#haddock-query")?.value.trim() || "";
    const receptor = $("#haddock-receptor")?.value.trim() || "";
    const partner = $("#haddock-partner")?.value.trim() || "";
    if (!receptor && !query) { toast("请填写受体 PDB ID/名称，或体系描述。"); return; }
    if (!partner) { toast("请填写对接伙伴（蛋白 PDB、糖链或配体）。"); return; }
    const btn = $("#haddock-form button[type=submit]");
    btn.disabled = true;
    try {
      const payload = { query: query || null, options: haddockOptions() };
      const job = await api("/api/v2/compute/mechanism", { method: "POST", body: JSON.stringify(payload) });
      toast(`HADDOCK3 作业已启动：${job.id}`);
      await loadJobs();
      if (state.poll) clearInterval(state.poll);
      state.poll = setInterval(loadJobs, 5000);
    } catch (err) {
      if (err.message !== "unauthorized") toast(err.message);
      await loadJobs();
    } finally { btn.disabled = false; }
  }

  function computeOptions() {
    const val = (id) => $(id)?.value.trim();
    const number = (id) => (val(id) === "" || val(id) == null ? undefined : Number(val(id)));
    const options = {
      docking_enabled: $("#p-docking")?.checked ?? true,
      md_enabled: $("#p-md")?.checked ?? true,
      md_mode: val("#p-md-mode") || "complex",
      qm_enabled: $("#p-qm")?.checked ?? true,
      docking_exhaustiveness: number("#p-exhaustiveness"),
      docking_poses: number("#p-poses"),
      docking_box_size: number("#p-box"),
      em_steps: number("#p-em-steps"),
      md_steps: number("#p-md-steps"),
      dt_ps: number("#p-dt"),
      temperature_k: number("#p-temp"),
      threads: number("#p-threads"),
      timeout_em: number("#p-timeout-em"),
      timeout_md: number("#p-timeout-md"),
      qm_cutoff_ry: number("#p-qm-cutoff"),
      qm_max_scf: number("#p-qm-scf"),
      advanced_scope: val("#p-advanced-scope") || "representative",
    };
    const receptors = val("#compute-receptors");
    const ligands = val("#compute-ligands");
    if (receptors) options.receptors = receptors;
    if (ligands) options.ligands = ligands;
    const seed = number("#p-seed");
    if (seed != null) options.docking_seed = Math.floor(seed);
    Object.keys(options).forEach((key) => { if (options[key] === undefined) delete options[key]; });
    return options;
  }

  function statusBadge(status) {
    const cls = status === "complete" ? "ok" : status === "error" ? "no" : status === "running" ? "blue" : "";
    return `<span class="badge ${cls}">${esc(status || "unknown")}</span>`;
  }

  async function loadJobs() {
    try {
      const res = await api("/api/v2/compute/jobs");
      state.jobs = (res.items || []).slice().sort((a, b) => String(b.created_utc || "").localeCompare(String(a.created_utc || "")));
      renderJobs(state.jobs);
      const active = (res.items || []).some((j) => ["queued", "running"].includes(j.status));
      if (active && !state.poll) state.poll = setInterval(loadJobs, 5000);
      if (!active && state.poll) { clearInterval(state.poll); state.poll = null; }
    } catch { /* ignore */ }
  }

  function downloadText(filename, text, type = "text/plain") {
    const blob = new Blob([text], { type: `${type};charset=utf-8` });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  function exportJob(job, kind) {
    if (!job) return;
    if (kind === "json") {
      downloadText(`${job.id}-parameters-and-results.json`, JSON.stringify(job, null, 2), "application/json");
      return;
    }
    const result = job.result || {};
    const haddock = result.haddock || (result.engine === "haddock" ? result : null);
    const rows = [
      ["job_id", job.id], ["query", job.query || ""], ["status", job.status], ["created_utc", job.created_utc || ""],
      ["vina_best_affinity_kcal_mol", result.docking?.best_affinity ?? ""],
      ["md_time_ps", result.gromacs?.time_ps ?? ""], ["md_mode", result.gromacs?.md_mode ?? ""], ["em_potential_kj_mol", result.gromacs?.em_potential_kj_mol ?? ""],
      ["cp2k_energy_hartree", result.cp2k?.energy_hartree ?? ""],
      ["haddock_workflow", haddock?.workflow ?? ""], ["haddock_best_score_au", haddock?.score ?? ""],
      ["haddock_score_unit", haddock?.score_unit ?? ""], ["haddock_models", haddock?.models?.length ?? ""],
      ["haddock_clusters", haddock?.clusters?.length ?? ""], ["haddock_best_model", haddock?.best_model ?? ""],
      ["parameter_fingerprint", job.parameter_fingerprint || ""],
      ["seed", (haddock ? job.config?.haddock_seed : job.config?.docking_seed) ?? ""], ["config_json", JSON.stringify(job.config || {})],
    ];
    const csv = rows.map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(",")).join("\n");
    downloadText(`${job.id}-summary.csv`, csv, "text/csv");
  }

  function renderJobs(jobs) {
    const list = $("#jobs-list");
    if (!list) return;
    const count = $("#jobs-count");
    if (count) count.textContent = state.lang === "en" ? `${jobs.length} jobs · newest first` : `${jobs.length} 个任务 · 按时间倒序`;
    if (!jobs.length) { list.innerHTML = '<div class="empty card"><h3>还没有计算任务</h3><p>生成配方后点击“运行机制计算”，或在上方直接输入蛋白与配体。</p></div>'; translateSubtree(list); return; }
    const openIds = new Set(Array.from(list.querySelectorAll("details.job[open]")).map((item) => item.dataset.jobId).filter(Boolean));
    list.innerHTML = jobs.map((j) => {
      const result = j.result || {};
      const pairs = j.pairs || [];
      const ranking = result.ranking || [];
      const haddock = result.haddock || (result.engine === "haddock" ? result : null) || {};
      const isHaddock = Boolean(result.haddock || result.engine === "haddock" || j.engine === "haddock" || j.config?.haddock_enabled === true);
      const target = j.target || result.target || {};
      const systemLabel = isHaddock
        ? ([target.pdb_id || target.protein || "", target.partner_pdb_id || target.partner || target.ligand || ""].filter(Boolean).join(" + ") || "HADDOCK3")
        : (pairs.slice(0, 3).map((p) => `${p.pdb_id}/${p.ligand}`).join(" · ") || "—");
      const chips = [];
      if (isHaddock) {
        if (haddock.workflow) chips.push(`HADDOCK ${haddock.workflow}`);
        if (haddock.score != null) chips.push(`score ${num(haddock.score, 3)} a.u.`);
        if (haddock.models?.length) chips.push(`${haddock.models.length} 模型`);
        if (haddock.clusters?.length) chips.push(`${haddock.clusters.length} 簇`);
        if (haddock.flexref) chips.push("flexref");
        if (haddock.emref) chips.push("emref");
        if (haddock.cluster) chips.push("聚类");
        if (haddock.reference_used === false) chips.push("无实验参考");
      } else {
        if (result.docking?.best_affinity != null) chips.push(`Vina ${num(result.docking.best_affinity, 2)} kcal/mol`);
        if (result.gromacs?.time_ps != null) chips.push(`MD ${num(result.gromacs.time_ps, 1)} ps`);
        if (result.gromacs?.md_mode === "complex") chips.push("复合物 MD");
        if (result.gromacs?.complex_error) chips.push("复合物回退");
        if (result.gromacs?.em_potential_kj_mol != null) chips.push(`EM ${num(result.gromacs.em_potential_kj_mol, 0)} kJ/mol`);
        if (result.gromacs?.em_converged === false) chips.push("EM 未收敛");
        if (result.cp2k?.energy_hartree != null) chips.push(`PBE ${num(result.cp2k.energy_hartree, 3)} Ha`);
      }
      if (j.failed_validation) chips.push("输入校验失败");
      else if (j.error) chips.push("作业失败");
      if (!isHaddock && j.config?.advanced_scope) chips.push(`高级 ${j.config.advanced_scope === "all" ? "全部" : "代表项"}`);
      if (!isHaddock && pairs.length > 1) chips.push(`${pairs.length} 对组合`);
      const artifacts = Array.from(new Set([...(result.artifacts || []), ...(j.steps || []).flatMap((s) => s.artifacts || [])]));
      const priority = (a) => {
        const x = a.toLowerCase();
        if (x.endsWith("best_model.pdb")) return 0;
        if (x === "complex.pdb" || x.endsWith("/complex.pdb")) return 0;
        if (x.includes("report.html") || x.endsWith("report.pdf")) return 1;
        if (x.endsWith("capri_ss.tsv")) return 2;
        if (x.endsWith("capri_clt.tsv")) return 3;
        if (x.endsWith("haddock.cfg")) return 4;
        if (x.endsWith("haddock_inputs.json")) return 5;
        if (x.endsWith("stdout.log")) return 6;
        if (x.includes("screening.csv")) return 2;
        if (x.endsWith("receptor.pdb")) return 3;
        if (x.includes("poses.pdbqt")) return 4;
        if (x.endsWith("md.gro")) return 5;
        if (x.endsWith("vina_result.json")) return 6;
        if (/\.(pdb|pdbqt|gro)$/.test(x)) return 7;
        if (x.endsWith(".json") || x.endsWith(".md") || x.endsWith(".csv")) return 8;
        return 9;
      };
      artifacts.sort((a, b) => priority(a) - priority(b));
      const table = isHaddock
        ? `<div class="matrix-table-wrap"><table class="matrix-table"><thead><tr><th>#</th><th>HADDOCK score (a.u.)</th><th>簇</th><th>簇大小</th><th>模型</th></tr></thead><tbody>${(haddock.models || []).slice(0, 20).map((row) => {
            const artifact = row.artifact || "";
            const url = artifact ? `/api/v2/compute/jobs/${encodeURIComponent(j.id)}/artifacts/${artifact.split("/").map(encodeURIComponent).join("/")}` : "";
            const model = row.model || artifact || "—";
            const clusterId = haddock.cluster === false ? null : row.cluster_id;
            const clusterPopulation = haddock.cluster === false ? null : row.cluster_population;
            return `<tr><td>${row.rank ?? "—"}</td><td class="${row.rank === 1 ? "best" : ""}">${row.score == null ? "—" : num(row.score, 3)}</td><td>${clusterId ?? "—"}</td><td>${clusterPopulation ?? "—"}</td><td>${url ? `<button type="button" class="linkish structure-open" data-pdb-url="${esc(url)}" data-pdb-label="${esc(`${j.id}/${model}`)}">3D · ${esc(model)}</button>` : esc(model)}</td></tr>`;
          }).join("") || '<tr><td colspan="5" class="muted">等待 HADDOCK3 结果…</td></tr>'}</tbody></table></div>`
        : ranking.length ? `<div class="matrix-table-wrap"><table class="matrix-table"><thead><tr><th>#</th><th>受体</th><th>配体</th><th>Vina kcal/mol</th><th>复合物</th></tr></thead><tbody>${ranking.slice(0, 12).map((row) => `<tr><td>${row.rank}</td><td>${esc(row.pdb_id)}</td><td>${esc(row.ligand)}</td><td class="${row.rank === 1 ? "best" : ""}">${row.best_affinity == null ? "—" : num(row.best_affinity, 2)}</td><td>${row.complex_pdb ? `<button type="button" class="linkish structure-open" data-pdb-url="/api/v2/compute/jobs/${encodeURIComponent(j.id)}/artifacts/${row.complex_pdb.split("/").map(encodeURIComponent).join("/")}" data-pdb-label="${esc(`${j.id}/${row.complex_pdb}`)}">3D 复合物</button>` : "—"}</td></tr>`).join("")}</tbody></table></div>` : "";
      return `<details class="job card" data-job-id="${esc(j.id)}" ${openIds.has(j.id) ? "open" : ""}>
        <summary>
          <div class="job-head"><div><h4>${esc(localizedText(j.query || "多受体 × 多配体筛选"))}</h4><p class="muted" style="font-size:11px;margin:3px 0 0">${esc(j.id)} · ${esc((j.created_utc || "").slice(0, 16).replace("T", " "))}${j.design_id ? ` · 配方 ${esc(j.design_id)}` : ""}</p></div>${statusBadge(j.status)}</div>
          ${chips.length ? `<div class="job-result">${chips.map((x) => `<span>${esc(x)}</span>`).join("")}</div>` : ""}
          <span class="job-open-hint">点击查看记录摘要</span>
        </summary>
        <div class="job-body">
          <div class="job-summary-grid">
            <div><span>任务</span><b>${esc(j.id)}</b></div>
            <div><span>状态</span><b>${esc(j.status || "unknown")}</b></div>
            <div><span>体系</span><b>${esc(systemLabel)}</b></div>
            <div><span>创建</span><b>${esc((j.created_utc || "").slice(0, 19).replace("T", " "))}</b></div>
          </div>
          ${j.error ? `<p class="note bad">${esc(localizedText(j.error))}</p>` : ""}
          <details class="job-detail">
            <summary>展开详细结果、步骤、文件与导出</summary>
            <div class="job-steps">${(j.steps || []).map((s) => `<div class="job-step ${esc(s.status)}" title="${esc(s.detail || s.label)}">${esc(s.label)}</div>`).join("")}</div>
            ${table}
            ${j.parameter_fingerprint ? `<p class="fineprint mono" style="margin-top:8px">指纹 ${esc(j.parameter_fingerprint.slice(0, 20))}… · seed ${esc((isHaddock ? j.config?.haddock_seed : j.config?.docking_seed) ?? "—")}</p>` : ""}
            ${artifacts.length ? `<div class="artifact-links">${artifacts.slice(0, 14).map((a) => {
              const url = `/api/v2/compute/jobs/${encodeURIComponent(j.id)}/artifacts/${a.split("/").map(encodeURIComponent).join("/")}`;
              if (/\.xtc$/i.test(a)) return `<button type="button" class="linkish trajectory-open" data-traj-url="/api/v3/structure/trajectory/${encodeURIComponent(j.id)}/${a.split("/").map(encodeURIComponent).join("/")}" data-pdb-label="${esc(`${j.id}/${a}`)}">3D 轨迹 · ${esc(a)}</button>`;
              return /\.(pdb|pdbqt|gro)$/i.test(a)
                ? `<button type="button" class="linkish structure-open" data-pdb-url="${esc(url)}" data-pdb-label="${esc(`${j.id}/${a}`)}">3D · ${esc(a)}</button>`
                : `<a href="${url}" target="_blank" rel="noopener">${esc(a)}</a>`;
            }).join("")}</div>` : ""}
            <div class="job-actions"><button type="button" class="linkish" data-export-job="json" data-job-id="${esc(j.id)}">导出参数与结果 JSON</button><button type="button" class="linkish" data-export-job="csv" data-job-id="${esc(j.id)}">导出摘要 CSV</button></div>
          </details>
        </div>
      </details>`;
    }).join("");
    translateSubtree(list);
  }

  async function submitCompute(event) {
    event.preventDefault();
    const query = $("#compute-query").value.trim();
    const receptors = $("#compute-receptors")?.value.trim();
    const ligands = $("#compute-ligands")?.value.trim();
    if (!query && !state.computeDesign && !receptors && !ligands) { toast("请输入体系、受体/配体，或先关联配方。"); return; }
    const btn = $("#compute-form button[type=submit]");
    btn.disabled = true;
    try {
      const payload = { query: query || null, options: computeOptions() };
      if (state.computeDesign) payload.design_id = state.computeDesign;
      const job = await api("/api/v2/compute/mechanism", { method: "POST", body: JSON.stringify(payload) });
      toast("作业已启动，正在后台运行。");
      await loadJobs();
      if (state.poll) clearInterval(state.poll);
      state.poll = setInterval(loadJobs, 5000);
    } catch (err) {
      if (err.message !== "unauthorized") toast(err.message);
      await loadJobs();
    } finally { btn.disabled = false; }
  }

  function useCompute(design) {
    state.computeDesign = design.design_id;
    $("#compute-design").innerHTML = `已关联 <b>${esc(design.design_id)}</b> · ${esc(state.caseTitle || design.system?.cn_name || design.selected?.cn_name || design.selected?.name || "")}`;
    $("#compute-query").value = design.brief?.query || "";
    setPage("compute");
  }

  async function changePassword(event) {
    event.preventDefault();
    const current_password = $("#pw-current").value;
    const new_password = $("#pw-new").value;
    try {
      await api("/api/auth/password", { method: "POST", body: JSON.stringify({ current_password, new_password }) });
      $("#pw-current").value = "";
      $("#pw-new").value = "";
      $("#pw-msg").textContent = "密码已更新。";
      toast("密码已更新。");
    } catch (err) { $("#pw-msg").textContent = err.message; }
  }

  function assistantLineBreaks(text) {
    return String(text || "").split(/\n{2,}/).map((part) => `<p>${esc(part).replace(/\n/g, "<br>")}</p>`).join("");
  }

  function ragT(zh, en) {
    return state.lang === "en" ? en : zh;
  }

  function ragNodeLabel(node) {
    const labels = {
      plan: ["规划", "Plan"],
      local_retrieve: ["本地检索", "Local search"],
      graph_expand: ["图谱扩展", "Graph expand"],
      assess_quality: ["质量门控", "Quality gate"],
      external_retrieve: ["外部 OA", "External OA"],
      draft: ["生成", "Draft"],
      verify: ["核验", "Verify"],
      revise: ["回查", "Revise"],
      human_rollback: ["人工回滚", "Human rollback"],
    };
    const pair = labels[node] || [node, node];
    return ragT(pair[0], pair[1]);
  }

  function ragQuality(q = {}) {
    const map = {
      strong: ["较强", "Strong", "ok"],
      moderate: ["中等", "Moderate", "blue"],
      weak: ["偏弱", "Weak", "warn"],
      insufficient: ["不足", "Insufficient", "no"],
    };
    const item = map[q.label] || [q.label || "—", q.label || "—", "blue"];
    return { zh: item[0], en: item[1], cls: item[2] };
  }

  function ragReviewStatus(status) {
    const map = {
      pending_review: ["待人工审核", "Pending human review", "warn"],
      approved: ["已审核通过", "Approved", "ok"],
      rejected: ["已驳回", "Rejected", "no"],
      rolled_back: ["已回滚", "Rolled back", "blue"],
    };
    const item = map[status] || [status || "—", status || "—", "blue"];
    return { zh: item[0], en: item[1], cls: item[2] };
  }

  function renderRagResult(res) {
    const answer = $("#assistant-answer");
    if (!answer || !res) return;
    const q = ragQuality(res.quality || {});
    const rs = ragReviewStatus(res.status);
    const warnings = res.warnings || [];
    const route = res.route || [];
    const evidence = res.evidence || [];
    const graph = res.graph || {};
    const verification = res.verification || {};
    const concepts = graph.concepts || [];
    const edges = graph.edges || [];
    const seen = new Set();
    const routeNodes = route.filter((item) => {
      if (seen.has(item.node)) return false;
      seen.add(item.node);
      return true;
    }).map((item) => `<span class="rag-route-node" title="${esc(item.detail || "")}">${esc(ragNodeLabel(item.node))}</span>`).join('<span class="rag-route-arrow">→</span>');
    const warningHtml = warnings.length ? `<div class="rag-warning"><b>${ragT("证据警告", "Evidence warnings")}</b><ul>${warnings.map((item) => `<li>${esc(item)}</li>`).join("")}</ul></div>` : "";
    const evidenceHtml = evidence.length ? `<details class="rag-details" open><summary>${ragT("证据清单", "Evidence")} · ${evidence.length}</summary><div class="rag-evidence-list">${evidence.map((item) => `
      <details class="rag-evidence-item">
        <summary><b>[${esc(item.evidence_id || "")}]</b> ${esc(item.title || "")}<span>${esc(item.source || "")}${item.year ? " · " + esc(item.year) : ""}${item.license ? " · " + esc(item.license) : ""}</span></summary>
        <p>${esc(item.snippet || item.abstract || ragT("仅题录信息。", "Metadata only."))}</p>
        ${item.url ? `<a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${ragT("打开原始入口", "Open source")} ↗</a>` : ""}
      </details>`).join("")}</div></details>` : "";
    const conceptHtml = concepts.length ? `<details class="rag-details"><summary>${ragT("图谱概念与标签", "Graph concepts and labels")} · ${concepts.length}</summary><div class="rag-concepts">${concepts.map((item) => `<span class="rag-concept">${esc(item.label || item.id || "")}<small>${esc(item.papers ?? "")}</small></span>`).join("")}</div><p class="fineprint">${esc(graph.notice || "")}</p></details>` : "";
    const edgesHtml = edges.length ? `<details class="rag-details"><summary>${ragT("关系边", "Relation edges")} · ${edges.length}</summary><div class="rag-edges">${edges.slice(0, 16).map((edge) => `<div><code>${esc(edge.label || edge.predicate || "")}</code><span>${esc(edge.source || "")} → ${esc(edge.target || "")}</span><small>${esc(edge.status || "")}</small></div>`).join("")}</div><p class="fineprint">${ragT("关键词共现关系是待验证假设；流程/模型关系不等于实验证据。", "Keyword co-occurrence is a hypothesis; workflow/model edges are not experimental evidence.")}</p></details>` : "";
    const claims = (verification.claims || []).slice(0, 6);
    const verifyHtml = `<details class="rag-details"><summary>${ragT("逐句核验", "Claim verification")} · ${esc(verification.status || "—")} · ${Math.round(Number(verification.support_rate || 0) * 100)}%</summary><div class="rag-claims">${claims.map((claim) => `<div class="rag-claim ${claim.status === "supported" ? "ok" : "warn"}"><span>${claim.status === "supported" ? "✓" : "!"}</span><p>${esc(claim.claim)}</p><small>${esc((claim.citations || []).join(" "))}</small></div>`).join("") || `<p class="muted">${ragT("无逐句核验记录。", "No claim-level checks.")}</p>`}</div><p class="fineprint">${esc(verification.rule || "")}</p></details>`;
    const actions = `<div class="rag-actions" data-rag-run="${esc(res.id || "")}">
      <button class="btn ghost small" type="button" data-rag-action="approve">${ragT("审核通过", "Approve")}</button>
      <button class="btn ghost small" type="button" data-rag-action="reject">${ragT("驳回", "Reject")}</button>
      <button class="btn ghost small" type="button" data-rag-action="feedback-up">${ragT("有帮助 +1", "Helpful +1")}</button>
      <button class="btn ghost small" type="button" data-rag-action="feedback-down">${ragT("无帮助 -1", "Not helpful -1")}</button>
      <button class="btn ghost small" type="button" data-rag-action="rollback">${ragT("回滚并重查", "Rollback & retry")}</button>
    </div>`;
    answer.innerHTML = `
      <div class="rag-summary">
        <span class="badge ${q.cls}">${ragT("证据", "Evidence")}：${ragT(q.zh, q.en)} · ${Math.round(Number((res.quality || {}).score || 0) * 100)}</span>
        <span class="badge ${rs.cls}">${ragT(rs.zh, rs.en)}</span>
        <span class="badge blue">${esc((res.engine || "langgraph"))}</span>
        <span class="badge">${ragT("证据", "Evidence")} ${evidence.length} · ${ragT("外部", "External")} ${(res.quality || {}).external_count || 0}</span>
      </div>
      <div class="rag-route">${routeNodes || `<span class="rag-route-node">${ragT("无路由记录", "No route")}</span>`}</div>
      <div class="rag-answer-text">${assistantLineBreaks(res.answer || "")}</div>
      ${warningHtml}
      ${evidenceHtml}
      ${conceptHtml}
      ${edgesHtml}
      ${verifyHtml}
      <p class="meta">${ragT("本地库", "Local library")} ${((res.limits || {}).local_library || {}).papers || 0} ${ragT("篇 OA；回答需人工审核，不构成同行评审或监管批准。", "OA papers; human review is required and is not peer review or regulatory approval.")}</p>
      ${res.deepagent?.status ? `<p class="fineprint">DeepAgent：${esc(res.deepagent.status)} · ${esc(res.deepagent.reason || "")}</p>` : ""}
      ${actions}
    `;
  }

  async function loadRagQueue() {
    const box = $("#rag-queue-list");
    const count = $("#rag-queue-count");
    if (!box) return;
    try {
      const res = await api("/api/v3/rag/reviews?status=pending_review&limit=20");
      const items = res.items || [];
      if (count) count.textContent = `${items.length} ${ragT("条待审核", "pending")}`;
      box.innerHTML = items.length ? items.map((item) => {
        const q = ragQuality(item.quality || {});
        return `<button class="rag-queue-item" type="button" data-run-id="${esc(item.id || "")}"><b>${esc(item.question || "")}</b><span>${esc(String(item.created_at || "").slice(0, 16).replace("T", " "))} · ${ragT(q.zh, q.en)}</span></button>`;
      }).join("") : `<p class="muted">${ragT("没有待审核记录。", "No pending reviews.")}</p>`;
    } catch {
      if (count) count.textContent = ragT("不可用", "unavailable");
      box.innerHTML = `<p class="muted">${ragT("审核队列暂不可用。", "Review queue unavailable.")}</p>`;
    }
  }

  async function loadAssistantStatus() {
    const badge = $("#assistant-status");
    try {
      const [status, ragStatus] = await Promise.all([
        api("/api/v3/assistant/status"),
        api("/api/v3/rag/status"),
      ]);
      state.assistantStatus = status;
      state.ragStatus = ragStatus;
      if (badge) {
        badge.textContent = `${ragStatus.orchestrator || "langgraph"} · ${ragStatus.local_literature?.papers || 0} OA`;
        badge.className = "badge ok";
      }
      await Promise.all([loadAssistantHistory(), loadRagQueue()]);
    } catch (err) {
      if (badge) { badge.textContent = "状态不可用"; badge.className = "badge no"; }
      if (err.message !== "unauthorized") toast(err.message);
    }
  }

  async function loadAssistantHistory() {
    const box = $("#assistant-history");
    if (!box) return;
    const query = $("#assistant-history-search")?.value.trim() || "";
    try {
      const res = await api(`/api/v3/assistant/history?limit=300&q=${encodeURIComponent(query)}`);
      const all = res.items || [];
      const items = state.lang === "en" ? all.filter((item) => !/[\u3400-\u9fff]/.test(`${item.question || ""}${item.answer || ""}`)) : all;
      const count = $("#assistant-history-count");
      if (count) count.textContent = state.lang === "en"
        ? `${items.length} English records shown / ${res.count ?? all.length} total`
        : `${items.length} 条显示 / 共 ${res.count ?? all.length} 条`;
      box.innerHTML = items.length ? items.map((item) => `<details class="assistant-history-item" data-assistant-id="${esc(item.id || "")}">
        <summary><b>${esc(item.question || (state.lang === "en" ? "(no question)" : "（无问题）"))}</b><span>${esc(String(item.ts || "").slice(0, 16).replace("T", " "))} · ${esc(item.model || "")}</span></summary>
        <div class="assistant-history-answer">${assistantLineBreaks(item.answer || (state.lang === "en" ? "(no answer)" : "（无回答）"))}</div>
      </details>`).join("") + (state.lang === "en" ? '<p class="fineprint">English mode shows English-language records only.</p>' : "") : `<p class="muted">${state.lang === "en" ? "No English-language assistant records yet." : "还没有匹配的服务器记录。"}</p>`;
    } catch { box.innerHTML = '<p class="muted">历史记录暂不可用。</p>'; }
  }

  async function askAssistant(event) {
    event.preventDefault();
    const input = $("#assistant-question");
    const answer = $("#assistant-answer");
    const button = $("#assistant-form button[type=submit]");
    const question = input?.value.trim();
    if (!question) { toast(ragT("请输入问题。", "Enter a question.")); return; }
    button.disabled = true;
    button.textContent = ragT("检索与核验中…", "Retrieving & verifying…");
    answer.innerHTML = `<p class="muted"><span class="spinner"></span> ${ragT("先查本地 10,000 篇 OA + 图谱；证据不足再查外部 OA；随后逐句核验。27B 模型可能较慢…", "Searching local 10,000 OA + graph; falling back to external OA if needed; then verifying claims. The 27B model may be slow…")}</p>`;
    try {
      const res = await api("/api/v3/rag/ask", { method: "POST", body: JSON.stringify({ question, max_iterations: 2 }) });
      renderRagResult(res);
      input.value = "";
      await Promise.all([loadAssistantHistory(), loadRagQueue()]);
    } catch (err) {
      answer.innerHTML = `<p class="note bad">${esc(err.message)}</p>`;
    } finally {
      button.disabled = false;
      button.textContent = ragT("检索并回答", "Search & answer");
    }
  }

  async function ragReviewAction(button) {
    const runId = button.closest("[data-rag-run]")?.dataset.ragRun;
    const action = button.dataset.ragAction;
    if (!runId || !action) return;
    if (action === "rollback") {
      const note = window.prompt(ragT("回滚原因/补充检索词（可留空）", "Rollback reason / extra search terms (optional)"), "");
      if (note === null) return;
      button.disabled = true;
      try {
        const res = await api(`/api/v3/rag/runs/${encodeURIComponent(runId)}/rollback`, { method: "POST", body: JSON.stringify({ reviewer: "local-human-reviewer", note, extra_query: note }) });
        renderRagResult(res.new_run);
        toast(ragT("已回滚并生成新记录；旧记录保留。", "Rolled back; old record retained."));
        await loadRagQueue();
      } catch (err) { toast(err.message); }
      finally { button.disabled = false; }
      return;
    }
    if (action === "feedback-up" || action === "feedback-down") {
      button.disabled = true;
      try {
        await api(`/api/v3/rag/runs/${encodeURIComponent(runId)}/feedback`, { method: "POST", body: JSON.stringify({ reward: action === "feedback-up" ? 1 : -1, dimension: "user_feedback" }) });
        toast(ragT("反馈已记录，并更新关系权重。", "Feedback recorded and relation weights updated."));
      } catch (err) { toast(err.message); }
      finally { button.disabled = false; }
      return;
    }
    const note = window.prompt(action === "approve" ? ragT("审核备注（可留空）", "Review note (optional)") : ragT("驳回原因（建议填写）", "Rejection reason (recommended)"), "");
    if (note === null) return;
    button.disabled = true;
    try {
      const res = await api(`/api/v3/rag/runs/${encodeURIComponent(runId)}/review`, { method: "POST", body: JSON.stringify({ action, reviewer: "local-human-reviewer", note }) });
      renderRagResult(res.record);
      toast(action === "approve" ? ragT("已审核通过。", "Approved.") : ragT("已驳回。", "Rejected."));
      await loadRagQueue();
    } catch (err) { toast(err.message); }
    finally { button.disabled = false; }
  }

  function markdownToHtml(text) {
    const raw = String(text || "").replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, "");
    const escaped = esc(raw.replace(/\[\[([^\]]+)\]\]/g, "$1").replace(/!\[\[([^\]]+)\]\]/g, "$1"));
    const lines = escaped.split(/\r?\n/);
    const out = [];
    let inCode = false, inList = false;
    const inline = (value) => value
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    lines.forEach((line) => {
      if (line.trim().startsWith("```")) {
        if (inList) { out.push("</ul>"); inList = false; }
        out.push(inCode ? "</pre>" : "<pre>");
        inCode = !inCode;
        return;
      }
      if (inCode) { out.push(line); return; }
      if (/^\s*[-*]\s+/.test(line)) {
        if (!inList) { out.push("<ul>"); inList = true; }
        out.push(`<li>${inline(line.replace(/^\s*[-*]\s+/, ""))}</li>`);
        return;
      }
      if (inList) { out.push("</ul>"); inList = false; }
      const heading = line.match(/^(#{1,4})\s+(.*)$/);
      if (heading) { out.push(`<h${heading[1].length}>${inline(heading[2])}</h${heading[1].length}>`); return; }
      if (/^\s*$/.test(line)) { out.push(""); return; }
      if (/^\s*\|/.test(line)) { out.push(`<p class="mono">${inline(line)}</p>`); return; }
      out.push(`<p>${inline(line)}</p>`);
    });
    if (inList) out.push("</ul>");
    if (inCode) out.push("</pre>");
    return out.join("\n");
  }

  async function loadNotes() {
    const select = $("#notes-select");
    const status = $("#notes-status");
    if (!select) return;
    try {
      const res = await api("/api/v3/notes");
      state.notes = res;
      if (status) { status.textContent = res.exists ? `${res.count} 篇 · 只读` : "目录不存在"; status.className = `badge ${res.exists ? "blue" : "no"}`; }
      const previous = select.value;
      const placeholder = state.lang === "en" ? "Select a note to view the original Chinese text…" : "选择一篇笔记…";
      select.innerHTML = `<option value="">${placeholder}</option>` + ((res.items || []).length
        ? res.items.map((item) => `<option value="${esc(item.path)}">${esc(item.title)} · ${esc(item.path)}</option>`).join("")
        : `<option value="">${state.lang === "en" ? "No Markdown notes found" : "没有找到 Markdown 笔记"}</option>`);
      if (state.lang === "en") {
        select.value = "";
        const box = $("#notes-content");
        if (box) box.innerHTML = '<p class="muted">Obsidian notes in this deployment are currently in Chinese. Select a note to view the original text.</p>';
      } else if (previous && (res.items || []).some((item) => item.path === previous)) {
        select.value = previous;
        if (select.value) readNote(select.value);
      } else if (select.value) readNote(select.value);
      else { const box = $("#notes-content"); if (box) box.innerHTML = '<p class="muted">目录为空或不可用；请检查 BIOFORGE_OBSIDIAN_DIR。</p>'; }
    } catch (err) {
      if (status) { status.textContent = "读取失败"; status.className = "badge no"; }
      const box = $("#notes-content");
      if (box) box.innerHTML = `<p class="note bad">${esc(err.message)}</p>`;
    }
  }

  async function readNote(path) {
    const box = $("#notes-content");
    if (!box || !path) return;
    try {
      const res = await api(`/api/v3/notes/read?path=${encodeURIComponent(path)}`);
      box.innerHTML = markdownToHtml(res.text);
      const status = $("#notes-status");
      if (status) { status.textContent = `只读 · ${String(res.modified || "").slice(0, 10)}`; status.className = "badge blue"; }
    } catch (err) {
      box.innerHTML = `<p class="note bad">${esc(err.message)}</p>`;
    }
  }

  function initAssistantAndNotes() {
    $("#assistant-form")?.addEventListener("submit", askAssistant);
    $("#assistant-history-refresh")?.addEventListener("click", loadAssistantHistory);
    $("#rag-queue-refresh")?.addEventListener("click", loadRagQueue);
    let historyTimer = null;
    $("#assistant-history-search")?.addEventListener("input", () => {
      clearTimeout(historyTimer);
      historyTimer = setTimeout(loadAssistantHistory, 240);
    });
    $("#assistant-history")?.addEventListener("click", (event) => {
      const item = event.target.closest(".assistant-history-item");
      if (!item || event.target.closest("a")) return;
      const answer = $("#assistant-answer");
      const content = item.querySelector(".assistant-history-answer");
      if (answer && content) answer.innerHTML = content.innerHTML + `<p class="meta">历史记录 ${esc(item.dataset.assistantId || "")}</p>`;
    });
    $("#assistant-answer")?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-rag-action]");
      if (button) ragReviewAction(button);
    });
    $("#rag-queue-list")?.addEventListener("click", async (event) => {
      const button = event.target.closest("[data-run-id]");
      if (!button) return;
      try {
        const record = await api(`/api/v3/rag/runs/${encodeURIComponent(button.dataset.runId)}`);
        renderRagResult(record);
        $("#assistant-answer")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      } catch (err) { toast(err.message); }
    });
    $("#notes-select")?.addEventListener("change", (event) => readNote(event.target.value));
    $("#notes-refresh")?.addEventListener("click", loadNotes);
    setInterval(() => {
      if (state.page !== "guide" || !$("#notes-auto")?.checked) return;
      const path = $("#notes-select")?.value;
      if (path && !$("#assistant-form button[type=submit]")?.disabled) readNote(path);
    }, 15000);
  }

  function swipe() {
    let x0 = null, y0 = null;
    const main = $("#main");
    main.addEventListener("touchstart", (e) => {
      if (e.touches.length !== 1) return;
      x0 = e.touches[0].clientX; y0 = e.touches[0].clientY;
    }, { passive: true });
    main.addEventListener("touchend", (e) => {
      if (x0 == null || !e.changedTouches.length) return;
      const dx = e.changedTouches[0].clientX - x0;
      const dy = e.changedTouches[0].clientY - y0;
      x0 = null; y0 = null;
      if ($(".sidebar")?.classList.contains("open") && dx < -40) return;
      if (Math.abs(dx) < 90 || Math.abs(dy) > 52 || Math.abs(dx) < Math.abs(dy) * 1.8) return;
      if (e.target.closest(".rail, .assistant-form, .assistant-sidebar, .assistant-history-list, .notes-content, .table-wrap, .matrix-table-wrap, .lab-tabs, .theme-grid, .spectrum-chart-wrap, .graph-canvas, .structure-canvas, input, textarea, select")) return;
      const order = ["design", "cases", "evidence", "compute", "lab", "resources", "guide", "settings"];
      const idx = order.indexOf(state.page);
      const next = dx < 0 ? order[Math.min(order.length - 1, idx + 1)] : order[Math.max(0, idx - 1)];
      if (next !== state.page) setPage(next);
    }, { passive: true });
    let closeX = null, closeY = null;
    document.addEventListener("touchstart", (e) => {
      if (!$(".sidebar")?.classList.contains("open") || e.touches.length !== 1) { closeX = null; return; }
      closeX = e.touches[0].clientX; closeY = e.touches[0].clientY;
    }, { passive: true });
    document.addEventListener("touchend", (e) => {
      if (closeX == null || !e.changedTouches.length) return;
      const dx = e.changedTouches[0].clientX - closeX;
      const dy = e.changedTouches[0].clientY - closeY;
      closeX = null; closeY = null;
      if (dx < -60 && Math.abs(dy) < 48 && Math.abs(dx) > Math.abs(dy) * 1.8) $(".sidebar")?.classList.remove("open");
    }, { passive: true });
  }

  const moleculeViewer = (() => {
    const canvas = $("#structure-canvas");
    const hint = $("#structure-hint");
    const meta = $("#structure-meta");
    if (!canvas) return { loadUrl: () => {}, loadText: () => {}, reset: () => {} };
    const ctx = canvas.getContext("2d");
    const elementColors = { C: "#9fb4c7", N: "#6ea8ff", O: "#ff6b6b", S: "#ffd166", P: "#ff9f43", F: "#75e6a4", CL: "#75e6a4", BR: "#c084fc", I: "#c084fc", H: "#e8eef5", NA: "#e879f9", FE: "#e879f9", ZN: "#a3a3a3", MG: "#4ade80", CA: "#22d3ee" };
    const vdw = { C: 1.7, N: 1.55, O: 1.52, S: 1.8, P: 1.8, F: 1.47, CL: 1.75, BR: 1.85, I: 1.98, H: 1.2 };
    const chainColors = ["#6ea8ff", "#ff9f43", "#75e6a4", "#c084fc", "#ffd166", "#ff6b6b", "#22d3ee", "#f472b6"];
    const AA = { ALA: "A", ARG: "R", ASN: "N", ASP: "D", CYS: "C", GLN: "Q", GLU: "E", GLY: "G", HIS: "H", ILE: "I", LEU: "L", LYS: "K", MET: "M", PHE: "F", PRO: "P", SER: "S", THR: "T", TRP: "W", TYR: "Y", VAL: "V", SEC: "U", PYL: "O", MSE: "M" };
    const standardAA = new Set(Object.keys(AA));
    const WATERS = new Set(["SOL", "WAT", "HOH", "TIP", "TIP3", "TIP3P", "TIP4", "SPC", "SPCE", "T3P", "T4P"]);
    const IONS = new Set(["NA", "CL", "K", "CA", "MG", "ZN", "FE", "MN", "CU", "BR", "IOD", "F", "LI", "CS", "RB", "SR", "BA", "CD", "CO", "NI", "AL", "SI", "NA+", "CL-", "K+", "CA2", "MG2"]);
    const GLYCANS = new Set(["NAG", "MAN", "BMA", "GAL", "GLC", "GCS", "FUC", "SIA", "NGA", "NDG", "BGC", "XYS", "RIB", "FRU", "GLA", "GALN", "GLCN", "SAH"]);
    const LIPIDS = new Set(["POPC", "POPE", "DPPC", "DOPC", "DOPE", "DMPC", "CHL", "CLR", "PLM", "OLA", "PAL", "MYR", "STE", "CER", "Sph"]);
    const NUCLEIC = new Set(["DA", "DC", "DG", "DT", "DU", "A", "C", "G", "U", "I", "T", "PSU", "5MC", "1MA", "M2G", "OMG", "OMC"]);
    const NUCLEIC_LETTER = { DA: "A", DC: "C", DG: "G", DT: "T", DU: "U", A: "A", C: "C", G: "G", U: "U", I: "I", T: "T", PSU: "U", "5MC": "C", "1MA": "A", M2G: "G", OMG: "G", OMC: "C" };
    const COMPONENT_LABELS = { protein: "蛋白/多肽", nucleic: "核酸", water: "水", ion: "离子", glycan: "糖链", lipid: "脂质", ligand: "配体/小分子", other: "其他" };
    const COMPONENT_COLORS = { protein: "#6ea8ff", nucleic: "#c084fc", water: "#22d3ee", ion: "#e879f9", glycan: "#ffd166", lipid: "#f472b6", ligand: "#75e6a4", other: "#9fb4c7" };
    let structures = [], current = null, modelIndex = 0, name = "";
    let style = "cartoon", colorMode = "element";
    let visibleComponents = new Set(["protein", "nucleic", "ligand", "glycan", "lipid", "ion"]);
    let componentSelectionReady = false;
    let rotX = -0.22, rotY = 0.55, zoom = 1, panX = 0, panY = 0, spin = true;
    let dragging = false, dragMode = "rotate", lastX = 0, lastY = 0, pinch = 0, pointers = new Map();
    let selected = null, screenAtoms = [], label = "structure";

    function size() {
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const rect = canvas.getBoundingClientRect();
      const w = Math.max(1, Math.round(rect.width * dpr));
      const h = Math.max(1, Math.round(rect.height * dpr));
      if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
      return { w: rect.width, h: rect.height, dpr };
    }

    function inferElement(line, atomName, pdbqt) {
      if (!pdbqt) {
        const raw = (line.slice(76, 78) || "").trim().toUpperCase();
        if (raw && /^[A-Z]{1,2}$/.test(raw)) return raw;
      }
      const letters = (atomName || "").replace(/[^A-Za-z]/g, "").toUpperCase();
      if (!letters) return "C";
      if (letters.startsWith("CL")) return "CL";
      if (letters.startsWith("BR")) return "BR";
      if (/^(FE|ZN|MG)$/.test(letters)) return letters;
      return letters[0];
    }

    function classifyComponent(residue, hetero) {
      if (WATERS.has(residue)) return "water";
      if (IONS.has(residue)) return "ion";
      if (standardAA.has(residue)) return "protein";
      if (NUCLEIC.has(residue)) return "nucleic";
      if (GLYCANS.has(residue)) return "glycan";
      if (LIPIDS.has(residue)) return "lipid";
      if (hetero || residue === "UNK" || residue === "MOL") return "ligand";
      return "other";
    }

    function finishStructure(atoms, trace, sequence, chains) {
      const derived = [], seenResidues = new Map(), representatives = new Map();
      atoms.forEach((atom, index) => {
        if (atom.component !== "protein" && atom.component !== "nucleic") return;
        const key = `${atom.chain}:${atom.resid}:${atom.residue}`;
        if (!seenResidues.has(key)) {
          const item = {
            chain: atom.chain, resid: atom.resid, resname: atom.residue,
            letter: atom.component === "protein" ? (AA[atom.residue] || "X") : (NUCLEIC_LETTER[atom.residue] || "X"),
            kind: atom.component, ss: atom.ss || "loop", index,
          };
          seenResidues.set(key, item);
          derived.push(item);
        }
        const currentRep = representatives.get(key);
        if (currentRep == null || (atom.component === "protein" && atom.atomName === "CA") || (atom.component === "nucleic" && atom.atomName === "P")) {
          representatives.set(key, index);
        }
      });
      const derivedTrace = [];
      for (let i = 1; i < derived.length; i += 1) {
        const a = derived[i - 1], b = derived[i];
        if (a.chain !== b.chain) continue;
        const ia = representatives.get(`${a.chain}:${a.resid}:${a.resname}`);
        const ib = representatives.get(`${b.chain}:${b.resid}:${b.resname}`);
        if (ia == null || ib == null) continue;
        const aa = atoms[ia], bb = atoms[ib];
        const cutoff = a.kind === "nucleic" ? 9.5 : 5.2;
        if (Math.hypot(aa.x - bb.x, aa.y - bb.y, aa.z - bb.z) < cutoff) derivedTrace.push([ia, ib]);
      }
      sequence = derived;
      trace = derivedTrace;
      let minX = Infinity, minY = Infinity, minZ = Infinity, maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
      atoms.forEach((a) => { minX = Math.min(minX, a.x); maxX = Math.max(maxX, a.x); minY = Math.min(minY, a.y); maxY = Math.max(maxY, a.y); minZ = Math.min(minZ, a.z); maxZ = Math.max(maxZ, a.z); });
      const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2, cz = (minZ + maxZ) / 2;
      let radius = 1;
      atoms.forEach((a) => { a.cx = a.x - cx; a.cy = a.y - cy; a.cz = a.z - cz; radius = Math.max(radius, Math.hypot(a.cx, a.cy, a.cz)); });
      const summaries = {};
      atoms.forEach((atom) => {
        const key = atom.component || "other";
        const entry = summaries[key] = summaries[key] || { id: key, label: COMPONENT_LABELS[key] || key, count: 0, residues: new Set() };
        entry.count += 1;
        if (atom.residue) entry.residues.add(atom.residue);
      });
      const components = Object.values(summaries).map((entry) => ({
        id: entry.id, label: entry.label, count: entry.count,
        residues: [...entry.residues].slice(0, 8), color: COMPONENT_COLORS[entry.id] || "#9fb4c7",
      }));
      const ligandAtoms = atoms.filter((atom) => atom.component === "ligand");
      const ligands = [];
      const seenLigands = new Set();
      ligandAtoms.forEach((atom) => {
        const key = `${atom.chain}:${atom.resid}:${atom.residue}`;
        if (seenLigands.has(key)) return;
        seenLigands.add(key);
        ligands.push({ residue: atom.residue, resid: atom.resid, chain: atom.chain, atoms: 0 });
      });
      ligands.forEach((ligand) => {
        ligand.atoms = ligandAtoms.filter((atom) => atom.chain === ligand.chain && atom.resid === ligand.resid && atom.residue === ligand.residue).length;
      });
      const seqIndex = new Map(sequence.map((item, index) => [`${item.chain}:${item.resid}:${item.resname}`, index]));
      const residueCount = new Set(atoms.filter((atom) => atom.component === "protein" || atom.component === "nucleic").map((atom) => `${atom.chain}:${atom.resid}:${atom.residue}`)).size;
      const bfactors = atoms.map((atom) => atom.bfactor || 0);
      const bfactorRange = [Math.min(...bfactors), Math.max(...bfactors)];
      return { atoms, trace, sequence, chains: [...chains], ligandCount: ligandAtoms.length, ligands, components, radius, residueCount, seqIndex, bfactorRange, bonds: buildBonds(atoms) };
    }

    function buildBonds(atoms) {
      if (atoms.length > 6500) return [];
      const cell = 2.1, grid = new Map();
      const bonds = [];
      const key = (x, y, z) => `${Math.floor(x / cell)},${Math.floor(y / cell)},${Math.floor(z / cell)}`;
      atoms.forEach((a, i) => { const k = key(a.x, a.y, a.z); if (!grid.has(k)) grid.set(k, []); grid.get(k).push(i); });
      atoms.forEach((a, i) => {
        const bx = Math.floor(a.x / cell), by = Math.floor(a.y / cell), bz = Math.floor(a.z / cell);
        for (let dx = -1; dx <= 1; dx += 1) for (let dy = -1; dy <= 1; dy += 1) for (let dz = -1; dz <= 1; dz += 1) {
          const list = grid.get(`${bx + dx},${by + dy},${bz + dz}`) || [];
          for (const j of list) {
            if (j <= i) continue;
            const b = atoms[j];
            if (a.chain !== b.chain && !a.ligand && !b.ligand) continue;
            const d2 = (a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2;
            if (d2 > 0.2 && d2 < 3.8) bonds.push([i, j]);
          }
        }
      });
      return bonds;
    }

    function parsePDBBlock(lines, pdbqt) {
      const atoms = [], ca = [], chains = new Set();
      const ssRanges = [];
      let ligandCount = 0;
      for (const line of lines) {
        if (line.startsWith("HELIX")) {
          ssRanges.push({ chain: line[19] || "A", start: parseInt(line.slice(21, 25), 10), end: parseInt(line.slice(33, 37), 10), ss: "helix" });
        } else if (line.startsWith("SHEET")) {
          ssRanges.push({ chain: line[21] || "A", start: parseInt(line.slice(22, 26), 10), end: parseInt(line.slice(33, 37), 10), ss: "sheet" });
        }
      }
      const ssFor = (chain, resid) => {
        const number = parseInt(resid, 10);
        if (Number.isFinite(number)) {
          const hit = ssRanges.find((range) => range.chain === chain && Number.isFinite(range.start) && number >= range.start && number <= range.end);
          if (hit) return hit.ss;
        }
        return "loop";
      };
      for (const line of lines) {
        if (!(line.startsWith("ATOM") || line.startsWith("HETATM"))) continue;
        if (line[16] && line[16] !== " " && line[16] !== "A") continue;
        const x = parseFloat(line.slice(30, 38)), y = parseFloat(line.slice(38, 46)), z = parseFloat(line.slice(46, 54));
        if (![x, y, z].every(Number.isFinite)) continue;
        const atomName = line.slice(12, 16).trim();
        const residue = line.slice(17, 20).trim().toUpperCase();
        const chain = line.slice(21, 22).trim() || "A";
        const resid = (line.slice(22, 26).trim() || "1") + (line.slice(26, 27).trim() || "");
        const element = inferElement(line, atomName, pdbqt);
        const hetero = line.startsWith("HETATM");
        const component = classifyComponent(residue, hetero);
        const ligand = component !== "protein" && component !== "nucleic";
        if (ligand) ligandCount += 1;
        chains.add(chain);
        const bfactor = parseFloat(line.slice(60, 66));
        const atom = { x, y, z, element, atomName, residue, resid, chain, ligand, component, ss: ssFor(chain, resid), bfactor: Number.isFinite(bfactor) ? bfactor : 0 };
        atoms.push(atom);
        if (atomName === "CA" && element === "C" && !ligand) ca.push({ atom, index: atoms.length - 1, chain, residue, resid });
      }
      const trace = [];
      for (let i = 1; i < ca.length; i += 1) {
        const a = ca[i - 1], b = ca[i];
        if (a.chain === b.chain && Math.hypot(a.atom.x - b.atom.x, a.atom.y - b.atom.y, a.atom.z - b.atom.z) < 5.2) trace.push([a.index, b.index]);
      }
      const sequence = ca.map((item) => ({ chain: item.chain, resid: item.resid, resname: item.residue, letter: AA[item.residue] || "X", index: item.index }));
      return finishStructure(atoms, trace, sequence, chains);
    }

    function parsePDB(text, labelLower) {
      const pdbqt = labelLower.includes(".pdbqt") || /^ROOT$/m.test(text) || /TORSDOF/m.test(text);
      const all = text.split(/\r?\n/);
      const blocks = [];
      let block = [], hasModel = false;
      for (const line of all) {
        if (line.startsWith("MODEL")) { hasModel = true; block = []; continue; }
        if (line.startsWith("ENDMDL")) { blocks.push(block); block = []; continue; }
        block.push(line);
      }
      if (block.length || !hasModel) blocks.push(block);
      const parsed = blocks.map((lines) => parsePDBBlock(lines, pdbqt)).filter((item) => item.atoms.length);
      if (!parsed.length) throw new Error("文件里没有可显示的原子坐标");
      parsed.multi = hasModel || parsed.length > 1;
      return parsed;
    }

    function parseGRO(text) {
      const lines = text.split(/\r?\n/);
      const frames = [];
      let i = 0;
      while (i + 2 < lines.length && frames.length < 40) {
        const count = parseInt(lines[i + 1], 10);
        if (!Number.isFinite(count) || count <= 0) break;
        const atoms = [], chains = new Set(), sequence = [], seen = new Set();
        let ligandCount = 0;
        for (let j = 0; j < count && i + 2 + j < lines.length; j += 1) {
          const line = lines[i + 2 + j];
          if (line.length < 44) continue;
          const resid = parseInt(line.slice(0, 5), 10) || 1;
          const residue = line.slice(5, 10).trim().toUpperCase();
          const atomName = line.slice(10, 15).trim();
          const x = parseFloat(line.slice(20, 28)), y = parseFloat(line.slice(28, 36)), z = parseFloat(line.slice(36, 44));
          if (![x, y, z].every(Number.isFinite)) continue;
          const element = inferElement("", atomName, true);
          const chain = "A";
          const component = classifyComponent(residue, false);
          const ligand = component !== "protein" && component !== "nucleic";
          if (ligand) ligandCount += 1;
          chains.add(chain);
          atoms.push({ x, y, z, element, atomName, residue, resid: String(resid), chain, ligand, component, ss: "loop", bfactor: 0 });
          const key = `${chain}:${resid}`;
          if (atomName === "CA" && !ligand && !seen.has(key)) {
            seen.add(key);
            sequence.push({ chain, resid: String(resid), resname: residue, letter: AA[residue] || "X", index: atoms.length - 1 });
          }
        }
        if (!atoms.length) break;
        const trace = [];
        for (let k = 1; k < sequence.length; k += 1) if (sequence[k - 1].chain === sequence[k].chain) trace.push([sequence[k - 1].index, sequence[k].index]);
        const parsed = finishStructure(atoms, trace, sequence, chains);
        frames.push(parsed);
        i += 2 + count + 1;
      }
      if (!frames.length) throw new Error("GRO 文件里没有可显示的原子坐标");
      frames.multi = frames.length > 1;
      return frames;
    }

    function chainColor(chain) {
      const idx = current ? current.chains.indexOf(chain) : 0;
      return chainColors[Math.max(0, idx) % chainColors.length];
    }

    const POLAR = new Set(["SER", "THR", "ASN", "GLN", "TYR", "CYS"]);
    const POSITIVE = new Set(["LYS", "ARG", "HIS"]);
    const NEGATIVE = new Set(["ASP", "GLU"]);
    function atomColor(atom, z) {
      if (colorMode === "chain") return chainColor(atom.chain);
      if (colorMode === "depth") {
        const t = Math.max(0, Math.min(1, (z + (current?.radius || 1)) / (2 * (current?.radius || 1))));
        return `hsl(${210 - t * 190} 72% 54%)`;
      }
      if (colorMode === "ss") {
        if (atom.component === "nucleic") return "#c084fc";
        if (atom.component !== "protein") return "#9fb4c7";
        if (atom.ss === "helix") return "#ff6b6b";
        if (atom.ss === "sheet") return "#ffd166";
        return "#7dd3fc";
      }
      if (colorMode === "polarity") {
        if (atom.component === "nucleic") return "#c084fc";
        if (atom.component !== "protein") return "#9fb4c7";
        if (POSITIVE.has(atom.residue)) return "#4f8cff";
        if (NEGATIVE.has(atom.residue)) return "#ff6b6b";
        if (POLAR.has(atom.residue)) return "#34d399";
        return "#e5c07b";
      }
      if (colorMode === "rainbow") {
        const key = `${atom.chain}:${atom.resid}:${atom.residue}`;
        const index = current?.seqIndex?.get(key) ?? 0;
        const total = Math.max(1, current?.sequence?.length || 1);
        return `hsl(${(index / total) * 300} 72% 55%)`;
      }
      if (colorMode === "bfactor") {
        const range = current?.bfactorRange || [0, 1];
        const span = Math.max(0.001, range[1] - range[0]);
        const t = Math.max(0, Math.min(1, ((atom.bfactor || 0) - range[0]) / span));
        return `hsl(${220 - t * 220} 78% 55%)`;
      }
      return elementColors[atom.element] || "#b8c4d2";
    }

    function renderComponentControls() {
      const box = $("#structure-components");
      if (!box) return;
      const L = state.lang === "en";
      if (!current || !current.components?.length) {
        box.innerHTML = `<span class="fineprint">${L ? "Components are generated from the real residues after a structure loads." : "加载结构后按文件真实残基生成组分。"}</span>`;
        return;
      }
      box.innerHTML = `<span class="component-label">${L ? "Show components" : "显示组分"}</span>` + current.components.map((component) => `
        <label class="component-chip" title="${esc(component.residues.join(" / "))}">
          <input type="checkbox" data-component="${esc(component.id)}" ${visibleComponents.has(component.id) ? "checked" : ""}>
          <i style="background:${component.color}"></i>${esc(localizedText(component.label))}<b>${component.count}</b>
        </label>`).join("") + `<span class="component-presets"><button type="button" class="btn ghost small" data-component-preset="all">${L ? "All" : "全部"}</button><button type="button" class="btn ghost small" data-component-preset="polymer">${L ? "Protein/ligand only" : "仅蛋白/配体"}</button><button type="button" class="btn ghost small" data-component-preset="none">${L ? "Hide water/ions" : "隐藏水/离子"}</button></span>`;
    }

    function componentSummary() {
      if (!current?.components?.length) return "";
      return current.components.map((component) => `${localizedText(component.label)} ${component.count}`).join(" · ");
    }

    function setModel(index) {
      if (!structures[index]) return;
      modelIndex = index;
      current = structures[index];
      selected = null;
      if (!componentSelectionReady) {
        const defaults = current.components.filter((component) => component.id !== "water").map((component) => component.id);
        visibleComponents = new Set(defaults.length ? defaults : current.components.map((component) => component.id));
        componentSelectionReady = true;
      }
      if (hint) hint.classList.add("hidden");
      const poseRow = $("#structure-pose-row"), poseSelect = $("#structure-pose");
      if (poseRow) poseRow.classList.toggle("hidden", !structures.multi);
      const L = state.lang === "en";
      if (poseSelect) {
        poseSelect.innerHTML = structures.map((_, i) => `<option value="${i}">${L ? `Model ${i + 1} / ${structures.length}` : `构象 ${i + 1} / ${structures.length}`}</option>`).join("");
        poseSelect.value = String(index);
      }
      const ligandNote = structures.multi ? (L ? ` · multi-model file, MODEL ${index + 1}/${structures.length}` : ` · 多构象文件，当前第 ${index + 1}/${structures.length} 个 MODEL`) : "";
      if (meta) meta.textContent = L
        ? `${name} · ${current.atoms.length} atoms · ${current.chains.length} chains · ${current.residueCount} polymer residues · ${componentSummary()}${ligandNote}; water hidden by default, toggle to show.`
        : `${name} · ${current.atoms.length} 原子 · ${current.chains.length} 链 · ${current.residueCount} 个聚合物残基 · ${componentSummary()}${ligandNote}；水默认隐藏，可勾选显示。`;
      renderComponentControls();
      renderSequence();
      draw();
    }

    function loadText(text, label) {
      const lower = String(label || "").toLowerCase();
      structures = lower.endsWith(".gro") || /^t_title|^Generated by GROMACS/m.test(text) ? parseGRO(text) : parsePDB(text, lower);
      name = label || "structure";
      componentSelectionReady = false;
      structures.multi = structures.multi || structures.length > 1;
      setModel(0);
    }

    async function loadUrl(url, label) {
      if (hint) { hint.classList.remove("hidden"); hint.textContent = state.lang === "en" ? "Loading structure…" : "正在加载结构…"; }
      try {
        const res = await fetch(url, { credentials: "same-origin" });
        if (!res.ok) throw new Error(`加载失败 (${res.status})`);
        loadText(await res.text(), label || url.split("/").pop() || "structure");
      } catch (err) {
        if (hint) { hint.classList.remove("hidden"); hint.textContent = err.message; }
        toast(err.message);
      }
    }

    function rotate(atom) {
      const cy = Math.cos(rotY), sy = Math.sin(rotY), cx = Math.cos(rotX), sx = Math.sin(rotX);
      const x1 = atom.cx * cy + atom.cz * sy;
      const z1 = -atom.cx * sy + atom.cz * cy;
      const y2 = atom.cy * cx - z1 * sx;
      const z2 = atom.cy * sx + z1 * cx;
      return [x1, y2, z2];
    }

    function draw() {
      const { w, h, dpr } = size();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      screenAtoms = [];
      if (!current || !current.atoms.length) return;
      const base = Math.min(w, h) * 0.42 / (current.radius || 1) * zoom;
      const items = [];
      current.atoms.forEach((atom, i) => {
        if (atom.component && !visibleComponents.has(atom.component)) return;
        const [x, y, z] = rotate(atom);
        const persp = Math.max(0.58, 1 + z / ((current.radius || 1) * 8));
        const px = w / 2 + panX + x * base * persp;
        const py = h / 2 + panY - y * base * persp;
        items.push({ atom, i, x: px, y: py, z, persp, color: atomColor(atom, z) });
        screenAtoms.push({ x: px, y: py, atom });
      });
      ctx.lineCap = "round";
      const itemByIndex = new Map(items.map((item) => [item.i, item]));
      if (style === "cartoon" || style === "trace") {
        current.trace.forEach(([ia, ib]) => {
          const a = itemByIndex.get(ia), b = itemByIndex.get(ib);
          if (!a || !b) return;
          const alpha = style === "trace" ? 0.55 : 0.9;
          ctx.globalAlpha = alpha;
          ctx.strokeStyle = atomColor(a.atom, a.z);
          ctx.lineWidth = style === "trace" ? 1.2 : Math.max(3, Math.min(9, base * 0.65 * a.persp));
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
          if (style === "cartoon") {
            ctx.globalAlpha = 0.28;
            ctx.strokeStyle = "#ffffff";
            ctx.lineWidth = Math.max(1, Math.min(4, base * 0.2));
            ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
          }
        });
        ctx.globalAlpha = 1;
        items.filter((x) => x.atom.ligand).sort((a, b) => a.z - b.z).forEach((p) => {
          ctx.fillStyle = p.color;
          ctx.beginPath(); ctx.arc(p.x, p.y, Math.max(2.2, Math.min(6, base * 0.18 * p.persp)), 0, Math.PI * 2); ctx.fill();
        });
      } else {
        if (current.atoms.length < 6500) {
          ctx.lineWidth = style === "spacefill" ? 1 : 1.2;
          current.bonds.forEach(([ia, ib]) => {
            const a = itemByIndex.get(ia), b = itemByIndex.get(ib);
            if (!a || !b) return;
            if (style === "spacefill" && !a.atom.ligand && !b.atom.ligand) return;
            ctx.strokeStyle = "rgba(143,164,183,.42)";
            ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
          });
        }
        items.sort((a, b) => a.z - b.z).forEach((p) => {
          const rad = style === "spacefill" ? (vdw[p.atom.element] || 1.6) * base * 0.55 * p.persp : Math.max(1.2, base * (p.atom.ligand ? 0.12 : 0.055) * p.persp);
          ctx.fillStyle = p.color;
          ctx.globalAlpha = p.atom.element === "H" ? 0.55 : 0.95;
          ctx.beginPath(); ctx.arc(p.x, p.y, rad, 0, Math.PI * 2); ctx.fill();
        });
        ctx.globalAlpha = 1;
      }
      if (selected) {
        const point = screenAtoms.find((p) => p.atom.resid === selected.resid && p.atom.chain === selected.chain);
        if (point) {
          ctx.strokeStyle = "#0071e3"; ctx.lineWidth = 2.5;
          ctx.beginPath(); ctx.arc(point.x, point.y, 13, 0, Math.PI * 2); ctx.stroke();
          ctx.fillStyle = "rgba(0,113,227,.92)"; ctx.font = "600 11px -apple-system, BlinkMacSystemFont, sans-serif";
          ctx.fillText(`${point.atom.residue} ${point.atom.chain}${point.atom.resid}`, point.x + 16, point.y - 10);
        }
      }
      const legend = $("#structure-legend");
      if (legend) {
        const res = current.sequence.length;
        const L = state.lang === "en";
        const visible = current.components.filter((component) => visibleComponents.has(component.id)).map((component) => `${localizedText(component.label)} ${component.count}`).join(" · ");
        const styleName = L ? (style === "cartoon" ? "Cartoon backbone" : style === "trace" ? "Backbone trace" : style === "spacefill" ? "Space-fill" : "Ball-and-stick") : (style === "cartoon" ? "卡通主链" : style === "trace" ? "主链线" : style === "spacefill" ? "空间填充" : "球棍");
        legend.innerHTML = `<span>${styleName}</span><span>${res} residues</span><span>${esc(visible || (L ? "All components hidden" : "当前隐藏全部组分"))}</span><span>${structures.length} model(s)</span>`;
      }
    }

    function renderSequence() {
      const el = $("#structure-sequence");
      if (!el) return;
      if (!current) { el.innerHTML = ""; return; }
      const groups = [];
      const groupMap = new Map();
      current.sequence.forEach((item) => {
        const key = `${item.chain}:${item.kind}`;
        if (!groupMap.has(key)) {
          const group = { chain: item.chain, kind: item.kind, items: [] };
          groupMap.set(key, group);
          groups.push(group);
        }
        groupMap.get(key).items.push(item);
      });
      const L = state.lang === "en";
      const html = groups.map((group) => `
        <div class="seq-group">
          <div class="seq-group-head"><b>${L ? "Chain" : "链"} ${esc(group.chain)} · ${group.kind === "nucleic" ? (L ? "nucleic acid" : "核酸") : (L ? "protein" : "蛋白")}</b><span>${group.items.length} ${L ? "residues" : "个残基"}</span></div>
          <div class="seq-row">${group.items.map((item) => {
            const active = selected && selected.resid === item.resid && selected.chain === item.chain;
            return `<button type="button" class="seq-res${item.kind === "nucleic" ? " nucleic" : ""}${active ? " active" : ""}" data-resid="${esc(item.resid)}" data-chain="${esc(item.chain)}" data-ss="${esc(item.ss || "loop")}" title="${esc(item.resname)} ${esc(item.resid)} · ${esc(item.ss || "loop")}">${esc(item.letter)}</button>`;
          }).join("")}</div>
        </div>`).join("");
      const ligandHtml = (current.ligands || []).length ? `<div class="seq-group"><div class="seq-group-head"><b>${L ? "Ligand / non-polymer" : "配体 / 非聚合物"}</b><span>${current.ligands.length} ${L ? "components" : "个组分"}</span></div><div class="seq-ligands">${current.ligands.map((ligand) => `<button type="button" class="seq-ligand" data-resid="${esc(ligand.resid)}" data-chain="${esc(ligand.chain)}" data-resname="${esc(ligand.residue)}">${esc(ligand.residue)} ${esc(ligand.chain)}${esc(ligand.resid)} · ${ligand.atoms} ${L ? "atoms" : "原子"}</button>`).join("")}</div></div>` : "";
      el.innerHTML = html + ligandHtml || `<p class="fineprint">${L ? "This structure has no displayable polymer sequence or ligand components." : "该结构没有可展示的聚合物序列或配体组分。"}</p>`;
      $$(".seq-res", el).forEach((btn) => btn.addEventListener("click", () => {
        const res = current.sequence.find((x) => x.resid === btn.dataset.resid && x.chain === btn.dataset.chain);
        if (res) selectResidue({ resid: res.resid, chain: res.chain, residue: res.resname, atomName: res.kind === "nucleic" ? "P" : "CA" });
      }));
      $$(".seq-ligand", el).forEach((btn) => btn.addEventListener("click", () => {
        selectResidue({ resid: btn.dataset.resid, chain: btn.dataset.chain, residue: btn.dataset.resname, atomName: "LIG" });
      }));
    }

    function selectResidue(atom) {
      selected = { resid: atom.resid, chain: atom.chain, residue: atom.residue, atomName: atom.atomName };
      const el = $("#structure-residue");
      if (el) el.innerHTML = state.lang === "en"
        ? `<b>Residue ${esc(atom.residue)} ${esc(atom.resid)}</b> · chain ${esc(atom.chain)} · click the sequence to locate; structural visualisation is not functional annotation.`
        : `<b>残基 ${esc(atom.residue)} ${esc(atom.resid)}</b> · 链 ${esc(atom.chain)} · 点击序列可定位；结构可视化不构成功能注释。`;
      renderSequence();
      draw();
    }

    function reset() { rotX = -0.22; rotY = 0.55; zoom = 1; panX = 0; panY = 0; selected = null; renderSequence(); draw(); }
    function fit() { zoom = 1; panX = 0; panY = 0; draw(); }

    canvas.addEventListener("pointerdown", (e) => {
      canvas.setPointerCapture(e.pointerId);
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pointers.size === 1) {
        dragging = true;
        dragMode = e.button === 2 || e.shiftKey ? "pan" : "rotate";
        lastX = e.clientX; lastY = e.clientY;
      }
      if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        pinch = Math.hypot(a.x - b.x, a.y - b.y);
        dragMode = "pinch";
      }
    });
    canvas.addEventListener("pointermove", (e) => {
      if (!pointers.has(e.pointerId)) return;
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        const dist = Math.hypot(a.x - b.x, a.y - b.y);
        if (pinch > 0 && dist > 0) zoom = Math.max(0.25, Math.min(10, zoom * (dist / pinch)));
        pinch = dist;
        draw();
        return;
      }
      if (!dragging) return;
      const dx = e.clientX - lastX, dy = e.clientY - lastY;
      lastX = e.clientX; lastY = e.clientY;
      if (dragMode === "pan") { panX += dx; panY += dy; }
      else { rotY += dx * 0.008; rotX = Math.max(-1.45, Math.min(1.45, rotX + dy * 0.008)); }
      draw();
    });
    function up(e) {
      pointers.delete(e.pointerId);
      pinch = 0;
      if (!pointers.size) { dragging = false; dragMode = "rotate"; }
    }
    canvas.addEventListener("pointerup", up);
    canvas.addEventListener("pointercancel", up);
    canvas.addEventListener("contextmenu", (e) => e.preventDefault());
    canvas.addEventListener("click", (e) => {
      if (!screenAtoms.length) return;
      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left, y = e.clientY - rect.top;
      let best = null, bestD = 14;
      screenAtoms.forEach((p) => { const d = Math.hypot(p.x - x, p.y - y); if (d < bestD) { bestD = d; best = p; } });
      if (best) selectResidue(best.atom);
    });
    canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      zoom = Math.max(0.25, Math.min(10, zoom * Math.exp(-e.deltaY * 0.0012)));
      draw();
    }, { passive: false });
    canvas.addEventListener("dblclick", fit);
    $("#structure-spin")?.addEventListener("change", (e) => { spin = e.target.checked; });
    $("#structure-style")?.addEventListener("change", (e) => { style = e.target.value; draw(); });
    $("#structure-color")?.addEventListener("change", (e) => { colorMode = e.target.value; draw(); });
    $("#structure-components")?.addEventListener("change", (e) => {
      const input = e.target.closest("[data-component]");
      if (!input) return;
      if (input.checked) visibleComponents.add(input.dataset.component);
      else visibleComponents.delete(input.dataset.component);
      draw();
    });
    $("#structure-components")?.addEventListener("click", (e) => {
      const preset = e.target.closest("[data-component-preset]")?.dataset.componentPreset;
      if (!preset) return;
      if (preset === "all") visibleComponents = new Set(current?.components?.map((component) => component.id) || []);
      if (preset === "polymer") visibleComponents = new Set(["protein", "nucleic", "ligand", "glycan", "lipid"].filter((id) => current?.components?.some((component) => component.id === id)));
      if (preset === "none") visibleComponents = new Set((current?.components || []).map((component) => component.id).filter((id) => id !== "water" && id !== "ion"));
      renderComponentControls();
      draw();
    });
    $("#structure-fit")?.addEventListener("click", fit);
    $("#structure-reset")?.addEventListener("click", reset);
    $("#structure-export")?.addEventListener("click", () => {
      draw();
      canvas.toBlob((blob) => {
        if (!blob) { toast("当前浏览器不支持导出图像。"); return; }
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `${name.replace(/[^\w.-]+/g, "_")}-view.png`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      }, "image/png");
    });
    $("#structure-pose")?.addEventListener("change", (e) => setModel(Number(e.target.value)));
    window.addEventListener("resize", () => draw());
    if (window.ResizeObserver) new ResizeObserver(() => draw()).observe(canvas);
    function loop() {
      if (spin && !dragging && pointers.size < 2 && current) { rotY += 0.0028; draw(); }
      requestAnimationFrame(loop);
    }
    requestAnimationFrame(loop);
    return { loadUrl, loadText, reset, fit };
  })();

  window.bioforge = { api, toast, moleculeViewer };

  const I18N_EN = {
    "设计工作台": "Design Studio", "案例库": "Case Library", "在线证据": "Evidence",
    "机制计算": "Mechanism", "模型实验室": "Model Lab", "使用指南": "Field Guide",
    "设置": "Settings", "资源库": "Resources", "在线数据库证据": "Federated Evidence",
    "端到端案例": "End-to-end cases", "点击任意案例即可复现": "Click any case to reproduce it",
    "一句话，生成": "One sentence, generate", "组": "set of", "可比较的配方。": "comparable formulations.",
    "候选组合": "Candidate set", "自动": "Auto", "食品配方": "Food formulation", "生物设计": "Biologic design",
    "高蛋白面包": "High-protein bread", "低糖酸奶": "Low-sugar yogurt", "植物肉": "Plant-based meat", "天然软糖": "Natural gummies",
    "生成方案 ↗": "Generate ↗", "生成 8 个候选、约束检查、证据与工艺卡。": "Generate 8 candidates, constraint checks, evidence and process cards.",
    "证据图谱": "Evidence graph", "运行机制计算": "Run mechanism", "可比较候选": "Comparable candidates",
    "横向滑动 · 点击查看详情": "Swipe horizontally · click for details",
    "输入一个产品目标开始": "Start with a product goal",
    "系统不会只给一个答案：它会生成 8 个可比较组合，并明确哪些约束已满足、哪些仍需实测。": "The system does not give one answer: it generates 8 comparable formulations and states which constraints pass and which still need measurement.",
    "检索时间 · 记录号 · 原始链接": "Retrieved · record ID · original link",
    "自动判断实体": "Auto-detect entity", "小分子 / 化合物": "Small molecule / compound",
    "蛋白 / 靶点": "Protein / target", "食品 / 配方": "Food / formulation", "化合物-蛋白复合": "Compound-protein complex",
    "检索": "Search", "先判断实体类型，再选择数据库；化合物不会调用 UniProt/PDB/STRING，蛋白结构只通过 UniProt→PDB 交叉引用。": "Entity type is detected before choosing databases; compounds do not query UniProt/PDB/STRING, and protein structures use only UniProt→PDB cross-references.",
    "谱图证据必须核对仪器、溶剂、碰撞能量和原始记录；这里只提供合法公开/机构入口，不抓取受限谱库。": "Spectra must be checked against instrument, solvent, collision energy and raw records; only legal public/institutional entry points are listed, with no scraping of restricted libraries.",
    "参考谱不等于同条件实测；MS 需说明离子模式/碰撞能量，NMR 需说明溶剂/频率，IR 需说明样品制备。完整目录见资源库“光谱与波谱证据”。": "Reference spectra are not same-condition measurements; report ion mode/collision energy for MS, solvent/frequency for NMR, and sample preparation for IR. See the spectroscopy group in Resources.",
    "本地 OA 文献库": "Local OA literature", "加载中…": "Loading…",
    "数据库、原文与机构入口 一处直达。": "Databases, full text and institutional access in one place.",
    "所有来源都标注许可、接入状态和用途。开放数据直接跳转；需许可或机构登录的来源只提供官方入口，不抓取、不代存账号密码。Sci-Hub 及绕过付费墙的链接不收录。": "Every source lists its licence, access status and purpose. Open data links out directly; licensed or institutional sources only expose official entry points. No Sci-Hub or paywall bypass links are listed.",
    "检索资源": "Search resources", "全部": "All", "可直接查询": "Direct query", "API/解析": "API / resolver",
    "需许可": "Licence required", "机构登录": "Institutional login", "读取来源目录…": "Reading source catalogue…",
    "解析标识符，找合法全文入口": "Resolve an identifier to a legal full text",
    "输入 DOI 或 PubMed PMID。": "Enter a DOI or PubMed PMID.", "只解析元数据和合法 OA 位置": "Only metadata and legal OA locations are resolved",
    "；最终权限由出版方或学校授权决定，不绕过付费墙。": "; final access depends on the publisher or your institution, with no paywall bypass.",
    "解析": "Resolve", "不会收集或保存你的图书馆账号密码。": "Library credentials are never collected or stored.",
    "软件不提供账号密码表单，也不代存校园密码。请从学校官方入口登录，再回到 DOI/出版社页面获取全文。": "The app provides no credential form and stores no campus password. Log in through the official university portal, then return to the DOI/publisher page.",
    "如果学校提供 EZproxy 前缀，可由管理员配置 BIOFORGE_EZPROXY_PREFIX ；软件只拼接官方登录 URL，不保存凭据。": "If your institution provides an EZproxy prefix, an administrator can set BIOFORGE_EZPROXY_PREFIX; only the official login URL is composed and credentials are not stored.",
    "打开机构登录说明": "Institutional access help", "对接 · MD · QM": "Docking · MD · QM",
    "计算参数 种子 · 采样 · 步数 · 超时": "Parameters: seed · sampling · steps · timeouts",
    "计算参数": "Compute parameters", "种子 · 采样 · 步数 · 超时": "seed · sampling · steps · timeouts",
    "运行 Vina 对接": "Run Vina docking", "运行短 MD": "Run short MD", "运行 CP2K": "Run CP2K",
    "随机种子": "Random seed", "Vina 采样强度": "Vina exhaustiveness", "输出构象数": "Poses",
    "对接盒边长 / Å": "Box edge / Å", "EM 步数": "EM steps", "MD 步数": "MD steps",
    "时间步 / ps": "Time step / ps", "温度 / K": "Temperature / K", "线程数": "Threads",
    "高级计算覆盖": "Advanced scope", "代表项（默认，推荐）": "Representative (default, recommended)",
    "全部受体/配体": "All receptors/ligands", "EM 超时 / s": "EM timeout / s", "MD 超时 / s": "MD timeout / s",
    "QM 截断能 / Ry": "QM cutoff / Ry", "QM SCF 上限": "QM SCF limit",
    "默认种子留空时每次生成新种子；固定种子可复现。超时只保护单步，不再因 EM 超时丢掉已完成对接。": "Leave the seed empty for a new seed each run; a fixed seed is reproducible. Timeouts protect individual steps, so a completed docking is not discarded by an EM timeout.",
    "恢复默认": "Reset defaults", "本地软件接口 检测路径 · HADDOCK": "Local tool paths · HADDOCK",
    "本地软件接口": "Local tool paths", "检测路径 · HADDOCK": "check paths · HADDOCK",
    "保存路径并检测": "Save paths and check", "参数可调 · 结果带指纹": "Adjustable parameters · fingerprinted results",
    "受体（PDB ID 或名称，可多个，逗号分隔）": "Receptors (PDB ID or name; comma-separated)",
    "配体（名称或 SMILES，可多个，逗号分隔）": "Ligands (name or SMILES; comma-separated)",
    "多个受体会与每个配体做笛卡尔组合；单次最多 12 对。高级 MD/QM 默认只跑代表项，避免误启动数小时任务；“全部”会逐项运行。": "Every receptor is paired with every ligand, up to 12 pairs per run. Advanced MD/QM runs the representative pair by default; choosing All runs each one.",
    "未关联配方": "No formulation linked", "启动作业": "Start job", "分子结构查看器": "Molecular structure viewer",
    "拖拽旋转 · 滚轮/双指缩放": "Drag to rotate · wheel/pinch to zoom", "加载 PDB": "Load PDB", "导出图像": "Export image",
    "自动旋转": "Auto-rotate", "表示法": "Representation", "卡通主链": "Cartoon backbone", "主链线": "Backbone trace",
    "球棍": "Ball and stick", "空间填充": "Space fill", "着色": "Colour", "按元素": "By element", "按链": "By chain",
    "按二级结构": "By secondary structure", "按残基极性": "By residue polarity", "按序列彩虹": "By sequence rainbow",
    "按 B-factor": "By B-factor", "按深度": "By depth", "聚焦": "Focus", "重置": "Reset",
    "加载结构后按文件真实残基生成组分。": "Components are generated from the real residues after loading a structure.",
    "构象": "Model", "从数据到下一轮候选": "From data to the next candidate round",
    "导入 · 训练 · 不确定性 · 贝叶斯优化 · 回灌": "Import · train · uncertainty · Bayesian optimisation · feedback",
    "01 数据底座": "01 Data foundation", "02 特征与训练": "02 Features and training", "03 不确定性与 BO": "03 Uncertainty and BO", "04 实测回灌": "04 Measurement feedback",
    "数据集": "Datasets", "训练与模型": "Training and models", "贝叶斯优化": "Bayesian optimisation", "实验回灌": "Experiment feedback",
    "载入内置演示数据": "Load built-in demo data", "下载 CSV 模板": "Download CSV template",
    "导入 CSV / JSON": "Import CSV / JSON", "名称": "Name", "来源类型": "Source type", "说明": "Notes", "文件": "File",
    "或粘贴 CSV / JSON": "Or paste CSV / JSON", "去重完全相同的行": "Deduplicate identical rows", "导入数据集": "Import dataset",
    "训练配置": "Training configuration", "未选择数据集": "No dataset selected", "目标列": "Target column", "算法": "Algorithm",
    "自动选择": "Auto select", "Ridge 线性": "Ridge linear", "随机森林": "Random forest", "梯度提升": "Gradient boosting",
    "高斯过程": "Gaussian process", "集成（RF+HGB+Ridge）": "Ensemble (RF+HGB+Ridge)", "交叉验证折数": "CV folds",
    "分组列（可选）": "Group column (optional)", "不分组": "No grouping", "允许合成/混合数据（仅流程验证）": "Allow synthetic/mixed data (workflow validation only)",
    "特征列 默认排除标识符和可能的结果列": "Feature columns exclude identifiers and likely outcome columns by default",
    "默认全选": "All by default", "清空": "Clear", "字段手册": "Field manual",
    "把每个按钮，变成可解释的动作。": "Turn every button into an explainable action.",
    "问 BioForge": "Ask BioForge", "笔记实时浏览": "Live note browser", "提问": "Ask", "刷新": "Refresh",
    "服务器记录 / 最近问答": "Server log / recent Q&A", "自动刷新": "Auto-refresh",
    "只读": "Read-only", "检测 Ollama…": "Checking Ollama…", "保存": "Save",
    "设计": "Design", "案例": "Cases", "证据": "Evidence", "计算": "Compute", "实验室": "Lab", "指南": "Guide",
    "资源": "Resources", "账户": "Account", "退出": "Sign out", "服务器已连接": "Server connected", "离线 / 未连接": "Offline / disconnected",
    "展开": "Expand", "收起": "Collapse", "中文": "Chinese", "English": "English",
    "问答历史": "Q&A history", "搜索问题或回答…": "Search questions or answers…", "条显示 / 共": "shown / total",
    "点击查看记录摘要": "Click for the record summary", "展开详细结果、步骤、文件与导出": "Expand details, steps, files and exports",
    "任务": "Job", "状态": "Status", "体系": "System", "创建": "Created", "输入校验失败": "Input validation failed", "作业失败": "Job failed",
    "光谱与参考峰": "Spectra and reference peaks", "数字孪生荧光与 UV-Vis 参考曲线": "Digital-twin fluorescence and UV-Vis reference curves",
    "模型阈值通过": "Model threshold passed", "需复核": "Needs review", "已训练模型": "Trained models",
    "最近追加 / 导入": "Recent feedback / imports", "证据图谱": "Evidence graph",
    "该候选暂无匹配的本地参考峰；可在“在线证据”中检索 PubChem/NIST/MassBank/SDBS，并核对仪器条件。": "No matching local reference peaks for this candidate; search PubChem/NIST/MassBank/SDBS in Evidence and check instrument conditions.",
    "候选来源：": "Candidate sources:", "参考谱/文献条目需回到原始记录核对，不能当作同条件实测。": "Reference spectra and citations must be checked against the original record; they are not same-condition measurements.",
    "MS 需注明离子模式/碰撞能量，NMR 需注明溶剂/频率，IR 需注明样品制备；谱图证据必须能追溯到原始记录。": "Report ion mode/collision energy for MS, solvent/frequency for NMR, and sample preparation for IR; spectral evidence must trace back to raw records.",
    "未识别受体。请填写 4 位 PDB ID、蛋白名称或 UniProt 映射；": "Receptor not recognised. Enter a 4-character PDB ID, protein name or UniProt mapping;",
    "未识别配体。请填写配体名称、化合物 ID 或 SMILES；": "Ligand not recognised. Enter a ligand name, compound ID or SMILES;",
    "不会再用 1BEB 代替。": "1BEB will not be substituted silently.",
    "不会再用 quercetin 代替。若只想做蛋白短 MD，请关闭对接/QM 后另行确认。": "Quercetin will not be substituted silently. For protein-only short MD, disable docking/QM and confirm explicitly.",
    "当前本地映射包括": "Current local mappings:",
    "登录工作台": "Sign in", "用户名": "Username", "密码": "Password", "进入 Studio": "Enter Studio",
    "修改服务器地址": "Change server address", "连接中": "Connecting", "v3.3.0 · 本地优先": "v3.3.0 · local-first",
    "资源与全文入口": "Resources and full-text access", "打开完整资源库": "Open full resource directory",
    "一组": "set", "生成方案": "Generate plan", "正在组合配方与评估相互作用": "Composing formulations and evaluating interactions",
    "IR · UV-Vis · 荧光 · MS · NMR 参考入口": "IR · UV-Vis · fluorescence · MS · NMR reference entry points",
    "数据库、原文与机构入口": "Databases, full text and institutional access", "一处直达。": "in one place.",
    "华南理工大学图书馆 ↗": "SCUT Library ↗", "CARSI 联盟 ↗": "CARSI Federation ↗", "华南理工大学主页 ↗": "SCUT homepage ↗",
    "MD 体系": "MD system", "蛋白-配体复合物（推荐）": "Protein–ligand complex (recommended)", "仅蛋白": "Protein only",
    "加载一个 PDB / PDBQT / GRO，或从计算结果中打开结构文件": "Load a PDB / PDBQT / GRO, or open a structure file from a calculation job",
    "点击原子可查看残基；拖拽旋转，右键/Shift 拖拽平移，滚轮或双指缩放。": "Click an atom to inspect its residue; drag to rotate, right-click/Shift-drag to pan, wheel/pinch to zoom.",
    "数据底座": "Data foundation", "特征与训练": "Features and training", "不确定性与 BO": "Uncertainty and BO", "实测回灌": "Measurement feedback",
    "≤ 20,000 行": "≤ 20,000 rows", "实测（wet lab）": "Wet lab", "文献整理": "Literature curated", "模拟": "Simulated", "合成 / 演示": "Synthetic / demo", "混合": "Mixed",
    "特征列": "Feature columns", "训练模型": "Train model", "EI + 不确定性": "EI + uncertainty", "模型": "Model",
    "目标方向": "Objective", "最大化": "Maximise", "最小化": "Minimise", "候选数": "Candidates", "搜索点数": "Search points",
    "搜索空间（默认使用训练范围）": "Search space (training range by default)", "可收窄，不能外推": "Narrow only; no extrapolation",
    "生成候选": "Generate candidates", "闭环": "Closed loop", "模型（用于重训）": "Model (for retraining)",
    "用最新数据重训": "Retrain with latest data", "导出数据集 CSV": "Export dataset CSV", "刷新近期记录": "Refresh recent records",
    "快速开始": "Quick start", "设计结果": "Design results", "3D 与计算": "3D and compute", "文献库": "Literature", "故障排查": "Troubleshooting",
    "回答会引用应用内指南与资源政策；不确定时会明确说明。": "Answers cite the in-app guide and resource policy; uncertainty is stated explicitly.",
    "问 BioForge（证据检索）": "Ask BioForge (evidence-grounded)",
    "先查本地 10,000 篇 OA 文献与知识图谱；证据不足时才调用 Europe PMC/OpenAlex 公共 API，并由 LangGraph 做检索—核验循环。所有回答进入人工审核队列，可回滚、修订和反馈；不要输入密码、Token、患者数据或未公开数据。": "Searches the local 10,000-paper OA library and knowledge graph first; only uses Europe PMC/OpenAlex when evidence is insufficient, with a LangGraph retrieve-and-verify loop. Every answer enters human review and can be rolled back, revised or rated. Never enter passwords, tokens, patient data or unpublished data.",
    "例如：槲皮素与乳清蛋白相互作用的证据强度如何？": "e.g. how strong is the evidence for quercetin–whey protein interactions?",
    "回答会显示证据、图谱标签、质量分级、核验结果与审核按钮；证据不足时会明确警告。": "Answers show evidence, graph labels, quality grade, verification and review controls; weak evidence is warned explicitly.",
    "检索并回答": "Search & answer",
    "人工审核队列": "Human review queue",
    "检测 RAG…": "Checking RAG…",
    "检索与核验中…": "Retrieving & verifying…",
    "本地库": "Local library",
    "证据": "Evidence",
    "外部": "External",
    "证据警告": "Evidence warnings",
    "证据清单": "Evidence list",
    "图谱概念与标签": "Graph concepts and labels",
    "关系边": "Relation edges",
    "逐句核验": "Claim verification",
    "审核通过": "Approve",
    "驳回": "Reject",
    "有帮助 +1": "Helpful +1",
    "无帮助 -1": "Not helpful -1",
    "回滚并重查": "Rollback & retry",
    "条待审核": "pending",
    "没有待审核记录。": "No pending reviews.",
    "审核队列暂不可用。": "Review queue unavailable.",
    "不可用": "unavailable",
    "回滚原因/补充检索词（可留空）": "Rollback reason / extra search terms (optional)",
    "审核备注（可留空）": "Review note (optional)",
    "驳回原因（建议填写）": "Rejection reason (recommended)",
    "已审核通过。": "Approved.",
    "已驳回。": "Rejected.",
    "已回滚并生成新记录；旧记录保留。": "Rolled back; the old record is retained.",
    "反馈已记录，并更新关系权重。": "Feedback recorded and relation weights updated.",
    "无路由记录": "No route",
    "无逐句核验记录。": "No claim-level checks.",
    "打开原始入口": "Open source",
    "仅题录信息。": "Metadata only.",
    "关键词共现关系是待验证假设；流程/模型关系不等于实验证据。": "Keyword co-occurrence is a hypothesis; workflow/model edges are not experimental evidence.",
    "先查本地 10,000 篇 OA + 图谱；证据不足再查外部 OA；随后逐句核验。27B 模型可能较慢…": "Searching local 10,000 OA + graph; falling back to external OA if needed; then verifying claims. The 27B model may be slow…",
    "加载笔记列表…": "Loading note list…", "选择一篇笔记查看只读内容。": "Select a note to read it.",
    "账户与系统": "Account and system", "App 服务器": "App server", "当前地址": "Current address", "当前用户": "Current user",
    "当前密码": "Current password", "新密码（≥ 8 位）": "New password (≥ 8 characters)", "更新密码": "Update password",
    "外观主题": "Appearance", "跟随系统": "System", "浅色": "Light", "深色": "Dark", "登录与 Token": "Sign-in and token",
    "退出登录": "Sign out", "PostgreSQL 知识库": "PostgreSQL knowledge base", "读取中…": "Reading…", "刷新数据库状态": "Refresh database status",
    "数据源与许可": "Sources and licences", "登录后加载。": "Loads after sign-in.", "版本": "Version",
    "记录实测": "Record measurement", "实测": "Measured", "备注": "Notes", "追加后立即重训": "Retrain immediately after appending",
    "取消": "Cancel", "保存实测并回灌": "Save measurement and feed back",
    "请输入用户名和密码。": "Enter your username and password.", "已安全退出。": "Signed out safely.",
    "EM 未收敛": "EM not converged", "复合物 MD": "Complex MD", "复合物回退": "Complex fallback",
    "高级 代表项": "Advanced: representative", "高级 全部": "Advanced: all",
    "独立哈希与来源标记": "Independent hash + source labels", "可追溯 artifact": "Traceable artifacts",
    "优化批次": "Optimisation runs", "候选可导出 CSV": "Candidates export to CSV", "演示数据": "Demo data",
    "合成流程数据": "Synthetic workflow data", "还没有数据集": "No datasets yet",
    "载入 180 行演示数据，或导入 CSV / JSON。": "Load 180 demo rows, or import CSV / JSON.",
    "选择一个数据集": "Select a dataset", "查看列类型、默认特征、目标候选和训练就绪状态。": "Inspect column types, default features, target candidates and training readiness.",
    "先在“数据集”页导入或载入演示数据。": "Import data or load the demo on the Datasets tab first.",
    "（无问题）": "(no question)", "（无回答）": "(no answer)", "还没有匹配的服务器记录。": "No matching server records.",
    "历史记录暂不可用。": "History is temporarily unavailable.", "请输入问题。": "Enter a question.",
    "文献": "Literature", "合成": "Synthetic", "高置信": "High confidence", "中置信": "Medium confidence", "低置信": "Low confidence",
    "集成": "Ensemble", "未知": "Unknown", "内置": "Built-in", "删除数据集": "Delete dataset",
    "条资源 · 资源库": "resources · directory", "元数据": "metadata", "内容": "content",
    "只列公开/机构授权入口；不提供 Sci-Hub 或付费墙绕过链接。": "Only public and institutional-access entry points are listed; no Sci-Hub or paywall-bypass links are provided.",
    "默认排除标识符和可能的结果列": "Exclude identifiers and likely outcome columns by default",
    "机构登录由学校官方页面完成": "Institutional sign-in is completed on the university page",
    "极光": "Aurora", "深海": "Ocean", "森林": "Forest", "日落": "Sunset", "莓果": "Berry", "石墨": "Graphite",
    "赛博": "Cyber", "卡通": "Cartoon", "国风": "Scroll", "实验室": "Lab", "糖果": "Candy", "沙丘": "Sand",
    "01 · 快速开始": "01 · Quick start", "02 · 设计工作台怎么读": "02 · Reading Design Studio",
    "03 · 证据图谱": "03 · Evidence graph", "04 · 机制计算与 3D": "04 · Mechanism and 3D",
    "05 · 模型实验室": "05 · Model Lab", "06 · 文献库与标签": "06 · Literature and tags",
    "07 · 故障排查": "07 · Troubleshooting", "08 · 数据库与来源": "08 · Database and sources",
    "09 · 必须保留的边界": "09 · Non-negotiable boundaries",
    "候选": "Candidates", "综合评分": "Overall score", "约束通过": "Constraint pass",
  };
  Object.assign(I18N_EN, {
    "例如：低钠番茄酱，钠降低 30%，pH 3.7，保持货架期和番茄风味": "e.g. low-sodium tomato sauce, 30% less sodium, pH 3.7, keeping shelf life and tomato flavour",
    "输入化合物、蛋白、靶点或关键词，例如 quercetin": "Enter a compound, protein, target or keyword, e.g. quercetin",
    "中英文均可，例如 槲皮素 乳清蛋白 相互作用 / quercetin whey protein": "Chinese or English, e.g. 槲皮素 乳清蛋白 相互作用 / quercetin whey protein",
    "例如 PubChem、UniProt、OpenAlex、图书馆": "e.g. PubChem, UniProt, OpenAlex, library",
    "留空自动": "Blank = random",
    "例如 1BEB": "e.g. 1BEB", "例如 A": "e.g. A", "例如 1GFL": "e.g. 1GFL",
    "例如 58,60,64 或 10-20": "e.g. 58,60,64 or 10-20", "例如 1,2,3": "e.g. 1,2,3",
    "例如 1,2,3（糖链残基）": "e.g. 1,2,3 (glycan residues)",
    "例如：1BEB 与 1GFL 的蛋白-蛋白对接；或 1BEB + quercetin 的蛋白-配体对接": "e.g. protein–protein docking of 1BEB and 1GFL; or protein–ligand docking of 1BEB + quercetin",
    "例如：分析乳清蛋白与槲皮素的结合机制，运行对接、短 MD 和 QM": "e.g. analyse whey protein–quercetin binding with docking, short MD and QM",
    "留空从一句话解析，例如 1BEB, 1GFL": "Blank = parse from goal, e.g. 1BEB, 1GFL",
    "留空从一句话解析，例如 quercetin, curcumin": "Blank = parse from goal, e.g. quercetin, curcumin",
    "PDB ID，例如 1BEB": "PDB ID, e.g. 1BEB",
    "例如：2026-10 乳清饮料实测": "e.g. Oct 2026 whey beverage measurements",
    "批次、单位、实验设计": "Batch, units, experimental design",
    "例如：证据图谱里的流程边算实验证据吗？": "e.g. are workflow edges in the evidence graph experimental evidence?",
    "仪器、批次、重复数": "Instrument, batch, replicates",
    "化学与食品身份": "Chemical and food identity",
    "食品与配方": "Food and formulations",
    "蛋白、结构与通路": "Proteins, structures and pathways",
    "文献与开放获取": "Literature and open access",
    "光谱与波谱证据": "Spectra and spectroscopic evidence",
    "华南理工大学 / 机构访问": "SCUT / institutional access",
    "标识符与引用工具": "Identifiers and citation tools",
    "化合物身份、性质、同义词与实验谱图。": "Compound identity, properties, synonyms and experimental spectra.",
    "化学实体本体与角色注释。": "Chemical entity ontology and role annotations.",
    "跨库化合物标识映射。": "Cross-database compound identifier mapping.",
    "仅跳转；自动查询需遵守站点条款。": "Link-out only; automated queries must follow site terms.",
    "需许可和 API key，未授权时不抓取。": "Licence and API key required; no scraping without authorisation.",
    "晶体结构数据库，需机构订阅。": "Crystal structure database; institutional subscription required.",
    "浏览器验证码会阻止自动抓取，保留链接入口。": "Browser CAPTCHAs block automated access; link-out entry retained.",
    "公开 NMR 参考；批量查询需遵守条款。": "Public NMR reference; bulk queries must follow terms.",
    "谱图记录许可逐条不同。": "Spectral record licences vary by record.",
    "脂质分类与结构参考。": "Lipid classification and structure reference.",
    "聚糖 accession 参考。": "Glycan accession reference.",
    "食品成分与营养数据；可用 API key 提高限额。": "Food composition and nutrition data; an API key raises rate limits.",
    "开放食品标签与产品数据。": "Open food labels and product data.",
    "食品成分与风味参考；下载需遵守条款。": "Food composition and flavour reference; downloads must follow terms.",
    "生物活性物质数据库，需许可。": "Bioactive compound database; licence required.",
    "蛋白序列、功能与交叉引用。": "Protein sequences, function and cross-references.",
    "实验结构。": "Experimental structures.",
    "预测结构；不是实验结构。": "Predicted structures; not experimental structures.",
    "蛋白互作证据与置信度。": "Protein interaction evidence and confidence.",
    "核酸/蛋白序列；建议配置 NCBI API key。": "Nucleic acid/protein sequences; an NCBI API key is recommended.",
    "通路与化合物；再分发前核对条款。": "Pathways and compounds; check terms before redistribution.",
    "生物活性与药物相似性数据。": "Bioactivity and drug-likeness data.",
    "本地 OA 元数据与全文来源。": "Local OA metadata and full-text sources.",
    "题录与摘要入口。": "Citation and abstract entry point.",
    "开放学术图谱；使用 contact email 进入 polite pool。": "Open scholarly graph; use a contact email to join the polite pool.",
    "按 DOI 查找合法 OA 版本。": "Find legal OA versions by DOI.",
    "DOI 元数据与引用关系。": "DOI metadata and citation links.",
    "开放获取期刊目录。": "Directory of open-access journals.",
    "聚合机构仓储；下载前核对许可。": "Aggregates institutional repositories; check licences before download.",
    "引用与相关文献入口。": "Citation and related-literature entry point.",
    "预印本；未经同行评审。": "Preprint; not peer reviewed.",
    "预印本；需核对版本与同行评审状态。": "Preprint; check version and peer-review status.",
    "IR/MS/UV-Vis 等参考谱与热化学数据；逐条核对仪器条件，不自动抓取。": "Reference IR/MS/UV-Vis spectra and thermochemical data; verify instrument conditions per record, with no automated scraping.",
    "IR、1H/13C NMR、MS 参考谱；适合交叉核对，不能替代同条件实测。": "Reference IR, 1H/13C NMR and MS spectra; suitable for cross-checking, not a substitute for same-condition measurement.",
    "代谢物 MS/MS 与 NMR 参考；商用或再分发前确认许可。": "Metabolite MS/MS and NMR references; confirm licence before commercial use or redistribution.",
    "EBI 代谢组学原始数据与谱图；按研究记录核对方法和许可。": "EBI metabolomics raw data and spectra; verify methods and licence per study.",
    "串联质谱网络与参考谱；用于候选发现，需核对碰撞能量与样本背景。": "Tandem MS networks and reference spectra; for candidate discovery, verify collision energy and sample background.",
    "NMR 原始峰表与结构归属交换格式；适合审计，不存放受版权保护的全文。": "Exchange format for raw NMR peak tables and assignments; suitable for audit, with no copyrighted full text stored.",
    "配体/组分的原子、键和标识符定义；用于结构核对。": "Atom, bond and identifier definitions for ligands/components; used for structure checks.",
    "请从学校官方入口登录；软件不收集账号密码。": "Sign in through the official university entry point; the app collects no credentials.",
    "通过学校身份认证访问已授权资源。": "Access licensed resources through university authentication.",
    "学校主页与统一身份认证入口。": "University homepage and unified identity entry point.",
    "DOI 解析；最终全文权限由出版方/机构决定。": "DOI resolution; final full-text access is decided by the publisher/institution.",
    "作者标识符。": "Author identifier.",
    "题录与引用元数据。": "Citation and reference metadata.",
    "已登记来源": "Registered sources", "机构入口": "Institutional entry points", "PostgreSQL 文献": "PostgreSQL literature",
    "文本块": "Text chunks", "图谱边": "Graph edges", "公开参考": "Public reference",
    "链接入口": "Link-out", "许可/机构来源": "Licensed/institutional sources",
    "未授权前不抓取、不复制": "No scraping or copying before authorisation",
    "已登记公共源": "Registered public sources", "需凭据": "Credentials required",
    "参考入口": "Reference entry", "读取来源许可…": "Reading source licences…",
    "没有匹配的资源。清空搜索或切换筛选。": "No matching resources. Clear the search or change filters.",
    "官方入口": "Official entry point", "查看站点条款": "See site terms",
    "已连接": "Connected", "向量": "Vectors", "体积": "Size",
    "登录后加载。": "Loads after sign-in.",
    "SDBS 有机化合物谱图数据库": "SDBS organic compound spectral database",
    "HMDB 人类代谢组数据库": "HMDB Human Metabolome Database",
    "华南理工大学图书馆": "SCUT Library", "CARSI 联盟": "CARSI Federation", "华南理工大学": "SCUT",
    "API / 解析": "API / resolver", "可查询": "Available",
    "需要商业/学术许可和 API key；未配置时不查询，也不复制其数据。": "Commercial/academic licence and API key required; without configuration, no queries are made and no data is copied.",
    "晶体结构数据库需机构订阅；本机未配置授权。": "Crystal structure database requires an institutional subscription; no licence is configured on this machine.",
    "ChemBook / 化学专业数据库": "ChemBook / chemistry database",
    "需用户提供有权的机构入口；未提供前不接入。": "Requires an authorised institutional entry point from the user; not connected until provided.",
    "可作为公开 NMR 参考入口；批量/自动查询需遵守站点条款。": "Usable as a public NMR reference entry point; bulk or automated queries must follow site terms.",
    "脂质分类与结构参考；自动查询需按接口条款配置。": "Lipid classification and structure reference; automated queries require configuration under the interface terms.",
    "聚糖 accession 参考；糖链身份需用 accession 精确检索。": "Glycan accession reference; identify glycans precisely by accession.",
    "高校图书馆电子资源": "University library e-resources",
    "需机构 IP/代理、账号和许可；不能绕过付费墙或批量下载。": "Requires institutional IP/proxy, account and licence; no paywall bypass or bulk downloads.",
    "实体分类 → 选择数据库 → 标识符验证 → 相关性过滤": "Entity classification → database selection → identifier verification → relevance filtering",
    "实体：小分子 / 化合物": "Entity: Small molecule / compound", "实体：蛋白 / 靶点": "Entity: Protein / target",
    "实体：食品 / 配方": "Entity: Food / formulation", "实体：化合物-蛋白复合": "Entity: Compound–protein complex",
    "查询扩展：": "Query expansion:", "中英文映射：": "Bilingual mapping:", "执行来源：": "Executed sources:",
    "相关度按词面覆盖与短语命中排序；不是统计显著性。": "Relevance is ranked by lexical coverage and phrase hits, not statistical significance.",
    "已拒绝：": "Rejected:", "高相关": "High relevance", "中相关": "Medium relevance", "低相关": "Low relevance",
    "排名": "Rank", "命中词：": "Matched terms:", "打开原始记录 ↗": "Open original record ↗",
    "已验证的跨库证据": "Verified cross-database evidence",
    "只展示 InChIKey 精确映射、UniProt→PDB xref 或谱图参考；不再使用名称候选冒充身份验证。": "Only exact InChIKey mappings, UniProt→PDB cross-references or spectral references are shown; name candidates are no longer presented as verified identities.",
    "记录来自各数据库公开接口；检索时间、记录号、匹配依据与许可已保留。": "Records come from public database APIs; retrieval time, record ID, match basis and licence are retained.",
    "本地快照": "Local snapshot", "仅链接": "Link only", "0 条": "0 records", "跳过": "Skipped", "错误": "Error",
    "正在检索本地索引…": "Searching the local index…", "未建立": "Not built", "读取失败": "Read failed",
    "全文": "Full text", "实体": "Entities", "关系": "Relations",
    "Europe PMC OA 元数据与本地 BM25 索引；不是系统综述。": "Europe PMC OA metadata and a local BM25 index; not a systematic review.",
    "本地文献库不可用。": "The local literature library is unavailable.",
    "未检测到蛋白或食品语境；按小分子/化合物处理，避免调用无关的蛋白和食品库": "No protein or food context detected; treated as a small molecule/compound to avoid irrelevant protein and food databases.",
    "结果按词面/短语相关度排序；strength 是高/中/低分级，不是统计显著性。": "Results are ranked by lexical/phrase relevance; strength is a high/medium/low grade, not statistical significance.",
    "先分类实体，再选择数据库；化合物不查 UniProt/PDB/STRING，食品不查蛋白库，蛋白结构只通过 UniProt xref 映射。": "Classify the entity before selecting databases: compounds skip UniProt/PDB/STRING, foods skip protein databases, and protein structures use only UniProt cross-references.",
    "在线记录缓存 24 h。每条记录保留来源、检索时间、原始链接、匹配依据和相关性；跨库链接只使用 InChIKey 或 UniProt/PDB xref。": "Online records are cached for 24 h. Every record keeps its source, retrieval time, original link, match basis and relevance; cross-database links use only InChIKey or UniProt/PDB cross-references.",
    "同一 InChIKey 的精确交叉引用；不是名称匹配。": "Exact cross-reference by identical InChIKey; not a name match.",
    "UniProt 记录中的 PDB 交叉引用。": "PDB cross-reference from the UniProt record.",
    "PubChem 谱图记录中标注的 MassBank accession；为参考链接，不是结构身份验证。": "MassBank accession referenced by the PubChem spectral record; a reference link, not structural identity verification.",
  });
  const I18N_HTML = {
    "一句话，生成一组可比较的配方。": "One sentence, generate <em>a set</em> of comparable formulations.",
    "独立 HADDOCK3 作业：按下列参数生成 haddock.cfg，保留输入结构、约束、日志、CAPRI 表和最佳模型。HADDOCK score 是任意单位（a.u.，越低越好），不是结合自由能；没有实验参考结构时不会把 CAPRI RMSD 当作验证。": "<b>Standalone HADDOCK3 job</b>: the parameters below generate <code>haddock.cfg</code> and retain the input structures, restraints, log, CAPRI tables and best model. The HADDOCK score is in arbitrary units (a.u., lower is better), not a binding free energy; without an experimental reference structure, CAPRI RMSD is not treated as validation.",
    "蛋白-配体请填配体名称或 SMILES；蛋白-多糖请填含糖链的 PDB（可写 1LMQ:B）。留空链号时自动选择首个合适链。": "For protein–ligand, enter a ligand name or SMILES; for protein–polysaccharide, enter a PDB containing a glycan chain (e.g. <code>1LMQ:B</code>). Leave the chain blank to auto-select the first suitable chain.",
  };
  const I18N_BLOCK = {
    "配方组合、在线数据库证据、本地分子机制计算与模型实验室。": "Formulation portfolios, federated evidence, local mechanism calculations and a model lab.",
    "覆盖饮料、乳品、烘焙、植物基、肉制品、酱料、糖果、冷冻甜品等 20 个食品体系；每条配方都附指标、相互作用、风险与来源。": "Covers 20 food systems including beverages, dairy, bakery, plant-based, meat, sauces, confectionery and frozen desserts; every formulation includes metrics, interactions, risks and sources.",
    "系统不会只给一个答案：它会生成 8 个可比较组合，并明确哪些约束已满足、哪些仍需实测。": "The system does not return one answer: it generates 8 comparable formulations and states which constraints pass and which still need measurement.",
    "先判断实体类型，再选择数据库；化合物不会调用 UniProt/PDB/STRING，蛋白结构只通过 UniProt→PDB 交叉引用。": "Entity type is detected before choosing databases; compounds do not query UniProt/PDB/STRING, and protein structures use only UniProt→PDB cross-references.",
    "谱图证据必须核对仪器、溶剂、碰撞能量和原始记录；这里只提供合法公开/机构入口，不抓取受限谱库。": "Spectral evidence must be checked against instrument, solvent, collision energy and raw records; only legal public/institutional entry points are listed, with no scraping of restricted libraries.",
    "参考谱不等于同条件实测；MS 需说明离子模式/碰撞能量，NMR 需说明溶剂/频率，IR 需说明样品制备。完整目录见资源库“光谱与波谱证据”。": "Reference spectra are not same-condition measurements; report ion mode/collision energy for MS, solvent/frequency for NMR, and sample preparation for IR. See the spectroscopy group in Resources.",
    "Europe PMC OA 元数据 + 本地 BM25 索引；标签由标题/摘要规则、MeSH、作者关键词与化合物映射生成。检索结果需核对原文与许可，不是系统综述。": "Europe PMC OA metadata plus a local BM25 index; tags come from title/abstract rules, MeSH, author keywords and compound mappings. Results must be checked against the original and its licence; this is not a systematic review.",
    "所有来源都标注许可、接入状态和用途。开放数据直接跳转；需许可或机构登录的来源只提供官方入口，不抓取、不代存账号密码。Sci-Hub 及绕过付费墙的链接不收录。": "Every source lists its licence, access status and purpose. Open data links out directly; licensed or institutional sources only expose official entry points. No Sci-Hub or paywall bypass links are listed.",
    "软件不提供账号密码表单，也不代存校园密码。请从学校官方入口登录，再回到 DOI/出版社页面获取全文。": "The app provides no credential form and stores no campus password. Log in through the official university portal, then return to the DOI/publisher page for full text.",
    "如果学校提供 EZproxy 前缀，可由管理员配置 BIOFORGE_EZPROXY_PREFIX；软件只拼接官方登录 URL，不保存凭据。": "If your institution provides an EZproxy prefix, an administrator can set BIOFORGE_EZPROXY_PREFIX; only the official login URL is composed and credentials are not stored.",
    "这是一个可审计的小数据工作台：CSV/JSON 导入、数据来源标记、交叉验证、残差/树集成/GP 不确定性、带约束搜索空间和 EI 候选。它不训练通用大模型，也不会把合成数据伪装成实验证据。": "An auditable small-data workbench: CSV/JSON import, source labels, cross-validation, residual/tree-ensemble/GP uncertainty, constrained search spaces and EI candidates. It does not train a foundation model or disguise synthetic data as experimental evidence.",
    "这份应用内指南解释数据从哪来、结果怎么读、哪些结论不能下。完整版同时保存在服务器 docs/USER_GUIDE.md 与 Obsidian 文献库。": "This in-app guide explains where data comes from, how to read results, and which conclusions are not supported. The full version is stored in docs/USER_GUIDE.md and the Obsidian library.",
    "使用服务器本地 Ollama 模型回答软件使用问题；记录会写入服务器 runtime/assistant/ 并保留每日备份。不要输入密码、Token 或未公开数据。": "Answers software questions with the local Ollama model; records are written to runtime/assistant/ with daily backups. Never enter passwords, tokens or unpublished data.",
    "无法把 Obsidian 桌面 UI 原样嵌入浏览器；这里直接读取服务器上的 Markdown 文件。选中笔记后会定时刷新，修改只请在 Obsidian 中进行。": "The Obsidian desktop UI cannot be embedded directly; this reads Markdown files on the server. Selected notes refresh periodically; edit only in Obsidian.",
    "主题只改变颜色与背景，不影响数据和权限。设置保存在本机浏览器。": "The theme only changes colours and background; data and permissions are unaffected. The setting is stored in this browser.",
    "配方与指标是 curated priors 与模板估算，不是实测或法规结论。": "Formulations and metrics are curated priors and template estimates, not measurements or regulatory conclusions.",
    "PostgreSQL 16 + pgvector；不可用时自动回退 SQLite FTS5。向量列已建立，嵌入尚未生成。": "PostgreSQL 16 + pgvector; falls back to SQLite FTS5 when unavailable. Vector columns exist but embeddings are not generated yet.",
    "有许可/凭据要求的来源不会伪装成“已接入”；需要机构代理或 API key 的来源会明确标注。": "Sources requiring a licence or credentials are never presented as connected; institutional proxy or API-key requirements are labelled explicitly.",
    "在线证据必须核验原始记录；计算结果是机制假设，不是自由能或安全结论。": "Online evidence must be checked against raw records; calculations are mechanistic hypotheses, not free energies or safety conclusions.",
    "模型实验室的预测来自表格模型与交叉验证不确定性，不是机理模型；合成/模拟数据不能替代湿实验。": "Model Lab predictions come from tabular models and cross-validation uncertainty, not mechanistic models; synthetic/simulated data cannot replace wet-lab experiments.",
    "BioForge 不提供账号密码输入框，也不接收、记录或代存校园密码。请在新窗口中使用学校官方 SSO/EZproxy/CARSI 登录，登录态由学校和出版社维护。": "BioForge provides no credential form and does not receive, record or store campus passwords. Log in through the official SSO/EZproxy/CARSI page in a new window; sessions are managed by the university and publisher.",
    "登录后回到 DOI、PubMed 或出版社页面获取全文；授权范围以学校许可为准。软件不绕过付费墙，也不提供 Sci-Hub 链接。": "After signing in, return to the DOI, PubMed or publisher page for full text; access is governed by institutional licences. The app does not bypass paywalls or provide Sci-Hub links.",
    "首次登录凭据保存在服务器runtime/login.txt；生产环境请立即修改密码。": "First-run credentials are stored in runtime/login.txt on the server; change them immediately before production use.",
    "只列公开/机构授权入口；不提供 Sci-Hub 或付费墙绕过链接。": "Only public and institutional-access entry points are listed; no Sci-Hub or paywall-bypass links are provided.",
    "输入 DOI 或 PubMed PMID。只解析元数据和合法 OA 位置；最终权限由出版方或学校授权决定，不绕过付费墙。": "Enter a DOI or PubMed PMID. Only metadata and legal OA locations are resolved; final access is decided by the publisher or your institution, with no paywall bypass.",
    "如果学校提供 EZproxy 前缀，可由管理员配置BIOFORGE_EZPROXY_PREFIX；软件只拼接官方登录 URL，不保存凭据。": "If your institution provides an EZproxy prefix, an administrator can set BIOFORGE_EZPROXY_PREFIX; only the official login URL is composed and credentials are not stored.",
    "多个受体会与每个配体做笛卡尔组合；单次最多 12 对。高级 MD/QM 默认只跑代表项，避免误启动数小时任务；“全部”会逐项运行。": "Every receptor is paired with every ligand, up to 12 pairs per run. Advanced MD/QM runs the representative pair by default to avoid accidental multi-hour jobs; All runs each pair.",
    "支持 PDB、PDBQT 多构象与 GROMACS GRO；组分会按蛋白链、核酸链、配体、糖链、脂质、离子和水全部列出。序列区换行展示所有链，不再截断；结构仅用于可视化，不替代专业结构分析。": "Supports PDB, multi-model PDBQT and GROMACS GRO; components list protein, nucleic acid, ligand, glycan, lipid, ion and water chains. Sequences show every chain on separate rows; the viewer is for visualisation, not a substitute for professional structural analysis.",
    "演示集是 180 行合成数据（source_type=synthetic），仅用于验证流程；训练时必须显式确认。": "The demo set is 180 synthetic rows (source_type=synthetic) for workflow validation only; explicit confirmation is required before training.",
    "训练使用交叉验证，默认按随机 KFold 划分；同批次/同配方请设置分组列。结果列若被强制作为特征，会标记数据泄漏风险。": "Training uses cross-validation with random KFold by default; set a group column for shared batches or formulations. Forcing an outcome column into features flags a data-leakage risk.",
    "采集函数为 Expected Improvement；候选按 EI 排序并做多样性筛选。范围外的输入会被收窄到训练数据范围。": "The acquisition function is Expected Improvement; candidates are ranked by EI with diversity filtering. Inputs outside the training range are clipped to that range.",
    "把湿实验/模拟结果追加到原数据集，再用同一配置重训。追加会更新数据集哈希和模型版本；合成数据仍需显式确认。": "Append wet-lab or simulated results to the original dataset, then retrain with the same configuration. Appending updates the dataset hash and model version; synthetic data still needs explicit confirmation.",
    "这份应用内指南解释数据从哪来、结果怎么读、哪些结论不能下。完整版同时保存在服务器docs/USER_GUIDE.md与 Obsidian 文献库。": "This in-app guide explains where data comes from, how to read results, and which conclusions are not supported. The full version is stored in docs/USER_GUIDE.md and the Obsidian library.",
    "使用服务器本地 Ollama 模型回答软件使用问题；记录会写入服务器runtime/assistant/并保留每日备份。不要输入密码、Token 或未公开数据。": "Answers software questions with the local Ollama model; records are written to runtime/assistant/ with daily backups. Never enter passwords, tokens or unpublished data.",
    "无法把 Obsidian 桌面 UI 原样嵌入浏览器；这里直接读取服务器上的 Markdown 文件。选中笔记后会定时刷新，修改只请在 Obsidian 中进行。": "The Obsidian desktop UI cannot be embedded directly; this reads Markdown files on the server. Selected notes refresh periodically; edit only in Obsidian.",
    "服务器启动后，浏览器打开http://服务器IP:8010；手机与服务器同一 Wi-Fi 时用局域网 IP。": "After the server starts, open http://SERVER-IP:8010 in a browser; use the LAN IP when the phone and server share Wi-Fi.",
    "登录后先在“设置”修改演示密码。公网访问必须使用 HTTPS，不要直接端口转发明文 HTTP。": "After signing in, change the demo password in Settings. Public access must use HTTPS; never port-forward plain HTTP.",
    "在“设计工作台”选择自动/食品/生物设计，输入目标并生成候选。": "In Design Studio choose Auto/Food/Biologic design, enter a goal and generate candidates.",
    "点击“证据图谱”检查推理链；点击“运行机制计算”进入 Vina/MD/QM 作业。": "Open Evidence graph to inspect the reasoning chain; choose Run mechanism to start Vina/MD/QM jobs.",
    "在“在线证据”底部检索本地 OA 文献；在“模型实验室”导入自己的实测数据。": "Search local OA literature at the bottom of Evidence; import your own measurements in Model Lab.",
    "远程访问：推荐 Cloudflare Tunnel、Tailscale 或带 HTTPS 的反向代理。具体步骤见服务器docs/DEPLOYMENT.md。": "Remote access: use Cloudflare Tunnel, Tailscale or an HTTPS reverse proxy. See docs/DEPLOYMENT.md.",
    "候选是可比较的数字原型，不是已经做出来的产品。综合评分是加权决策指数，不是成功概率。约束通过只表示模型内的规则通过，仍需实测。": "Candidates are comparable digital prototypes, not finished products. Overall score is a weighted decision index, not a probability of success. Constraint passes mean only that model rules passed; measurements are still required.",
    "食品模式展示配方占比、配料角色、相互作用与工艺；生物模式展示蛋白/化合物、保护剂组合、Tm、保留率、亮度与光谱。": "Food mode shows formulation ratios, ingredient roles, interactions and process; biologic mode shows protein/compound, protectant combinations, Tm, retention, brightness and spectra.",
    "at_risk表示筛选区间跨过边界，必须做验证实验。所有区间都是假设，不是统计置信区间。": "at_risk means the screening interval crosses a boundary and a validation experiment is required. All intervals are assumptions, not statistical confidence intervals.",
    "报告不会用随机数挑选候选；每个候选都能追溯到数据版本、规则和参数指纹。": "Reports do not pick candidates with random numbers; each candidate traces back to data version, rules and parameter fingerprint.",
    "节点代表设计、候选、配料/保护剂、推理步骤、约束、文献或数据源；边代表使用、支持、相互作用或下一步。滚轮/双指缩放，拖拽平移，点击节点查看详情。": "Nodes represent designs, candidates, ingredients/protectants, reasoning steps, constraints, literature or data sources; edges represent use, support, interaction or next steps. Scroll/pinch to zoom, drag to pan, click a node for details.",
    "“类型着色”区分节点角色；“连接度着色”让枢纽节点更醒目。数据源节点可打开原始数据库；文献节点来自 curated prior，不等于临床证据。": "Type colour distinguishes node roles; degree colour highlights hubs. Data-source nodes open the original database; literature nodes come from curated priors and are not clinical evidence.",
    "Vina 给出对接姿态与打分；GROMACS 短 MD 只检查局部稳定性；CP2K 只计算小体系电子结构。三者都不是生产级自由能、成药性或安全结论。": "Vina returns docking poses and scores; short GROMACS MD checks local stability only; CP2K computes electronic structure for small systems. None is a production free energy, druggability or safety conclusion.",
    "3D 查看器支持 PDB、PDBQT 多构象、GRO；可切换卡通/主链/球棍/空间填充，按元素/链/深度着色，显示配体与单字母序列。点击原子查看残基，导出当前视图 PNG。": "The 3D viewer supports PDB, multi-model PDBQT and GRO; switch cartoon/backbone/ball-and-stick/space-fill, colour by element/chain/depth, and show ligands and one-letter sequences. Click an atom to inspect its residue; export the current view as PNG.",
    "从计算结果中可直接打开 receptor.pdb、poses.pdbqt、md.gro；多构象文件会显示构象选择器。": "Open receptor.pdb, poses.pdbqt or md.gro directly from results; multi-model files show a model selector.",
    "先导入 CSV/JSON，明确标记实测、文献、模拟或合成来源。训练使用交叉验证；合成数据必须显式勾选。贝叶斯优化只会在训练范围内搜索，不会外推。": "Import CSV/JSON and label sources as measured, literature, simulated or synthetic. Training uses cross-validation; synthetic data requires an explicit checkbox. Bayesian optimisation searches only within the training range and never extrapolates.",
    "预测区间与 EI 是统计辅助，不是实验保证。回灌实测会更新数据哈希与模型版本。": "Prediction intervals and EI are statistical aids, not experimental guarantees. Feeding back measurements updates the data hash and model version.",
    "本地库当前含 10,000 篇 Europe PMC OA 元数据、25,000+ 文本块和 Obsidian 笔记。检索使用 SQLite FTS5/BM25，不需要联网。": "The local library contains 10,000 Europe PMC OA records, 25,000+ text chunks and Obsidian notes. Search uses SQLite FTS5/BM25 and works offline.",
    "标签映射：标题/摘要规则 → topic；MeSH → mesh/…；作者关键词 → keyword/…；化合物 → chemical/…。Obsidian 笔记位于服务器数据目录的obsidian/<year>/。": "Tag mapping: title/abstract rules → topic; MeSH → mesh/…; author keywords → keyword/…; compounds → chemical/…. Obsidian notes live under obsidian/<year>/ in the server data directory.",
    "手机打不开：确认地址是电脑局域网 IP 和 8010 端口；127.0.0.1只指手机自己。检查防火墙与同一 Wi-Fi。": "Phone cannot connect: confirm the computer LAN IP and port 8010; 127.0.0.1 points to the phone itself. Check the firewall and that both devices share Wi-Fi.",
    "Internal Server Error：查看logs/bioforge.log或logs/server-v3.log；生物设计缺少 ID 的问题已在 3.2 修复。": "Internal Server Error: check logs/bioforge.log or logs/server-v3.log; missing biologic design IDs were fixed in 3.2.",
    "计算失败：在“机制计算”展开本地软件接口，检查 Vina/GROMACS/CP2K 路径；超时只保护单步。": "Calculation failed: expand Local tool paths in Mechanism and check Vina/GROMACS/CP2K paths; timeouts protect individual steps only.",
    "数据备份：备份runtime/、Lab 数据库与文献数据目录；不要把runtime/.token或密码提交到仓库。": "Backup: back up runtime/, the Lab database and literature data; never commit runtime/.token or passwords.",
    "主库为 PostgreSQL 16 + pgvector；当前已同步10,000条文献元数据、25,062个文本块、48,544个图谱实体和76,954条边。页面“资源库”列出全部公开/许可来源、许可说明和官方跳转链接。": "The primary database is PostgreSQL 16 + pgvector; it currently syncs 10,000 literature records, 25,062 text chunks, 48,544 graph entities and 76,954 edges. Resources lists every public/licensed source, licence note and official link.",
    "pgvector 字段已建立但尚未生成嵌入向量；文献检索当前使用 PostgreSQL 全文索引，失败时回退到本地 SQLite FTS5。开放获取解析只调用 Crossref、Europe PMC、Unpaywall 等合法接口。": "pgvector columns exist but embeddings are not generated yet; literature search uses PostgreSQL full-text search and falls back to SQLite FTS5. OA resolution calls only legal APIs such as Crossref, Europe PMC and Unpaywall.",
    "Sci-Hub、付费墙绕过、验证码规避和未授权批量下载不提供。机构资源请使用学校官方 SSO/EZproxy/CARSI 登录；软件不收集账号密码。": "Sci-Hub, paywall bypass, CAPTCHA circumvention and unauthorised bulk downloads are not provided. Use official SSO/EZproxy/CARSI for institutional access; the app collects no credentials.",
    "配方、模型、对接、MD、QM 和文献检索均为研究与设计决策支持。": "Formulations, models, docking, MD, QM and literature search are research and design-decision support only.",
    "不构成食品/药品/医疗器械合规、安全性、有效性或临床结论。": "They do not constitute food, drug or medical-device compliance, safety, efficacy or clinical conclusions.",
    "合成/模拟数据不能替代湿实验；文献标签不能替代人工阅读。": "Synthetic/simulated data cannot replace wet-lab experiments; literature tags cannot replace human reading.",
    "公网部署前必须修改默认密码、启用 HTTPS、限制访问并做好备份。": "Before public deployment, change default passwords, enable HTTPS, restrict access and maintain backups.",
    "手机和电脑需在同一局域网。服务器默认监听 0.0.0.0:8010；明文 HTTP 只建议在可信家庭/实验室网络使用。远程客户请按 docs/DEPLOYMENT.md 部署 HTTPS。": "Phone and computer must share a LAN. The server listens on 0.0.0.0:8010; plain HTTP is only appropriate on a trusted home/lab network. For remote clients, deploy HTTPS as described in docs/DEPLOYMENT.md.",
    "浏览器使用 HttpOnly 会话 Cookie。外部脚本/AutoDL 可使用服务器生成的 API Token：": "The browser uses an HttpOnly session cookie. External scripts/AutoDL can use a server-generated API token:",
    "Token 只用于 API 鉴权，不是数据库密钥，也不会传给第三方；请保持 0600 权限，不要提交到仓库。": "The token is only for API authentication, not a database key, and is never sent to third parties; keep it at mode 0600 and never commit it.",
    "有许可/凭据要求的来源不会伪装成“已接入”；需要机构代理或 API key 的来源会明确标注。": "Sources requiring a licence or credentials are never presented as connected; institutional proxy or API-key requirements are labelled explicitly.",
    "食品引擎 2.1.0-food · 生物引擎 1.0.0 · 模型实验室 3.3.0 · 文献库 3.3.0": "Food engine 2.1.0-food · Biologic engine 1.0.0 · Model Lab 3.3.0 · Literature 3.3.0",
    "全部硬约束通过": "All hard constraints pass", "约束存在区间风险": "Constraint ranges at risk",
    "存在未达标约束": "Unmet constraints", "证据等级": "Evidence grade",
    "决策指数，不是概率": "Decision index, not a probability", "这张结果怎么读？": "How to read this result",
    "决策指数、筛选区间与实测边界": "Decision index, screening ranges and measurement boundaries",
    "约束状态": "Constraint status", "通过": "Pass", "占比与组成": "Proportions and composition",
    "来源": "Source", "蛋白质": "Protein", "糖": "Sugar", "钠": "Sodium", "脂肪": "Fat",
    "配料": "Ingredient", "占比": "Share", "角色": "Role", "组成来源": "Composition source",
    "工艺": "Process", "加工条件与分子变化": "Process conditions and molecular changes",
    "机理规则 + 文献先验的方向性预测；不是本配方实测。": "Directional prediction from mechanistic rules + literature priors; not measured for this formulation.",
    "约束审计": "Constraint audit", "警告与下一步": "Warnings and next steps",
    "数据版本": "Data versions", "控制点": "Control points", "QC 与验收": "QC and acceptance",
    "推理链与边界": "Reasoning chain and boundaries", "数字孪生与验证": "Digital twin and validation",
    "保护剂组合": "Protectant blend", "食品级": "Food grade", "风险与待验证": "Risks and validation",
    "指标": "Metric", "模型值": "Model value", "工艺后保留": "Process retention",
    "总保留": "Overall retention", "货架后保留": "Storage retention",
    "模型达到目标概率": "Model probability of meeting target", "有效 Tm": "Effective Tm", "亮度": "Brightness",
    "候选由约束筛选与保护剂组合优化生成。": "Candidate generated by constraint screening and protectant-blend optimisation.",
    "该候选仅展示保护剂组合；完整工艺卡属于当前选中候选。": "This candidate shows only the protectant blend; the full process card belongs to the current selection.",
    "过敏原": "Allergen", "负向作用": "Negative interactions", "正向作用": "Positive interactions",
    "添加剂": "Additive", "是": "Yes", "否": "No", "模型阈值通过": "Model threshold passed", "需复核": "Review required",
    "光谱与参考峰": "Spectra and reference peaks", "类型": "Type", "溶剂/条件": "Solvent/conditions",
    "参考峰": "Reference peaks", "级别": "Level", "候选来源：": "Candidate source:",
    "该候选暂无匹配的本地参考峰；可在“在线证据”中检索 PubChem/NIST/MassBank/SDBS，并核对仪器条件。": "No matching local reference peaks for this candidate; search PubChem/NIST/MassBank/SDBS in Evidence and verify instrument conditions.",
    "发射参考": "Emission reference", "工艺后（数字孪生）": "After processing (digital twin)", "UV-Vis 参考": "UV-Vis reference",
    "数字孪生与验证": "Digital twin and validation", "风险与待验证": "Risks and validation",
    "未设置可计算的硬约束。": "No computable hard constraints were set.", "估算": "Estimate", "限制": "Limit",
    "筛选区间": "Screening range", "约束": "Constraint", "状态": "Status",
    "已知事实": "Known facts", "显式规则": "Explicit rules", "关键假设": "Key assumptions",
    "必须验证": "Validation required", "相对基础模板的改动": "Changes from the base template",
    "为什么是这个组合": "Why this combination", "相互作用": "Interactions",
    "未检出显著正向作用。": "No significant positive interactions detected.",
    "指标是怎么来的": "How the metrics were derived", "推理链与证据边界": "Reasoning chain and evidence boundaries",
    "事实、规则、假设和待验证项分开记录；不使用随机数挑选配料。": "Facts, rules, assumptions and validation items are recorded separately; ingredients are not chosen randomly.",
    "当前候选没有加工变化预测。": "No processing-change prediction is available for this candidate.",
    "高影响": "High impact", "中影响": "Medium impact", "低影响": "Low impact",
    "温度": "Temperature", "时间": "Time", "热负荷": "Heat load", "宏观：": "Macro: ", "验证：": "Validation: ",
    "评分、保留率与验证边界": "Score, retention and validation boundaries",
    "硬约束逐项展示点估计、筛选区间和状态；": "Hard constraints are shown with point estimates, screening ranges and status; ",
    " 表示区间跨过边界，必须实测复核。": " means the range crosses the boundary and must be verified.",
    "配方为数字原型；法规、过敏原和微生物安全需实测与当地法规核验。": "The formulation is a digital prototype; regulatory, allergen and microbiological safety require measurement and local regulatory review.",
    "未关联配方": "No formulation linked",
    "文件里没有可显示的原子坐标": "No displayable atom coordinates in the file",
    "GRO 文件里没有可显示的原子坐标": "No displayable atom coordinates in the GRO file",
    "：多目标加权排序，不是概率，也不是感官/法规结论。": ": multi-objective weighted ranking, not a probability, and not a sensory/regulatory conclusion.",
    "只表示模型估算落在阈值内；": "only means the model estimate falls within the threshold; ",
    "表示筛选区间跨过边界，需优先实测。": " means the screening range crosses the boundary and needs priority measurement.",
    "：来自 curated 配方模板和 USDA FDC 参考映射；供应商批次、加工损失与地区法规仍需核验。": ": from curated formulation templates and USDA FDC reference mapping; supplier batches, processing losses and local regulations still require verification.",
    "：结果附来源列表；引用前核对原文。": ": sources are listed with the result; check the original before citing.",
    "表示区间跨过边界，必须实测复核。": " means the range crosses the boundary and must be measured and reviewed.",
    "食品体系模板 + 配料酸/缓冲先验": "Food-system template + ingredient acid/buffer priors",
    "配料 aw curated 先验": "Ingredient aw curated prior",
    "curated 食品化学规则": "Curated food-chemistry rules",
    "用户目标/查询优先级 + curated 规则": "User goal/query priority + curated rules",
    "面包酵母": "Baker's yeast", "蔗糖": "Sucrose", "氯化钠": "Sodium chloride", "黄原胶": "Xanthan gum",
    "被替代、禁用或归一化移除": "replaced, disabled or normalised out",
    "乳铁蛋白": "Lactoferrin", "乳清蛋白": "Whey protein", "尿酸": "Uric acid", "非布司他": "Febuxostat",
    "全部": "all", "代表项": "representative",
    "可直接查询": "Direct query", "API / 解析": "API / resolver", "需许可": "Licence required",
    "机构登录": "Institutional login", "链接入口": "Link only", "公开参考": "Public reference",
    "色素保留率": "Color retention", "膳食纤维下限": "Dietary fibre minimum", "变体": "variant", "热保护剂": "Thermoprotectant", "螯合剂": "Chelator",
    "护色剂": "Color protectant", "保留率": "Retention", "筛选级启发式": "Screening heuristic",
    "加速褪色": "Accelerated fading", "巴氏温度/时间": "pasteurisation temperature/time",
    "光照/氧": "light/oxygen", "海藻糖/柠檬酸盐保护上限": "capped trehalose/citrate protection",
    "柠檬酸盐": "citrate", "生育酚保护上限": "capped tocopherol protection",
    "海藻糖保护上限": "capped trehalose protection", "包装透光和维生素光敏性": "package light transmission and vitamin photosensitivity",
    "筛选级启发式：pH、巴氏温度/时间、柠檬酸、光照/氧，以及海藻糖/柠檬酸盐保护上限": "screening heuristic: pH, pasteurisation temperature/time, citric acid, light/oxygen, and capped trehalose/citrate protection",
    "筛选级启发式：pH、温度、光照/氧，以及海藻糖/柠檬酸盐保护上限": "screening heuristic: pH, temperature, light/oxygen, and capped trehalose/citrate protection",
    "筛选级启发式：温度、光照/氧和生育酚保护上限": "screening heuristic: temperature, light/oxygen and capped tocopherol protection",
    "筛选级启发式：温度、光照/氧和海藻糖保护上限": "screening heuristic: temperature, light/oxygen and capped trehalose protection",
    "筛选级启发式：包装透光和维生素光敏性": "screening heuristic: package light transmission and vitamin photosensitivity",
    "海藻糖可提高藻蓝蛋白的热/储存稳定性，但无法消除酸性褪色。": "Trehalose can improve the thermal/storage stability of phycocyanin but cannot eliminate acid-induced fading.",
    "酸性条件使藻蓝蛋白变性/聚集，蓝色褪去；需 pH 稳定和低温工艺。": "Acidic conditions denature/aggregate phycocyanin and the blue colour fades; pH stabilisation and low-temperature processing are required.",
    "抗坏血酸和光氧化加速藻蓝蛋白褪色。": "Ascorbic acid and photo-oxidation accelerate phycocyanin fading.",
    "靶向体系": "Targets system", "选择候选": "Selects candidate", "选择策略": "Selects strategy",
    "使用配料": "Uses ingredient", "配伍": "Formulates with", "配料相互作用": "Ingredient interaction",
    "由证据支持": "Supported by evidence", "机制说明": "Mechanism note", "推理起点": "Start",
    "下一步工艺": "Next process", "下一步": "Next", "返回设计": "Complete",
    "开始工艺": "Starts process", "预测成分变化": "Predicts change",
    "关闭详情": "Close details", "可缩放、可拖拽的证据图谱": "Zoomable, draggable evidence graph",
    "约束有风险": "Constraint at risk", "约束未达标": "Constraint not met",
    "GROMACS 可执行文件": "GROMACS executable", "GROMACS 数据目录": "GROMACS data directory",
    "CP2K 可执行文件": "CP2K executable", "CP2K 数据目录": "CP2K data directory",
    "已检测": "Detected", "HADDOCK 已检测；小分子对接仍默认使用 Vina。": "HADDOCK detected; small-molecule docking still defaults to Vina.",
    "多受体 × 多配体筛选": "Multi-receptor × multi-ligand screening",
    "未关联配方，且没有输入体系描述。请先选择设计结果，或填写蛋白/受体与配体。": "No formulation linked and no system description. Select a design result or enter protein/receptor and ligand.",
    "导出参数与结果 JSON": "Export parameters and results JSON", "导出摘要 CSV": "Export summary CSV",
    "受体": "Receptor", "配体": "Ligand", "复合物": "Complex", "3D 复合物": "3D complex",
    "3D 轨迹": "3D trajectory", "Authorization: Bearer <runtime/.token 内容>": "Authorization: Bearer <contents of runtime/.token>",
    "还没有计算任务": "No compute jobs yet",
    "生成配方后点击“运行机制计算”，或在上方直接输入蛋白与配体。": "Generate a formulation, then choose Run mechanism; or enter a protein and ligand above.",
    "复合物 MD": "Complex MD", "复合物回退": "Complex fallback", "EM 未收敛": "EM did not converge",
    "输入校验失败": "Input validation failed", "作业失败": "Job failed",
    "点击查看记录摘要": "Click to view record summary", "任务": "Task", "状态": "Status", "体系": "System", "创建": "Created",
    "全部展开": "Expand all", "全部收起": "Collapse all", "HADDOCK3 运行选择": "HADDOCK3 run setup",
    "展开详细结果、步骤、文件与导出": "Expand detailed results, steps, files and export",
    "作业已启动，正在后台运行。": "Job started and running in the background.",
    "Obsidian notes in this deployment are currently in Chinese. Select a note to view the original text.": "Obsidian notes in this deployment are currently in Chinese. Select a note to view the original text.",
  };
  const I18N_GRAPH = {
    "当前设计任务本身；它连接目标、约束、候选和证据。": "The current design task; it connects goals, constraints, candidates and evidence.",
    "要解决的食品体系，例如面包、酸奶或饮料；不是某个配料。": "The food system to solve, such as bread, yoghurt or a beverage; not an individual ingredient.",
    "蛋白/多肽靶点或体系组分；结构靶点不等于已验证功能。": "A protein/peptide target or system component; a structural target is not a validated function.",
    "小分子、活性成分或候选物。": "A small molecule, active ingredient or candidate.",
    "生物制剂设计中的目标蛋白或分子。": "The target protein or molecule in biologic design.",
    "设计候选；连接配料/保护剂与推理链。": "A design candidate; links ingredients/protectants to the reasoning chain.",
    "配方或设计策略；是决策路径，不是实验证据。": "A formulation or design strategy; it is a decision path, not experimental evidence.",
    "食品配料；其功能与证据来自本地策展数据。": "A food ingredient; its function and evidence come from local curated data.",
    "生物制剂保护剂/辅料；不是活性成分。": "A biologic protectant/excipient; not an active ingredient.",
    "必须满足的约束或验收目标。": "A constraint or acceptance target that must be met.",
    "推理链步骤；表示计算/决策顺序，不等于因果证明。": "A reasoning-chain step; it shows compute/decision order, not causal proof.",
    "具体单元操作步骤；由当前配方模板生成，仍需中试验证。": "A specific unit operation generated by the current formulation template; still requires pilot validation.",
    "加工引起的成分/分子变化预测；来源和置信度逐条保留。": "A predicted processing-induced compositional/molecular change; source and confidence are retained per item.",
    "机制说明节点；用于连接原因与结果，不能替代实测。": "A mechanism-note node linking cause and effect; it cannot replace measurement.",
    "策展文献或证据节点；没有公开链接时会明确标注。": "A curated literature or evidence node; items without public links are marked explicitly.",
    "本地已登记的数据来源及其许可/认证状态。": "A locally registered data source with its licence/authentication status.",
    "本次在线检索实际返回的数据源。": "A data source actually returned by this online search.",
    "在线数据库返回的单条记录；保留原始链接、时间和匹配依据。": "A single record returned by an online database; the original link, time and match basis are retained.",
    "设计约束。": "A design constraint.", "图谱节点。": "Graph node.",
    "设计对象指向要解决的食品体系或生物靶点；不是分子结合证据。": "The design object points to the food system or biological target to solve; this is not molecular-binding evidence.",
    "设计任务选择该候选；表示决策结果。": "The design task selected this candidate; it represents a decision result.",
    "设计任务采用该配方/设计策略。": "The design task adopted this formulation/design strategy.",
    "候选配方使用该配料；边的权重是配方占比。": "The candidate formulation uses this ingredient; edge weight is the formulation share.",
    "候选与保护剂/辅料配伍；边的权重是配方占比。": "The candidate is formulated with this protectant/excipient; edge weight is the formulation share.",
    "两条配料之间的方向性相互作用；证据字符串来自策展规则/文献先验，不是本配方实测。": "A directional interaction between two ingredients; the evidence string comes from curated rules/literature priors, not measurement of this formulation.",
    "配料功能或声明指向一条策展证据。": "An ingredient function or claim points to a curated evidence item.",
    "候选的机制说明；不是独立实验。": "A mechanism note for the candidate; not an independent experiment.",
    "设计约束或验收目标。": "A design constraint or acceptance target.",
    "推理链从设计进入第一步。": "The reasoning chain enters its first step from the design.",
    "推理链顺序；只表示步骤先后，不自动证明因果。": "Reasoning-chain order; it only shows step sequence and does not prove causation.",
    "推理链完成并回到设计对象。": "The reasoning chain completes and returns to the design object.",
    "文本/实体提及关系。": "A text/entity mention relationship.",
    "文献作者关系。": "A literature authorship relationship.",
    "文献发表来源关系。": "A literature publication-source relationship.",
    "在线数据源包含该记录。": "The online data source contains this record.",
    "在线记录可作为候选的外部证据线索；需核对原始记录，不等于已验证。": "The online record is an external evidence lead for the candidate; verify the original record, as this is not validation.",
    "由 UniChem 按 InChIKey 验证的同一化合物映射。": "A same-compound mapping verified by UniChem via InChIKey.",
    "UniProt 记录中的 PDB 交叉引用。": "A PDB cross-reference in a UniProt record.",
    "记录中标注的谱图/数据库参考；不是结构身份验证。": "A spectrum/database reference noted in the record; not structural identity validation.",
    "从推理/设计进入具体单元操作。": "The reasoning/design enters a specific unit operation.",
    "单元操作的先后顺序；不代表因果或充分性。": "Unit-operation sequence; it does not imply causation or sufficiency.",
    "规则/文献先验给出的加工变化预测；必须用实测验证。": "A processing-change prediction from rules/literature priors; must be verified experimentally.",
    "流程/决策关系；只表示软件步骤或选择顺序，不是实验证据。": "A workflow/decision relationship; it only shows software steps or selection order, not experimental evidence.",
    "本地策展条目、配料先验或文献摘录；需回到原始研究核对条件。": "A local curated entry, ingredient prior or literature excerpt; return to the original study to check conditions.",
    "标识符级交叉验证；证明记录指向同一实体，不等于功能或结合验证。": "Identifier-level cross-checking; it shows records point to the same entity, not functional or binding validation.",
    "本次在线检索实际返回的记录；可点击原始链接核对，但未做实验复现。": "A record actually returned by this online search; check the original link, but no experimental replication was done.",
    "数据库参考记录；不是同条件实测，不能单独作为结论依据。": "A database reference record; it is not measurement under the same conditions and cannot support a conclusion alone.",
    "规则/文献先验的计算预测；必须用实测数据验证。": "A computational prediction from rules/literature priors; must be verified with measured data.",
    "来源状态未知；不应作为证据使用。": "Unknown provenance; do not use as evidence.",
    "当前边没有公开引用；这是规则/流程关系，不能当作实验证据。": "This edge has no public citation; it is a rule/workflow relationship, not experimental evidence.",
    "该节点/关系没有附带可公开链接的证据；请把它当作流程或待核对线索。": "This node/relationship has no publicly linked evidence; treat it as workflow or a lead to verify.",
    "流程关系": "Workflow relationship", "本地策展": "Local curation", "标识符级验证": "Identifier-level verification",
    "本次在线记录": "This online record", "参考记录": "Reference record", "模型预测": "Model prediction", "来源未知": "Unknown provenance",
    "节点和边分别是什么意思？": "What do nodes and edges mean?",
    "节点是设计对象、配料、约束、工艺步骤、预测变化或证据记录；颜色表示类型，大小表示连接度。": "Nodes are design objects, ingredients, constraints, process steps, predicted changes or evidence records; colour shows type and size shows degree.",
    "边表示关系；边的中文标签说明语义，点击边可查看其含义、来源、置信度和原始链接。": "Edges represent relationships; edge labels describe the semantics. Click an edge to see its meaning, source, confidence and original link.",
    "工作流边只表示决策/步骤顺序；curated 边是本地文献/规则先验；verified 边是标识符级交叉验证；model 边是机理规则预测，必须实测。": "Workflow edges only show decisions or step order; curated edges are local literature/rule priors; verified edges are identifier-level cross-checks; model edges are mechanistic predictions that require measurement.",
    "每条边都有 evidence_status、basis 和 citations。workflow 只是流程；没有 citations 的非工作流边会显示 caveat。": "Every edge has evidence_status, basis and citations. workflow is only process; non-workflow edges without citations show a caveat.",
    "双击节点打开右侧完整证据；点击“打开来源”才跳转到原始链接。": "Double-click a node to open its full evidence on the right; only Open source jumps to the original link.",
    "拖拽节点会牵拉相连节点 · 滚轮/双指缩放 · 点击聚焦 · 双击打开证据 · 点击边看关系": "Drag a node to pull connected nodes · scroll/pinch to zoom · click to focus · double-click for evidence · click an edge for its relationship",
    "返回在线检索": "Back to online search", "着色": "Colour by",
    "按类型": "Type", "按连接度": "Degree", "按计算状态": "Compute status",
    "数据源/在线记录": "Data sources/online records", "推理链/工艺": "Reasoning/process",
    "适应视图": "Fit view", "重新布局": "Re-layout",
    "点击节点聚焦并查看解释；双击节点打开完整证据；点击边查看关系语义。": "Click a node to focus and read its explanation; double-click for full evidence; click an edge for its relationship semantics.",
    "节点 / 关系图例与定义": "Node / edge legend and definitions",
    "点击展开，再点任一项查看含义": "Expand, then click any item for its meaning",
    "点击节点类型或关系类型，查看定义、来源状态与当前数量。": "Click a node or edge type to see its definition, provenance and current count.",
    "怎么读：": "How to read: ",
    "流程边不是因果；模型边必须实测；在线记录需打开原始链接核对。": "Workflow edges are not causal; model edges require measurement; online records must be checked at the original link.",
    "节点颜色 = 类型；节点大小 = 连接度。图谱由当前设计结果和 curated 数据实时构图；在线记录只有在检索后才会出现。": "Node colour = type; node size = degree. The graph is built live from the current design and curated data; online records appear only after a search.",
    "节点详情": "Node details", "关系详情": "Edge details", "证据与来源": "Evidence and sources",
    "相连节点与关系": "Connected nodes and edges", "打开原始记录 ↗": "Open original record ↗",
    "来源依据：": "Basis: ", "机制/说明：": "Mechanism/note: ", "方向性权重": "Directional weight", "符号": "Sign",
    "这条边的证据": "Evidence for this edge", "两端节点": "Connected nodes", "关系边。": "Relationship edge.",
    "这是流程/工艺步骤，不是外部实验证据；它的作用是把下一步和输入输出讲清楚。": "This is a workflow/process step, not external experimental evidence; it clarifies the next step and its inputs/outputs.",
    "该步骤由当前配方模板生成，没有独立外部证据；请用中试或 QC 验收。": "This step is generated by the current formulation template and has no independent external evidence; validate it in a pilot run or QC.",
    "该节点没有附带的公开证据链接；请核对本地策展来源。": "This node has no public evidence link; check the local curated source.",
    "这是顺序边，不自动证明因果；请查看相邻步骤的详情。": "This is a sequence edge and does not prove causation; check the adjacent steps.",
    "该关系没有附带公开链接；请核对本地策展依据。": "This relationship has no public link; check the local curated basis.",
    "该类型节点表示设计对象或证据线索。": "This node type represents a design object or evidence lead.",
    "每条边都带来源状态；没有引用的边不能当作实验证据。": "Every edge carries a provenance status; an edge without citations is not experimental evidence.",
    "节点是设计对象、配料、工艺步骤或证据记录。": "Nodes are design objects, ingredients, process steps or evidence records.",
    "边是关系；点击边查看语义、来源和置信度。": "Edges are relationships; click an edge to see its semantics, source and confidence.",
    "节点和边分别是什么意思？": "What do nodes and edges mean?",
    "蛋白/多肽": "Protein/peptide", "配体/小分子": "Ligand/small molecule", "水": "Water", "离子": "Ion", "核酸": "Nucleic acid",
    "乳清蛋白与槲皮素": "Whey protein–Quercetin", "乳铁蛋白和非布司他": "Lactoferrin–Febuxostat",
    "设计": "Design", "食品体系": "Food system", "体系": "System", "蛋白": "Protein",
    "小分子": "Small molecule", "生物靶点": "Biological target", "候选": "Candidate", "策略": "Strategy",
    "保护剂": "Protectant", "推理步骤": "Reasoning step", "工艺步骤": "Process step",
    "加工变化预测": "Processing-change prediction", "机制": "Mechanism",
    "数据源": "Data source", "在线源": "Online source", "文献": "Literature",
    "在线记录": "Online record", "节点": "Node", "流程": "Workflow", "策展": "Curated",
    "已验证": "Verified", "模型": "Model", "在线": "Online", "参考": "Reference", "未知": "Unknown",
    "靶向体系": "Targets system", "选择候选": "Selects candidate", "选择策略": "Selects strategy",
    "使用配料": "Uses ingredient", "配伍": "Formulates with", "配料相互作用": "Ingredient interaction",
    "由证据支持": "Supported by evidence", "机制说明": "Mechanism note", "起点": "Start",
    "下一步": "Next", "完成": "Complete", "包含记录": "Contains record", "候选证据": "Candidate evidence",
    "精确结构映射": "Exact structure mapping", "谱图参考": "Spectrum reference",
    "开始工艺": "Starts process", "下一步工艺": "Next process", "预测变化": "Predicts change",
    "提及": "Mentions", "作者": "Author", "发表于": "Published in",
    "占比": "Share", "角色": "Role", "评分": "Score", "详情": "Detail", "许可": "Licence",
    "说明": "Note", "名称": "Name", "满足目标": "Meets target", "宏观影响": "Macro impact",
    "验证建议": "Validation advice", "影响强度": "Impact level", "相关度": "Relevance",
    "证据强度": "Evidence strength", "检索时间": "Retrieved", "匹配依据": "Match basis",
    "原始链接": "Original link", "步骤": "Step", "边界": "Boundary", "置信度": "Confidence",
    "值": "Value", "查询": "Query",
    "HADDOCK3 对接": "HADDOCK3 docking",
    "蛋白-蛋白 · 蛋白-配体 · 蛋白-多糖": "Protein–protein · protein–ligand · protein–polysaccharide",
    "独立 HADDOCK3 作业": "Standalone HADDOCK3 job",
    "体系描述（可选，留空也可按下方字段运行）": "System description (optional; fields below are sufficient)",
    "工作流": "Workflow",
    "蛋白-蛋白": "Protein–protein",
    "蛋白-配体": "Protein–ligand",
    "蛋白-多糖": "Protein–polysaccharide",
    "受体（PDB ID 或名称）": "Receptor (PDB ID or name)",
    "受体链（留空自动）": "Receptor chain (auto if blank)",
    "对接伙伴（蛋白 PDB / 糖链 / 配体名称或 SMILES）": "Partner (protein PDB / glycan / ligand name or SMILES)",
    "伙伴链（配体忽略）": "Partner chain (ignored for ligands)",
    "受体活性残基（逗号/空格/范围）": "Receptor active residues (comma/space/range)",
    "伙伴活性残基（配体填 1）": "Partner active residues (use 1 for ligands)",
    "约束半径 / Å": "Restraint radius / Å",
    "最大约束数": "Max restraints",
    "刚体采样数": "Rigid-body sampling",
    "评分容差": "Score tolerance",
    "精修选取数": "Models selected for refinement",
    "最小簇大小": "Minimum cluster size",
    "输出模型数": "Output models",
    "聚类截断 / Å": "Cluster cutoff / Å",
    "CPU 核数": "CPU cores",
    "随机种子": "Random seed",
    "超时 / s": "Timeout / s",
    "vDW 权重": "vDW weight",
    "静电权重": "Electrostatic weight",
    "分子间刚体权重": "Intermolecular rigid weight",
    "介电常数 ε": "Dielectric constant ε",
    "flexref 刚体步数": "flexref rigid-body steps",
    "flexref cool1 步数": "flexref cool1 steps",
    "flexref 半柔性精修": "flexref semi-flexible refinement",
    "emref 能量最小化": "emref energy minimisation",
    "聚类并选代表模型": "Cluster and select representative models",
    "无活性残基时用 cmrest": "Use cmrest when no active residues",
    "无活性残基时用 ranair": "Use ranair when no active residues",
    "启动 HADDOCK3 作业": "Start HADDOCK3 job",
    "HADDOCK3 · 对接 · MD · QM": "HADDOCK3 · docking · MD · QM",
    "HADDOCK3 / AutoDock Vina / GROMACS / CP2K": "HADDOCK3 / AutoDock Vina / GROMACS / CP2K",
    "默认 20 个刚体采样，运行时间取决于体系与核数；配体需要 RDKit 生成 3D 结构。作业步骤和文件会记录在下方任务卡片。": "Default rigid-body sampling is 20; runtime depends on the system and core count. Ligands require RDKit to generate a 3D structure. Steps and files are recorded in the job card below.",
    "HADDOCK score (a.u.)": "HADDOCK score (a.u.)",
    "簇": "Cluster", "簇大小": "Cluster size", "模型": "Model",
    "无实验参考": "No experimental reference",
    "score": "score",
    "解析 HADDOCK3 受体与伙伴": "Resolve HADDOCK3 receptor and partner",
    "准备 HADDOCK3 结构与约束": "Prepare HADDOCK3 structures and restraints",
    "HADDOCK3 对接与精修": "HADDOCK3 docking and refinement",
    "生成 HADDOCK3 报告": "Generate HADDOCK3 report",
    "1. 原料验收–称量": "1. Raw-material receipt–weighing", "1. 原料验收与称量": "1. Raw-material receipt and weighing", "2. 预处理": "2. Pretreatment",
    "3. 混合/乳化/成型": "3. Mixing/emulsification/forming", "4. 发酵/烘焙": "4. Fermentation/baking",
    "5. 冷却/包装/储存": "5. Cooling/packaging/storage",
    "蛋白质：变性/展开，随后可能聚集或凝胶": "Protein: denaturation/unfolding, followed by possible aggregation or gelation",
    "抗坏血酸：氧化/热降解，营养保留下降": "Ascorbic acid: oxidation/thermal degradation; nutrient retention decreases",
    "不饱和脂质：氧化生成过氧化物、醛酮和异味": "Unsaturated lipids: oxidation produces peroxides, aldehydes/ketones and off-flavours",
    "淀粉：糊化、吸水膨胀和黏度上升": "Starch: gelatinisation, water uptake/swelling and increased viscosity",
    "胶体/稳定剂：水合、凝胶或增稠网络形成": "Colloids/stabilisers: hydration, gelation or thickening-network formation",
  };
  Object.assign(I18N_EN, window.BIOFORGE_I18N_DATA || {}, I18N_BLOCK, I18N_GRAPH);
  const I18N_NUMERIC = window.BIOFORGE_I18N_NUMERIC || {};
  const I18N_TERMS = Object.assign({
    "软面包": "Soft bread", "稳定性优先": "Stability-first", "均衡型": "Balanced", "清洁标签": "Clean label",
    "成本优先": "Cost-first", "感官优先": "Sensory-first", "高蛋白": "High-protein", "低糖": "Low-sugar",
    "低钠": "Low-sodium", "植物基": "Plant-based", "高纤": "High-fiber",
    "被替代、禁用或归一化移除": "replaced, disabled or normalised out",
    "乳铁蛋白": "Lactoferrin", "乳清蛋白": "Whey protein", "尿酸": "Uric acid", "非布司他": "Febuxostat",
    "全部": "all", "代表项": "representative",
    "靶向体系": "Targets system", "选择候选": "Selects candidate", "选择策略": "Selects strategy",
    "使用配料": "Uses ingredient", "配伍": "Formulates with", "配料相互作用": "Ingredient interaction",
    "由证据支持": "Supported by evidence", "机制说明": "Mechanism note", "推理起点": "Start",
    "下一步工艺": "Next process", "下一步": "Next", "返回设计": "Complete",
    "开始工艺": "Starts process", "预测成分变化": "Predicts change",
    "个节点": "nodes", "条边": "edges", "设计": "Design",
    "可直接查询": "Direct query", "API / 解析": "API / resolver", "需许可": "Licence required",
    "机构登录": "Institutional login", "链接入口": "Link only", "公开参考": "Public reference",
    "色素保留率": "Color retention", "膳食纤维下限": "Dietary fibre minimum", "变体": "variant", "热保护剂": "Thermoprotectant", "螯合剂": "Chelator",
    "护色剂": "Color protectant", "保留率": "Retention", "筛选级启发式": "Screening heuristic",
    "加速褪色": "Accelerated fading", "巴氏温度/时间": "pasteurisation temperature/time",
    "光照/氧": "light/oxygen", "海藻糖/柠檬酸盐保护上限": "capped trehalose/citrate protection",
    "柠檬酸盐": "citrate", "生育酚保护上限": "capped tocopherol protection",
    "海藻糖保护上限": "capped trehalose protection", "包装透光和维生素光敏性": "package light transmission and vitamin photosensitivity",
    "筛选级启发式：pH、巴氏温度/时间、柠檬酸、光照/氧，以及海藻糖/柠檬酸盐保护上限": "screening heuristic: pH, pasteurisation temperature/time, citric acid, light/oxygen, and capped trehalose/citrate protection",
    "筛选级启发式：pH、温度、光照/氧，以及海藻糖/柠檬酸盐保护上限": "screening heuristic: pH, temperature, light/oxygen, and capped trehalose/citrate protection",
    "筛选级启发式：温度、光照/氧和生育酚保护上限": "screening heuristic: temperature, light/oxygen and capped tocopherol protection",
    "筛选级启发式：温度、光照/氧和海藻糖保护上限": "screening heuristic: temperature, light/oxygen and capped trehalose protection",
    "筛选级启发式：包装透光和维生素光敏性": "screening heuristic: package light transmission and vitamin photosensitivity",
    "海藻糖可提高藻蓝蛋白的热/储存稳定性，但无法消除酸性褪色。": "Trehalose can improve the thermal/storage stability of phycocyanin but cannot eliminate acid-induced fading.",
    "酸性条件使藻蓝蛋白变性/聚集，蓝色褪去；需 pH 稳定和低温工艺。": "Acidic conditions denature/aggregate phycocyanin and the blue colour fades; pH stabilisation and low-temperature processing are required.",
    "抗坏血酸和光氧化加速藻蓝蛋白褪色。": "Ascorbic acid and photo-oxidation accelerate phycocyanin fading.",
    "强化抗氧化/抑菌/水分活度和热保护，适合长货架期。": "strengthens antioxidant/antimicrobial/water-activity and heat protection for a long shelf life.",
    "在基础模板上补齐关键功能角色，兼顾稳定、感官与成本。": "fills key functional roles on the base template while balancing stability, sensory and cost.",
    "优先天然配料，减少或替换合成添加剂和 E 编号成分。": "prioritises natural ingredients and reduces or replaces synthetic additives and E-number ingredients.",
    "用低成本的成熟原料替代高价原料，同时保留关键工艺控制。": "replaces high-cost ingredients with lower-cost established ingredients while keeping key process controls.",
    "强化脂肪、甜味、鲜味和质构，追求更接近目标产品的口感和风味。": "strengthens fat, sweetness, umami and texture for a closer match to the target product.",
    "增加优质蛋白来源并用水分/胶体平衡质构。": "adds high-quality protein sources and balances texture with water/colloids.",
    "降低可发酵糖和总糖，使用高倍甜味剂/纤维/水分复配。": "reduces fermentable and total sugars using high-intensity sweeteners/fibre/water.",
    "部分替代 NaCl，使用酸、鲜味、香辛料和钾盐补足风味。": "partially replaces NaCl and uses acid, umami, spices and potassium salts for flavour.",
    "去除动物源配料，使用植物蛋白、植物油脂和亲水胶体。": "removes animal-derived ingredients and uses plant proteins, plant fats and hydrocolloids.",
    "增加可溶性/不溶性膳食纤维，兼顾质构和水分。": "increases soluble/insoluble dietary fibre while balancing texture and moisture.",
    "食品体系模板 + 配料酸/缓冲先验": "Food-system template + ingredient acid/buffer priors",
    "配料 aw curated 先验": "Ingredient aw curated prior",
    "curated 食品化学规则": "Curated food-chemistry rules",
    "用户目标/查询优先级 + curated 规则": "User goal/query priority + curated rules",
    "配方质量的": "Formulation mass",
    "来自 USDA FDC SR Legacy，其余为 curated estimate": "from USDA FDC SR Legacy; the rest is curated estimate",
    "满足目标/工艺/质构平衡": "meets target/process/texture balance",
  }, window.BIOFORGE_I18N_TERMS || {});
  const I18N_TERM_LIST = Object.entries(I18N_TERMS).sort((a, b) => b[0].length - a[0].length);
  function applyI18nTerms(value) {
    let out = value;
    for (const [cn, en] of I18N_TERM_LIST) if (out.includes(cn)) out = out.split(cn).join(en);
    return out;
  }
  const I18N_BLOCK_COMPACT = Object.fromEntries(Object.entries(I18N_BLOCK).map(([key, value]) => [key.replace(/\s+/g, ""), value]));
  const I18N_PATTERNS = [
    [/^(\d+) 模型$/, "$1 models"], [/^(\d+) 簇$/, "$1 clusters"],
    [/^(\d+) 个食品体系 · (\d+) 个端到端案例$/, "$1 food systems · $2 end-to-end cases"],
    [/^([\d,]+) 个$/, "$1"],
    [/^([\d,]+) 已生成$/, "$1 generated"],
    [/^([\d,—]+) 条 ·(.*)$/, "$1 items ·$2"],
    [/^([\d,]+) 条$/, "$1 items"],
    [/^正在规划并检索 (.+)$/, "Planning and searching $1"],
    [/^([\d,]+) 个来源$/, "$1 sources"],
    [/^([\d,]+) 篇 · ([\d,]+) 块$/, "$1 papers · $2 chunks"],
    [/^OA ([\d,]+)$/, "OA $1"],
    [/^排名 (.+)$/, "Rank $1"],
    [/^中英文映射：(.+)$/, "Bilingual mapping: $1"],
    [/^检测到蛋白\/靶点词「(.+)」与相互作用词「(.+)」$/, "Protein/target term “$1” and interaction term “$2” detected"],
    [/^检测到蛋白\/酶\/靶点词「(.+)」$/, "Protein/enzyme/target term “$1” detected"],
    [/^检测到食品\/配方词「(.+)」$/, "Food/formulation term “$1” detected"],
    [/^(.+) · 仅链接$/, "$1 · Link only"], [/^(.+) · 本地快照$/, "$1 · Local snapshot"],
    [/^(.+) · 跳过$/, "$1 · Skipped"], [/^(.+) · 错误$/, "$1 · Error"], [/^(.+) · 0 条$/, "$1 · 0 records"],
    [/^高相关 (.+)$/, "High relevance $1"], [/^中相关 (.+)$/, "Medium relevance $1"], [/^低相关 (.+)$/, "Low relevance $1"],
    [/^全文 ([\d,]+)$/, "Full text $1"], [/^实体 ([\d,]+)$/, "Entities $1"], [/^关系 ([\d,]+)$/, "Relations $1"],
    [/^(.*)同一 InChIKey 的精确交叉引用；不是名称匹配。$/, "$1exact cross-reference by identical InChIKey; not a name match."],
    [/^(.*)PubChem 谱图记录中标注的 MassBank accession；为参考链接，不是结构身份验证。$/, "$1MassBank accession referenced by the PubChem spectral record; a reference link, not structural identity verification."],
    [/^(.*)UniProt 记录中的 PDB 交叉引用。$/, "$1PDB cross-reference from the UniProt record."],
    [/^(\d+) 条资源 · 资源库$/, "$1 resources · directory"],
    [/^(\d+) 个节点 · (\d+) 条边$/, "$1 nodes · $2 edges"],
    [/^(\d+) 条显示 \/ 共 (\d+) 条$/, "$1 shown / $2 total"],
    [/^(.+) · 配方 (.+)$/, "$1 · formulation $2"],
    [/^(\d+) 对组合$/, "$1 pairs"],
    [/^(.*) · 本地$/, "$1 · local"],
    [/^只读 · (.+)$/, "Read-only · $1"],
    [/^(\d+) 行$/, "$1 rows"],
    [/^(\d+) 条资源 · 资源库$/, "$1 resources · directory"],
    [/^(\d+) 个训练类别$/, "$1 training classes"],
    [/^训练范围 (.+) – (.+)$/, "Training range $1 – $2"],
    [/^(\d+) 个残基$/, "$1 residues"],
    [/^(\d+) 个组分$/, "$1 components"],
    [/^链 (.+) · 蛋白$/, "Chain $1 · protein"],
    [/^链 (.+) · 核酸$/, "Chain $1 · nucleic acid"],
    [/^(\d+) 个可比较候选$/, "$1 comparable candidates"],
    [/^候选 (\d+)$/, "Candidate $1"],
    [/^证据等级 (.+)$/, "Evidence grade $1"],
    [/^证据 ([A-Za-z]+)$/, "Evidence $1"],
    [/^(\d+) 过敏原$/, "$1 allergens"],
    [/^(\d+) 负向作用$/, "$1 negative interactions"],
    [/^(\d+) 正向作用$/, "$1 positive interactions"],
    [/^以 100 g \/ 100 mL 计 · (\d+) 项配料$/, "Per 100 g / 100 mL · $1 ingredients"],
    [/^配方 · (.+)$/, "Formulation · $1"],
    [/^候选 · (.+)$/, "Candidate · $1"],
    [/^(.+) · 稳定性优先$/, "$1 · Stability priority"],
    [/^(.+) · 清洁标签$/, "$1 · Clean label"],
    [/^(.+) · 成本优先$/, "$1 · Cost priority"],
    [/^(.+) · 感官优先$/, "$1 · Sensory priority"],
    [/^(.+) · 高蛋白$/, "$1 · High protein"],
    [/^(.+) · 低糖$/, "$1 · Low sugar"],
    [/^(.+) · 低钠$/, "$1 · Low sodium"],
    [/^(.+) · 植物基$/, "$1 · Plant-based"],
    [/^(.+) · 均衡型$/, "$1 · Balanced"],
    [/^保护剂组合 · (\d+) 项$/, "Protectant blend · $1 items"],
    [/^综合评分 (.+)$/, "Overall score $1"],
    [/^(\d+) 项配料$/, "$1 ingredients"],
    [/^证据 (\d+) 条$/, "Evidence $1 items"],
    [/^组成：USDA FDC SR Legacy 覆盖 (.+)% 配方质量；(.+) 个配料使用 curated estimate。FDC 是参考数据，不是供应商批次实测。$/, "Composition: USDA FDC SR Legacy covers $1% of formulation mass; $2 ingredients use curated estimates. FDC is reference data, not supplier-batch measurements."],
    [/^组成：USDA FDC SR Legacy 覆盖 (.+)% 配方质量；(.+) 个配料使用 curated estimate。$/, "Composition: USDA FDC SR Legacy covers $1% of formulation mass; $2 ingredients use curated estimates."],
    [/^(\d+) 个策展数据集$/, "$1 curated datasets"],
    [/^(.+)。区间是筛选假设，不是统计置信区间。$/, "$1. Ranges are screening assumptions, not statistical confidence intervals."],
    [/^(.+) · 变体（(.+)→(.+)）$/, "$1 · variant ($3 replaces $2)"],
    [/^以(.+)为基准，用(.+)替代(.+)；用于比较原料选择对指标和约束的影响。$/, "Using $1 as the basis, replace $3 with $2; used to compare how ingredient choice affects metrics and constraints."],
    [/^查询要求色素保留率 ≥ ([\d.]+)%；本引擎仅做筛选级启发式估算，必须用加速褪色或货架期实测确认。$/, "Query requires color retention ≥ $1%; this engine only gives a screening-level heuristic estimate; confirm with accelerated fading or shelf-life testing."],
    [/^色素保留率筛选估算 ([\d.]+)% 低于目标 ([\d.]+)%；需调整 pH\/热处理或保护剂，并以实测为准。$/, "Screening color-retention estimate $1% is below the $2% target; adjust pH/heat treatment or protectants and verify experimentally."],
    [/^色素保留率筛选估算 ([\d.]+)%（目标 ([\d.]+)%）；接近阈值，必须做加速褪色实测。$/, "Screening color-retention estimate $1% (target $2%); close to the threshold, accelerated fading tests are required."],
    [/^色素保留率筛选估算 ([\d.]+)%，目标 ([\d.]+)%；必须实测。$/, "Screening color-retention estimate $1%, target $2%; experimental verification required."],
    [/^色素保留率筛选估算 ([\d.]+)%（(.+)）；不是实测。$/, "Screening color-retention estimate $1% ($2); not measured."],
    [/^推荐策略「(.+)」：综合评分 ([\d.]+)；(.+)$/, "Recommended strategy '$1': composite score $2; $3"],
    [/^识别产品体系：(.+)；生成 (\d+) 个可比较配方，而不是单一答案。$/, "Identified system: $1; generated $2 comparable formulations, not a single answer."],
    [/^关键估算：pH (.+)、aw (.+)、蛋白质 (.+)%、糖 (.+)%、钠 (.+) mg\/100g。$/, "Key estimates: pH $1, aw $2, protein $3%, sugar $4%, sodium $5 mg/100g."],
    [/^([+−]) (.+) × (.+)$/, "$1 $2 × $3"],
    [/^已识别产品体系为 (.+)。$/, "Identified system: $1."],
    [/^组成计算覆盖 (.+)% 的配方质量来自 USDA FDC SR Legacy，其余为 curated estimate。$/, "Composition calculation covers $1% of formulation mass from USDA FDC SR Legacy; the rest is curated estimate."],
    [/^已生成 (\d+) 个候选。$/, "Generated $1 candidates."],
    [/^(\w+) · 策略添加：补足目标功能角色或约束$/, "$1 · strategy addition: fills a target functional role or constraint"],
    [/^water ([\d.]+)% → ([\d.]+)% · 满足目标\/工艺\/质构平衡$/, "water $1% → $2% · meets target/process/texture balance"],
    [/^温度 (.+)$/, "Temperature $1"],
    [/^时间 (.+)$/, "Time $1"],
    [/^热负荷 (.+)$/, "Heat load $1"],
    [/^Evidence (\d+) 条$/, "Evidence $1 items"],
    [/^· 限制 (.+)$/, "· Limit $1"],
    [/^筛选区间 (.+)$/, "Screening range $1"],
    [/^配方质量的 (.+)% 来自 USDA FDC SR Legacy，其余为 curated estimate · (.+)$/, "$1% of formulation mass comes from USDA FDC SR Legacy; the rest is curated estimate · $2"],
    [/^中等影响：酸催化水解为(.+)和(.+)$/, "Medium impact: acid-catalysed hydrolysis to $1 and $2"],
    [/^指纹 (.+) · seed (.+)$/, "Fingerprint $1 · seed $2"],
    [/^3D 轨迹 · (.+)$/, "3D trajectory · $1"],
    [/^(.+)与(.+)的结合$/, "$1–$2 binding"],
    [/^分析(.+)和(.+)$/, "Analyse $1 and $2"],
    [/^分析\s*(.+?)\s*[–-]\s*(.+?)\s+binding$/i, "Analyse $1 – $2 binding"],
    [/^Analyse\s+(.+?)与(.+?)的结合机制[，,]\s*运行对接、短\s*MD\s+and\s+QM$/i, "Analyse $1–$2 binding mechanism; run docking, short MD and QM"],
    [/^高级 (全部|代表项)$/, "Advanced $1"],
    [/^(\d+) 篇 · 只读$/, "$1 notes · read-only"],
    [/^配方 (.+)$/, "formulation $1"],
    [/^([A-Za-z][A-Za-z0-9 .+%\-]*)[与和]([A-Za-z][A-Za-z0-9 .+%\-]*)$/, "$1–$2"],
    [/^HADDOCK (.+)；小分子对接仍默认使用 Vina。$/, "HADDOCK $1; small-molecule docking still defaults to Vina."],
    [/^HADDOCK 未检测到；可填写 haddock3 路径。$/, "HADDOCK not detected; enter the haddock3 path."],
    [/^(.+) 的证据网络$/, "$1 evidence network"],
    [/^(\d+) 节点 · (\d+) 边$/, "$1 nodes · $2 edges"],
    [/^(\d+) 个节点 · (\d+) 条边$/, "$1 nodes · $2 edges"],
    [/^(\d+) 个节点$/, "$1 nodes"],
    [/^(\d+) 条边$/, "$1 edges"],
    [/^(\d+) 条关系$/, "$1 relations"],
    [/^置信度 (.+)$/, "Confidence $1"],
    [/^(.+) · (\d+) 条关系 · 置信度 (.+)$/, "$1 · $2 relations · Confidence $3"],
    [/^(.+) · (\d+) 条关系$/, "$1 · $2 relations"],
    [/^(.+) · (\d+) 个节点$/, "$1 · $2 nodes"],
    [/^(.+) · (\d+) 条边 · (.+)$/, "$1 · $2 edges · $3"],
    [/^(.+) 已聚焦。右侧是完整证据与来源；拖拽该节点会牵拉相连节点。$/, "$1 focused. Full evidence and sources are on the right; dragging this node pulls connected nodes."],
    [/^(.+) 已聚焦。双击可展开完整证据；拖拽该节点会牵拉相连节点。$/, "$1 focused. Double-click for full evidence; dragging this node pulls connected nodes."],
    [/^正在查看关系 (.+)。证据、含义和两端节点在右侧。$/, "Viewing relationship $1. Evidence, meaning and both connected nodes are on the right."],
    [/^(\d+)\. (.+)$/, "$1. $2"],
    [/^手动计算输入: (.+)$/, "Manual compute input: $1"],
    [/^未识别受体。请填写 4 位 PDB ID、蛋白名称或 UniProt 映射；当前本地映射包括 (.+)。不会再用 1BEB 代替。$/, "Receptor not recognised. Enter a 4-character PDB ID, protein name or UniProt mapping; current local mappings: $1. 1BEB is not substituted."],
    [/^未识别配体。请填写配体名称、化合物 ID 或 SMILES；不会再用 quercetin 代替。若只想做蛋白短 MD，请关闭对接\/QM 后另行确认。$/, "Ligand not recognised. Enter a ligand name, compound ID or SMILES; quercetin is not substituted. For protein-only short MD, disable docking/QM and confirm separately."],
    [/^目标蛋白「(.+)」不在本地策展数据库中，无法负责任地生成候选；不会用藻蓝蛋白或其他蛋白替代。请提供 UniProt\/PDB 标识并先导入策展记录，或从已收录的荧光蛋白\/食品蛋白中选择。$/, "Target protein “$1” is not in the local curated database; candidates cannot be generated responsibly and will not be replaced with phycocyanin or another protein. Provide a UniProt/PDB identifier and import a curated record, or choose a listed fluorescent/food protein."],
  ];
  function translateText(value, lang) {
    if (lang !== "en") return null;
    const match = String(value).match(/^(\s*)([\s\S]*?)(\s*)$/);
    const key = match ? match[2] : value;
    let translated = I18N_EN[key] || I18N_TERMS[key];
    if (!translated) {
      const numbers = key.match(/\d+(?:\.\d+)?/g) || [];
      const skeleton = key.replace(/\d+(?:\.\d+)?/g, "\u0001");
      const template = I18N_NUMERIC[skeleton];
      if (template && numbers.length) {
        let index = 0;
        translated = template.replace(/\u0001/g, () => numbers[index++] ?? "");
      }
    }
    if (!translated) {
      for (const [pattern, replacement] of I18N_PATTERNS) {
        if (pattern.test(key)) { translated = key.replace(pattern, replacement); break; }
      }
    }
    if (!translated) {
      const termTranslated = applyI18nTerms(key);
      if (termTranslated !== key) translated = termTranslated;
    }
    if (!translated) return null;
    if (/[\u3400-\u9fff]/.test(translated)) translated = applyI18nTerms(translated);
    return `${match[1]}${translated}${match[3]}`;
  }
  function normalizeI18nKey(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }
  function applyBlockTranslations(lang) {
    $$("[data-i18n-html]").forEach((el) => {
      if (!el.__zhHtml) el.__zhHtml = el.innerHTML;
      const key = normalizeI18nKey(el.textContent);
      el.innerHTML = lang === "en" ? (I18N_HTML[key] || el.__zhHtml) : el.__zhHtml;
      el.dataset.i18nBlock = "1";
    });
    $$(".login-gate [class], .login-gate p, .login-gate li, .modal-card [class], .modal-card p, #resource-popover p, main [class], main p, main li, main h1, main h2, main h3").forEach((el) => {
      if (el.closest("script, style, code, pre, textarea, a, button")) return;
      if (el.querySelector("a, button, input, select, textarea")) return;
      if (el.dataset.i18nBlock === "1") return;
      const key = normalizeI18nKey(el.textContent);
      const translated = I18N_BLOCK[key] || I18N_BLOCK_COMPACT[key.replace(/\s+/g, "")];
      if (!translated) return;
      if (!el.__zhHtml) el.__zhHtml = el.innerHTML;
      if (lang === "en") { el.textContent = translated; el.dataset.i18nBlock = "1"; }
    });
    if (lang === "zh") {
      $$("main [data-i18n-block='1']").forEach((el) => {
        if (el.__zhHtml) el.innerHTML = el.__zhHtml;
        delete el.dataset.i18nBlock;
      });
    }
  }
  function translateSubtree(root) {
    if (state.lang !== "en" || !root) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) translateNode(node, "en");
    root.querySelectorAll("[placeholder], [title], [aria-label]").forEach((el) => translateElementAttributes(el, "en"));
  }
  function translateNode(node, lang) {
    if (!node || node.nodeType !== 3) return;
    const parent = node.parentElement;
    if (!parent || parent.closest("script, style, code, pre, textarea, [data-i18n-block='1']")) return;
    if (lang === "en") {
      if (node.__zhText == null) node.__zhText = node.nodeValue;
      const translated = translateText(node.__zhText, lang);
      if (translated != null && node.nodeValue !== translated) node.nodeValue = translated;
    } else if (node.__zhText != null) {
      if (node.nodeValue !== node.__zhText) node.nodeValue = node.__zhText;
    }
  }
  function translateElementAttributes(el, lang) {
    if (!el || el.nodeType !== 1) return;
    ["placeholder", "title", "aria-label"].forEach((attr) => {
      if (!el.hasAttribute(attr)) return;
      const store = el.__zhAttrs || (el.__zhAttrs = {});
      if (lang === "en") {
        if (store[attr] == null) store[attr] = el.getAttribute(attr);
        const translated = translateText(store[attr], lang);
        if (translated != null) el.setAttribute(attr, translated);
      } else if (store[attr] != null) {
        el.setAttribute(attr, store[attr]);
      }
    });
  }
  function applyLanguage(lang) {
    state.lang = lang === "en" ? "en" : "zh";
    document.documentElement.lang = state.lang === "en" ? "en" : "zh-CN";
    const btn = $("#lang-btn");
    if (btn) { btn.textContent = state.lang === "en" ? "ZH" : "EN"; btn.title = state.lang === "en" ? "切换到中文" : "Switch to English"; }
    const tokenBox = $(".token-box");
    if (tokenBox) tokenBox.textContent = state.lang === "en" ? "Authorization: Bearer <contents of runtime/.token>" : "Authorization: Bearer <runtime/.token 内容>";
    if (state.cases.length) renderCases();
    if (state.resources) { renderResources(); renderResourcePopover(); }
    if (state.design) renderDesign();
    if (state.jobs.length) renderJobs(state.jobs);
    applyBlockTranslations(state.lang);
    if (state.lang === "en") {
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      let node;
      while ((node = walker.nextNode())) translateNode(node, "en");
      $$("[placeholder], [title], [aria-label]").forEach((el) => translateElementAttributes(el, "en"));
    } else {
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      let node;
      while ((node = walker.nextNode())) translateNode(node, "zh");
      $$("[placeholder], [title], [aria-label]").forEach((el) => translateElementAttributes(el, "zh"));
    }
    updateThemeUi();
    try { localStorage.setItem("bioforge-lang", state.lang); } catch { /* ignore */ }
    document.title = state.lang === "en" ? "BioForge Studio · Explainable food and biologic design" : "BioForge Studio · 可解释的食品与生物设计";
  }
  function makeGuideCollapsible() {
    $$(".guide-section").forEach((section) => {
      if (section.tagName === "DETAILS") return;
      const heading = section.querySelector("h3");
      if (!heading) return;
      const details = document.createElement("details");
      details.className = section.className;
      details.id = section.id;
      details.open = section.id === "guide-start";
      const summary = document.createElement("summary");
      heading.remove();
      summary.appendChild(heading);
      details.appendChild(summary);
      while (section.firstChild) details.appendChild(section.firstChild);
      section.replaceWith(details);
    });
  }

  function initLanguage() {
    let lang = "zh";
    try { lang = new URLSearchParams(location.search).get("lang") || localStorage.getItem("bioforge-lang") || "zh"; } catch { /* ignore */ }
    applyLanguage(lang);
    $("#lang-btn")?.addEventListener("click", () => applyLanguage(state.lang === "en" ? "zh" : "en"));
    const observer = new MutationObserver((mutations) => {
      if (state.lang !== "en") return;
      mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((node) => {
          if (node.nodeType === 3) translateNode(node, "en");
          else if (node.nodeType === 1) {
            const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
            let child;
            while ((child = walker.nextNode())) translateNode(child, "en");
            if (node.matches?.("[placeholder], [title], [aria-label]")) translateElementAttributes(node, "en");
            node.querySelectorAll?.("[placeholder], [title], [aria-label]").forEach((el) => translateElementAttributes(el, "en"));
          }
        });
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  async function init() {
    initTheme();
    makeGuideCollapsible();
    modeButtons();
    $$(".nav-item, .mobile-tabs button").forEach((b) => b.addEventListener("click", () => setPage(b.dataset.page)));
    $("#menu-btn")?.addEventListener("click", (e) => { e.stopPropagation(); $(".sidebar")?.classList.toggle("open"); });
    document.addEventListener("pointerdown", (e) => {
      if (!$(".sidebar")?.classList.contains("open")) return;
      if (e.target.closest(".sidebar, #menu-btn")) return;
      $(".sidebar")?.classList.remove("open");
    });
    $("#design-form").addEventListener("submit", submitDesign);
    $$("#quick-prompts .chip").forEach((c) => c.addEventListener("click", () => { $("#design-query").value = c.dataset.q; submitDesign(); }));
    $("#login-form").addEventListener("submit", login);
    $("#logout-btn")?.addEventListener("click", logout);
    $("#account-btn")?.addEventListener("click", () => setPage("settings"));
    $("#resource-chip")?.addEventListener("click", (event) => {
      event.stopPropagation();
      const box = $("#resource-popover");
      if (box?.classList.contains("hidden")) openResourcePopover(); else closeResourcePopover();
    });
    $("#resource-popover-close")?.addEventListener("click", closeResourcePopover);
    $("#resource-popover")?.addEventListener("click", (event) => event.stopPropagation());
    $("#resource-open-page")?.addEventListener("click", () => { closeResourcePopover(); setPage("resources"); });
    document.addEventListener("pointerdown", (event) => {
      if ($("#resource-popover")?.classList.contains("hidden")) return;
      if (event.target.closest("#resource-popover, #resource-chip")) return;
      closeResourcePopover();
    });
    document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeResourcePopover(); });
    $("#resource-filters")?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-filter]");
      if (!button) return;
      state.resourceFilter = button.dataset.filter;
      $$("#resource-filters button").forEach((item) => item.classList.toggle("active", item === button));
      renderResources();
    });
    $("#resource-search")?.addEventListener("input", (event) => { state.resourceQuery = event.target.value.trim(); renderResources(); });
    $("#identifier-form")?.addEventListener("submit", resolveIdentifier);
    $("#knowledge-refresh")?.addEventListener("click", loadKnowledgeStatus);
    $("#institution-help")?.addEventListener("click", () => $("#institution-modal")?.classList.remove("hidden"));
    $("#institution-modal-close")?.addEventListener("click", () => $("#institution-modal")?.classList.add("hidden"));
    $("#institution-modal")?.addEventListener("click", (event) => {
      if (event.target === $("#institution-modal")) $("#institution-modal").classList.add("hidden");
    });
    $("#password-form")?.addEventListener("submit", changePassword);
    $("#server-settings-btn")?.addEventListener("click", () => window.AndroidBridge?.openServerSettings());
    $("#native-server-btn")?.addEventListener("click", () => window.AndroidBridge?.openServerSettings());
    refreshNativeServer();
    $("#graph-btn")?.addEventListener("click", graphDesign);
    $("#compute-btn")?.addEventListener("click", () => state.design && useCompute(state.design));
    $("#evidence-form")?.addEventListener("submit", (e) => { e.preventDefault(); runEvidence(); });
    $("#lit-form")?.addEventListener("submit", searchLiterature);
    $("#help-btn")?.addEventListener("click", () => setPage("guide"));
    $("#compute-form")?.addEventListener("submit", submitCompute);
    $("#haddock-form")?.addEventListener("submit", submitHaddock);
    $("#haddock-reset")?.addEventListener("click", resetHaddock);
    $("#haddock-open")?.addEventListener("click", () => {
      const panel = $("#haddock-panel");
      if (!panel) return;
      panel.open = true;
      panel.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    $("#haddock-workflow")?.addEventListener("change", updateHaddockHints);
    updateHaddockHints();
    $("#params-reset")?.addEventListener("click", resetParams);
    $("#tool-save")?.addEventListener("click", saveTools);
    $("#tool-panel")?.addEventListener("toggle", (e) => { if (e.target.open && !state.tools) loadTools(); });
    $("#structure-form")?.addEventListener("submit", (e) => {
      e.preventDefault();
      const id = $("#structure-pdb").value.trim().toUpperCase();
      if (!/^[0-9A-Z]{4}$/.test(id)) { toast("请输入 4 位 PDB ID。"); return; }
      moleculeViewer.loadUrl(`/api/v3/structure/${encodeURIComponent(id)}`, `PDB ${id}`);
    });
    $("#jobs-expand-all")?.addEventListener("click", () => {
      $$("#jobs-list details.job").forEach((item) => {
        item.open = true;
        item.querySelectorAll("details.job-detail").forEach((detail) => { detail.open = true; });
      });
    });
    $("#jobs-collapse-all")?.addEventListener("click", () => {
      $$("#jobs-list details.job").forEach((item) => {
        item.open = false;
        item.querySelectorAll("details.job-detail").forEach((detail) => { detail.open = false; });
      });
    });
    $("#jobs-list")?.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-pdb-url]");
      if (btn) {
        moleculeViewer.loadUrl(btn.dataset.pdbUrl, btn.dataset.pdbLabel || "structure");
        $("#structure-card")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
      const trajBtn = e.target.closest("[data-traj-url]");
      if (trajBtn) {
        trajBtn.disabled = true;
        toast("正在把 XTC 轨迹转换为多帧 PDB，首次转换可能需要几十秒…");
        moleculeViewer.loadUrl(trajBtn.dataset.trajUrl, trajBtn.dataset.pdbLabel || "trajectory")
          .finally(() => { trajBtn.disabled = false; });
        $("#structure-card")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
      const exportBtn = e.target.closest("[data-export-job]");
      if (exportBtn) exportJob(state.jobs.find((job) => job.id === exportBtn.dataset.jobId), exportBtn.dataset.exportJob);
    });
    swipe();
    initAssistantAndNotes();
    initLanguage();
    if ("serviceWorker" in navigator && /^https?:$/.test(location.protocol)) {
      navigator.serviceWorker.register("sw.js").catch(() => {});
    }
    try {
      const me = await api("/api/auth/me");
      state.me = me.user;
      showApp();
      await bootData();
    } catch (err) {
      if (err.message !== "unauthorized") {
        const offline = err instanceof TypeError || /fetch|network|failed/i.test(err.message || "");
        showLogin(offline ? "无法连接服务器：请确认电脑服务已启动、手机与电脑在同一 Wi-Fi，并修改服务器地址。" : err.message);
      }
    }
  }

  init();
})();
