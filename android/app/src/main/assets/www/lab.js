(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (v, digits = 2) => (v == null || Number.isNaN(Number(v)) ? "—" : Number(v).toLocaleString("zh-CN", { maximumFractionDigits: digits }));
  const int = (v) => (v == null || Number.isNaN(Number(v)) ? "—" : String(Math.round(Number(v))));
  const dateText = (v) => (v ? String(v).slice(0, 16).replace("T", " ") : "—");

  const SOURCE = {
    measured: ["实测", "ok"],
    literature: ["文献", "blue"],
    simulation: ["模拟", "warn"],
    synthetic: ["合成", "warn"],
    mixed: ["混合", "warn"],
  };
  const CONFIDENCE = { high: ["高置信", "ok"], medium: ["中置信", "warn"], low: ["低置信", "no"] };
  const ALGORITHM = {
    ridge: "Ridge",
    random_forest: "随机森林",
    gradient_boosting: "梯度提升",
    gaussian_process: "高斯过程",
    ensemble: "集成",
    auto: "自动",
  };

  const state = {
    loaded: false,
    loading: false,
    datasets: [],
    models: [],
    overview: null,
    dataset: null,
    trainResult: null,
    optimize: null,
    modelDetail: null,
    trainKey: "",
    trainDatasetId: "",
    features: new Set(),
    feedback: null,
    modal: null,
  };

  function sourceBadge(type) {
    const [label, cls] = SOURCE[type] || [type || "未知", ""];
    return `<span class="badge ${cls}">${esc(label)}</span>`;
  }

  function confidenceBadge(value) {
    const [label, cls] = CONFIDENCE[value] || ["—", ""];
    return `<span class="badge ${cls}">${esc(label)}</span>`;
  }

  function guard(err) {
    if (err?.message !== "unauthorized") window.bioforge.toast(err?.message || String(err));
  }

  function columnsOf(dataset) {
    return dataset?.schema?.columns || [];
  }

  function needSynthetic(dataset) {
    return ["synthetic", "mixed"].includes(dataset?.source_type);
  }

  function validFeatureColumns(dataset, target) {
    return columnsOf(dataset).filter((column) => {
      if (column.name === target) return false;
      if (column.role === "identifier") return false;
      if (!["numeric", "categorical"].includes(column.type)) return false;
      if (column.type === "categorical" && Number(column.unique) > 60) return false;
      return true;
    });
  }

  function defaultFeatureNames(dataset, target) {
    const columns = validFeatureColumns(dataset, target);
    const candidates = new Set((dataset?.feature_candidates || []).filter((name) => name !== target));
    const chosen = candidates.size ? columns.filter((column) => candidates.has(column.name)) : columns;
    return chosen.filter((column) => !column.leakage_risk).map((column) => column.name);
  }

  function cell(value, limit = 32) {
    if (value == null || value === "") return '<span class="muted">—</span>';
    const text = String(value);
    return esc(text.length > limit ? `${text.slice(0, limit)}…` : text);
  }

  function table(headers, rows, className = "") {
    return `<div class="table-wrap"><table class="lab-table ${className}">
      <thead><tr>${headers.map((header) => `<th>${esc(header)}</th>`).join("")}</tr></thead>
      <tbody>${rows.map((row) => `<tr>${row.map((value) => `<td>${value}</td>`).join("")}</tr>`).join("")}</tbody>
    </table></div>`;
  }

  async function fetchAll() {
    const [overview, datasets, models] = await Promise.all([
      window.bioforge.api("/api/v3/lab/overview"),
      window.bioforge.api("/api/v3/lab/datasets"),
      window.bioforge.api("/api/v3/lab/models"),
    ]);
    state.overview = overview;
    state.datasets = datasets.items || [];
    state.models = models.items || [];
    renderStats();
    renderDatasets();
    renderModels();
    populateSelectors();
  }

  function renderStats() {
    const box = $("#lab-stats");
    if (!box) return;
    const overview = state.overview || {};
    const demo = overview.demo || {};
    box.innerHTML = [
      ["数据集", int(overview.datasets), "独立哈希与来源标记"],
      ["模型", int(overview.models), "可追溯 artifact"],
      ["优化批次", int(overview.runs), "候选可导出 CSV"],
      ["演示数据", demo.rows ? `${demo.rows} 行` : "—", demo.sha256 ? demo.sha256.slice(0, 12) : "合成流程数据"],
    ].map(([label, value, note]) => `<div class="lab-stat"><span>${esc(label)}</span><b>${esc(value)}</b><small>${esc(note)}</small></div>`).join("");
  }

  function renderDatasets() {
    const box = $("#lab-dataset-list");
    if (!box) return;
    const count = $("#lab-dataset-count");
    if (count) count.textContent = String(state.datasets.length);
    if (!state.datasets.length) {
      box.innerHTML = `<div class="lab-empty"><b>还没有数据集</b><span>载入 180 行演示数据，或导入 CSV / JSON。</span></div>`;
      return;
    }
    box.innerHTML = state.datasets.map((dataset) => {
      const active = state.dataset?.id === dataset.id;
      const columns = columnsOf(dataset);
      return `<div class="lab-dataset-item ${active ? "active" : ""}" data-lab-dataset="${esc(dataset.id)}" role="button" tabindex="0">
        <div class="lab-dataset-top">
          <div class="lab-dataset-title"><b>${esc(dataset.name)}</b>${sourceBadge(dataset.source_type)}${dataset.is_demo ? '<span class="badge">内置</span>' : ""}</div>
          <button class="lab-delete" type="button" data-lab-delete-dataset="${esc(dataset.id)}" title="删除数据集">×</button>
        </div>
        <div class="lab-dataset-meta">
          <span>${int(dataset.row_count)} 行</span>
          <span>${columns.length ? `${int(columns.length)} 列` : `${int((dataset.feature_candidates || []).length)} 特征`}</span>
          <span>${esc(dataset.hash_short || (dataset.hash || "").slice(0, 12))}</span>
        </div>
        <div class="lab-dataset-foot">
          <span>${esc(dateText(dataset.updated_utc || dataset.created_utc))}</span>
          <span>${int((dataset.feature_candidates || []).length)} 个默认特征</span>
        </div>
      </div>`;
    }).join("");
  }

  async function selectDataset(id, options = {}) {
    if (!id) return;
    try {
      const dataset = await window.bioforge.api(`/api/v3/lab/datasets/${encodeURIComponent(id)}`);
      const changed = state.dataset?.id !== dataset.id;
      state.dataset = dataset;
      state.datasets = state.datasets.map((item) => (item.id === dataset.id ? { ...item, ...dataset } : item));
      renderDatasets();
      renderDatasetDetail();
      populateSelectors();
      fillTrainForm(dataset);
      renderFeedback();
      if (changed) {
        state.trainResult = null;
        state.optimize = null;
        state.feedback = null;
        renderTrainResult(null);
        renderOptimize(null);
      }
      if (!options.silent) $("#lab-train-btn")?.focus({ preventScroll: true });
    } catch (err) {
      guard(err);
    }
  }

  function renderDatasetDetail() {
    const box = $("#lab-dataset-detail");
    if (!box) return;
    const dataset = state.dataset;
    if (!dataset) {
      box.innerHTML = `<div class="empty card lab-empty-card"><h3>选择一个数据集</h3><p>查看列类型、默认特征、目标候选和训练就绪状态。</p></div>`;
      return;
    }
    const columns = columnsOf(dataset);
    const warnings = dataset.warnings || [];
    const training = dataset.training || {};
    const readyLabel = !training.allowed ? "缺少数值目标" : !training.min_rows_met ? "行数不足" : training.needs_synthetic_opt_in ? "需确认合成数据" : "可训练";
    const readyClass = training.allowed && training.min_rows_met ? (training.needs_synthetic_opt_in ? "warn" : "ok") : "no";
    const schemaRows = columns.map((column) => [
      `<b>${esc(column.name)}</b>`,
      `<span class="badge ${column.type === "numeric" ? "blue" : ""}">${esc(column.type)}</span>`,
      `<span class="muted">${esc(column.role || "")}</span>`,
      `${((column.missing_rate || 0) * 100).toFixed(1)}%`,
      int(column.unique),
      column.default_feature ? '<span class="badge ok">默认</span>' : column.leakage_risk ? '<span class="badge warn">泄漏风险</span>' : '<span class="muted">—</span>',
    ]);
    const names = columns.slice(0, 10).map((column) => column.name);
    const previewRows = (dataset.preview || []).map((row) => [
      ...names.map((name) => cell(row[name])),
      `<span class="muted">${esc(row._source || "import")}</span>`,
    ]);
    const featureChips = (dataset.feature_candidates || []).map((name) => `<span class="lab-chip plain">${esc(name)}</span>`).join("");
    const targetChips = (dataset.target_candidates || []).map((name) => `<span class="lab-chip target plain">${esc(name)}</span>`).join("");
    box.innerHTML = `<div class="card lab-card lab-dataset-detail">
      <div class="lab-detail-head">
        <div>
          <div class="lab-dataset-title"><h3>${esc(dataset.name)}</h3>${sourceBadge(dataset.source_type)}${dataset.is_demo ? '<span class="badge">内置演示</span>' : ""}</div>
          <p class="muted">${esc(dataset.description || "无说明")} · 更新 ${esc(dateText(dataset.updated_utc))} · SHA ${esc(dataset.hash_short)}</p>
        </div>
        <div class="lab-actions compact">
          <button class="btn primary" id="lab-detail-train" type="button">用于训练</button>
          <a class="btn ghost" id="lab-detail-export" href="/api/v3/lab/datasets/${encodeURIComponent(dataset.id)}/csv" data-lab-download data-filename="bioforge-${esc(dataset.id)}.csv">导出 CSV</a>
          <button class="btn ghost danger" id="lab-detail-delete" type="button">删除</button>
        </div>
      </div>
      <div class="lab-detail-stats">
        <div><span>行数</span><b>${int(dataset.row_count)}</b></div>
        <div><span>列数</span><b>${int(columns.length)}</b></div>
        <div><span>默认特征</span><b>${int((dataset.feature_candidates || []).length)}</b></div>
        <div><span>数值目标候选</span><b>${int((dataset.target_candidates || []).length)}</b></div>
        <div><span>训练就绪</span><b><span class="badge ${readyClass}">${esc(readyLabel)}</span></b></div>
      </div>
      ${warnings.length ? `<div class="lab-warnings">${warnings.map((warning) => `<p>${esc(warning)}</p>`).join("")}</div>` : ""}
      <div class="lab-schema-block">
        <div class="lab-subhead"><h4>列与角色</h4><span class="fineprint">outcome 列默认不进入特征；仍可手工强制选择，但会触发泄漏警告。</span></div>
        ${table(["列", "类型", "角色", "缺失", "唯一值", "默认"], schemaRows)}
      </div>
      <div class="lab-chip-row"><span class="fineprint">目标候选</span>${targetChips || '<span class="muted">无</span>'}</div>
      <div class="lab-chip-row"><span class="fineprint">默认特征</span>${featureChips || '<span class="muted">无</span>'}</div>
      <div class="lab-subhead"><h4>数据预览</h4><span class="fineprint">前 8 行 · 最多显示 10 列</span></div>
      ${table([...names, "来源"], previewRows)}
      <p class="fineprint">${esc(training.reasons?.length ? `训练限制：${training.reasons.join("；")}` : "训练前仍应检查单位、批次、缺失机制和实验设计。")}</p>
    </div>`;
    $("#lab-detail-train")?.addEventListener("click", () => {
      setTab("train");
      fillTrainForm(state.dataset);
    });
    $("#lab-detail-delete")?.addEventListener("click", async (event) => {
      const button = event.currentTarget;
      if (button.dataset.confirm !== "1") {
        button.dataset.confirm = "1";
        button.textContent = "再点一次删除";
        window.setTimeout(() => {
          if (button.isConnected) {
            button.dataset.confirm = "";
            button.textContent = "删除";
          }
        }, 4000);
        return;
      }
      await deleteDataset(dataset.id);
    });
  }

  function populateSelectors() {
    const options = state.datasets.map((dataset) => `<option value="${esc(dataset.id)}">${esc(dataset.name)} · ${int(dataset.row_count)} 行</option>`).join("");
    ["#lab-train-dataset", "#lab-fb-dataset"].forEach((selector) => {
      const select = $(selector);
      if (!select) return;
      const previous = state.dataset?.id || select.value;
      select.innerHTML = options || '<option value="">暂无数据集</option>';
      if (state.datasets.some((dataset) => dataset.id === previous)) select.value = previous;
      else if (state.datasets[0]) select.value = state.datasets[0].id;
    });
    const modelOptions = state.models.map((model) => {
      const r2 = model.metrics?.r2 == null ? "—" : Number(model.metrics.r2).toFixed(3);
      return `<option value="${esc(model.id)}">${esc(model.target)} · ${esc(ALGORITHM[model.resolved_algorithm] || model.resolved_algorithm)} · R² ${r2}</option>`;
    }).join("");
    ["#lab-opt-model", "#lab-fb-model"].forEach((selector) => {
      const select = $(selector);
      if (!select) return;
      const previous = select.value;
      select.innerHTML = modelOptions || '<option value="">暂无模型</option>';
      if (state.models.some((model) => model.id === previous)) select.value = previous;
      else if (state.models[0]) select.value = state.models[0].id;
    });
  }

  function fillTrainForm(dataset) {
    if (!dataset) return;
    const select = $("#lab-train-dataset");
    if (select) select.value = dataset.id;
    const targets = dataset.target_candidates || [];
    const targetSelect = $("#lab-train-target");
    if (!targetSelect) return;
    if (!targets.length) {
      targetSelect.innerHTML = '<option value="">没有数值目标</option>';
      state.trainKey = "";
      state.features = new Set();
      $("#lab-feature-list").innerHTML = '<div class="lab-empty"><b>没有可训练目标</b><span>目标列必须是数值型，且至少有 5 个有效值。</span></div>';
      $("#lab-train-btn").disabled = true;
      $("#lab-train-dataset-badge").textContent = "不可训练";
      return;
    }
    const desired = targets.includes(state.trainKey.split("|")[1]) ? state.trainKey.split("|")[1] : targets.includes("stability_days") ? "stability_days" : targets[0];
    targetSelect.innerHTML = targets.map((name) => `<option value="${esc(name)}">${esc(name)}</option>`).join("");
    targetSelect.value = desired;
    const groupSelect = $("#lab-train-group");
    if (groupSelect) {
      const groups = columnsOf(dataset).filter((column) => column.type === "categorical" && Number(column.unique) <= 60 && column.name !== desired);
      const previous = groupSelect.value;
      groupSelect.innerHTML = '<option value="">不分组</option>' + groups.map((column) => `<option value="${esc(column.name)}">${esc(column.name)}</option>`).join("");
      if (groups.some((column) => column.name === previous)) groupSelect.value = previous;
      else groupSelect.value = "";
    }
    const synthetic = $("#lab-train-synthetic");
    if (synthetic && state.trainDatasetId !== dataset.id) synthetic.checked = false;
    state.trainDatasetId = dataset.id;
    $("#lab-train-btn").disabled = !(dataset.training?.min_rows_met !== false);
    $("#lab-train-dataset-badge").textContent = needSynthetic(dataset) ? "合成/混合：需勾选确认" : `${dataset.name} · ${int(dataset.row_count)} 行`;
    renderFeatureList(dataset, desired);
  }

  function renderFeatureList(dataset, target) {
    const box = $("#lab-feature-list");
    if (!box || !dataset) return;
    const columns = validFeatureColumns(dataset, target);
    const key = `${dataset.id}|${target}`;
    if (state.trainKey !== key) {
      state.trainKey = key;
      state.features = new Set(defaultFeatureNames(dataset, target));
    }
    const validNames = new Set(columns.map((column) => column.name));
    state.features = new Set([...state.features].filter((name) => validNames.has(name) && name !== target));
    if (!state.features.size && columns.length) state.features = new Set(defaultFeatureNames(dataset, target));
    if (!columns.length) {
      box.innerHTML = '<div class="lab-empty"><b>没有可用特征</b><span>需要数值或低基数类别列；文本/标识符不能直接训练。</span></div>';
      return;
    }
    box.innerHTML = columns.map((column) => {
      const checked = state.features.has(column.name);
      const leak = Boolean(column.leakage_risk);
      const type = column.type === "numeric" ? "数值" : `${int(column.unique)} 类`;
      const extra = leak ? " · 可能是结果列" : "";
      return `<label class="feature-item ${leak ? "leak" : ""}">
        <input type="checkbox" data-feature-name="${esc(column.name)}" ${checked ? "checked" : ""}>
        <span><b>${esc(column.name)}</b><small>${esc(type)} · 缺失 ${((column.missing_rate || 0) * 100).toFixed(1)}%${esc(extra)}</small></span>
      </label>`;
    }).join("");
    $$("#lab-feature-list input[type=checkbox]").forEach((input) => {
      input.addEventListener("change", () => {
        if (input.checked) state.features.add(input.dataset.featureName);
        else state.features.delete(input.dataset.featureName);
      });
    });
  }

  function renderModels() {
    const box = $("#lab-model-list");
    if (!box) return;
    if ($("#lab-model-count")) $("#lab-model-count").textContent = String(state.models.length);
    if (!state.models.length) {
      box.innerHTML = `<div class="lab-empty"><b>还没有模型</b><span>导入数据后选择目标列与特征，训练第一个小模型。</span></div>`;
      return;
    }
    box.innerHTML = state.models.map((model) => {
      const metrics = model.metrics || {};
      const source = model.dataset?.source_type || "unknown";
      return `<details class="lab-model-item">
        <summary class="lab-model-head">
          <div><b>${esc(model.target)}</b><span class="badge blue">${esc(ALGORITHM[model.resolved_algorithm] || model.resolved_algorithm)}</span>${sourceBadge(source)}</div>
          <span class="fineprint">v${esc(model.version)} · ${esc(dateText(model.created_utc))} · R² ${num(metrics.r2, 3)}</span>
        </summary>
        <div class="lab-model-metrics">
          <span>R² <b>${num(metrics.r2, 3)}</b></span>
          <span>MAE <b>${num(metrics.mae, 2)}</b></span>
          <span>RMSE <b>${num(metrics.rmse, 2)}</b></span>
          <span>n <b>${int(model.n_samples)}</b></span>
        </div>
        <div class="lab-model-foot">
          <span class="muted">${esc(model.dataset?.name || model.dataset_id)} · ${esc(model.dataset_id || "")}</span>
          <span class="lab-actions compact">
            <button class="btn ghost small" type="button" data-lab-model-detail="${esc(model.id)}">详情</button>
            <button class="btn dark small" type="button" data-lab-use-model="${esc(model.id)}">用于优化</button>
          </span>
        </div>
      </details>`;
    }).join("");
  }

  async function loadModel(id) {
    const response = await window.bioforge.api(`/api/v3/lab/models/${encodeURIComponent(id)}`);
    state.modelDetail = response.model;
    return response.model;
  }

  async function useModel(id) {
    try {
      const card = await loadModel(id);
      const select = $("#lab-opt-model");
      if (select) select.value = id;
      renderSpace(card);
      setTab("optimize");
    } catch (err) {
      guard(err);
    }
  }

  async function showModelDetail(id) {
    try {
      const card = await loadModel(id);
      state.trainResult = card;
      renderTrainResult(card);
      setTab("train");
      $("#lab-train-result")?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      guard(err);
    }
  }

  function renderTrainResult(card) {
    const box = $("#lab-train-result");
    if (!box) return;
    if (!card) {
      box.innerHTML = "";
      return;
    }
    const metrics = card.metrics || {};
    const warnings = card.warnings || [];
    const caveats = card.caveats || [];
    const importance = card.feature_importance || [];
    const parity = card.parity || [];
    const leakage = card.leakage_risk_features || [];
    box.innerHTML = `<div class="card lab-card lab-train-result">
      <div class="lab-card-head">
        <div><span class="eyebrow">TRAINED MODEL</span><h3>${esc(card.target)}</h3><p class="muted">${esc(card.model_id)} · ${esc(card.model_version)} · ${esc(ALGORITHM[card.algorithm_resolved] || card.algorithm_resolved)}</p></div>
        <div class="lab-actions compact"><button class="btn primary" type="button" data-lab-use-model="${esc(card.model_id)}">用于贝叶斯优化</button></div>
      </div>
      <div class="lab-metrics">
        <div><span>R²</span><b>${num(metrics.r2, 3)}</b></div>
        <div><span>MAE</span><b>${num(metrics.mae, 2)}</b></div>
        <div><span>RMSE</span><b>${num(metrics.rmse, 2)}</b></div>
        <div><span>Baseline MAE</span><b>${num(metrics.baseline_mae, 2)}</b></div>
        <div><span>样本</span><b>${int(metrics.n)}</b></div>
        <div><span>特征</span><b>${int(metrics.n_features)}</b></div>
      </div>
      <div class="lab-chart-grid">
        <div class="lab-chart">
          <div class="lab-subhead"><h4>OOF 预测 vs 实测</h4><span class="fineprint">交叉验证外推预测</span></div>
          ${scatterSVG(parity, card.target)}
        </div>
        <div class="lab-chart">
          <div class="lab-subhead"><h4>置换重要性</h4><span class="fineprint">ΔMAE，越高越重要</span></div>
          ${barsHTML(importance)}
        </div>
      </div>
      <div class="lab-meta-grid">
        <div><span>数据来源</span><b>${sourceBadge(card.dataset?.source_type)} ${esc(card.dataset?.name || "")}</b></div>
        <div><span>交叉验证</span><b>${esc(card.cv?.scheme || "—")} · ${int(card.cv?.folds)} 折${card.cv?.group_column ? ` · 分组 ${esc(card.cv.group_column)}` : ""}</b></div>
        <div><span>特征</span><b>${int(card.n_features)} 个</b></div>
        <div><span>数据集哈希</span><b class="mono">${esc((card.dataset?.hash || "").slice(0, 16))}</b></div>
      </div>
      ${leakage.length ? `<div class="lab-warnings strong"><p>数据泄漏风险特征：${leakage.map(esc).join("、")}。这些列可能是同批实验结果，不能用于真实预测。</p></div>` : ""}
      ${warnings.length ? `<div class="lab-warnings">${warnings.map((warning) => `<p>${esc(warning)}</p>`).join("")}</div>` : ""}
      <details class="lab-caveats"><summary>模型边界与假设</summary><ul>${caveats.map((caveat) => `<li>${esc(caveat)}</li>`).join("")}</ul></details>
    </div>`;
  }

  function scatterSVG(points, target) {
    if (!points?.length) return '<div class="lab-empty small">没有交叉验证预测点。</div>';
    const values = points.flatMap((point) => [Number(point.actual), Number(point.predicted)]).filter(Number.isFinite);
    if (!values.length) return '<div class="lab-empty small">预测点无效。</div>';
    let min = Math.min(...values);
    let max = Math.max(...values);
    const span = max - min || Math.max(Math.abs(max), 1);
    min -= span * 0.08;
    max += span * 0.08;
    const W = 440, H = 280, L = 48, R = 14, T = 16, B = 38;
    const sx = (value) => L + ((value - min) / (max - min)) * (W - L - R);
    const sy = (value) => H - B - ((value - min) / (max - min)) * (H - T - B);
    const ticks = Array.from({ length: 5 }, (_, index) => min + ((max - min) * index) / 4);
    const grid = ticks.map((tick) => {
      const x = sx(tick), y = sy(tick);
      return `<line x1="${x.toFixed(1)}" y1="${T}" x2="${x.toFixed(1)}" y2="${H - B}" class="lab-grid-line"/>
        <line x1="${L}" y1="${y.toFixed(1)}" x2="${W - R}" y2="${y.toFixed(1)}" class="lab-grid-line"/>
        <text x="${x.toFixed(1)}" y="${H - B + 16}" text-anchor="middle" class="lab-axis-text">${esc(num(tick, 0))}</text>
        <text x="${L - 7}" y="${(y + 3).toFixed(1)}" text-anchor="end" class="lab-axis-text">${esc(num(tick, 0))}</text>`;
    }).join("");
    const dots = points.map((point) => {
      const x = sx(Number(point.actual));
      const y = sy(Number(point.predicted));
      const std = point.std == null ? "" : ` ± ${num(point.std, 2)}`;
      return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3.2" class="lab-dot"><title>实测 ${num(point.actual, 2)} · 预测 ${num(point.predicted, 2)}${std}</title></circle>`;
    }).join("");
    return `<svg class="lab-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(target)} 的交叉验证预测与实测对比">
      ${grid}
      <line x1="${sx(min).toFixed(1)}" y1="${sy(min).toFixed(1)}" x2="${sx(max).toFixed(1)}" y2="${sy(max).toFixed(1)}" class="lab-diagonal"/>
      ${dots}
      <text x="${W / 2}" y="${H - 6}" text-anchor="middle" class="lab-axis-title">实测 ${esc(target)}</text>
      <text x="12" y="12" class="lab-axis-title">预测</text>
    </svg>`;
  }

  function barsHTML(importance) {
    if (!importance?.length) return '<div class="lab-empty small">没有可用的置换重要性。</div>';
    const rows = importance.slice(0, 10);
    const max = Math.max(...rows.map((row) => Number(row.delta_mae) || 0), 1e-12);
    return `<div class="lab-bars">${rows.map((row) => {
      const value = Math.max(0, Number(row.delta_mae) || 0);
      const width = Math.max(1.5, (value / max) * 100);
      return `<div class="lab-bar-row">
        <span class="lab-bar-label" title="${esc(row.feature)}">${esc(row.feature)}</span>
        <span class="lab-bar-track"><i style="width:${width.toFixed(1)}%"></i></span>
        <span class="lab-bar-value">${num(value, 2)}</span>
      </div>`;
    }).join("")}</div>`;
  }

  function renderSpace(card) {
    const box = $("#lab-space-list");
    if (!box) return;
    if (!card) {
      box.innerHTML = '<div class="lab-empty"><b>选择一个模型</b><span>搜索空间来自训练数据的范围与类别。</span></div>';
      return;
    }
    const stats = card.feature_stats || {};
    const features = card.features || [];
    box.innerHTML = features.map((name) => {
      const item = stats[name] || {};
      if (item.type === "categorical") {
        const values = item.values || [];
        return `<div class="space-item">
          <div class="space-head"><b>${esc(name)}</b><span>${int(values.length)} 个训练类别</span></div>
          <div class="space-values">${values.map((value) => `<label class="check compact"><input type="checkbox" data-space-cat="${esc(name)}" value="${esc(value)}" checked> ${esc(value)}</label>`).join("")}</div>
        </div>`;
      }
      const min = item.min;
      const max = item.max;
      return `<div class="space-item">
        <div class="space-head"><b>${esc(name)}</b><span>训练范围 ${num(min, 3)} – ${num(max, 3)}</span></div>
        <div class="space-inputs">
          <input type="number" step="any" data-space-min="${esc(name)}" value="${min == null ? "" : esc(min)}" aria-label="${esc(name)} 最小值">
          <span>至</span>
          <input type="number" step="any" data-space-max="${esc(name)}" value="${max == null ? "" : esc(max)}" aria-label="${esc(name)} 最大值">
        </div>
      </div>`;
    }).join("") || '<div class="lab-empty small">该模型没有可用特征统计。</div>';
    $("#lab-opt-status").textContent = `已载入 ${features.length} 个特征 · ${card.target}`;
  }

  function collectSpace(card) {
    const space = {};
    const stats = card.feature_stats || {};
    for (const name of card.features || []) {
      const item = stats[name] || {};
      if (item.type === "categorical") {
        const checked = $$("#lab-space-list input[data-space-cat]").filter((input) => input.dataset.spaceCat === name && input.checked);
        if (!checked.length) throw new Error(`请为 ${name} 至少选择一个类别。`);
        space[name] = { values: checked.map((input) => input.value) };
      } else {
        const minInput = $$("#lab-space-list input[data-space-min]").find((input) => input.dataset.spaceMin === name);
        const maxInput = $$("#lab-space-list input[data-space-max]").find((input) => input.dataset.spaceMax === name);
        if (!minInput || !maxInput) continue;
        const min = Number(minInput.value);
        const max = Number(maxInput.value);
        if (!Number.isFinite(min) || !Number.isFinite(max)) throw new Error(`${name} 的范围必须是数值。`);
        if (min > max) throw new Error(`${name} 的最小值不能大于最大值。`);
        space[name] = { min, max };
      }
    }
    return space;
  }

  async function submitOptimize() {
    const select = $("#lab-opt-model");
    const modelId = select?.value;
    if (!modelId) {
      window.bioforge.toast("请先训练或选择一个模型。");
      return;
    }
    const button = $("#lab-opt-btn");
    const status = $("#lab-opt-status");
    button.disabled = true;
    status.textContent = "正在计算 EI 与多样性筛选…";
    try {
      const card = state.modelDetail?.model_id === modelId ? state.modelDetail : await loadModel(modelId);
      const space = collectSpace(card);
      const payload = {
        model_id: modelId,
        direction: $("#lab-opt-direction").value,
        n_candidates: Number($("#lab-opt-count").value),
        search_size: Number($("#lab-opt-search").value),
        space,
        seed: 42,
      };
      const result = await window.bioforge.api("/api/v3/lab/optimize", { method: "POST", body: JSON.stringify(payload) });
      state.optimize = result;
      renderOptimize(result);
      status.textContent = `已完成 ${result.candidates?.length || 0} 个候选。`;
      window.bioforge.toast(`已生成 ${result.candidates?.length || 0} 个候选。`);
      try {
        state.overview = await window.bioforge.api("/api/v3/lab/overview");
        renderStats();
      } catch { /* non-blocking */ }
      $("#lab-opt-result")?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      status.textContent = "";
      guard(err);
    } finally {
      button.disabled = false;
    }
  }

  function renderOptimize(result) {
    const box = $("#lab-opt-result");
    if (!box) return;
    if (!result) {
      box.innerHTML = `<div class="empty card lab-empty-card"><h3>生成下一轮候选</h3><p>选择模型后，算法会在训练范围内用 EI 采样，并给出预测区间与置信度。</p></div>`;
      return;
    }
    const candidates = result.candidates || [];
    const observed = result.observed_range || {};
    box.innerHTML = `<div class="card lab-card lab-opt-result">
      <div class="lab-card-head">
        <div><span class="eyebrow">BAYESIAN OPTIMIZATION</span><h3>${esc(result.target)} · ${result.direction === "maximize" ? "最大化" : "最小化"}</h3><p class="muted">${esc(result.run_id)} · 模型 ${esc(result.model_version || result.model_id)}</p></div>
        <div class="lab-actions compact"><a class="btn ghost" href="/api/v3/lab/runs/${encodeURIComponent(result.run_id)}/csv" data-lab-download data-filename="bioforge-${esc(result.run_id)}.csv">导出候选 CSV</a></div>
      </div>
      <div class="lab-metrics">
        <div><span>历史最优</span><b>${num(result.observed_best, 2)}</b></div>
        <div><span>候选</span><b>${candidates.length}</b></div>
        <div><span>搜索点数</span><b>${int(result.search_size)}</b></div>
        <div><span>训练范围</span><b>${num(observed.min, 1)} – ${num(observed.max, 1)}</b></div>
      </div>
      <div class="lab-candidates">${candidates.map((candidate, index) => candidateHTML(candidate, index)).join("")}</div>
      ${(result.warnings || []).length ? `<div class="lab-warnings">${result.warnings.map((warning) => `<p>${esc(warning)}</p>`).join("")}</div>` : ""}
      <p class="fineprint">${esc(result.notice || "")}</p>
    </div>`;
  }

  function candidateHTML(candidate, index) {
    const features = candidate.features || {};
    const chips = Object.entries(features).map(([name, value]) => `<span class="lab-chip"><span>${esc(name)}</span><b>${esc(typeof value === "number" ? num(value, 2) : value)}</b></span>`).join("");
    return `<div class="lab-candidate">
      <div class="lab-candidate-head">
        <div><span class="lab-rank">候选 ${String(candidate.rank || index + 1).padStart(2, "0")}</span>${confidenceBadge(candidate.confidence)}</div>
        <button class="btn ghost small" type="button" data-lab-feedback="${index}">记录实测</button>
      </div>
      <div class="lab-candidate-pred">
        <b>${num(candidate.predicted, 2)}</b><span>± ${num(candidate.uncertainty, 2)}</span>
        <small>95% 区间 ${num(candidate.lower_95, 2)} – ${num(candidate.upper_95, 2)}</small>
      </div>
      <div class="lab-candidate-meta"><span>EI ${num(candidate.acquisition, 4)}</span><span>${esc(candidate.candidate_id || "")}</span></div>
      <div class="lab-chip-row">${chips}</div>
    </div>`;
  }

  function renderFeedback() {
    const box = $("#lab-feedback-result");
    if (!box) return;
    const dataset = state.dataset;
    const exportLink = $("#lab-fb-export");
    if (exportLink) {
      if (dataset) {
        exportLink.href = `/api/v3/lab/datasets/${encodeURIComponent(dataset.id)}/csv`;
        exportLink.dataset.filename = `bioforge-${dataset.id}.csv`;
      } else exportLink.removeAttribute("href");
    }
    const fbDataset = $("#lab-fb-dataset");
    if (fbDataset && dataset) fbDataset.value = dataset.id;
    const msg = $("#lab-fb-msg");
    if (msg) msg.textContent = dataset ? `${int(dataset.row_count)} 行 · 更新 ${dateText(dataset.updated_utc)} · 哈希 ${dataset.hash_short}` : "";
    if (!dataset) {
      box.innerHTML = `<div class="empty card lab-empty-card"><h3>还没有可回灌的数据集</h3><p>先导入实测数据，或从优化候选里记录实测。</p></div>`;
      return;
    }
    const columns = columnsOf(dataset);
    const names = columns.slice(0, 8).map((column) => column.name);
    const recent = (dataset.recent || []).slice(0, 8);
    const feedback = state.feedback && state.feedback.id === dataset.id ? state.feedback : null;
    const retrained = feedback?.retrain?.model;
    box.innerHTML = `${feedback ? `<div class="card lab-card lab-feedback-result">
      <div class="lab-card-head"><div><span class="eyebrow">LOOP CLOSED</span><h3>已追加 ${int(feedback.append?.rows)} 行</h3><p class="muted">${esc(feedback.append?.source || "wet_lab")} · 数据集现在 ${int(feedback.append?.total_rows)} 行</p></div><span class="badge ok">已回灌</span></div>
      <div class="lab-meta-grid">
        <div><span>模型</span><b>${esc(feedback.feedback?.model_id || "")}</b></div>
        <div><span>目标</span><b>${esc(feedback.feedback?.target || "")}</b></div>
        <div><span>实测值</span><b>${num(feedback.feedback?.measured, 2)}</b></div>
        <div><span>重训</span><b>${retrained ? esc(retrained.model_id) : "未重训"}</b></div>
      </div>
      ${retrained ? `<p class="fineprint">新模型 ${esc(retrained.model_version)} · R² ${num(retrained.metrics?.r2, 3)} · 旧模型保留，可追溯。</p>` : ""}
      ${feedback.feedback?.evidence_graph ? `<p class="fineprint">证据图谱：${feedback.feedback.evidence_graph.written ? `已写入 ${int(feedback.feedback.evidence_graph.edges || 0)} 条来源边（${esc(feedback.feedback.evidence_graph.feedback_id || "")}）` : `未写入（${esc(feedback.feedback.evidence_graph.reason || "数据库不可用")}）`}</p>` : ""}
    </div>` : ""}
    <details class="card lab-card">
      <summary class="lab-card-head"><div><h3>最近追加 / 导入</h3><p class="muted">最新 8 行，点击展开；来源标签与时间均保留。</p></div><button class="btn ghost small" id="lab-fb-refresh-inline" type="button">刷新</button></summary>
      <div style="margin-top:12px">${table([...names, "来源", "时间"], recent.map((row) => [
        ...names.map((name) => cell(row[name])),
        `<span class="badge">${esc(row._source || "import")}</span>`,
        `<span class="muted">${esc(dateText(row._created_utc))}</span>`,
      ]))}</div>
      <p class="fineprint">回灌会把候选特征 + 实测目标写成新行；不会覆盖历史记录。重训使用原模型配置，并保留父模型链接；成功回灌会同时写入证据图谱数据库。</p>
    </details>`;
    $("#lab-fb-refresh-inline")?.addEventListener("click", () => selectDataset(dataset.id));
  }

  async function retrainSelected() {
    const modelId = $("#lab-fb-model")?.value;
    if (!modelId) {
      window.bioforge.toast("请先训练一个模型，或从模型列表选择。");
      return;
    }
    const button = $("#lab-fb-retrain-btn");
    button.disabled = true;
    const previous = button.textContent;
    button.textContent = "重训中…";
    try {
      const result = await window.bioforge.api(`/api/v3/lab/models/${encodeURIComponent(modelId)}/retrain`, { method: "POST" });
      state.trainResult = result.model;
      await refresh();
      renderTrainResult(result.model);
      window.bioforge.toast(`已重训：${result.model.model_version}。`);
      setTab("train");
    } catch (err) {
      guard(err);
    } finally {
      button.disabled = false;
      button.textContent = previous;
    }
  }

  function setTab(tab) {
    $$("#lab-tabs [data-lab-tab]").forEach((button) => button.classList.toggle("active", button.dataset.labTab === tab));
    $$(".lab-panel").forEach((panel) => panel.classList.add("hidden"));
    $(`#lab-panel-${tab}`)?.classList.remove("hidden");
    if (tab === "train" && state.dataset) fillTrainForm(state.dataset);
    if (tab === "optimize") {
      const id = $("#lab-opt-model")?.value;
      if (!id) renderSpace(null);
      else if (state.modelDetail?.model_id === id) renderSpace(state.modelDetail);
      else loadModel(id).then((card) => renderSpace(card)).catch(guard);
    }
    if (tab === "feedback") renderFeedback();
  }

  async function refresh() {
    await fetchAll();
    const current = state.dataset?.id;
    const next = current && state.datasets.some((dataset) => dataset.id === current) ? current : state.datasets[0]?.id;
    if (next) await selectDataset(next, { silent: true });
    else {
      state.dataset = null;
      state.trainResult = null;
      state.optimize = null;
      state.trainKey = "";
      state.trainDatasetId = "";
      state.features = new Set();
      renderDatasetDetail();
      renderTrainResult(null);
      renderOptimize(null);
      renderFeedback();
      clearTrainForm();
    }
  }

  async function loadLab() {
    if (state.loading) return;
    state.loading = true;
    try {
      await fetchAll();
      state.loaded = true;
      const next = state.datasets[0]?.id;
      if (next) await selectDataset(next, { silent: true });
      else {
        state.dataset = null;
        state.trainKey = "";
        state.trainDatasetId = "";
        state.features = new Set();
        renderDatasetDetail();
        renderTrainResult(null);
        renderOptimize(null);
        renderFeedback();
        clearTrainForm();
      }
    } catch (err) {
      guard(err);
    } finally {
      state.loading = false;
    }
  }

  function clearTrainForm() {
    const target = $("#lab-train-target");
    if (target) target.innerHTML = '<option value="">未选择数据集</option>';
    const features = $("#lab-feature-list");
    if (features) features.innerHTML = '<div class="lab-empty"><b>未选择数据集</b><span>先在“数据集”页导入或载入演示数据。</span></div>';
    const group = $("#lab-train-group");
    if (group) group.innerHTML = '<option value="">不分组</option>';
    const button = $("#lab-train-btn");
    if (button) button.disabled = true;
    const badge = $("#lab-train-dataset-badge");
    if (badge) badge.textContent = "未选择数据集";
    const select = $("#lab-train-dataset");
    if (select && !state.datasets.length) select.innerHTML = '<option value="">暂无数据集</option>';
  }

  async function enter() {
    if (!state.loaded) {
      await loadLab();
      return;
    }
    if (state.dataset) {
      renderDatasets();
      renderDatasetDetail();
      renderFeedback();
    }
  }

  async function saveDownload(url, filename) {
    try {
      const response = await fetch(url, { credentials: "same-origin" });
      if (!response.ok) throw new Error(`下载失败 (${response.status})`);
      const text = await response.text();
      window.AndroidBridge.saveText(filename || "bioforge.csv", "text/csv", text);
    } catch (err) {
      window.bioforge.toast(err.message || "下载失败。");
    }
  }

  async function importDemo() {
    const button = $("#lab-demo-btn");
    button.disabled = true;
    const previous = button.textContent;
    button.textContent = "载入中…";
    try {
      const result = await window.bioforge.api("/api/v3/lab/datasets/demo", { method: "POST" });
      state.feedback = null;
      await refresh();
      await selectDataset(result.id);
      window.bioforge.toast(result.import?.created === false ? "演示数据已存在，已选中。" : "演示数据已载入（合成数据）。");
      setTab("data");
    } catch (err) {
      guard(err);
    } finally {
      button.disabled = false;
      button.textContent = previous;
    }
  }

  async function importDataset(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const file = $("#lab-import-file")?.files?.[0];
    let content = $("#lab-import-text")?.value.trim() || "";
    let format = "csv";
    if (file) {
      content = await file.text();
      format = /\.json$/i.test(file.name) ? "json" : "csv";
    } else if (/^[\[{]/.test(content.trim())) {
      format = "json";
    }
    if (!content) {
      window.bioforge.toast("请选择文件或粘贴 CSV / JSON。");
      return;
    }
    let name = $("#lab-import-name")?.value.trim();
    if (!name && file) name = file.name.replace(/\.[^.]+$/, "").slice(0, 80);
    if (!name) {
      window.bioforge.toast("请填写数据集名称。");
      $("#lab-import-name")?.focus();
      return;
    }
    const source = $("#lab-import-source")?.value || "measured";
    const button = form.querySelector("button[type=submit]");
    const message = $("#lab-import-msg");
    button.disabled = true;
    message.textContent = "正在解析、推断类型并去重…";
    try {
      const payload = {
        name,
        content,
        source_type: source,
        format,
        description: $("#lab-import-desc")?.value.trim() || "",
        dedupe: Boolean($("#lab-import-dedupe")?.checked),
      };
      const result = await window.bioforge.api("/api/v3/lab/datasets", { method: "POST", body: JSON.stringify(payload) });
      message.textContent = `已导入 ${int(result.import?.rows)} 行${result.import?.duplicates_skipped ? `，跳过 ${int(result.import.duplicates_skipped)} 行重复` : ""} · ${result.hash_short}`;
      form.reset();
      state.feedback = null;
      await refresh();
      await selectDataset(result.id);
      setTab("data");
      window.bioforge.toast(`数据集已导入：${result.name}。`);
    } catch (err) {
      message.textContent = err.message || "导入失败。";
      guard(err);
    } finally {
      button.disabled = false;
    }
  }

  async function submitTraining() {
    if (!state.dataset) {
      window.bioforge.toast("请先选择数据集。");
      return;
    }
    const target = $("#lab-train-target")?.value;
    const features = $$("#lab-feature-list input[type=checkbox]").filter((input) => input.checked).map((input) => input.dataset.featureName);
    if (!target) {
      window.bioforge.toast("请选择数值目标列。");
      return;
    }
    if (!features.length) {
      window.bioforge.toast("请至少选择一个特征列。");
      return;
    }
    if (needSynthetic(state.dataset) && !$("#lab-train-synthetic")?.checked) {
      window.bioforge.toast("合成/混合数据必须勾选“允许合成数据”才能训练。");
      $("#lab-train-synthetic")?.focus();
      return;
    }
    const button = $("#lab-train-btn");
    const status = $("#lab-train-status");
    button.disabled = true;
    status.textContent = "训练中：交叉验证 + 不确定性校准…";
    try {
      const result = await window.bioforge.api("/api/v3/lab/train", {
        method: "POST",
        body: JSON.stringify({
          dataset_id: state.dataset.id,
          target,
          features,
          algorithm: $("#lab-train-algorithm")?.value || "auto",
          include_synthetic: Boolean($("#lab-train-synthetic")?.checked),
          cv_folds: Number($("#lab-train-folds")?.value || 5),
          group_column: $("#lab-train-group")?.value || null,
        }),
      });
      state.trainResult = result.model;
      state.modelDetail = result.model;
      renderTrainResult(result.model);
      const models = await window.bioforge.api("/api/v3/lab/models");
      state.models = models.items || [];
      renderModels();
      populateSelectors();
      const optSelect = $("#lab-opt-model");
      if (optSelect) optSelect.value = result.model.model_id;
      const feedbackSelect = $("#lab-fb-model");
      if (feedbackSelect) feedbackSelect.value = result.model.model_id;
      renderSpace(result.model);
      status.textContent = `完成 · R² ${num(result.model.metrics?.r2, 3)} · MAE ${num(result.model.metrics?.mae, 2)}`;
      try {
        state.overview = await window.bioforge.api("/api/v3/lab/overview");
        renderStats();
      } catch { /* non-blocking */ }
      window.bioforge.toast(`模型已训练：${result.model.model_id}。`);
      $("#lab-train-result")?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      status.textContent = "";
      guard(err);
    } finally {
      button.disabled = false;
    }
  }

  async function onOptimizeModelChange() {
    const id = $("#lab-opt-model")?.value;
    if (!id) {
      renderSpace(null);
      return;
    }
    try {
      const card = await loadModel(id);
      renderSpace(card);
    } catch (err) {
      guard(err);
    }
  }

  async function deleteDataset(id) {
    try {
      await window.bioforge.api(`/api/v3/lab/datasets/${encodeURIComponent(id)}?confirm=yes-delete-dataset`, { method: "DELETE" });
      if (state.dataset?.id === id) state.dataset = null;
      state.feedback = null;
      state.trainResult = null;
      state.optimize = null;
      await refresh();
      window.bioforge.toast("数据集及其模型已删除。");
    } catch (err) {
      guard(err);
    }
  }

  async function openFeedback(index) {
    const result = state.optimize;
    const candidate = result?.candidates?.[Number(index)];
    if (!candidate) return;
    const modelId = result.model_id;
    let card = state.modelDetail;
    if (card?.model_id !== modelId) {
      try {
        card = await loadModel(modelId);
      } catch (err) {
        guard(err);
        return;
      }
    }
    state.modal = { modelId, target: result.target, candidate };
    $("#lab-modal-title").textContent = `记录 ${candidate.candidate_id} 的实测`;
    $("#lab-modal-sub").textContent = `模型预测 ${num(candidate.predicted, 2)} ± ${num(candidate.uncertainty, 2)}（95% 区间 ${num(candidate.lower_95, 2)} – ${num(candidate.upper_95, 2)}）。保存后会追加到原数据集。`;
    $("#lab-modal-target-name").textContent = `· ${result.target}`;
    $("#lab-modal-measured").value = "";
    $("#lab-modal-measured").placeholder = `例如 ${num(candidate.predicted, 1)}`;
    $("#lab-modal-notes").value = "";
    $("#lab-modal-retrain").checked = true;
    $("#lab-modal-preview").textContent = `候选特征：${Object.entries(candidate.features || {}).map(([name, value]) => `${name}=${value}`).join(" · ")}`;
    $("#lab-modal").classList.remove("hidden");
    document.body.classList.add("lab-modal-open");
    window.setTimeout(() => $("#lab-modal-measured")?.focus(), 60);
  }

  function closeFeedback() {
    $("#lab-modal")?.classList.add("hidden");
    document.body.classList.remove("lab-modal-open");
    state.modal = null;
  }

  async function submitFeedback(event) {
    event.preventDefault();
    if (!state.modal) return;
    const measured = Number($("#lab-modal-measured")?.value);
    if (!Number.isFinite(measured)) {
      window.bioforge.toast("请输入有效的实测数值。");
      return;
    }
    const button = event.currentTarget.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      const result = await window.bioforge.api("/api/v3/lab/feedback", {
        method: "POST",
        body: JSON.stringify({
          model_id: state.modal.modelId,
          features: state.modal.candidate.features,
          measured: { [state.modal.target]: measured },
          notes: $("#lab-modal-notes")?.value.trim() || "",
          retrain: Boolean($("#lab-modal-retrain")?.checked),
        }),
      });
      state.feedback = result;
      closeFeedback();
      await refresh();
      setTab("feedback");
      const retrained = result.retrain?.model;
      window.bioforge.toast(retrained ? `实测已追加，并重训为 ${retrained.model_version}。` : "实测已追加到数据集。");
    } catch (err) {
      guard(err);
    } finally {
      button.disabled = false;
    }
  }

  function bind() {
    $("#lab-tabs")?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-lab-tab]");
      if (button) setTab(button.dataset.labTab);
    });
    $("#lab-demo-btn")?.addEventListener("click", importDemo);
    $("#lab-import-form")?.addEventListener("submit", importDataset);
    $("#lab-train-btn")?.addEventListener("click", submitTraining);
    $("#lab-opt-btn")?.addEventListener("click", submitOptimize);
    $("#lab-opt-model")?.addEventListener("change", onOptimizeModelChange);
    $("#lab-fb-retrain-btn")?.addEventListener("click", retrainSelected);
    $("#lab-fb-refresh")?.addEventListener("click", () => state.dataset && selectDataset(state.dataset.id));
    $("#lab-train-dataset")?.addEventListener("change", (event) => event.target.value && selectDataset(event.target.value));
    $("#lab-fb-dataset")?.addEventListener("change", (event) => event.target.value && selectDataset(event.target.value));
    $("#lab-train-target")?.addEventListener("change", (event) => {
      if (state.dataset) {
        if ($("#lab-train-group")?.value === event.target.value) $("#lab-train-group").value = "";
        renderFeatureList(state.dataset, event.target.value);
      }
    });
    $("#lab-feature-all")?.addEventListener("click", () => {
      if (!state.dataset) return;
      const target = $("#lab-train-target")?.value;
      const defaults = new Set(defaultFeatureNames(state.dataset, target));
      $$("#lab-feature-list input[type=checkbox]").forEach((input) => { input.checked = defaults.has(input.dataset.featureName); });
      state.features = defaults;
    });
    $("#lab-feature-none")?.addEventListener("click", () => {
      $$("#lab-feature-list input[type=checkbox]").forEach((input) => { input.checked = false; });
      state.features = new Set();
    });
    $("#lab-feedback-form")?.addEventListener("submit", submitFeedback);
    $("#lab-modal-close")?.addEventListener("click", closeFeedback);
    $("#lab-modal-cancel")?.addEventListener("click", closeFeedback);
    $("#lab-modal")?.addEventListener("click", (event) => { if (event.target.id === "lab-modal") closeFeedback(); });
    document.addEventListener("keydown", (event) => { if (event.key === "Escape" && state.modal) closeFeedback(); });
    document.addEventListener("click", (event) => {
      const downloadLink = event.target.closest("[data-lab-download]");
      if (downloadLink && window.AndroidBridge?.saveText) {
        event.preventDefault();
        saveDownload(downloadLink.href, downloadLink.dataset.filename || "bioforge.csv");
        return;
      }
      const deleteButton = event.target.closest("[data-lab-delete-dataset]");
      if (deleteButton) {
        event.stopPropagation();
        const id = deleteButton.dataset.labDeleteDataset;
        if (deleteButton.dataset.confirm !== "1") {
          deleteButton.dataset.confirm = "1";
          deleteButton.textContent = "确认";
          window.setTimeout(() => {
            if (deleteButton.isConnected) {
              deleteButton.dataset.confirm = "";
              deleteButton.textContent = "×";
            }
          }, 4000);
          return;
        }
        deleteDataset(id);
        return;
      }
      const dataset = event.target.closest("[data-lab-dataset]");
      if (dataset) {
        selectDataset(dataset.dataset.labDataset);
        return;
      }
      const useButton = event.target.closest("[data-lab-use-model]");
      if (useButton) {
        useModel(useButton.dataset.labUseModel);
        return;
      }
      const detailButton = event.target.closest("[data-lab-model-detail]");
      if (detailButton) {
        showModelDetail(detailButton.dataset.labModelDetail);
        return;
      }
      const feedbackButton = event.target.closest("[data-lab-feedback]");
      if (feedbackButton) openFeedback(Number(feedbackButton.dataset.labFeedback));
    });
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const dataset = event.target.closest?.("[data-lab-dataset]");
      if (!dataset || event.target.closest("button")) return;
      event.preventDefault();
      selectDataset(dataset.dataset.labDataset);
    });
  }

  function init() {
    if (!window.bioforge) return;
    bind();
  }

  window.BioForgeLab = { enter, load: loadLab, init };
  init();
})();
