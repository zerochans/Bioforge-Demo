from __future__ import annotations

import base64
import csv
import html
import io
import json
import os
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from PIL import Image, ImageDraw, ImageFont

from . import data

PALETTE = {
    "ink": "#102a2e",
    "teal": "#0d7f76",
    "teal_soft": "#8fd3c7",
    "coral": "#e76f51",
    "gold": "#e9b949",
    "blue": "#3d6fa5",
    "grid": "#d8e3df",
    "paper": "#fbfaf5",
}


def _setup_fonts() -> None:
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        "/usr/share/fonts/wps-fonts/STSONG.TTF",
    ]
    family = "DejaVu Sans"
    for path in candidates:
        if Path(path).exists():
            try:
                font_manager.fontManager.addfont(path)
                family = font_manager.FontProperties(fname=path).get_name()
                break
            except Exception:
                continue
    plt.rcParams["font.family"] = family
    plt.rcParams["font.sans-serif"] = [family, "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.facecolor"] = PALETTE["paper"]
    plt.rcParams["axes.facecolor"] = PALETTE["paper"]
    plt.rcParams["axes.edgecolor"] = "#9ab5ad"
    plt.rcParams["axes.labelcolor"] = PALETTE["ink"]
    plt.rcParams["text.color"] = PALETTE["ink"]
    plt.rcParams["xtick.color"] = PALETTE["ink"]
    plt.rcParams["ytick.color"] = PALETTE["ink"]
    plt.rcParams["grid.color"] = PALETTE["grid"]
    plt.rcParams["grid.alpha"] = 0.55


_setup_fonts()


def _save(fig, path: Path) -> Path:
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=PALETTE["paper"])
    plt.close(fig)
    return path


def _clean_axes(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, alpha=0.6)


def _artifacts_dir(result: dict[str, Any]) -> Path:
    job_dir = data.JOBS_DIR / result["job_id"]
    (job_dir / "charts").mkdir(parents=True, exist_ok=True)
    return job_dir


def make_charts(result: dict[str, Any]) -> dict[str, str]:
    job_dir = _artifacts_dir(result)
    charts = job_dir / "charts"
    selected = result["selected"]
    metrics = selected["metrics"]
    virtual = result["virtual_experiment"]
    brief = result["brief"]
    cond = brief["conditions"]
    paths: dict[str, str] = {}

    ax_title = f"{selected.get('cn_name', selected['id'])} · 数字孪生"
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    ax.plot(virtual["temperature"]["x"], virtual["temperature"]["base"], color="#9aa7a3", lw=1.6, label="无保护剂")
    ax.plot(virtual["temperature"]["x"], virtual["temperature"]["optimized"], color=PALETTE["teal"], lw=2.5, label="优化配方")
    ax.axvline(cond["process_temp_c"], color=PALETTE["coral"], ls="--", lw=1.2)
    ax.text(cond["process_temp_c"] + 1, 0.08, f"工艺 {cond['process_temp_c']:g}°C", color=PALETTE["coral"], fontsize=9)
    ax.set_xlabel("温度 / °C")
    ax.set_ylabel("荧光保留率")
    ax.set_ylim(0, 1.05)
    ax.set_title(f"{ax_title} · 温度响应")
    ax.legend(frameon=False, loc="upper right")
    _clean_axes(ax)
    paths["temperature"] = str(_save(fig, charts / "retention_temperature.png"))

    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    ax.plot(virtual["ph"]["x"], virtual["ph"]["base"], color="#9aa7a3", lw=1.6, label="无保护剂")
    ax.plot(virtual["ph"]["x"], virtual["ph"]["optimized"], color=PALETTE["teal"], lw=2.5, label="优化配方")
    ax.axvline(cond["ph"], color=PALETTE["coral"], ls="--", lw=1.2)
    ax.text(cond["ph"] + 0.08, 0.08, f"目标 pH {cond['ph']:g}", color=PALETTE["coral"], fontsize=9)
    ax.set_xlabel("pH")
    ax.set_ylabel("荧光保留率")
    ax.set_ylim(0, 1.05)
    ax.set_title(f"{ax_title} · pH 响应")
    ax.legend(frameon=False, loc="lower right")
    _clean_axes(ax)
    paths["ph"] = str(_save(fig, charts / "retention_ph.png"))

    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.4))
    ax = axes[0]
    ax.plot(virtual["time"]["x"], virtual["time"]["base"], color="#9aa7a3", lw=1.6, label="无保护剂")
    ax.plot(virtual["time"]["x"], virtual["time"]["optimized"], color=PALETTE["teal"], lw=2.5, label="优化配方")
    ax.set_xlabel("工艺时间 / min")
    ax.set_ylabel("保留率")
    ax.set_ylim(0, 1.05)
    ax.set_title(f"工艺动力学 @ {cond['process_temp_c']:g}°C")
    ax.legend(frameon=False)
    _clean_axes(ax)
    ax = axes[1]
    ax.plot(virtual["storage"]["x"], virtual["storage"]["optimized"], color=PALETTE["blue"], lw=2.5)
    ax.axhline(brief["spectral"]["target_retention"], color=PALETTE["coral"], ls="--", lw=1.1)
    ax.set_xlabel("储存天数 / day")
    ax.set_ylabel("保留率")
    ax.set_ylim(0, 1.05)
    ax.set_title(f"货架期 @ {cond['storage_temp_c']:g}°C")
    _clean_axes(ax)
    fig.suptitle(f"{ax_title} · 动力学", fontsize=11)
    fig.tight_layout()
    paths["kinetics"] = str(_save(fig, charts / "kinetics.png"))

    spectra = result["spectra"]["fluorescence"]
    wave = np.array(spectra["wavelength_nm"])
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.5))
    ax = axes[0]
    ax.plot(wave, spectra["emission_reference"], color="#9aa7a3", lw=2, label="未胁迫参考")
    ax.plot(wave, spectra["emission_stressed"], color=PALETTE["teal"], lw=2.4, label="优化配方")
    ax.fill_between(wave, spectra["emission_stressed"], color=PALETTE["teal_soft"], alpha=0.25)
    ax.set_xlabel("波长 / nm")
    ax.set_ylabel("归一化荧光")
    ax.set_title("荧光发射光谱")
    ax.legend(frameon=False)
    _clean_axes(ax)
    ax = axes[1]
    uv_wave = np.array(spectra["uvvis_wavelength_nm"])
    ax.plot(uv_wave, spectra["uvvis_reference"], color="#9aa7a3", lw=2, label="未胁迫参考")
    ax.plot(uv_wave, spectra["uvvis_stressed"], color=PALETTE["coral"], lw=2.4, label="优化配方")
    ax.set_xlabel("波长 / nm")
    ax.set_ylabel("归一化吸光度")
    ax.set_title("UV-Vis 吸收光谱")
    ax.legend(frameon=False)
    _clean_axes(ax)
    fig.suptitle(f"{ax_title} · 光谱稳定性（Δλem {metrics['spectral']['delta_em_nm']:.1f} nm）", fontsize=11)
    fig.tight_layout()
    paths["spectra"] = str(_save(fig, charts / "spectra.png"))

    mc = virtual["monte_carlo"]
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    ax.hist(mc["samples"], bins=16, color=PALETTE["teal_soft"], edgecolor=PALETTE["teal"], alpha=0.85)
    ax.axvline(mc["mean"], color=PALETTE["teal"], lw=2, label=f"均值 {mc['mean']:.1%}")
    ax.axvline(brief["spectral"]["target_retention"], color=PALETTE["coral"], ls="--", lw=1.5, label="目标")
    ax.set_xlabel("总保留率")
    ax.set_ylabel("抽样数")
    ax.set_title(f"Monte Carlo 不确定度（P(达标) = {mc['prob_meet_target']:.0%}）")
    ax.legend(frameon=False)
    _clean_axes(ax)
    paths["monte_carlo"] = str(_save(fig, charts / "monte_carlo.png"))

    labels = [item["variable"] for item in virtual["sensitivity"]]
    values = [item["delta_retention"] for item in virtual["sensitivity"]]
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    colors = [PALETTE["coral"] if value < 0 else PALETTE["teal"] for value in values]
    ax.barh(labels, values, color=colors, alpha=0.85)
    ax.axvline(0, color=PALETTE["ink"], lw=1)
    ax.set_xlabel("保留率变化（单变量扰动）")
    ax.set_title("敏感性分析 / 龙卷风图")
    _clean_axes(ax)
    paths["sensitivity"] = str(_save(fig, charts / "sensitivity.png"))

    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    ax.plot(virtual["dose_response"]["x"], virtual["dose_response"]["optimized"], color=PALETTE["gold"], lw=2.6)
    ax.axhline(brief["spectral"]["target_retention"], color=PALETTE["coral"], ls="--", lw=1.2)
    ax.set_xlabel("保护剂总添加量 / % w/w")
    ax.set_ylabel("工艺后保留率")
    ax.set_ylim(0, 1.05)
    ax.set_title("保护剂剂量响应")
    _clean_axes(ax)
    paths["dose_response"] = str(_save(fig, charts / "dose_response.png"))

    reference = result["spectra"].get("reference_peaks", [])
    types = []
    for spec in reference:
        if spec["type"] not in types:
            types.append(spec["type"])
    if types:
        fig, axes = plt.subplots(1, len(types[:4]), figsize=(4.2 * min(4, len(types)), 3.1), squeeze=False)
        for ax, kind in zip(axes[0], types[:4]):
            for spec in reference:
                if spec["type"] != kind:
                    continue
                positions = [peak[0] for peak in spec["peaks"]]
                intensities = [peak[1] for peak in spec["peaks"]]
                ax.vlines(positions, 0, intensities, color=PALETTE["blue"], lw=2)
                ax.scatter(positions, intensities, color=PALETTE["coral"], s=18, zorder=3)
            ax.set_title(kind)
            ax.set_xlabel("位置 / 相对单位")
            ax.set_ylabel("相对强度")
            _clean_axes(ax)
        fig.suptitle("参考谱峰库（近似，仅用于方法开发）", fontsize=11)
        fig.tight_layout()
        paths["four_spectra"] = str(_save(fig, charts / "four_spectra.png"))

    paths["logic_graph"] = str(make_logic_graph(result, charts / "logic_graph.png"))
    return paths


def make_logic_graph(result: dict[str, Any], path: Path) -> Path:
    import networkx as nx
    nodes = result["logic_chain"]["nodes"]
    edges = result["logic_chain"]["edges"]
    graph = nx.DiGraph()
    for node in nodes:
        graph.add_node(node["id"])
    for edge in edges:
        graph.add_edge(edge["from"], edge["to"])
    layers = {
        "query": 0, "constraints": 1, "db": 2, "screen": 3, "blend": 4,
        "twin": 5, "spectra": 6, "md": 7, "qm": 8, "formulation": 7, "lab": 9,
    }
    positions: dict[str, tuple[float, float]] = {}
    layer_nodes: dict[int, list[str]] = {}
    for node in nodes:
        layer_nodes.setdefault(layers.get(node["id"], 5), []).append(node["id"])
    for layer, members in layer_nodes.items():
        count = len(members)
        for index, member in enumerate(members):
            positions[member] = (layer * 2.2, (index - (count - 1) / 2) * 1.9)
    fig, ax = plt.subplots(figsize=(13, 6.4))
    status_color = {"computed": PALETTE["teal"], "planned": PALETTE["gold"], "external": PALETTE["blue"]}
    for node in nodes:
        color = status_color.get(node.get("status", "computed"), PALETTE["teal"])
        ax.scatter(*positions[node["id"]], s=1800, color=color, alpha=0.96, zorder=3, edgecolor="white", linewidth=1.4)
        ax.text(*positions[node["id"]], node["label"], ha="center", va="center", fontsize=8.2, color="white", zorder=4, weight="bold")
    for edge in edges:
        start = positions[edge["from"]]
        end = positions[edge["to"]]
        ax.annotate("", xy=end, xytext=start, arrowprops=dict(arrowstyle="-|>", color="#8aa39b", lw=1.2, shrinkA=18, shrinkB=18), zorder=1)
    ax.set_xlim(-1.2, max(p[0] for p in positions.values()) + 1.2)
    ax.set_ylim(-max(2.2, max(abs(p[1]) for p in positions.values()) + 1.2), max(2.2, max(abs(p[1]) for p in positions.values()) + 1.2))
    ax.axis("off")
    ax.set_title("BioForge 决策链路图（绿=已计算，黄=需外部实验/计算）", fontsize=11, pad=10)
    fig.tight_layout()
    return _save(fig, path)


def _font_for_pillow(size: int = 22):
    for path in (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        "/usr/share/fonts/wps-fonts/STSONG.TTF",
    ):
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size, index=0)
            except Exception:
                continue
    return ImageFont.load_default()


def make_animation(result: dict[str, Any]) -> dict[str, str | None]:
    job_dir = _artifacts_dir(result)
    selected = result["selected"]
    brief = result["brief"]
    virtual = result["virtual_experiment"]
    spectra = result["spectra"]["fluorescence"]
    temps = np.linspace(20.0, 100.0, 17)
    retentions = np.interp(temps, virtual["temperature"]["x"], virtual["temperature"]["optimized"])
    wave = np.array(spectra["wavelength_nm"])
    emission = np.array(spectra["emission_reference"])
    uv_wave = np.array(spectra["uvvis_wavelength_nm"])
    uv_ref = np.array(spectra["uvvis_reference"])
    frames_dir = job_dir / "frames"
    frames_dir.mkdir(exist_ok=True)
    font = _font_for_pillow(26)
    small = _font_for_pillow(18)
    frames = []
    for index, (temp, retention) in enumerate(zip(temps, retentions)):
        fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.4))
        ax = axes[0]
        ax.plot(wave, emission, color="#b7c6c0", lw=1.8, label="参考")
        ax.plot(wave, emission * retention, color=PALETTE["teal"], lw=2.6, label="当前")
        ax.fill_between(wave, emission * retention, color=PALETTE["teal_soft"], alpha=0.3)
        ax.set_xlim(380, 750)
        ax.set_ylim(0, 1.05)
        ax.set_xlabel("波长 / nm")
        ax.set_ylabel("归一化荧光")
        ax.set_title("荧光发射")
        ax.legend(frameon=False, loc="upper right")
        _clean_axes(ax)
        ax = axes[1]
        ax.plot(uv_wave, uv_ref, color="#b7c6c0", lw=1.8, label="参考")
        ax.plot(uv_wave, uv_ref * (0.35 + 0.65 * retention), color=PALETTE["coral"], lw=2.4, label="当前")
        ax.set_xlim(240, 700)
        ax.set_ylim(0, 1.05)
        ax.set_xlabel("波长 / nm")
        ax.set_ylabel("归一化吸光度")
        ax.set_title("UV-Vis")
        _clean_axes(ax)
        fig.suptitle(f"{selected.get('cn_name', selected['id'])} · 加热虚拟实验 · {temp:.0f}°C · 保留 {retention:.0%}", fontsize=11)
        fig.tight_layout()
        frame_path = frames_dir / f"frame_{index:03d}.png"
        fig.savefig(frame_path, dpi=110, facecolor=PALETTE["paper"])
        plt.close(fig)
        frames.append(frame_path)
    gif_path = job_dir / "animation.gif"
    images = [Image.open(path).convert("RGB") for path in frames]
    if images:
        images[0].save(gif_path, save_all=True, append_images=images[1:], duration=260, loop=0, optimize=True)
    mp4_path = job_dir / "animation.mp4"
    mp4_ok = False
    if shutil.which("ffmpeg") and frames:
        command = [
            "ffmpeg", "-y", "-loglevel", "error", "-framerate", "5",
            "-i", str(frames_dir / "frame_%03d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4_path),
        ]
        try:
            subprocess.run(command, check=True, timeout=120)
            mp4_ok = mp4_path.exists() and mp4_path.stat().st_size > 0
        except Exception:
            mp4_ok = False
    shutil.rmtree(frames_dir, ignore_errors=True)
    return {"gif": gif_path.name if gif_path.exists() else None, "mp4": mp4_path.name if mp4_ok else None}


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    head = "".join(f"<th>{html.escape(str(item))}</th>" for item in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(cell))}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _img_tag(path: str | Path, alt: str = "") -> str:
    path = Path(path)
    if not path.exists():
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f'<img alt="{html.escape(alt)}" src="data:image/png;base64,{encoded}">'


def _ingredient_rows(result: dict[str, Any]) -> list[list[str]]:
    return [
        [item["cn_name"] or item["name"], f"{float(item['pct']):.4g}", item.get("role_cn") or item["role"], item.get("range", ""), "是" if item.get("food_safe") else "否/研究级"]
        for item in result["formulation"]["ingredients"]
    ]


def _write_csvs(result: dict[str, Any], job_dir: Path) -> dict[str, str]:
    tables = job_dir / "tables"
    tables.mkdir(exist_ok=True)
    written: dict[str, str] = {}
    ingredients = result["formulation"]["ingredients"]
    with (tables / "ingredients.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["name", "cn_name", "pct_w_w", "dose_mg_l", "role", "range", "food_safe", "note"])
        for item in ingredients:
            writer.writerow([item["name"], item.get("cn_name", ""), item["pct"], item.get("dose_mg_l", ""), item["role"], item.get("range", ""), item.get("food_safe", ""), item.get("note", "")])
    written["ingredients"] = "tables/ingredients.csv"
    candidates = result["candidates"]
    with (tables / "candidates.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "name", "kind", "score", "meets_spec", "tm_eff_c", "overall_retention", "delta_em_nm", "shape_cosine", "food_status", "blend"])
        for item in candidates:
            writer.writerow([
                item["id"], item["name"], item["kind"], item["score"], item["meets_spec"], item["metrics"]["tm_eff_c"],
                item["metrics"]["overall_retention"], item["metrics"]["spectral"]["delta_em_nm"], item["metrics"]["spectral"]["shape_cosine"],
                item["metrics"].get("food_status", ""), "; ".join(f"{x['id']}:{x['pct']}" for x in item["blend"]),
            ])
    written["candidates"] = "tables/candidates.csv"
    virtual = result["virtual_experiment"]
    for key in ("temperature", "ph", "time", "storage", "dose_response"):
        with (tables / f"virtual_{key}.csv").open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["x", "base", "optimized"])
            if "base" in virtual[key]:
                for x, base, opt in zip(virtual[key]["x"], virtual[key]["base"], virtual[key]["optimized"]):
                    writer.writerow([x, base, opt])
            else:
                for x, opt in zip(virtual[key]["x"], virtual[key]["optimized"]):
                    writer.writerow([x, "", opt])
        written[f"virtual_{key}"] = f"tables/virtual_{key}.csv"
    with (tables / "monte_carlo.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        for key, value in virtual["monte_carlo"].items():
            if key != "samples":
                writer.writerow([key, value])
    written["monte_carlo"] = "tables/monte_carlo.csv"
    with (tables / "sensitivity.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["variable", "change", "delta_retention"])
        for item in virtual["sensitivity"]:
            writer.writerow([item["variable"], item["change"], item["delta_retention"]])
    written["sensitivity"] = "tables/sensitivity.csv"
    if result["spectra"].get("reference_peaks"):
        with (tables / "spectral_reference.csv").open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["spectrum_id", "compound_id", "type", "solvent", "position", "relative_intensity", "notes"])
            for spec in result["spectra"]["reference_peaks"]:
                for peak in spec["peaks"]:
                    writer.writerow([spec["id"], spec["compound_id"], spec["type"], spec.get("solvent", ""), peak[0], peak[1], spec.get("notes", "")])
        written["spectral_reference"] = "tables/spectral_reference.csv"
    combined = job_dir / "dataset.csv"
    with combined.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["table", "key", "value", "extra"])
        for item in ingredients:
            writer.writerow(["ingredients", item["name"], item["pct"], f"{item['role']}; food_safe={item.get('food_safe')}"])
        for item in candidates:
            writer.writerow(["candidates", item["id"], item["score"], f"retention={item['metrics']['overall_retention']}; meets={item['meets_spec']}"])
        for key in ("temperature", "ph", "time", "storage", "dose_response"):
            for x, opt in zip(virtual[key]["x"], virtual[key]["optimized"]):
                writer.writerow([f"virtual_{key}", x, opt, ""])
        for item in virtual["sensitivity"]:
            writer.writerow(["sensitivity", item["variable"], item["delta_retention"], item["change"]])
        writer.writerow(["monte_carlo", "mean", virtual["monte_carlo"]["mean"], ""])
        writer.writerow(["monte_carlo", "p05", virtual["monte_carlo"]["p05"], ""])
        writer.writerow(["monte_carlo", "p95", virtual["monte_carlo"]["p95"], ""])
        writer.writerow(["monte_carlo", "prob_meet_target", virtual["monte_carlo"]["prob_meet_target"], ""])
    written["dataset"] = "dataset.csv"
    return written


def build_html(result: dict[str, Any], charts: dict[str, str], job_dir: Path) -> Path:
    brief = result["brief"]
    selected = result["selected"]
    metrics = selected["metrics"]
    formulation = result["formulation"]
    virtual = result["virtual_experiment"]
    validation = result["validation"]
    css = """
    :root { --ink:#102a2e; --teal:#0d7f76; --coral:#e76f51; --gold:#e9b949; --paper:#fbfaf5; --line:#d8e3df; }
    * { box-sizing: border-box; }
    body { margin:0; background:var(--paper); color:var(--ink); font-family: "Noto Sans CJK SC","Noto Sans CJK JP","WenQuanYi Micro Hei",Arial,sans-serif; line-height:1.65; }
    .wrap { max-width: 1120px; margin: 0 auto; padding: 28px 24px 60px; }
    header { border-bottom: 3px solid var(--teal); padding-bottom: 16px; margin-bottom: 22px; }
    .brand { font-size: 13px; letter-spacing: .18em; color: var(--teal); font-weight: 700; text-transform: uppercase; }
    h1 { margin: 6px 0 4px; font-size: 30px; line-height: 1.25; }
    h2 { margin: 34px 0 12px; font-size: 21px; border-left: 5px solid var(--teal); padding-left: 10px; }
    h3 { margin: 20px 0 8px; font-size: 16px; }
    .meta { color:#5f7670; font-size: 13px; }
    .grid { display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 12px; }
    .kpi { background:#fff; border:1px solid var(--line); border-radius:12px; padding:12px 14px; }
    .kpi .label { font-size: 12px; color:#5f7670; }
    .kpi .value { font-size: 22px; font-weight: 800; color:var(--teal); margin-top: 2px; }
    .note { background:#fff8e8; border:1px solid #f0d79a; border-radius:10px; padding:12px 14px; margin:12px 0; }
    .warning { background:#fff1ec; border:1px solid #f3b7a5; border-radius:10px; padding:12px 14px; margin:12px 0; }
    .ok { color:#0d7f76; font-weight:700; } .bad { color:#c44f39; font-weight:700; }
    table { width:100%; border-collapse:collapse; background:#fff; border:1px solid var(--line); border-radius:10px; overflow:hidden; font-size:13px; }
    th { background:#e9f4f1; text-align:left; padding:8px 10px; font-weight:700; }
    td { border-top:1px solid var(--line); padding:8px 10px; vertical-align:top; }
    .cols { display:grid; grid-template-columns: 1fr 1fr; gap:18px; }
    .card { background:#fff; border:1px solid var(--line); border-radius:14px; padding:16px 18px; }
    img { max-width:100%; height:auto; border-radius:8px; border:1px solid var(--line); background:#fff; }
    .chart { margin:10px 0 22px; }
    code, pre { background:#102a2e; color:#e8f4ef; border-radius:8px; padding:2px 6px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
    pre { padding:12px; overflow:auto; font-size:12px; line-height:1.45; }
    ul, ol { padding-left: 22px; }
    .pill { display:inline-block; padding:2px 9px; border-radius:999px; font-size:12px; background:#e9f4f1; color:var(--teal); margin-right:6px; }
    .small { font-size:12px; color:#5f7670; }
    footer { margin-top: 40px; border-top:1px solid var(--line); padding-top:14px; color:#5f7670; font-size:12px; }
    @media (max-width: 820px) { .grid { grid-template-columns: repeat(2,1fr); } .cols { grid-template-columns: 1fr; } h1 { font-size:24px; } }
    @media print { body { background:#fff; } .wrap { max-width:none; padding:0; } .card, table, .kpi { break-inside: avoid; } }
    """
    parts = [
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>BioForge 设计报告 · {html.escape(selected.get('cn_name', selected['id']))}</title>",
        f"<style>{css}</style></head><body><div class='wrap'>",
        "<header><div class='brand'>BioForge Studio · In-silico design report</div>",
        f"<h1>{html.escape(selected.get('cn_name', selected['id']))} · {html.escape(formulation['name'])}</h1>",
        f"<div class='meta'>Job {html.escape(result['job_id'])} · {html.escape(result['created_utc'])} · Engine {html.escape(result['engine_version'])} · 仅用于研究与设计决策支持</div></header>",
        "<div class='grid'>",
        f"<div class='kpi'><div class='label'>预测总保留率</div><div class='value'>{metrics['overall_retention']:.1%}</div><div class='small'>目标 {brief['spectral']['target_retention']:.0%}</div></div>",
        f"<div class='kpi'><div class='label'>有效 Tm</div><div class='value'>{metrics['tm_eff_c']:.1f}°C</div><div class='small'>原始 {metrics['tm_c']:.1f}°C</div></div>",
        f"<div class='kpi'><div class='label'>Δλem</div><div class='value'>{metrics['spectral']['delta_em_nm']:.1f} nm</div><div class='small'>谱形余弦 {metrics['spectral']['shape_cosine']:.3f}</div></div>",
        f"<div class='kpi'><div class='label'>P(达标)</div><div class='value'>{virtual['monte_carlo']['prob_meet_target']:.0%}</div><div class='small'>Monte Carlo n={virtual['monte_carlo']['n']}</div></div>",
        "</div>",
        "<div class='note'><b>一句话结论：</b>" + html.escape(result['decision_summary'][0] + ' ' + result['decision_summary'][3]) + "</div>",
    ]
    if result.get("warnings"):
        parts.append("<div class='warning'><b>重要边界：</b><ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in result["warnings"]) + "</ul></div>")
    parts.append("<h2>1. 需求解析与设计约束</h2><div class='cols'><div class='card'>")
    parts.append("<p><b>原始需求：</b>" + html.escape(brief["query"]) + "</p>")
    parts.append("<p><b>目标类型：</b>" + html.escape(brief["target_kind"]) + " / " + html.escape(brief["mode"]) + "</p>")
    parts.append("<p><b>条件：</b>pH " + f"{brief['conditions']['ph']:g}" + " · " + f"{brief['conditions']['process_temp_c']:g}°C / {brief['conditions']['process_time_min']:g} min" + " · 储存 " + f"{brief['conditions']['storage_temp_c']:g}°C / {brief['conditions']['shelf_days']} d" + "</p>")
    parts.append("<p><b>输出：</b>" + "、".join(html.escape(item) for item in brief["outputs"]) + "</p></div><div class='card'><b>模型假设</b><ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in brief["assumptions"]) + "</ul></div></div>")
    parts.append("<h2>2. 候选筛选与决策依据</h2>")
    rows = []
    for item in result["candidates"][:8]:
        rows.append([
            item["cn_name"], item["kind"], f"{item['score']:.3f}", f"{item['metrics']['overall_retention']:.1%}",
            f"{item['metrics']['tm_eff_c']:.1f}", f"{item['metrics']['spectral']['delta_em_nm']:.1f}",
            "是" if item["meets_spec"] else "否",
            "、".join(f"{x['cn_name']} {x['pct']:g}%" for x in item["blend"]) or "—",
        ])
    parts.append(_table(["候选", "类型", "综合评分", "预测保留", "Tm_eff/°C", "Δλem/nm", "达标", "保护剂"], rows))
    parts.append("<div class='chart'>" + _img_tag(charts.get("spectra", ""), "光谱稳定性") + "</div>")
    parts.append("<h2>3. 配方与工艺</h2>")
    parts.append(_table(["配料", "% w/w", "作用", "建议范围", "食品级"], _ingredient_rows(result)))
    parts.append("<div class='cols'><div class='card'><h3>工艺步骤</h3><ol>" + "".join(f"<li><b>{html.escape(step['title'])}</b>：{html.escape(step['detail'])}</li>" for step in formulation["process"]) + "</ol></div>")
    parts.append("<div class='card'><h3>关键控制点</h3><ul>" + "".join(f"<li><b>{html.escape(item['parameter'])}</b>：{html.escape(item['target'])} <span class='small'>({html.escape(item['why'])})</span></li>" for item in formulation["controls"]) + "</ul></div></div>")
    parts.append("<h3>QC 与货架期</h3>")
    parts.append(_table(["检测", "方法", "验收", "阶段"], [[q["test"], q["method"], q["acceptance"], q["stage"]] for q in formulation["qc"]]))
    parts.append("<div class='note'>" + html.escape(formulation["storage"]) + "</div>")
    parts.append("<h2>4. 虚拟实验与不确定度</h2>")
    for key in ("temperature", "ph", "kinetics", "monte_carlo", "sensitivity", "dose_response"):
        if key in charts:
            parts.append("<div class='chart'>" + _img_tag(charts[key], key) + "</div>")
    parts.append("<div class='cols'><div class='card'><b>Monte Carlo</b>" + _table(["指标", "值"], [
        ["均值", f"{virtual['monte_carlo']['mean']:.1%}"], ["5% 分位", f"{virtual['monte_carlo']['p05']:.1%}"],
        ["95% 分位", f"{virtual['monte_carlo']['p95']:.1%}"], ["达标概率", f"{virtual['monte_carlo']['prob_meet_target']:.0%}"],
    ]) + "</div><div class='card'><b>敏感性</b>" + _table(["变量", "扰动", "Δ保留率"], [[x["variable"], x["change"], f"{x['delta_retention']:+.3f}"] for x in virtual["sensitivity"]]) + "</div></div>")
    parts.append("<h2>5. 光谱与“基本不变”判定</h2>")
    parts.append("<p>预测总保留率 <b>" + f"{metrics['overall_retention']:.1%}" + "</b>；发射峰位移 <b>" + f"{metrics['spectral']['delta_em_nm']:.1f} nm" + "</b>；谱形余弦 <b>" + f"{metrics['spectral']['shape_cosine']:.3f}" + "</b>；判定：<span class='" + ("ok" if selected["meets_spec"] else "bad") + "'>" + ("达到阈值" if selected["meets_spec"] else "未达到阈值") + "</span>。</p>")
    if result["spectra"].get("reference_peaks"):
        parts.append("<h3>参考谱峰（近似）</h3><p class='small'>IR/MS/NMR 是参考峰库与实验方法开发数据，不是从头预测。</p>")
        rows = []
        for spec in result["spectra"]["reference_peaks"]:
            rows.append([spec["id"], spec["type"], spec.get("solvent", ""), ", ".join(f"{p[0]} ({p[1]})" for p in spec["peaks"]), spec.get("notes", "")])
        parts.append(_table(["谱图", "类型", "溶剂", "峰 (相对强度)", "备注"], rows))
        if "four_spectra" in charts:
            parts.append("<div class='chart'>" + _img_tag(charts["four_spectra"], "参考谱峰") + "</div>")
    parts.append("<h2>6. MD / QM / 实验验证方案</h2>")
    parts.append("<p><b>快速检查：</b>MMFF " + ("已运行" if validation["quick_checks"]["molecular_mechanics"].get("available") else "未运行/不适用") + "；QM " + ("已运行" if validation["quick_checks"]["quantum_mechanics"].get("available") else "未运行/不适用") + "。生产级 MD/QM 需要外部引擎，以下是可复现方案。</p>")
    parts.append("<h3>MD 协议</h3><ul>" + "".join(f"<li>{html.escape(step)}</li>" for step in validation["md"]["protocol"]) + "</ul>")
    parts.append("<h3>QM / TD-DFT 协议</h3><ul>" + "".join(f"<li>{html.escape(step)}</li>" for step in validation["qm"]["protocol"]) + "</ul>")
    parts.append("<h3>线下实验设计</h3><ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in validation["experimental"]["design"].split("; ")) + "</ul>")
    parts.append("<div class='chart'>" + _img_tag(charts.get("logic_graph", ""), "决策链路") + "</div>")
    parts.append("<h2>7. 可追溯性与限制</h2>")
    parts.append("<p class='small'>数据包版本：</p><pre>" + html.escape(json.dumps(result["provenance"]["datasets"], ensure_ascii=False, indent=2)) + "</pre>")
    parts.append("<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in result["provenance"]["limitations"]) + "</ul>")
    parts.append("<h2>8. 下一步清单</h2><ol><li>用真实样品复测候选的表达、纯化和光谱。</li><li>按配方做热/酸/光/氧挑战，至少 3 个独立批次。</li><li>运行 MD/QM 方案并与实测光谱比较。</li><li>食品场景完成法规、过敏原、微生物和感官评估。</li><li>把实测数据回填到 App 的反馈接口，启用学习校正。</li></ol>")
    parts.append("<footer>BioForge Studio · " + html.escape(result["job_id"]) + " · 本报告由数字孪生与策展数据生成，不构成法规、医疗或食品安全批准。请保留原始数据、模型版本和实验记录。</footer>")
    parts.append("</div></body></html>")
    path = job_dir / "report.html"
    path.write_text("".join(parts), encoding="utf-8")
    return path


def build_pdf(result: dict[str, Any], charts: dict[str, str], job_dir: Path) -> Path | None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import Image as RLImage
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception:
        return None
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    except Exception:
        return None
    path = job_dir / "report.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=15 * mm, bottomMargin=15 * mm, title="BioForge Design Report", author="BioForge Studio")
    styles = getSampleStyleSheet()
    base = ParagraphStyle("cn", parent=styles["BodyText"], fontName="STSong-Light", fontSize=9.5, leading=15, alignment=TA_LEFT, textColor=colors.HexColor(PALETTE["ink"]))
    title = ParagraphStyle("title", parent=base, fontSize=20, leading=26, spaceAfter=6, textColor=colors.HexColor(PALETTE["teal"]))
    h2 = ParagraphStyle("h2", parent=base, fontSize=14, leading=19, spaceBefore=12, spaceAfter=5, textColor=colors.HexColor(PALETTE["teal"]))
    small = ParagraphStyle("small", parent=base, fontSize=8, leading=12, textColor=colors.HexColor("#5f7670"))
    selected = result["selected"]
    brief = result["brief"]
    metrics = selected["metrics"]
    story = []
    story.append(Paragraph("BioForge Studio · In-silico design report", small))
    story.append(Paragraph(f"{selected.get('cn_name', selected['id'])} · {result['formulation']['name']}", title))
    story.append(Paragraph(f"Job {result['job_id']} · {result['created_utc']} · Engine {result['engine_version']} · 仅用于研究与设计决策支持", small))
    story.append(Spacer(1, 6))
    story.append(Paragraph("一句话结论", h2))
    for line in result["decision_summary"]:
        story.append(Paragraph("• " + html.escape(line), base))
    story.append(Paragraph("关键数字", h2))
    kpi = [
        ["预测总保留率", f"{metrics['overall_retention']:.1%}", "目标", f"{brief['spectral']['target_retention']:.0%}"],
        ["有效 Tm", f"{metrics['tm_eff_c']:.1f}°C", "原始 Tm", f"{metrics['tm_c']:.1f}°C"],
        ["Δλem", f"{metrics['spectral']['delta_em_nm']:.1f} nm", "谱形余弦", f"{metrics['spectral']['shape_cosine']:.3f}"],
        ["P(达标)", f"{result['virtual_experiment']['monte_carlo']['prob_meet_target']:.0%}", "MC n", str(result['virtual_experiment']['monte_carlo']['n'])],
    ]
    table = Table(kpi, colWidths=[35 * mm, 40 * mm, 35 * mm, 40 * mm])
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8d8d3")), ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f4f9f7")), ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"), ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.append(table)
    story.append(Paragraph("配方", h2))
    rows = [[Paragraph(str(item["cn_name"] or item["name"]), base), f"{item['pct']:.4g} %", Paragraph(str(item.get("role_cn") or item["role"]), base)] for item in result["formulation"]["ingredients"]]
    ing_table = Table([["配料", "% w/w", "作用"]] + rows, colWidths=[70 * mm, 25 * mm, 70 * mm])
    ing_table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c8d8d3")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9f4f1")), ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"), ("FONTSIZE", (0, 0), (-1, -1), 7.6), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(ing_table)
    story.append(Paragraph("工艺", h2))
    for step in result["formulation"]["process"]:
        story.append(Paragraph(f"{step['step']}. {html.escape(step['title'])}：{html.escape(step['detail'])}", base))
    for key in ("spectra", "temperature", "ph", "kinetics", "monte_carlo", "sensitivity", "logic_graph"):
        chart_path = Path(charts.get(key, ""))
        if chart_path.exists():
            story.append(Paragraph({"spectra": "光谱", "temperature": "温度响应", "ph": "pH 响应", "kinetics": "动力学", "monte_carlo": "不确定度", "sensitivity": "敏感性", "logic_graph": "决策链路"}.get(key, key), h2))
            width = 170 * mm
            try:
                from PIL import Image as PILImage
                with PILImage.open(chart_path) as im:
                    ratio = im.height / im.width
                story.append(RLImage(str(chart_path), width=width, height=width * ratio))
            except Exception:
                story.append(RLImage(str(chart_path), width=width, height=width * 0.45))
    story.append(Paragraph("验证与限制", h2))
    for line in result["provenance"]["limitations"]:
        story.append(Paragraph("• " + html.escape(line), base))
    story.append(Paragraph("重要边界", h2))
    for line in result["warnings"]:
        story.append(Paragraph("• " + html.escape(line), base))
    story.append(Spacer(1, 6))
    story.append(Paragraph("本报告由数字孪生与策展数据生成，不构成法规、医疗或食品安全批准。请保留原始数据、模型版本和实验记录。", small))
    doc.build(story)
    return path


def build_protocol(result: dict[str, Any], job_dir: Path) -> Path:
    brief = result["brief"]
    selected = result["selected"]
    formulation = result["formulation"]
    validation = result["validation"]
    lines = [
        f"# {selected.get('cn_name', selected['id'])} 实验包",
        "",
        f"- Job: `{result['job_id']}`",
        f"- 生成时间: {result['created_utc']}",
        f"- 目标: {brief['query']}",
        f"- 条件: pH {brief['conditions']['ph']:g}; {brief['conditions']['process_temp_c']:g}°C / {brief['conditions']['process_time_min']:g} min; 储存 {brief['conditions']['storage_temp_c']:g}°C / {brief['conditions']['shelf_days']} d",
        "",
        "## 安全与合规",
        "",
        "- 本实验包仅供研究与设计验证；不是食品/药品/临床批准。",
        "- 荧光蛋白通常不是食品配料；食品场景请使用食品级色素并完成法规评估。",
        "- 佩戴 PPE，按 SDS 处理酸、碱、防腐剂和有机溶剂。",
        "",
        "## 配料表（1 L）",
        "",
        "| 配料 | % w/w | 作用 | 建议范围 |",
        "|---|---:|---|---|",
    ]
    for item in formulation["ingredients"]:
        lines.append(f"| {item['cn_name'] or item['name']} | {item['pct']:.4g} | {item.get('role_cn') or item['role']} | {item.get('range', '')} |")
    lines += ["", "## 工艺", ""]
    for step in formulation["process"]:
        lines.append(f"{step['step']}. **{step['title']}**：{step['detail']}")
    lines += ["", "## 关键控制点", ""]
    for item in formulation["controls"]:
        lines.append(f"- **{item['parameter']}**：{item['target']}（{item['why']}）")
    lines += ["", "## QC", "", "| 检测 | 方法 | 验收 | 阶段 |", "|---|---|---|---|"]
    for item in formulation["qc"]:
        lines.append(f"| {item['test']} | {item['method']} | {item['acceptance']} | {item['stage']} |")
    lines += ["", "## 虚拟实验条件", "", f"- 预测总保留率: {selected['metrics']['overall_retention']:.1%}", f"- 目标: {brief['spectral']['target_retention']:.0%}", f"- Monte Carlo P(达标): {result['virtual_experiment']['monte_carlo']['prob_meet_target']:.0%}", ""]
    lines += ["## MD 协议", ""]
    for step in validation["md"]["protocol"]:
        lines.append(f"- {step}")
    lines += ["", "## QM / TD-DFT 协议", ""]
    for step in validation["qm"]["protocol"]:
        lines.append(f"- {step}")
    lines += ["", "## 实验设计", "", validation["experimental"]["design"], "", "### 样品", ""]
    for item in validation["experimental"]["samples"]:
        lines.append(f"- {item}")
    lines += ["", "### 统计", ""]
    for item in validation["experimental"]["statistics"]:
        lines.append(f"- {item}")
    lines += ["", "## 限制", ""]
    for item in result["provenance"]["limitations"]:
        lines.append(f"- {item}")
    path = job_dir / "protocol.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def build_artifacts(result: dict[str, Any]) -> dict[str, Any]:
    data.ensure_dirs()
    job_dir = _artifacts_dir(result)
    charts = make_charts(result)
    animation = make_animation(result)
    html_path = build_html(result, charts, job_dir)
    pdf_path = build_pdf(result, charts, job_dir)
    protocol_path = build_protocol(result, job_dir)
    tables = _write_csvs(result, job_dir)
    manifest = {
        "job_id": result["job_id"],
        "created_utc": result["created_utc"],
        "engine_version": result["engine_version"],
        "charts": {key: os.path.relpath(value, job_dir) for key, value in charts.items()},
        "animation_gif": animation.get("gif"),
        "animation_mp4": animation.get("mp4"),
        "report_html": html_path.name,
        "report_pdf": pdf_path.name if pdf_path else None,
        "protocol_md": protocol_path.name,
        "tables": tables,
        "note": "All artifacts are generated locally and contain no telemetry.",
    }
    (job_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    readme = (
        "BioForge Studio artifact package\n"
        f"Job: {result['job_id']}\n"
        "Open report.html for the narrative report; report.pdf for a printable version.\n"
        "Charts are in charts/, data tables in tables/, animation.gif/animation.mp4 for the virtual experiment.\n"
        "This package is an in-silico design hypothesis, not a regulatory or food-safety approval.\n"
    )
    (job_dir / "README.txt").write_text(readme, encoding="utf-8")
    zip_path = job_dir / "package.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in ("report.html", "report.pdf", "protocol.md", "dataset.csv", "manifest.json", "README.txt", "animation.gif", "animation.mp4", "logic_graph.png"):
            path = job_dir / name
            if path.exists():
                archive.write(path, arcname=name)
        for folder in ("charts", "tables"):
            base = job_dir / folder
            if base.exists():
                for path in sorted(base.rglob("*")):
                    if path.is_file():
                        archive.write(path, arcname=str(path.relative_to(job_dir)))
    for path in job_dir.rglob("*"):
        if path.is_file():
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
    try:
        os.chmod(job_dir, 0o700)
    except OSError:
        pass
    artifacts = {
        "charts": {key: f"charts/{Path(value).name}" for key, value in charts.items()},
        "animation_gif": "animation.gif" if animation.get("gif") else None,
        "animation_mp4": "animation.mp4" if animation.get("mp4") else None,
        "logic_graph": "charts/logic_graph.png",
        "report_html": "report.html",
        "report_pdf": "report.pdf" if pdf_path else None,
        "protocol_md": "protocol.md",
        "dataset_csv": "dataset.csv",
        "package_zip": "package.zip",
        "manifest": "manifest.json",
        "tables": tables,
    }
    return artifacts


def save_job(result: dict[str, Any]) -> Path:
    job_dir = _artifacts_dir(result)
    path = job_dir / "result.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    _cleanup_jobs(keep=30)
    return path


def _cleanup_jobs(keep: int = 30) -> None:
    jobs = [path for path in data.JOBS_DIR.iterdir() if path.is_dir()] if data.JOBS_DIR.exists() else []
    jobs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    for path in jobs[keep:]:
        shutil.rmtree(path, ignore_errors=True)
