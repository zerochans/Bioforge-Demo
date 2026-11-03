(function () {
  "use strict";
  var D = window.BIOFORGE_DATA || { proteins: { items: [] }, protectants: { items: [] }, compounds: { items: [] }, matrices: { items: [] }, spectra: { items: [] } };
  var COLORS = { "\u7d2b": 420, "\u84dd": 470, "\u9752": 490, "\u7eff": 520, "\u9ec4": 550, "\u6a59": 590, "\u7ea2": 620, "\u8fdc\u7ea2": 670 };
  var ROLE_CN = {
    "functional fluorophore": "\u529f\u80fd\u8367\u5149\u6210\u5206", "thermoprotectant": "\u8010\u70ed\u4fdd\u62a4\u5242",
    "aggregation_suppressor": "\u805a\u96c6\u6291\u5236\u5242", "antioxidant": "\u6297\u6c27\u5316\u5242",
    "buffer": "\u7f13\u51b2\u5242", "buffer_stabilizer": "\u7f13\u51b2\u7a33\u5b9a\u5242",
    "bulking_stabilizer": "\u586b\u5145\u7a33\u5b9a\u5242", "preservative": "\u9632\u8150\u5242",
    "stabilizer": "\u7a33\u5b9a\u5242", "surfactant": "\u8868\u9762\u6d3b\u6027\u5242",
    "acidulant": "\u9178\u5ea6\u8c03\u8282\u5242", "sweetener": "\u751c\u5473\u5242", "q.s. to 100 %": "\u5b9a\u5bb9\u81f3 100%"
  };
  var DEFAULT_WEIGHTS = { stability: 0.45, spectral: 0.25, food_safety: 0.15, brightness: 0.1, cost: 0.05 };

  function clamp(v, lo, hi) { return Math.max(lo === undefined ? 0 : lo, Math.min(hi === undefined ? 1 : hi, v)); }
  function sigmoid(x) { return 1 / (1 + Math.exp(-x)); }
  function gauss(x, c, w) { var z = (x - c) / Math.max(1e-9, w); return Math.exp(-0.5 * z * z); }
  function byId(items, id) { for (var i = 0; i < items.length; i++) { if (items[i].id === id) return items[i]; } return null; }
  function has(hay, words) { var t = hay.toLowerCase(); for (var i = 0; i < words.length; i++) { if (t.indexOf(words[i].toLowerCase()) >= 0) return true; } return false; }
  function hashSeed(text) { var h = 2166136261; for (var i = 0; i < text.length; i++) { h ^= text.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
  function rngFrom(seed) {
    var a = seed >>> 0;
    return function () { a |= 0; a = (a + 0x6D2B79F5) | 0; var t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  }
  function normal(rng) { var u = 0, v = 0; while (u === 0) u = rng(); while (v === 0) v = rng(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); }
  function round(v, n) { var f = Math.pow(10, n === undefined ? 4 : n); return Math.round(v * f) / f; }

  function parseBrief(text) {
    var q = (text || "").trim().slice(0, 6000);
    if (!q) q = "\u8bbe\u8ba1\u4e00\u4e2a\u5728\u52a0\u70ed\u548c\u9178\u6027\u6761\u4ef6\u4e0b\u5149\u8c31\u57fa\u672c\u4e0d\u53d8\u7684\u7eff\u8272\u53d1\u5149\u86cb\u767d";
    var lower = q.toLowerCase();
    var food = has(q, ["\u996e\u6599", "\u98df\u54c1", "\u996e\u54c1", "\u53e3\u670d", "\u98df\u54c1\u7ea7", "\u6c41", "juice", "\u5976", "milk", "soda", "beverage", "drink", "food"]);
    var fluorescent = has(q, ["\u8367\u5149", "\u53d1\u5149", "fluoresc", "luminesc", "gfp", "rfp"]);
    var wantsProtein = has(q, ["\u86cb\u767d", "protein", "\u9176", "enzyme"]);
    var wantsCompound = has(q, ["\u5c0f\u5206\u5b50", "\u5316\u5408\u7269", "\u63a2\u9488", "small molecule", "compound", "ligand"]);
    var requested = wantsCompound && !wantsProtein ? "compound" : (wantsProtein ? "protein" : null);
    var spectral = {
      uv_vis: has(q, ["\u7d2b\u5916", "uv", "\u5438\u6536\u5149\u8c31", "absorb"]),
      fluorescence: fluorescent || has(q, ["\u8367\u5149\u5149\u8c31", "\u53d1\u5c04\u5149\u8c31", "emission"]),
      ir: has(q, ["\u7ea2\u5916", "ftir", " ir "]),
      ms: has(q, ["\u8d28\u8c31", "mass spec", "lc-ms"]),
      nmr: has(q, ["\u6838\u78c1", "nmr"])
    };
    var four = has(q, ["\u56db\u5927\u8c31", "\u56db\u8c31"]);
    if (four) { spectral.uv_vis = spectral.fluorescence = spectral.ir = spectral.ms = spectral.nmr = true; }
    var invariance = has(q, ["\u4e0d\u53d8", "\u57fa\u672c\u4e0d\u53d8", "\u4fdd\u6301", "\u7a33\u5b9a", "unchanged", "invariant"]) && (spectral.fluorescence || spectral.uv_vis);
    var matrixId = "lab_buffer";
    if (has(q, ["\u6a59\u6c41", "\u679c\u6c41", "juice"])) matrixId = "orange_juice";
    else if (has(q, ["\u725b\u5976", "\u4e73", "milk", "dairy"])) matrixId = "milk";
    else if (has(q, ["\u78b3\u9178", "\u6c7d\u6c34", "soda", "carbonat"])) matrixId = "carbonated";
    else if (has(q, ["\u8fd0\u52a8", "sports"])) matrixId = "sports_drink";
    else if (has(q, ["\u8336", "tea"])) matrixId = "green_tea";
    else if (has(q, ["\u690d\u7269\u86cb\u767d", "\u8c46\u5976", "plant protein"])) matrixId = "plant_protein";
    else if (has(q, ["\u9178\u5976", "yogurt"])) matrixId = "yogurt_drink";
    else if (food) matrixId = "beverage_generic";
    var matrix = byId(D.matrices.items, matrixId) || D.matrices.items[0];
    var temp = null, ph = null, minutes = null, days = null;
    var m = lower.match(/(-?\d+(?:\.\d+)?)\s*(?:°\s*c|℃|\u6444\u6c0f\u5ea6|\u5ea6c)/); if (m) temp = parseFloat(m[1]);
    if (temp === null) { m = lower.match(/(\d{2,3}(?:\.\d+)?)\s*\u5ea6(?!\s*(?:\u5929|\u65e5|\u5206\u949f|min))/); if (m) temp = parseFloat(m[1]); }
    if (temp === null && has(q, ["\u716e\u6cb8", "boiling"])) temp = 100;
    if (temp === null && has(q, ["\u5df4\u6c0f", "pasteur"])) temp = 72;
    m = lower.match(/ph\s*[=:：]?\s*(\d(?:\.\d)?)/); if (m) ph = parseFloat(m[1]);
    if (ph === null && has(q, ["\u5f3a\u9178", "strong acid"])) ph = 2.5;
    if (ph === null && has(q, ["\u9178", "acid"])) ph = 3.5;
    if (ph === null && has(q, ["\u4e2d\u6027", "neutral"])) ph = 7;
    m = lower.match(/(\d+(?:\.\d+)?)\s*(\u5206\u949f|\u5206|min(?:ute)?s?|\u5c0f\u65f6|h(?:our)?s?)/);
    if (m) { minutes = parseFloat(m[1]); if (m[2].indexOf("\u5c0f\u65f6") >= 0 || m[2].charAt(0) === "h") minutes *= 60; }
    m = lower.match(/(\d+)\s*(\u5929|\u65e5|days?)/); if (m) days = parseInt(m[1], 10);
    var storageTemp = matrix.storage_temp_c;
    if (has(q, ["\u51b7\u85cf", "4\u5ea6", "4\u2103", "fridge"])) storageTemp = 4;
    if (has(q, ["\u51b7\u51bb", "freeze"])) storageTemp = -20;
    if (has(q, ["\u5ba4\u6e29", "\u5e38\u6e29", "room temperature"])) storageTemp = 25;
    var values = lower.match(/(\d{3})\s*nm/g) || [];
    var ex = null, em = null, desiredColor = null;
    var colorText = q.replace(/\u7d2b\u5916/g, "UV").replace(/\u7ea2\u5916/g, "IR");
    var colorKeys = Object.keys(COLORS).sort(function (a, b) { return b.length - a.length; });
    for (var ci = 0; ci < colorKeys.length; ci++) {
      var color = colorKeys[ci];
      var matched = colorText.indexOf(color + "\u8272") >= 0 || colorText.indexOf(color + "\u5149") >= 0;
      if (!matched) {
        var near = new RegExp("(?:\u53d1|\u5448|\u8367\u5149|emit|fluoresc\\w*)[^\\u3002\\uff1b;\\n]{0,6}" + color);
        matched = near.test(colorText);
      }
      if (matched) { desiredColor = color; if (em === null) em = COLORS[color]; break; }
    }
    if (values.length === 1) em = parseFloat(values[0]);
    if (values.length >= 2) { ex = parseFloat(values[0]); em = parseFloat(values[1]); }
    var target = 0.8;
    var pct = lower.match(/(\d{2,3}(?:\.\d+)?)\s*%/); if (pct) target = clamp(parseFloat(pct[1]) / 100, 0.5, 0.99);
    if (has(q, ["\u57fa\u672c\u4e0d\u53d8", "unchanged"])) target = Math.max(target, 0.9);
    var outputs = ["report"];
    if (has(q, ["gif", "\u52a8\u56fe"])) outputs.push("gif");
    if (has(q, ["\u89c6\u9891", "video", "mp4"])) outputs.push("video");
    if (has(q, ["\u5b9e\u9a8c", "protocol", "\u65b9\u6848", "\u914d\u65b9"])) outputs.push("protocol");
    if (has(q, ["\u6570\u636e", "dataset", "csv"])) outputs.push("dataset");
    var weights = Object.assign({}, DEFAULT_WEIGHTS);
    if (has(q, ["\u4eae", "bright"])) { weights.brightness += 0.1; weights.stability -= 0.05; }
    if (has(q, ["\u4fbf\u5b9c", "\u6210\u672c", "cost", "cheap"])) { weights.cost += 0.1; weights.stability -= 0.05; }
    if (food) { weights.food_safety += 0.1; weights.brightness -= 0.05; }
    var totalW = weights.stability + weights.spectral + weights.food_safety + weights.brightness + weights.cost;
    Object.keys(weights).forEach(function (k) { weights[k] = Math.max(0, weights[k]) / totalW; });
    var assumptions = [
      "\u6a21\u578b\u57fa\u8d28\uff1a" + (matrix.cn_name || matrix.name) + "\uff0c\u5de5\u827a " + (temp === null ? matrix.process_temp_c : temp) + "\u00b0C / " + (minutes === null ? matrix.process_time_min : minutes) + " min\uff0c\u50a8\u5b58 " + storageTemp + "\u00b0C / " + (days === null ? matrix.shelf_days : days) + " \u5929\u3002",
      "\u7a33\u5b9a\u6027\u53c2\u6570\u662f\u6587\u732e\u8d8b\u52bf\u6821\u51c6\u7684\u6570\u5b57\u5b6a\u751f\u5148\u9a8c\uff0c\u4e0d\u662f\u672c\u5b9e\u9a8c\u5ba4\u5b9e\u6d4b\u503c\u3002",
      "\u79bb\u7ebf\u6a21\u5f0f\u4e0e\u670d\u52a1\u7aef\u5f15\u64ce\u4f7f\u7528\u76f8\u540c\u7684\u673a\u5236\u6a21\u578b\u548c\u540c\u4e00\u6570\u636e\u5305\uff1b\u6570\u503c\u53ef\u80fd\u56e0\u6570\u5b57\u7cbe\u5ea6\u4e0e\u987a\u5e8f\u7565\u6709\u5dee\u5f02\u3002"
    ];
    var warnings = [];
    if (food) warnings.push("\u98df\u54c1\u914d\u65b9\u5fc5\u987b\u6309\u9500\u552e\u5730\u6cd5\u89c4\u6838\u9a8c\u914d\u6599\u3001\u6700\u5927\u4f7f\u7528\u91cf\u3001\u6807\u7b7e\u548c\u8fc7\u654f\u539f\uff1b\u672c\u7ed3\u679c\u4e0d\u662f\u6cd5\u89c4\u6216\u98df\u54c1\u5b89\u5168\u6279\u51c6\u3002");
    if (has(q, ["\u7ea2\u5916", "\u8d28\u8c31", "\u6838\u78c1"])) warnings.push("IR/MS/NMR \u5728\u672c\u6d41\u7a0b\u4e2d\u7528\u4e8e\u53c2\u8010\u8c31\u5e93\u5339\u914d\u4e0e\u5b9e\u9a8c\u65b9\u6848\u751f\u6210\uff1b\u86cb\u767d\u8d28\u7684 IR/MS/NMR \u4e0d\u80fd\u7531\u672c\u6a21\u578b\u4ece\u5934\u9884\u6d4b\u3002");
    return {
      query: q, language: /[\u4e00-\u9fff]/.test(q) ? "zh" : "en",
      goal: invariance ? "heat_acid_spectral_invariance" : "fluorescent_design",
      target_kind: food && fluorescent ? "food_beverage" : (requested === "compound" ? "small_molecule" : (food ? "food_beverage" : "fluorescent_protein")),
      requested_kind: requested, mode: food ? "food" : "research", food_context: food, food_safe_required: food,
      matrix_id: matrix.id, conditions: { process_temp_c: temp === null ? matrix.process_temp_c : temp, process_time_min: minutes === null ? matrix.process_time_min : minutes, ph: ph === null ? matrix.ph : ph, storage_temp_c: storageTemp, shelf_days: days === null ? matrix.shelf_days : days },
      spectral: Object.assign({ invariance: invariance, desired_ex_nm: ex, desired_em_nm: em, desired_color: desiredColor, target_retention: target }, spectral),
      outputs: outputs, priorities: weights, explicit_protein_id: null, explicit_compound_id: null,
      assumptions: assumptions, warnings: warnings
    };
  }

  function candidatePool(brief) {
    var food = brief.food_safe_required;
    var requested = brief.requested_kind;
    var includeProteins = brief.target_kind !== "small_molecule";
    var includeCompounds = brief.target_kind !== "fluorescent_protein" || requested === "compound";
    if (requested === "protein") includeCompounds = false;
    if (requested === "compound") includeProteins = false;
    var pool = [];
    if (includeProteins) {
      D.proteins.items.forEach(function (item) {
        if (item.type !== "fluorescent_protein" && item.type !== "food_colorant_protein") return;
        if (food && String(item.food_status || "").indexOf("food") !== 0) return;
        pool.push(Object.assign({}, item, { _kind: "protein" }));
      });
    }
    if (includeCompounds) {
      D.compounds.items.forEach(function (item) {
        if (!item.fluorescence) return;
        if (food && !item.food_safe) return;
        pool.push(Object.assign({}, item, { _kind: "compound" }));
      });
    }
    return pool;
  }

  function blendEffect(item, pct) {
    var k = item.K_pct || 10;
    var maxEffect = (item.dtm10_c || 0) * (k + 10) / 10;
    return pct > 0 ? maxEffect * pct / (k + pct) : 0;
  }
  function blendDtm(blend, matrix) {
    if (!blend.length) return 0;
    var base = 0;
    blend.forEach(function (item) { var src = byId(D.protectants.items, item.id); if (src) base += blendEffect(src, item.pct); });
    var inter = D.protectants.interactions || {};
    Object.keys(inter).forEach(function (pair) {
      var parts = pair.split("|");
      var l = blend.filter(function (x) { return x.id === parts[0]; })[0];
      var r = blend.filter(function (x) { return x.id === parts[1]; })[0];
      if (l && r) {
        var ls = byId(D.protectants.items, l.id), rs = byId(D.protectants.items, r.id);
        base += Math.min(blendEffect(ls, l.pct), blendEffect(rs, r.pct)) * (inter[pair] - 1);
      }
    });
    return Math.max(0, base / (0.7 + 0.3 * (matrix.matrix_factor || 1)));
  }
  function effectiveProps(record, kind, blend, brief, matrix) {
    var tm = kind === "protein" ? (record.tm_c || 75) : (record.tm_c || 72);
    var acid = kind === "protein" ? (record.acid_ph50 || 5) : (record.acid_ph50 || 4.5);
    var scale = kind === "protein" ? 1 : 0.45;
    var dtm = blendDtm(blend, matrix) * scale;
    var ph = brief.conditions.ph;
    var processTemp = brief.conditions.process_temp_c;
    var acidPenalty = Math.max(0, 6.5 - ph) * (kind === "protein" ? 1.2 : 0.55);
    var matrixPenalty = Math.max(0, (matrix.matrix_factor || 1) - 1) * 3;
    var tmEff = tm + dtm - acidPenalty - matrixPenalty;
    var acidEff = acid - 0.1 * dtm + 0.05 * (ph - 4);
    var folded = sigmoid((tmEff - processTemp) / 4) * sigmoid((ph - acidEff) / 0.4);
    return { tm: tm, tm_eff: tmEff, dtm: dtm, acid_ph50: acid, acid_ph50_eff: acidEff, folded: folded };
  }
  function kineticRetention(record, kind, props, brief, matrix, temp, timeMin, storage) {
    if (timeMin <= 0) return 1;
    var ph = brief.conditions.ph;
    var kRef = kind === "protein" ? 1e-5 : 5e-6;
    var thermalQ = kind === "protein" ? 0.06 : 0.05;
    var acidQ = kind === "protein" ? 0.15 : 0.1;
    var protectionScale = kind === "protein" ? 2.5 : 1.2;
    var thermal = Math.pow(10, thermalQ * (temp - 25));
    var acid = Math.pow(10, acidQ * (7 - ph));
    var matrixFactor = matrix.matrix_factor || 1;
    var protection = 1 + Math.max(0, props.dtm) / 8 * protectionScale;
    var k = kRef * thermal * acid * matrixFactor / Math.max(0.2, protection);
    if (storage) {
      var light = String(matrix.light || "").toLowerCase();
      var lightFactor = light.indexOf("clear") >= 0 ? 2.2 : 1;
      var photo = record.photostability !== undefined && record.photostability !== null ? record.photostability : 0.35;
      k *= 1 + (1 - photo) * (lightFactor - 1) * 0.8;
      var oxygen = String(matrix.oxygen || "moderate").toLowerCase();
      var oxygenFactor = oxygen === "low" ? 0.8 : (oxygen === "air" ? 1.2 : 1);
      if (record.o2_required === false) oxygenFactor = Math.min(oxygenFactor, 1);
      k *= oxygenFactor;
    }
    var retention = Math.exp(-k * timeMin);
    var foldedFactor = kind === "compound" ? 1 : 0.15 + 0.85 * props.folded;
    return clamp(retention * foldedFactor);
  }
  function spectralMetrics(record, kind, retention, brief, ph) {
    var acid = record.acid_ph50 || 4.5;
    var shift = 0.8 + 4.5 * (1 - retention) + Math.max(0, acid - ph) * 0.7;
    var interference = kind === "compound" ? (record.uv_interference || 0) * 0.02 : 0;
    return { intensity_retention: round(retention, 4), delta_em_nm: round(shift, 2), shape_cosine: round(clamp(0.999 - 0.025 * (1 - retention) - interference), 4), uv_vis_change_pct: round(100 * (1 - retention) * 0.65, 2) };
  }
  function optimizeBlend(record, kind, brief, matrix) {
    var food = brief.food_safe_required;
    var ph = brief.conditions.ph;
    var protectants = D.protectants.items.filter(function (item) {
      if ((item.max_pct || 0) <= 0) return false;
      if (food && !item.food_safe) return false;
      if (ph < (item.ph_min || 0) - 0.6 || ph > (item.ph_max || 14) + 0.6) return false;
      return true;
    });
    var maxTotal = food && brief.target_kind === "food_beverage" ? 22 : 35;
    if (kind === "compound") maxTotal = Math.min(maxTotal, 18);
    function score(specs) {
      var expanded = specs.map(function (s) { var src = byId(D.protectants.items, s.id); return Object.assign({}, src, { pct: s.pct }); });
      var dtm = blendDtm(expanded, matrix) * (kind === "protein" ? 1 : 0.45);
      var penalty = 0;
      expanded.forEach(function (item) {
        var maxP = Math.max(0.001, item.max_pct || 1);
        penalty += (item.uv_interference || 0) * (item.pct / maxP) * (brief.spectral.invariance || brief.spectral.uv_vis ? 0.8 : 0.3);
        if (item.allergen) penalty += 3;
        penalty += item.cost === "low" ? 0.02 : (item.cost === "high" ? 0.14 : 0.06);
      });
      var total = expanded.reduce(function (sum, item) { return sum + item.pct; }, 0);
      if (total > 15) penalty += (total - 15) * (food ? 0.06 : 0.02);
      return { score: dtm - penalty, dtm: dtm, items: expanded };
    }
    function makeBlend(selected, scale) {
      var specs = selected.map(function (item) {
        var typical = item.typical_pct || [1, 5];
        var target = typical[1] * scale;
        return { id: item.id, pct: round(Math.min(item.max_pct, Math.max(typical[0] * 0.5, target)), 3) };
      });
      var total = specs.reduce(function (s, x) { return s + x.pct; }, 0);
      if (total > maxTotal) specs.forEach(function (x) { x.pct = round(x.pct * maxTotal / total, 3); });
      return specs;
    }
    var candidates = [score([])];
    protectants.forEach(function (item) {
      var scale = item.role === "preservative" ? 0.5 : 0.8;
      candidates.push(score(makeBlend([item], scale)));
    });
    for (var i = 0; i < protectants.length; i++) {
      for (var j = i + 1; j < protectants.length; j++) {
        candidates.push(score(makeBlend([protectants[i], protectants[j]], 0.72)));
      }
    }
    var rng = rngFrom(hashSeed(brief.query + "|" + record.id));
    for (var t = 0; t < 260; t++) {
      var size = 2 + Math.floor(rng() * 3);
      var chosen = [];
      while (chosen.length < size && protectants.length) {
        var pick = protectants[Math.floor(rng() * protectants.length)];
        if (chosen.indexOf(pick) < 0) chosen.push(pick);
      }
      candidates.push(score(makeBlend(chosen, 0.55 + rng() * 0.85)));
    }
    candidates.sort(function (a, b) { return b.score - a.score; });
    return candidates[0];
  }
  function evaluate(record, kind, blendResult, brief, matrix) {
    var cond = brief.conditions;
    var props = effectiveProps(record, kind, blendResult.items, brief, matrix);
    var processRet = kineticRetention(record, kind, props, brief, matrix, cond.process_temp_c, cond.process_time_min, false);
    var storageBrief = { conditions: Object.assign({}, cond, { process_temp_c: cond.storage_temp_c }) };
    var storageProps = effectiveProps(record, kind, blendResult.items, storageBrief, matrix);
    var storageRet = kineticRetention(record, kind, storageProps, storageBrief, matrix, cond.storage_temp_c, cond.shelf_days * 1440, true);
    var overall = clamp(processRet * storageRet);
    var spectral = spectralMetrics(record, kind, overall, brief, cond.ph);
    var target = brief.spectral.target_retention;
    var meets = brief.spectral.invariance ? (overall >= target && spectral.delta_em_nm <= 3 && spectral.shape_cosine >= 0.98) : overall >= target;
    var desired = brief.spectral.desired_em_nm;
    var em = record.em_nm;
    var fit = desired && em ? gauss(Number(em), Number(desired), 35) : (desired ? 0.2 : 1);
    var brightness = record.brightness || (kind === "compound" ? 1 : 0.8);
    var brightnessScore = clamp(brightness / 1.6);
    var foodScore = (String(record.food_status || "").indexOf("food") === 0 || record.food_safe) ? 1 : 0.35;
    var costScore = String(record.food_status || "").indexOf("food") === 0 ? 1 : 0.65;
    var weights = brief.priorities;
    var total = weights.stability * overall + weights.spectral * (0.55 * fit + 0.45 * spectral.shape_cosine) + weights.food_safety * foodScore + weights.brightness * brightnessScore + weights.cost * costScore;
    if (brief.food_safe_required && foodScore < 0.9) total *= 0.25;
    if (desired && fit < 0.35) total *= 0.5;
    if (desired && fit < 0.1) total *= 0.5;
    if (!meets) total *= 0.35 + 0.35 * clamp(overall / Math.max(1e-6, target));
    if (overall < 0.05) total *= 0.5;
    return {
      id: record.id, name: record.name, cn_name: record.cn_name || record.name, kind: kind,
      type: record.type || "compound", score: round(clamp(total), 4), meets_spec: meets,
      metrics: {
        tm_c: round(props.tm, 2), tm_eff_c: round(props.tm_eff, 2), dtm_c: round(props.dtm, 2),
        acid_ph50: round(props.acid_ph50, 2), acid_ph50_eff: round(props.acid_ph50_eff, 2),
        process_retention: round(processRet, 4), storage_retention: round(storageRet, 4),
        overall_retention: round(overall, 4), target_retention: target, brightness: brightness,
        ex_nm: record.ex_nm, em_nm: record.em_nm, food_status: record.food_status, spectral: spectral,
        spectral_fit: round(fit, 4)
      },
      blend: blendResult.items.map(function (item) {
        return { id: item.id, name: item.name, cn_name: item.cn_name, pct: item.pct, role: item.role, role_cn: ROLE_CN[item.role] || item.role, mechanism: item.mechanism || [], dtm_c: round(blendEffect(item, item.pct), 2), food_safe: item.food_safe, notes: item.notes || "", notes_cn: item.notes_cn || item.notes || "" };
      }),
      rationale: [
        "\u9884\u6d4b\u5de5\u827a\u4fdd\u7559\u7387 " + Math.round(overall * 1000) / 10 + "%\uff08\u76ee\u6807 " + Math.round(target * 100) + "%\uff09\uff0c\u0394\u03bbem " + spectral.delta_em_nm + " nm\u3002",
        "\u6709\u6548 Tm " + round(props.tm_eff, 1) + "\u00b0C\uff08\u539f\u59cb " + round(props.tm, 1) + "\u00b0C\uff09\uff0c\u6709\u6548 pH50 " + round(props.acid_ph50_eff, 2) + "\u3002"
      ],
      record: record
    };
  }
  function design(text, options) {
    options = options || {};
    var brief = parseBrief(text);
    var matrix = byId(D.matrices.items, brief.matrix_id) || D.matrices.items[0];
    var pool = candidatePool(brief);
    if (!pool.length) pool = D.proteins.items.filter(function (p) { return p.type === "fluorescent_protein"; }).map(function (p) { return Object.assign({}, p, { _kind: "protein" }); });
    var candidates = pool.map(function (record) {
      var blendResult = optimizeBlend(record, record._kind, brief, matrix);
      var evaluated = evaluate(record, record._kind, blendResult, brief, matrix);
      evaluated.record = record;
      return evaluated;
    });
    candidates.sort(function (a, b) { return (b.score - a.score) || (b.metrics.overall_retention - a.metrics.overall_retention); });
    var selected = candidates[0];
    var virtual = simulateVirtual(selected, brief, matrix);
    var spectra = simulateSpectra(selected, brief);
    var formulation = buildFormulation(selected, brief, matrix);
    var result = {
      job_id: "offline-" + Date.now().toString(36),
      created_utc: new Date().toISOString(),
      engine_version: "1.0.0-offline",
      offline: true,
      brief: brief,
      candidates: candidates.slice(0, 10),
      selected: selected,
      formulation: formulation,
      virtual_experiment: virtual,
      spectra: spectra,
      validation: offlineValidation(selected, brief),
      logic_chain: logicChain(brief, selected),
      provenance: {
        engine_version: "1.0.0-offline",
        model: { type: "browser digital twin mirror", calibration: "same curated priors as server" },
        datasets: { items: D.proteins.items.length + D.compounds.items.length + D.protectants.items.length, matrices: D.matrices.items.length, spectra: D.spectra.items.length },
        limitations: ["离线模式为精简数字孪生；完整报告、MD/QM 协议、训练校正和数据库连接需要服务器。", "所有结果仅用于研究与设计决策支持，不是法规或食品安全批准。"]
      }
    };
    result.warnings = brief.warnings.concat(selected.warnings || []).concat(globalWarnings(brief, selected));
    result.assumptions = brief.assumptions;
    result.decision_summary = decisionSummary(brief, selected);
    return result;
  }
  function globalWarnings(brief, selected) {
    var w = [];
    var desired = brief.spectral.desired_em_nm;
    if (desired && selected.metrics.spectral_fit < 0.5) w.push("\u76ee\u6807\u53d1\u5c04\u6ce2\u957f\u9644\u8fd1\u6ca1\u6709\u9ad8\u5339\u914d\u5019\u9009\uff08\u5339\u914d\u5ea6 " + selected.metrics.spectral_fit + "\uff09\u3002");
    if (!selected.meets_spec) w.push("\u5f53\u524d\u7ea6\u675f\u4e0b\u6ca1\u6709\u5019\u9009\u8fbe\u5230\u201c\u57fa\u672c\u4e0d\u53d8\u201d\u9608\u503c\uff1b\u53ef\u964d\u4f4e\u5de5\u827a\u6e29\u5ea6/\u65f6\u95f4\u3001\u63d0\u9ad8\u4fdd\u62a4\u5242\u5242\u91cf\u6216\u6539\u7528\u5c01\u88c5/\u51bb\u5e72\u3002");
    return w;
  }
  function decisionSummary(brief, selected) {
    var lines = ["\u63a8\u8350\u5019\u9009\uff1a" + selected.cn_name + "\uff08" + selected.kind + "\uff09\uff0c\u7efc\u5408\u8bc4\u5206 " + selected.score + "\u3002"];
    lines.push(selected.blend.length ? "\u4fdd\u62a4\u5242\u7ec4\u5408\uff1a" + selected.blend.map(function (x) { return x.cn_name + " " + x.pct + "%"; }).join("\u3001") + "\u3002" : "\u5f53\u524d\u7ea6\u675f\u4e0b\u6ca1\u6709\u51c0\u6536\u76ca\u4e3a\u6b63\u7684\u4fdd\u62a4\u5242\u7ec4\u5408\u3002");
    lines.push("\u6570\u5b57\u5b6a\u751f\u9884\u6d4b\uff1a\u5de5\u827a\u540e " + Math.round(selected.metrics.process_retention * 1000) / 10 + "%\uff0c\u8d27\u67b6\u671f\u540e " + Math.round(selected.metrics.storage_retention * 1000) / 10 + "%\u3002");
    lines.push("\u5149\u8c31\u5224\u5b9a\uff1a\u0394\u03bbem " + selected.metrics.spectral.delta_em_nm + " nm\uff0c\u4f59\u5f26 " + selected.metrics.spectral.shape_cosine + "\uff0c" + (selected.meets_spec ? "\u8fbe\u5230" : "\u672a\u8fbe\u5230") + "\u201c\u57fa\u672c\u4e0d\u53d8\u201d\u9608\u503c\u3002");
    return lines;
  }
  function simulateVirtual(selected, brief, matrix) {
    var record = selected.record, kind = selected.kind;
    var blend = selected.blend.map(function (item) { return { id: item.id, pct: item.pct }; });
    var cond = brief.conditions;
    function curve(xs, fn) { return xs.map(fn); }
    var tempX = [], phX = [], timeX = [];
    for (var t = 20; t <= 100; t += 2) tempX.push(t);
    for (var p = 2; p <= 9.001; p += 0.2) phX.push(round(p, 2));
    for (var m = 0; m <= 60; m += 1) timeX.push(m);
    var baseTemp = curve(tempX, function (t) { var local = { conditions: Object.assign({}, cond, { process_temp_c: t }) }; return round(kineticRetention(record, kind, effectiveProps(record, kind, [], local, matrix), local, matrix, t, cond.process_time_min), 4); });
    var optTemp = curve(tempX, function (t) { var local = { conditions: Object.assign({}, cond, { process_temp_c: t }) }; return round(kineticRetention(record, kind, effectiveProps(record, kind, blend, local, matrix), local, matrix, t, cond.process_time_min), 4); });
    var basePh = curve(phX, function (p) { var local = { conditions: Object.assign({}, cond, { ph: p }) }; return round(kineticRetention(record, kind, effectiveProps(record, kind, [], local, matrix), local, matrix, cond.process_temp_c, cond.process_time_min), 4); });
    var optPh = curve(phX, function (p) { var local = { conditions: Object.assign({}, cond, { ph: p }) }; return round(kineticRetention(record, kind, effectiveProps(record, kind, blend, local, matrix), local, matrix, cond.process_temp_c, cond.process_time_min), 4); });
    var baseTime = curve(timeX, function (m) { return round(kineticRetention(record, kind, effectiveProps(record, kind, [], brief, matrix), brief, matrix, cond.process_temp_c, m), 4); });
    var optTime = curve(timeX, function (m) { return round(kineticRetention(record, kind, effectiveProps(record, kind, blend, brief, matrix), brief, matrix, cond.process_temp_c, m), 4); });
    var storageX = [], step = Math.max(1, Math.floor(cond.shelf_days / 30));
    for (var d = 0; d <= cond.shelf_days; d += step) storageX.push(d);
    var storageBrief = { conditions: Object.assign({}, cond, { process_temp_c: cond.storage_temp_c }) };
    var storageProps = effectiveProps(record, kind, blend, storageBrief, matrix);
    var storageY = curve(storageX, function (d) { var local = { conditions: Object.assign({}, cond, { shelf_days: d }) }; return round(kineticRetention(record, kind, storageProps, local, matrix, cond.storage_temp_c, d * 1440, true), 4); });
    var rng = rngFrom(hashSeed(brief.query + selected.id + "mc"));
    var samples = [];
    for (var i = 0; i < 200; i++) {
      var temp = cond.process_temp_c + normal(rng) * 1;
      var ph = cond.ph + normal(rng) * 0.08;
      var b = blend.map(function (item) { return { id: item.id, pct: item.pct * clamp(1 + normal(rng) * 0.15, 0.5, 1.5) }; });
      var local = { conditions: Object.assign({}, cond, { process_temp_c: temp, ph: ph }) };
      var rec = Object.assign({}, record);
      if (kind === "protein") {
        rec.tm_c = (record.tm_c || 75) + normal(rng) * (record.tm_sd || 2.5);
        rec.acid_ph50 = (record.acid_ph50 || 5) + normal(rng) * (record.acid_ph50_sd || 0.35);
      }
      var props = effectiveProps(rec, kind, b, local, matrix);
      var process = kineticRetention(rec, kind, props, local, matrix, temp, cond.process_time_min, false);
      var storage = kineticRetention(rec, kind, props, local, matrix, cond.storage_temp_c, cond.shelf_days * 1440, true);
      samples.push(round(clamp(process * storage), 4));
    }
    samples.sort(function (a, b) { return a - b; });
    var mean = samples.reduce(function (s, x) { return s + x; }, 0) / samples.length;
    var target = brief.spectral.target_retention;
    var prob = samples.filter(function (x) { return x >= target; }).length / samples.length;
    var sensitivity = [
      { variable: "process_temp_c", delta: 0.02 }, { variable: "ph", delta: 0.2 }, { variable: "process_time_min", delta: 0.2 }, { variable: "tm_c", delta: 2 }, { variable: "dtm_c", delta: 0.2 }
    ].map(function (item) {
      var local = { conditions: Object.assign({}, cond) };
      var rec = Object.assign({}, record);
      var b = blend.map(function (x) { return { id: x.id, pct: x.pct }; });
      if (item.variable === "process_temp_c") local.conditions.process_temp_c += item.delta;
      else if (item.variable === "ph") local.conditions.ph += item.delta;
      else if (item.variable === "process_time_min") local.conditions.process_time_min *= 1 + item.delta;
      else if (item.variable === "tm_c") rec.tm_c = (record.tm_c || 75) + item.delta;
      else b.forEach(function (x) { x.pct *= 1 + item.delta; });
      var props = effectiveProps(rec, kind, b, local, matrix);
      var value = kineticRetention(rec, kind, props, local, matrix, local.conditions.process_temp_c, local.conditions.process_time_min);
      var baseProps = effectiveProps(record, kind, blend, brief, matrix);
      var base = kineticRetention(record, kind, baseProps, brief, matrix, cond.process_temp_c, cond.process_time_min);
      return { variable: item.variable, change: item.variable === "ph" ? "+" + item.delta : "+" + Math.round(item.delta * 100) + "%", delta_retention: round(value - base, 4) };
    });
    sensitivity.sort(function (a, b) { return Math.abs(b.delta_retention) - Math.abs(a.delta_retention); });
    var totalPct = blend.reduce(function (s, x) { return s + x.pct; }, 0);
    var doseX = [], doseY = [];
    for (var dd = 0; dd <= Math.max(5, totalPct * 1.6); dd += Math.max(0.5, totalPct * 1.6 / 24)) {
      doseX.push(round(dd, 2));
      var scaled = blend.map(function (x) { return { id: x.id, pct: x.pct * dd / Math.max(1e-9, totalPct) }; });
      doseY.push(round(kineticRetention(record, kind, effectiveProps(record, kind, scaled, brief, matrix), brief, matrix, cond.process_temp_c, cond.process_time_min), 4));
    }
    return {
      temperature: { x: tempX, base: baseTemp, optimized: optTemp },
      ph: { x: phX, base: basePh, optimized: optPh },
      time: { x: timeX, base: baseTime, optimized: optTime },
      storage: { x: storageX, optimized: storageY },
      dose_response: { x: doseX, optimized: doseY },
      monte_carlo: { n: samples.length, mean: round(mean, 4), p05: samples[Math.floor(samples.length * 0.05)], p50: samples[Math.floor(samples.length * 0.5)], p95: samples[Math.floor(samples.length * 0.95)], prob_meet_target: round(prob, 4), samples: samples.slice(0, 80) },
      sensitivity: sensitivity,
      process_retention: selected.metrics.process_retention,
      storage_retention: selected.metrics.storage_retention,
      overall_retention: selected.metrics.overall_retention,
      predicted_shelf_life_days: null
    };
  }
  function simulateSpectra(selected, brief) {
    var record = selected.record, kind = selected.kind;
    var retention = selected.metrics.overall_retention;
    var em = record.em_nm || 520, ex = record.ex_nm || [470];
    if (!Array.isArray(ex)) ex = [ex];
    var wave = [], exc = [], emission = [], stressed = [];
    for (var w0 = 380; w0 <= 750; w0 += 2) wave.push(w0);
    wave.forEach(function (w) {
      var e = 0; ex.forEach(function (c) { e += gauss(w, c, 17); }); exc.push(round(e, 5));
      var g = gauss(w, em, 22); emission.push(round(g, 5)); stressed.push(round(g * retention, 5));
    });
    var uvWave = [], uvRef = [], uvStress = [];
    for (var w3 = 240; w3 <= 700; w3 += 2) {
      uvWave.push(w3);
      var value = 0;
      if (kind === "protein") { value += 0.55 * gauss(w3, 280, 12); ex.forEach(function (c) { value += 0.8 * gauss(w3, c, 18); }); }
      else { ex.forEach(function (c) { value += gauss(w3, c, 20); }); }
      uvRef.push(round(value, 5)); uvStress.push(round(value * (0.35 + 0.65 * retention), 5));
    }
    return {
      fluorescence: { wavelength_nm: wave, excitation: exc, emission_reference: emission, emission_stressed: stressed, uvvis_wavelength_nm: uvWave, uvvis_reference: uvRef, uvvis_stressed: uvStress, metrics: selected.metrics.spectral, theoretical_mass_da: record.mw || null },
      reference_peaks: D.spectra.items.filter(function (s) { return s.compound_id === record.id; }),
      invariance: { target_retention: brief.spectral.target_retention, intensity_retention: retention, delta_em_nm: selected.metrics.spectral.delta_em_nm, shape_cosine: selected.metrics.spectral.shape_cosine, meets_spec: selected.meets_spec },
      note: "\u79bb\u7ebf\u6a21\u5f0f\uff1a\u8367\u5149/UV-Vis \u7531\u6570\u5b57\u5b6a\u751f\u751f\u6210\uff1bIR/MS/NMR \u4e3a\u53c2\u8010\u8c31\u5cf0\u5e93\u3002"
    };
  }
  function buildFormulation(selected, brief, matrix) {
    var record = selected.record, kind = selected.kind, ph = brief.conditions.ph, food = brief.food_safe_required;
    var dose = kind === "protein" ? (record.id === "phycocyanin" ? 300 : 200) : ((record.typical_mg_l || [20])[0]);
    var ingredients = [{ name: record.name, cn_name: record.cn_name, pct: round(dose / 10000, 5), dose_mg_l: dose, role: "\u529f\u80fd\u8367\u5149\u6210\u5206", range: Math.round(dose * 0.5) + "-" + Math.round(dose * 2) + " mg/L", food_safe: !!(record.food_safe || String(record.food_status || "").indexOf("food") === 0), note: "\u5148\u7528\u50a8\u5907\u6db2\u52a0\u5165\uff0c\u907f\u514d\u6ce1\u6cab\u548c\u5c40\u90e8\u8fc7\u6d53\u3002" }];
    selected.blend.forEach(function (item) { ingredients.push({ name: item.name, cn_name: item.cn_name, pct: item.pct, role: item.role, range: round(Math.max(0.01, item.pct * 0.6), 3) + "-" + round(item.pct * 1.4, 3) + " %", food_safe: item.food_safe, note: item.notes_cn || item.notes }); });
    if (ph <= 6.5) ingredients.push({ name: "Sodium citrate", cn_name: "\u67e0\u6aac\u9178\u94a0", pct: 0.5, role: "buffer", range: "0.2-1.0 %", food_safe: true, note: "\u7a33\u5b9a pH\u3002" });
    else ingredients.push({ name: "L-Histidine", cn_name: "L-\u7ec4\u6c28\u9178", pct: 0.2, role: "buffer", range: "0.1-0.5 %", food_safe: true, note: "\u8fd1\u4e2d\u6027\u7f13\u51b2\u3002" });
    if (ph < 5) ingredients.push({ name: "Citric acid", cn_name: "\u67e0\u6aac\u9178", pct: 0.15, role: "acidulant", range: "\u6309 pH \u6ef4\u5b9a", food_safe: true, note: "\u7f13\u6162\u6ef4\u5b9a\u5230\u76ee\u6807 pH\u3002" });
    if (food && ph <= 4.5) ingredients.push({ name: "Sodium benzoate", cn_name: "\u82ef\u7532\u9178\u94a0", pct: 0.05, role: "preservative", range: "\u22640.1 %\uff08\u6309\u6cd5\u89c4\uff09", food_safe: true, note: "\u9178\u6027\u996e\u6599\u9632\u8150\u3002" });
    if (food && brief.target_kind === "food_beverage") ingredients.push({ name: "Rebaudioside A", cn_name: "\u83b1\u9c8d\u8fea\u82f7A", pct: 0.02, role: "sweetener", range: "\u6309\u751c\u5ea6\u7b49\u91cf\u66ff\u6362", food_safe: true, note: "\u53ef\u9009\u3002" });
    var used = ingredients.reduce(function (s, x) { return s + x.pct; }, 0);
    if (used >= 100) { var scale = 99 / used; ingredients.forEach(function (x) { x.pct = round(x.pct * scale, 5); }); used = ingredients.reduce(function (s, x) { return s + x.pct; }, 0); }
    ingredients.push({ name: "Purified water", cn_name: "\u7eaf\u5316\u6c34", pct: round(100 - used, 4), role: "q.s. to 100 %", range: "balance", food_safe: true, note: "\u5b9a\u5bb9\u3002" });
    ingredients.forEach(function (item) { item.role_cn = ROLE_CN[item.role] || item.role; });
    return {
      name: (record.cn_name || record.name) + "\u00b7" + (matrix.cn_name || matrix.name) + "\u539f\u578b", serving_basis: "1 L", ingredients: ingredients,
      process: [
        { step: 1, title: "\u9884\u6eb6\u4fdd\u62a4\u5242", detail: "\u5728 40-50\u00b0C \u7eaf\u5316\u6c34\u4e2d\u6eb6\u89e3\u4fdd\u62a4\u5242\uff0c\u907f\u514d\u7ed3\u5757\u3002" },
        { step: 2, title: "\u7f13\u51b2\u4e0e pH", detail: "\u52a0\u5165\u7f13\u51b2\u76d0\uff0c\u6162\u6162\u8c03\u5230 pH " + ph + "\u3002" },
        { step: 3, title: "\u52a0\u5165\u529f\u80fd\u6210\u5206", detail: "\u52a0\u5165 " + (record.cn_name || record.name) + " \u81f3 " + dose + " mg/L\uff0c\u907f\u5149\u4f4e\u901f\u6405\u62cc\u3002" },
        { step: 4, title: "\u9664\u6c27\u4e0e\u9632\u8150", detail: "\u5145\u6c2e/\u8131\u6c14 10-15 min\uff0c\u6309\u6cd5\u89c4\u52a0\u5165\u9632\u8150\u5242\u3002" },
        { step: 5, title: "\u70ed\u5904\u7406", detail: brief.conditions.process_temp_c + "\u00b0C / " + brief.conditions.process_time_min + " min\uff08\u6216\u7b49\u6548\u5de5\u827a\u9a8c\u8bc1\uff09\u3002" },
        { step: 6, title: "\u704c\u88c5\u4e0e\u51b7\u5374", detail: "\u907f\u5149\u704c\u88c5\uff0c\u5feb\u901f\u51b7\u5374\u5230\u50a8\u5b58\u6e29\u5ea6\u3002" }
      ],
      controls: [
        { parameter: "pH", target: ph + " \u00b1 0.1", why: "\u9178\u662f\u4e3b\u8981\u5931\u6d3b\u53d8\u91cf\u3002" },
        { parameter: "\u5de5\u827a\u6e29\u5ea6/\u65f6\u95f4", target: brief.conditions.process_temp_c + "\u00b0C / " + brief.conditions.process_time_min + " min", why: "\u7d2f\u79ef\u70ed\u8d1f\u8377\u51b3\u5b9a\u4e0d\u53ef\u9006\u5931\u6d3b\u3002" },
        { parameter: "\u6eb6\u89e3\u6c27", target: "\u22641 ppm\uff08\u5982\u53ef\u884c\uff09", why: "\u964d\u4f4e\u6c27\u5316\u3002" },
        { parameter: "\u5149\u7167", target: "\u907f\u5149/UV \u963b\u9694\u5305\u88c5", why: "\u591a\u6570\u8367\u5149\u56e2\u5bf9\u5149\u654f\u611f\u3002" }
      ],
      qc: [
        { test: "\u8367\u5149\u53d1\u5c04\u5149\u8c31", method: "\u8367\u5149\u5206\u5149\u5149\u5ea6\u8ba1", acceptance: "\u4fdd\u7559\u7387 \u2265 " + Math.round(brief.spectral.target_retention * 100) + "%\uff0c\u0394\u03bbem \u2264 3 nm", stage: "0h/\u52a0\u901f/\u8d27\u67b6\u671f" },
        { test: "UV-Vis", method: "1 cm \u6bd4\u8272\u76bf", acceptance: "\u7279\u5f81\u5cf0\u4f4d\u7f6e\u4e0d\u6f02\u79fb", stage: "\u6bcf\u6279" },
        { test: "pH", method: "\u6821\u51c6 pH \u8ba1", acceptance: ph + " \u00b1 0.1", stage: "\u6bcf\u6279" },
        { test: "\u5fae\u751f\u7269", method: "\u6309\u4ea7\u54c1\u6807\u51c6", acceptance: "\u7b26\u5408\u6cd5\u89c4", stage: "\u6bcf\u6279" }
      ],
      storage: "\u6570\u5b57\u5b6a\u751f\u9884\u6d4b\uff1a" + brief.conditions.shelf_days + " \u5929\u540e\u4fdd\u7559\u7387 " + Math.round(selected.metrics.overall_retention * 1000) / 10 + "%\uff08" + brief.conditions.storage_temp_c + "\u00b0C\uff09\u3002\u5fc5\u987b\u505a\u771f\u5b9e\u6837\u54c1\u5b9e\u6d4b\u3002",
      packaging: "\u907f\u5149\u73bb\u7483/\u9ad8\u963b\u9694 PET\uff1b\u53ef\u9009\u6c27\u6c14\u6e05\u9664\u5242\u548c\u6c2e\u6c14\u9876\u7a7a\u3002",
      regulatory: ["\u672c\u914d\u65b9\u662f\u6570\u5b57\u539f\u578b\uff0c\u4e0d\u662f\u98df\u54c1\u5b89\u5168\u751f\u4ea7\u8bb8\u53ef\u3002", food ? "\u6240\u6709\u914d\u6599\u5fc5\u987b\u7b26\u5408\u9500\u552e\u5730\u6cd5\u89c4\u548c\u6700\u5927\u4f7f\u7528\u91cf\u3002" : "\u7814\u7a76\u7528\u9014\uff0c\u4e0d\u6784\u6210\u98df\u54c1/\u836f\u54c1\u5408\u89c4\u58f0\u660e\u3002"],
      warnings: ["\u9700\u8981\u771f\u5b9e\u4e2d\u8bd5\u3001\u611f\u5b98\u548c\u6cd5\u89c4\u590d\u6838\u3002"],
      cost_note: "\u6210\u672c\u672a\u542b\u8868\u8fbe\u7eaf\u5316\u548c\u68c0\u6d4b\uff1b\u8bf7\u7528\u672c\u5730\u4f9b\u5e94\u5546\u62a5\u4ef7\u66ff\u6362\u3002"
    };
  }
  function offlineValidation(selected, brief) {
    return {
      summary: "\u79bb\u7ebf\u6a21\u5f0f\u63d0\u4f9b\u7b80\u5316\u9a8c\u8bc1\u65b9\u6848\uff1b\u5b8c\u6574 MD/QM \u547d\u4ee4\u4e0e\u5feb\u901f\u68c0\u67e5\u9700\u8fde\u63a5\u670d\u52a1\u5668\u3002",
      quick_checks: { molecular_mechanics: { available: false, reason: "\u79bb\u7ebf\u6a21\u5f0f\u4e0d\u8fd0\u884c\uff1b\u670d\u52a1\u5668\u7aef\u53ef\u7528 RDKit" }, quantum_mechanics: { available: false, reason: "\u79bb\u7ebf\u6a21\u5f0f\u4e0d\u8fd0\u884c\uff1b\u670d\u52a1\u5668\u7aef\u53ef\u9009 PySCF" } },
      md: { protocol: ["\u51c6\u5907\u7ed3\u6784\u3001\u8d28\u5b50\u5316\u72b6\u6001\u4e0e\u529b\u573a\u3002", "\u6eb6\u5242\u5316\u3001\u4e2d\u548c\u3001\u52a0\u76d0\u3002", "\u80fd\u91cf\u6700\u5c0f\u5316\u4e0e NVT/NPT \u5e73\u8861\u3002", "3 \u00d7 100 ns \u751f\u4ea7 MD\uff0c\u5206\u6790 RMSD/RMSF/Rg/SASA/\u6c22\u952e\u3002", "\u5728\u5de5\u827a\u6e29\u5ea6\u548c\u50a8\u5b58\u6e29\u5ea6\u4e0b\u91cd\u590d\u3002"] },
      qm: { protocol: ["\u6784\u5efa\u8272\u56e2/\u4fdd\u62a4\u5242\u6a21\u578b\u3002", "B3LYP-D3/def2-SVP \u4f18\u5316\u5e76\u505a\u9891\u7387\u786e\u8ba4\u3002", "TD-DFT \u8ba1\u7b97\u6fc0\u53d1\u6001\u4e0e\u53d1\u5c04\u3002", "\u4e0e\u5b9e\u6d4b\u5149\u8c31\u6bd4\u8f83\uff0c\u62a5\u544a\u65b9\u6cd5\u4e0d\u786e\u5b9a\u5ea6\u3002"] },
      experimental: { design: "\u968f\u673a\u3001\u76f2\u6cd5\u3001\u914d\u5bf9\u8bbe\u8ba1\uff1b\u22653 \u6279\u6b21 \u00d7 \u22653 \u6280\u672f\u91cd\u590d\u3002", samples: ["\u5bf9\u7167\u3001\u914d\u65b9\u3001\u70ed/\u9178/\u5149\u6c27\u6311\u6218\u3001\u8d27\u67b6\u671f\u70b9\u3002"], statistics: ["\u62a5\u544a\u5747\u503c\u00b1SD \u4e0e 95% CI\uff1b\u9884\u6ce8\u518c\u7b49\u6548\u8fb9\u754c\u3002"], acceptance: ["\u2265" + Math.round(brief.spectral.target_retention * 100) + "% \u4fdd\u7559\u7387\u4e0e \u0394\u03bbem \u2264 3 nm\u3002"] },
      digital_twin: { status: "computed", predicted_overall_retention: selected.metrics.overall_retention, target: brief.spectral.target_retention },
      limitations: ["\u79bb\u7ebf\u6a21\u5f0f\u4e0d\u4f1a\u4ee3\u66ff\u5b9e\u9a8c\u9a8c\u8bc1\u3002", "\u86cb\u767d\u8d28\u53ef\u80fd\u7f3a\u5c11\u5b9e\u9a8c\u7ed3\u6784\u3002", "\u6cd5\u89c4\u4e0e\u5b89\u5168\u6027\u4e0d\u5728\u6a21\u578b\u8303\u56f4\u5185\u3002"]
    };
  }
  function logicChain(brief, selected) {
    var nodes = [
      { id: "query", label: "\u81ea\u7136\u8bed\u8a00\u9700\u6c42", detail: brief.query.slice(0, 120), status: "computed" },
      { id: "constraints", label: "\u7ea6\u675f\u89e3\u6790", detail: "pH " + brief.conditions.ph + "; " + brief.conditions.process_temp_c + "\u00b0C/" + brief.conditions.process_time_min + " min", status: "computed" },
      { id: "db", label: "\u672c\u5730\u6570\u636e\u5305", detail: D.proteins.items.length + " \u86cb\u767d + " + D.compounds.items.length + " \u5c0f\u5206\u5b50", status: "computed" },
      { id: "screen", label: "\u5019\u9009\u7b5b\u9009", detail: selected.cn_name + " " + selected.score, status: "computed" },
      { id: "blend", label: "\u4fdd\u62a4\u5242\u4f18\u5316", detail: selected.blend.map(function (x) { return x.cn_name + " " + x.pct + "%"; }).join("\u3001") || "\u65e0", status: "computed" },
      { id: "twin", label: "\u6570\u5b57\u5b6a\u751f", detail: "\u4fdd\u7559 " + Math.round(selected.metrics.overall_retention * 1000) / 10 + "%", status: "computed" },
      { id: "spectra", label: "\u5149\u8c31\u6a21\u62df", detail: "\u0394\u03bbem " + selected.metrics.spectral.delta_em_nm + " nm", status: "computed" },
      { id: "md", label: "MD \u9a8c\u8bc1", detail: "\u9700\u670d\u52a1\u5668/HPC", status: "planned" },
      { id: "qm", label: "QM \u9a8c\u8bc1", detail: "\u9700\u670d\u52a1\u5668/HPC", status: "planned" },
      { id: "formulation", label: "\u914d\u65b9\u4e0e\u5de5\u827a", detail: "\u914d\u6599\u3001pH/\u6c27/\u5149\u63a7\u5236", status: "computed" },
      { id: "lab", label: "\u7ebf\u4e0b\u5b9e\u9a8c\u5305", detail: "\u6837\u54c1/\u4eea\u5668/\u7edf\u8ba1", status: "planned" }
    ];
    var edges = [["query", "constraints"], ["constraints", "db"], ["db", "screen"], ["screen", "blend"], ["blend", "twin"], ["twin", "spectra"], ["spectra", "md"], ["md", "qm"], ["spectra", "formulation"], ["formulation", "lab"], ["qm", "lab"]];
    return { nodes: nodes, edges: edges.map(function (e) { return { from: e[0], to: e[1] }; }) };
  }
  function spectralMatch(peaks, type, tolerance) {
    if (!peaks || !peaks.length) return { query: [], matches: [], note: "no query peaks" };
    var normalized = peaks.map(function (p) { return Array.isArray(p) ? [Number(p[0]), Number(p[1] === undefined ? 1 : p[1])] : [Number(p), 1]; });
    var defaults = { "UV-Vis": 10, "IR": 20, "MS": 0.5, "1H-NMR": 0.12 };
    var tol = tolerance || defaults[type] || 10;
    var results = D.spectra.items.filter(function (s) { return s.type === type; }).map(function (spec) {
      var score = 0, coverage = 0;
      normalized.forEach(function (q) {
        var nearest = spec.peaks[0], best = Infinity;
        spec.peaks.forEach(function (r) { var d = Math.abs(r[0] - q[0]); if (d < best) { best = d; nearest = r; } });
        if (best <= tol) { coverage++; score += q[1] * nearest[1] * Math.exp(-0.5 * Math.pow(best / Math.max(1e-9, tol / 2), 2)); }
      });
      score /= Math.max(1, normalized.length);
      return { spectrum_id: spec.id, compound_id: spec.compound_id, type: spec.type, score: round(clamp(score), 4), coverage: round(coverage / Math.max(1, normalized.length), 4), reference_peaks: spec.peaks, notes: spec.notes };
    });
    results.sort(function (a, b) { return b.score - a.score; });
    return { query: normalized.map(function (p) { return { position: p[0], intensity: p[1] }; }), type: type, tolerance: tol, matches: results.slice(0, 5), note: "\u79bb\u7ebf\u8c31\u5e93\u5339\u914d\uff0c\u4e0d\u80fd\u66ff\u4ee3\u6807\u51c6\u54c1\u3002" };
  }
  function makeCsv(result) {
    var lines = ["table,key,value,extra"];
    result.formulation.ingredients.forEach(function (item) { lines.push(["ingredients", item.name, item.pct, item.role].join(",")); });
    result.candidates.forEach(function (item) { lines.push(["candidates", item.id, item.score, "retention=" + item.metrics.overall_retention + ";meets=" + item.meets_spec].join(",")); });
    ["temperature", "ph", "time", "storage", "dose_response"].forEach(function (key) {
      var block = result.virtual_experiment[key];
      (block.x || []).forEach(function (x, i) { lines.push(["virtual_" + key, x, (block.optimized || [])[i], ""].join(",")); });
    });
    lines.push(["monte_carlo", "mean", result.virtual_experiment.monte_carlo.mean, ""].join(","));
    lines.push(["monte_carlo", "prob_meet_target", result.virtual_experiment.monte_carlo.prob_meet_target, ""].join(","));
    return lines.join("\n");
  }
  function makeJson(result) { return JSON.stringify(result, null, 2); }
  function makeReportHtml(result, images) {
    images = images || {};
    var esc = function (value) { return String(value === undefined || value === null ? "" : value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); };
    var rows = result.formulation.ingredients.map(function (item) { return "<tr><td>" + esc(item.cn_name || item.name) + "</td><td>" + item.pct + "</td><td>" + esc(item.role_cn || item.role) + "</td></tr>"; }).join("");
    var candidateRows = result.candidates.slice(0, 8).map(function (item) { return "<tr><td>" + esc(item.cn_name) + "</td><td>" + item.score + "</td><td>" + Math.round(item.metrics.overall_retention * 1000) / 10 + "%</td><td>" + item.metrics.spectral.delta_em_nm + " nm</td><td>" + (item.meets_spec ? "\u662f" : "\u5426") + "</td></tr>"; }).join("");
    var chartHtml = Object.keys(images).map(function (key) { return "<div class='chart'><img src='" + images[key] + "' alt='" + key + "'></div>"; }).join("");
    var warningHtml = result.warnings.map(function (item) { return "<li>" + esc(item) + "</li>"; }).join("");
    return "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>BioForge \u79bb\u7ebf\u62a5\u544a</title><style>body{font-family:system-ui,'Noto Sans CJK SC',sans-serif;background:#fbfaf5;color:#102a2e;margin:0;padding:22px;line-height:1.6}h1{font-size:24px}table{width:100%;border-collapse:collapse;background:#fff;font-size:13px;margin:10px 0}th,td{border:1px solid #d8e3df;padding:6px 8px;text-align:left}th{background:#e9f4f1}img{max-width:100%;border:1px solid #d8e3df;border-radius:8px}.chart{margin:12px 0}.warn{background:#fff1ec;border:1px solid #f3b7a5;border-radius:10px;padding:10px 14px}.note{background:#fff8e8;border:1px solid #f0d79a;border-radius:10px;padding:10px 14px}small{color:#5f7670}</style></head><body><h1>BioForge \u79bb\u7ebf\u8bbe\u8ba1\u62a5\u544a</h1><p><small>" + esc(result.created_utc) + " \u00b7 " + esc(result.selected.cn_name) + " \u00b7 " + esc(result.formulation.name) + "</small></p><div class='note'><b>\u7ed3\u8bba\uff1a</b>" + esc(result.decision_summary[0] + " " + result.decision_summary[3]) + "</div><div class='warn'><b>\u91cd\u8981\u8fb9\u754c\uff1a</b><ul>" + warningHtml + "</ul></div><h2>\u5019\u9009\u6392\u5e8f</h2><table><tr><th>\u5019\u9009</th><th>\u8bc4\u5206</th><th>\u4fdd\u7559\u7387</th><th>\u0394\u03bbem</th><th>\u8fbe\u6807</th></tr>" + candidateRows + "</table><h2>\u914d\u65b9</h2><table><tr><th>\u914d\u6599</th><th>% w/w</th><th>\u4f5c\u7528</th></tr>" + rows + "</table>" + chartHtml + "<h2>\u9650\u5236</h2><ul><li>\u4ec5\u7528\u4e8e\u7814\u7a76\u4e0e\u8bbe\u8ba1\u51b3\u7b56\u652f\u6301\uff0c\u4e0d\u662f\u6cd5\u89c4\u6216\u98df\u54c1\u5b89\u5168\u6279\u51c6\u3002</li><li>\u79bb\u7ebf\u6a21\u5f0f\u4e0d\u4f1a\u4ee3\u66ff\u771f\u5b9e\u5b9e\u9a8c\uff1b\u8bf7\u8fde\u63a5\u670d\u52a1\u5668\u751f\u6210\u5b8c\u6574\u62a5\u544a\u3001GIF/\u89c6\u9891\u4e0e MD/QM \u65b9\u6848\u3002</li></ul></body></html>";
  }
  window.BioForgeOffline = {
    version: "1.0.0-offline",
    parseBrief: parseBrief,
    design: design,
    spectralMatch: spectralMatch,
    makeCsv: makeCsv,
    makeJson: makeJson,
    makeReportHtml: makeReportHtml,
    data: D
  };
})();
