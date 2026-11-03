#!/usr/bin/env python3
"""Build the deterministic synthetic dataset used by the Model Lab demo.

The data are NOT experimental measurements. They exist only to exercise the
import -> train -> optimize -> feedback workflow on a fresh install.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SEED = 20261020
N = 180

PROTEIN_EFFECT = {"whey": 9.0, "soy": 7.0, "pea": 6.0, "casein": 8.0}
HYDRO_STABILITY = {"xanthan": 18.0, "pectin": 12.0, "cmc": 15.0, "guar": 10.0, "none": 0.0}
HYDRO_VISCOSITY = {"xanthan": 78.0, "pectin": 38.0, "cmc": 58.0, "guar": 68.0, "none": 0.0}
SYSTEM_EFFECT = {"beverage": 0.0, "yogurt": 2.0, "sauce": 7.0, "dairy": 4.0}


def clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def main() -> None:
    rng = np.random.default_rng(SEED)
    rows = []
    for i in range(N):
        system = rng.choice(list(SYSTEM_EFFECT), p=[0.31, 0.26, 0.23, 0.20])
        protein = rng.choice(list(PROTEIN_EFFECT), p=[0.40, 0.20, 0.22, 0.18])
        hydro = rng.choice(list(HYDRO_STABILITY), p=[0.18, 0.20, 0.18, 0.16, 0.28])
        protein_pct = float(rng.uniform(0.5, 7.5))
        sugar_pct = float(rng.uniform(0.0, 12.0))
        fat_pct = float(rng.uniform(0.0, 5.5))
        ph = float(rng.uniform(3.3, 6.9))
        bar = float(rng.uniform(30, 300))
        temp = float(rng.uniform(60, 95))
        hold_s = float(rng.choice([5, 10, 15, 20, 30, 45, 60]))
        storage = float(rng.choice([4, 10, 20, 25, 30]))

        stability = (
            14.0
            + SYSTEM_EFFECT[system]
            + 8.5 * protein_pct
            + HYDRO_STABILITY[hydro]
            + 0.030 * bar
            - 5.0 * abs(ph - 6.4)
            - 0.55 * max(0.0, temp - 72.0)
            - 0.32 * max(0.0, storage - 20.0)
            + 0.55 * min(sugar_pct, 8.0)
            + 0.8 * fat_pct
            + 1.6 * math.log1p(hold_s)
            + rng.normal(0, 4.5)
        )
        stability = clip(stability, 4.0, 365.0)

        particle = (
            1950.0
            - 4.7 * bar
            - 32.0 * protein_pct
            + 145.0 * abs(ph - 6.4)
            + 85.0 * abs(temp - 74.0)
            + 35.0 * fat_pct
            + rng.normal(0, 90)
        )
        particle = clip(particle, 70.0, 4200.0)

        viscosity = (
            18.0
            + HYDRO_VISCOSITY[hydro]
            + 16.0 * protein_pct
            + 2.4 * sugar_pct
            + 0.055 * bar
            - 3.0 * abs(ph - 6.0)
            + rng.normal(0, 13)
        )
        viscosity = clip(viscosity, 4.0, 1200.0)

        sensory = (
            7.6
            + 0.10 * fat_pct
            - 0.09 * abs(sugar_pct - 7.0)
            - 0.24 * abs(ph - 5.0)
            + 0.18 * min(protein_pct, 5.0)
            - 0.012 * abs(temp - 75.0)
            + rng.normal(0, 0.35)
        )
        sensory = clip(sensory, 2.5, 10.0)

        row = {
            "sample_id": f"DEMO-{i + 1:03d}",
            "system": system,
            "protein_type": protein,
            "hydrocolloid": hydro,
            "protein_pct": round(protein_pct, 2),
            "sugar_pct": round(sugar_pct, 2),
            "fat_pct": round(fat_pct, 2),
            "ph": round(ph, 2),
            "homogenization_bar": round(bar, 0),
            "pasteurization_temp_c": round(temp, 1),
            "pasteurization_time_s": int(hold_s),
            "storage_temp_c": int(storage),
            "stability_days": round(stability, 1),
            "particle_size_nm": round(particle, 0),
            "viscosity_mpas": round(viscosity, 1),
            "sensory_score": round(sensory, 2),
        }
        rows.append(row)

    for index in (17, 83, 141):
        rows[index]["particle_size_nm"] = ""
    rows[42]["ph"] = ""
    rows[109]["sensory_score"] = ""

    header = list(rows[0].keys())
    DATA.mkdir(parents=True, exist_ok=True)
    csv_path = DATA / "lab_demo.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)

    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    meta = {
        "name": "演示配方实验（合成数据）",
        "source_type": "synthetic",
        "description": "确定性生成的 180 条合成配方-工艺-结果数据，仅用于验证导入、训练、贝叶斯优化与回灌流程；不是实测数据，不能用于真实决策。",
        "generator": "scripts/build_lab_demo.py",
        "seed": SEED,
        "rows": N,
        "columns": header,
        "sha256": digest,
        "target_candidates": ["stability_days", "particle_size_nm", "viscosity_mpas", "sensory_score"],
    }
    (DATA / "lab_demo.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {csv_path} ({N} rows) sha256={digest}")


if __name__ == "__main__":
    main()
