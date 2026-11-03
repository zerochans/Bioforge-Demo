#!/usr/bin/env node
"use strict";
const fs = require("fs");
const path = require("path");

global.window = global;
const root = path.resolve(__dirname, "..");
eval(fs.readFileSync(path.join(root, "web", "data.js"), "utf8"));
eval(fs.readFileSync(path.join(root, "web", "offline.js"), "utf8"));

const queries = [
  "设计一个在72°C、pH 4.0饮料中基本不变的绿色荧光食品配方，总保留率≥80%",
  "Find a fluorescent protein that stays bright after 90°C for 10 minutes at pH 3.5",
  "小分子荧光探针，发射520 nm，用于水相缓冲液，抗光漂白",
  "藻蓝蛋白在酸性饮料中的保护剂组合，pH 4.2，巴氏杀菌72°C/15 s"
];

for (const query of queries) {
  const result = window.BioForgeOffline.design(query);
  const selected = result.selected;
  if (!selected || !result.formulation.ingredients.length) throw new Error("incomplete result for: " + query);
  if (result.virtual_experiment.monte_carlo.n < 100) throw new Error("Monte Carlo missing");
  if (result.spectra.fluorescence.wavelength_nm.length < 100) throw new Error("spectra missing");
  if (BioForgeOffline.makeReportHtml(result, {}).length < 800) throw new Error("report too small");
  if (BioForgeOffline.makeCsv(result).split("\n").length < 10) throw new Error("csv too small");
  console.log(`${query.slice(0, 24)}… -> ${selected.id} (${selected.kind}) score=${selected.score} meets=${selected.meets_spec}`);
}

const match = window.BioForgeOffline.spectralMatch([[370, 1.0], [255, 0.6]], "UV-Vis");
if (!match.matches.length || match.matches[0].compound_id !== "quercetin") throw new Error("spectra match regression");
console.log(`offline check OK: ${queries.length} designs, top match=${match.matches[0].compound_id}`);
