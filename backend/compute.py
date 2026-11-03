from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from . import data

MOLECULE_PYTHON = os.environ.get("BIOFORGE_PYTHON", sys.executable)
GMX = os.environ.get(
    "BIOFORGE_GMX",
    "/home/h3c/softwares/anaconda3/envs/qmmm_env/bin.AVX2_256/gmx",
)
GMXLIB = os.environ.get(
    "BIOFORGE_GMXLIB",
    "/home/h3c/softwares/anaconda3/envs/qmmm_env/share/gromacs/top",
)
CP2K = os.environ.get("BIOFORGE_CP2K", "/home/h3c/softwares/anaconda3/envs/qmmm_env/bin/cp2k.ssmp")
CP2K_DATA = os.environ.get(
    "BIOFORGE_CP2K_DATA",
    "/home/h3c/softwares/anaconda3/envs/qmmm_env/share/cp2k/data",
)
MK_RECEPTOR = os.environ.get(
    "BIOFORGE_MK_RECEPTOR",
    "/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/mk_prepare_receptor.py",
)
MK_LIGAND = os.environ.get(
    "BIOFORGE_MK_LIGAND",
    "/home/h3c/softwares/anaconda3/envs/molecule_tools/bin/mk_prepare_ligand.py",
)
OBABEL = os.environ.get("BIOFORGE_OBABEL", "/home/h3c/softwares/anaconda3/envs/mychem/bin/obabel")
ACPYPE = os.environ.get(
    "BIOFORGE_ACPYPE",
    str(Path(MOLECULE_PYTHON).parent / "acpype"),
)
HADDOCK = os.environ.get(
    "BIOFORGE_HADDOCK",
    str(Path(MOLECULE_PYTHON).parent / "haddock3"),
)
TOOL_SETTINGS_PATH = data.RUNTIME_DIR / "tool_paths.json"
TOOL_PATH_KEYS = ("gromacs", "gromacs_lib", "cp2k", "cp2k_data", "mk_prepare_receptor", "mk_prepare_ligand", "obabel", "haddock")
PDB_CACHE = data.RUNTIME_DIR / "cache" / "pdb"
_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}

PROTEIN_MAP = {
    "whey": ("1BEB", "beta-lactoglobulin", "P02754"),
    "乳清": ("1BEB", "beta-lactoglobulin", "P02754"),
    "lactoglobulin": ("1BEB", "beta-lactoglobulin", "P02754"),
    "gfp": ("1GFL", "green fluorescent protein", "P42212"),
    "lysozyme": ("1LYZ", "lysozyme", "P00698"),
    "溶菌酶": ("1LYZ", "lysozyme", "P00698"),
    "albumin": ("1AO6", "serum albumin", "P02768"),
    "白蛋白": ("1AO6", "serum albumin", "P02768"),
    "phycocyanin": ("1GH0", "C-phycocyanin", "P72509"),
    "藻蓝蛋白": ("1GH0", "C-phycocyanin", "P72509"),
}

LIGAND_MAP = {
    "槲皮素": "quercetin",
    "quercetin": "quercetin",
    "姜黄素": "curcumin",
    "curcumin": "curcumin",
    "咖啡因": "caffeine",
    "caffeine": "caffeine",
    "芦丁": "rutin",
    "rutin": "rutin",
    "白藜芦醇": "resveratrol",
    "resveratrol": "resveratrol",
}

HADDOCK_WORKFLOWS = ("protein-protein", "protein-ligand", "protein-polysaccharide")
CARBOHYDRATE_RESIDUES = {
    "NAG", "NDG", "BMA", "MAN", "GAL", "GLC", "FUC", "SIA", "NGA", "NGL",
    "BGC", "XYS", "RAM", "GUL", "IDR", "QUI", "RHA", "ARA", "XYL", "SOR",
    "FRU", "RIB", "PSI", "TAG", "DAG", "MAL", "SUC", "TRE", "LAT", "GLA",
    "GCS", "GCU", "UDP", "GDP", "ADP", "ALL", "ALT", "API", "BOB", "BDP",
}

LIGAND_SMILES = {
    "quercetin": "C1=CC(=C(C=C1C2=C(C(=O)C3=C(C=C(C=C3O2)O)O)O)O)O",
    "curcumin": "COC1=C(C=CC(=C1)/C=C/C(=O)CC(=O)/C=C/C2=CC(=C(C=C2)O)OC)O",
    "caffeine": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",
    "rutin": "CC1OC(OC2C(O)C(O)C(OC2CO)OC3=C(OC4=CC(=CC(=C4C3=O)O)O)C5=CC(=C(C=C5)O)O)C(O)C(O)C1O",
    "resveratrol": "C1=CC(=CC=C1/C=C/C2=CC(=CC(=C2)O)O)O",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_tool_paths() -> dict[str, str]:
    defaults = {
        "gromacs": GMX,
        "gromacs_lib": GMXLIB,
        "cp2k": CP2K,
        "cp2k_data": CP2K_DATA,
        "mk_prepare_receptor": MK_RECEPTOR,
        "mk_prepare_ligand": MK_LIGAND,
        "obabel": OBABEL,
        "haddock": HADDOCK,
    }
    if TOOL_SETTINGS_PATH.exists():
        try:
            payload = json.loads(TOOL_SETTINGS_PATH.read_text(encoding="utf-8"))
            for key in TOOL_PATH_KEYS:
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    defaults[key] = value.strip()
        except Exception:
            pass
    return defaults


def _apply_tool_paths(paths: dict[str, str]) -> None:
    global GMX, GMXLIB, CP2K, CP2K_DATA, MK_RECEPTOR, MK_LIGAND, OBABEL, HADDOCK
    GMX = paths["gromacs"]
    GMXLIB = paths["gromacs_lib"]
    CP2K = paths["cp2k"]
    CP2K_DATA = paths["cp2k_data"]
    MK_RECEPTOR = paths["mk_prepare_receptor"]
    MK_LIGAND = paths["mk_prepare_ligand"]
    OBABEL = paths["obabel"]
    HADDOCK = paths["haddock"]


def tool_settings() -> dict[str, Any]:
    paths = _load_tool_paths()
    available = {}
    for key, value in paths.items():
        exists = os.path.isdir(value) if key in {"gromacs_lib", "cp2k_data"} else os.path.isfile(value)
        available[key] = bool(exists)
    return {
        "paths": paths,
        "available": available,
        "defaults": {
            "gromacs": "/path/to/gmx",
            "gromacs_lib": "/path/to/share/gromacs/top",
            "cp2k": "/path/to/cp2k.ssmp",
            "cp2k_data": "/path/to/share/cp2k/data",
            "mk_prepare_receptor": "/path/to/mk_prepare_receptor.py",
            "mk_prepare_ligand": "/path/to/mk_prepare_ligand.py",
            "obabel": "/path/to/obabel",
            "haddock": "/path/to/haddock3",
        },
        "editable": list(TOOL_PATH_KEYS),
        "directory_keys": ["gromacs_lib", "cp2k_data"],
    }


def update_tool_settings(payload: dict[str, Any]) -> dict[str, Any]:
    paths = _load_tool_paths()
    errors: dict[str, str] = {}
    for key in TOOL_PATH_KEYS:
        if key not in payload:
            continue
        raw = payload.get(key)
        if not isinstance(raw, str) or not raw.strip():
            errors[key] = "path must be a non-empty string"
            continue
        value = os.path.expanduser(raw.strip())
        if not os.path.isabs(value):
            errors[key] = "path must be absolute"
            continue
        check = os.path.isdir(value) if key in {"gromacs_lib", "cp2k_data"} else os.path.isfile(value)
        if not check:
            errors[key] = "directory not found" if key in {"gromacs_lib", "cp2k_data"} else "file not found"
            continue
        if key not in {"gromacs_lib", "cp2k_data"} and not os.access(value, os.X_OK):
            errors[key] = "file is not executable"
            continue
        paths[key] = value
    if errors:
        raise ValueError(json.dumps(errors, ensure_ascii=False))
    data.ensure_dirs()
    TOOL_SETTINGS_PATH.write_text(json.dumps(paths, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(TOOL_SETTINGS_PATH, 0o600)
    except OSError:
        pass
    _apply_tool_paths(paths)
    return capabilities()


def _int_option(options: dict[str, Any], key: str, default: int, low: int, high: int) -> int:
    try:
        value = int(options.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def _float_option(options: dict[str, Any], key: str, default: float, low: float, high: float) -> float:
    try:
        value = float(options.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def _bool_option(options: dict[str, Any], key: str, default: bool) -> bool:
    value = options.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off", ""}
    return bool(value)


def _normalize_options(options: dict[str, Any] | None) -> dict[str, Any]:
    source = dict(options or {})
    seed_raw = source.get("docking_seed", source.get("seed"))
    try:
        seed = int(seed_raw) if seed_raw not in (None, "") else None
    except (TypeError, ValueError):
        seed = None
    if seed is not None:
        seed = max(0, min(2**31 - 1, seed))
    config = {
        "docking_enabled": _bool_option(source, "docking_enabled", True),
        "docking_exhaustiveness": _int_option(source, "docking_exhaustiveness", 8, 1, 64),
        "docking_poses": _int_option(source, "docking_poses", 9, 1, 20),
        "docking_box_size": _float_option(source, "docking_box_size", 26.0, 16.0, 48.0),
        "docking_seed": seed,
        "md_enabled": _bool_option(source, "md_enabled", True),
        "md_mode": "protein" if str(source.get("md_mode") or "complex").strip().lower() == "protein" else "complex",
        "em_steps": _int_option(source, "em_steps", 5000, 50, 5000),
        "md_steps": _int_option(source, "md_steps", 1000, 100, 100000),
        "dt_ps": _float_option(source, "dt_ps", 0.002, 0.001, 0.004),
        "temperature_k": _float_option(source, "temperature_k", 300.0, 250.0, 400.0),
        "box_padding_nm": _float_option(source, "box_padding_nm", 0.8, 0.6, 1.5),
        "threads": _int_option(source, "threads", min(8, os.cpu_count() or 2), 1, 64),
        "qm_enabled": _bool_option(source, "qm_enabled", True),
        "qm_cutoff_ry": _int_option(source, "qm_cutoff_ry", 300, 150, 600),
        "qm_max_scf": _int_option(source, "qm_max_scf", 30, 10, 200),
        "timeout_prepare": _int_option(source, "timeout_prepare", 300, 30, 7200),
        "timeout_docking": _int_option(source, "timeout_docking", 600, 30, 7200),
        "timeout_em": _int_option(source, "timeout_em", 900, 30, 7200),
        "timeout_md": _int_option(source, "timeout_md", 1800, 30, 7200),
        "timeout_qm": _int_option(source, "timeout_qm", 600, 30, 7200),
        "haddock_enabled": _bool_option(source, "haddock_enabled", False),
        "haddock_workflow": str(source.get("haddock_workflow") or "protein-protein").strip().lower(),
        "haddock_receptor": str(source.get("haddock_receptor") or "").strip()[:120],
        "haddock_receptor_chain": str(source.get("haddock_receptor_chain") or "").strip().upper()[:2],
        "haddock_partner": str(source.get("haddock_partner") or "").strip()[:500],
        "haddock_partner_chain": str(source.get("haddock_partner_chain") or "").strip().upper()[:2],
        "haddock_active_receptor": str(source.get("haddock_active_receptor") or "").strip()[:500],
        "haddock_active_partner": str(source.get("haddock_active_partner") or "").strip()[:500],
        "haddock_restraint_radius": _float_option(source, "haddock_restraint_radius", 6.5, 0.0, 30.0),
        "haddock_max_restraints": _int_option(source, "haddock_max_restraints", 200, 1, 1000),
        "haddock_sampling": _int_option(source, "haddock_sampling", 20, 1, 500),
        "haddock_tolerance": _float_option(source, "haddock_tolerance", 5.0, 0.0, 99.0),
        "haddock_select_top": _int_option(source, "haddock_select_top", 5, 1, 100),
        "haddock_flexref": _bool_option(source, "haddock_flexref", True),
        "haddock_emref": _bool_option(source, "haddock_emref", True),
        "haddock_cluster": _bool_option(source, "haddock_cluster", True),
        "haddock_min_population": _int_option(source, "haddock_min_population", 1, 1, 100),
        "haddock_top_models": _int_option(source, "haddock_top_models", 4, 1, 50),
        "haddock_clust_cutoff": _float_option(source, "haddock_clust_cutoff", 1.5, 0.1, 20.0),
        "haddock_ncores": _int_option(source, "haddock_ncores", min(8, os.cpu_count() or 2), 1, 64),
        "haddock_seed": _int_option(source, "haddock_seed", 917, 0, 9999999999999999),
        "haddock_timeout": _int_option(source, "haddock_timeout", 1800, 60, 14400),
        "haddock_w_vdw": _float_option(source, "haddock_w_vdw", 1.0, 0.0, 100.0),
        "haddock_w_elec": _float_option(source, "haddock_w_elec", 1.0, 0.0, 100.0),
        "haddock_inter_rigid": _float_option(source, "haddock_inter_rigid", 1.0, 0.0, 1.0),
        "haddock_epsilon": _float_option(source, "haddock_epsilon", 10.0, 1.0, 78.0),
        "haddock_cmrest": _bool_option(source, "haddock_cmrest", True),
        "haddock_ranair": _bool_option(source, "haddock_ranair", False),
        "haddock_mdsteps_rigid": _int_option(source, "haddock_mdsteps_rigid", 500, 0, 10000),
        "haddock_mdsteps_cool1": _int_option(source, "haddock_mdsteps_cool1", 500, 0, 10000),
        "advanced_scope": "all" if str(source.get("advanced_scope") or "representative").strip().lower() == "all" else "representative",
        "max_pairs": _int_option(source, "max_pairs", 12, 1, 12),
    }
    return config


def _fingerprint(target: dict[str, Any], config: dict[str, Any]) -> str:
    payload = json.dumps({"target": target, "config": config}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _run(cmd: list[str], cwd: Path, timeout: int = 300, env: dict[str, str] | None = None, input_text: str | None = None) -> subprocess.CompletedProcess:
    merged = os.environ.copy()
    merged.setdefault("GMX_MAXBACKUP", "-1")
    merged.setdefault("GMXLIB", GMXLIB)
    merged.setdefault("OMP_NUM_THREADS", "8")
    if env:
        for key, value in env.items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = value
    process = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdin=subprocess.PIPE if input_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=merged,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except OSError:
            process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except OSError:
                process.kill()
            stdout, stderr = process.communicate()
        raise subprocess.TimeoutExpired(cmd, timeout, output=stdout, stderr=stderr)
    return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)


def _tool_version(cmd: list[str], timeout: int = 15) -> str | None:
    try:
        result = _run(cmd, Path("/tmp"), timeout=timeout)
        text = (result.stdout + result.stderr).strip().splitlines()
        return text[0][:160] if text else None
    except Exception:
        return None


_apply_tool_paths(_load_tool_paths())


def capabilities() -> dict[str, Any]:
    capabilities_list = []
    vina_ok = False
    try:
        import vina  # type: ignore
        vina_ok = True
    except Exception:
        pass
    capabilities_list.append({
        "id": "vina",
        "name": "AutoDock Vina",
        "available": vina_ok,
        "kind": "docking",
        "version": getattr(__import__("vina"), "__version__", "1.2.7") if vina_ok else None,
        "note": "Python API + Meeko receptor/ligand preparation; rigid receptor.",
    })
    try:
        import openmm  # type: ignore
        platforms = []
        try:
            from openmm import Platform  # type: ignore
            platforms = [Platform.getPlatform(i).getName() for i in range(Platform.getNumPlatforms())]
        except Exception:
            pass
        capabilities_list.append({
            "id": "openmm", "name": "OpenMM", "available": True, "kind": "md",
            "version": getattr(openmm, "version", None) and openmm.version.version,
            "platforms": platforms,
            "note": "CPU/Reference platform availability determines speed; GROMACS is the default MD engine.",
        })
    except Exception:
        capabilities_list.append({"id": "openmm", "name": "OpenMM", "available": False, "kind": "md"})
    capabilities_list.append({
        "id": "gromacs", "name": "GROMACS", "available": Path(GMX).exists(), "kind": "md",
        "version": _tool_version([GMX, "--version"]),
        "note": "pdb2gmx -> solvate -> steepest-descent EM -> short NVT MD; complex mode adds ACPYPE/GAFF2 ligand topology.",
    })
    capabilities_list.append({
        "id": "cp2k", "name": "CP2K", "available": Path(CP2K).exists(), "kind": "qm",
        "version": _tool_version([CP2K, "--version"]),
        "note": "PBE/DZVP-MOLOPT-GTH single-point on the ligand; gas-phase periodic box.",
    })
    capabilities_list.append({
        "id": "amber", "name": "AmberTools (sander/sqm/antechamber/tleap)", "available": shutil.which("sander") is not None,
        "kind": "md/qm", "version": _tool_version(["sander", "--version"]) if shutil.which("sander") else None,
    })
    capabilities_list.append({
        "id": "obabel", "name": "Open Babel", "available": Path(OBABEL).exists(), "kind": "conversion",
        "version": _tool_version([OBABEL, "-V"]),
    })
    haddock_ok = Path(HADDOCK).exists()
    capabilities_list.append({
        "id": "haddock", "name": "HADDOCK3", "available": haddock_ok, "kind": "docking/refinement",
        "version": _tool_version([HADDOCK, "--version"]) if haddock_ok else None,
        "note": "HADDOCK3 workflows: protein-protein, protein-ligand and protein-polysaccharide. Inputs, sampling, restraints, refinement and clustering are adjustable; scores are arbitrary units, not binding free energies.",
    })
    return {
        "tools": capabilities_list,
        "paths": {
            "gromacs": GMX, "gromacs_lib": GMXLIB, "cp2k": CP2K, "cp2k_data": CP2K_DATA,
            "mk_prepare_receptor": MK_RECEPTOR, "mk_prepare_ligand": MK_LIGAND, "obabel": OBABEL,
            "haddock": HADDOCK, "acpype": ACPYPE,
        },
        "defaults": {
            "em_steps": 5000, "md_steps": 1000, "dt_ps": 0.002, "temperature_k": 300,
            "threads": min(8, os.cpu_count() or 2), "timeout_em": 900, "timeout_md": 1800,
            "haddock_workflow": "protein-protein", "haddock_sampling": 20, "haddock_tolerance": 5.0,
            "haddock_select_top": 5, "haddock_flexref": True, "haddock_emref": True, "haddock_cluster": True,
            "haddock_min_population": 1, "haddock_top_models": 4, "haddock_clust_cutoff": 1.5,
            "haddock_ncores": min(8, os.cpu_count() or 2), "haddock_seed": 917, "haddock_timeout": 1800,
            "haddock_w_vdw": 1.0, "haddock_w_elec": 1.0, "haddock_inter_rigid": 1.0, "haddock_epsilon": 10.0,
            "haddock_cmrest": True, "haddock_ranair": False, "haddock_mdsteps_rigid": 500, "haddock_mdsteps_cool1": 500,
        },
        "limits": {
            "md_steps": [100, 100000], "threads": [1, 64], "timeout_md": [30, 7200],
            "haddock_sampling": [1, 500], "haddock_tolerance": [0.0, 99.0], "haddock_select_top": [1, 100],
            "haddock_min_population": [1, 100], "haddock_top_models": [1, 50], "haddock_clust_cutoff": [0.1, 20.0],
            "haddock_ncores": [1, 64], "haddock_seed": [0, 9999999999999999], "haddock_timeout": [60, 14400],
            "haddock_w_vdw": [0.0, 100.0], "haddock_w_elec": [0.0, 100.0], "haddock_inter_rigid": [0.0, 1.0],
            "haddock_epsilon": [1.0, 78.0], "haddock_mdsteps_rigid": [0, 10000], "haddock_mdsteps_cool1": [0, 10000],
        },
        "haddock_workflows": list(HADDOCK_WORKFLOWS),
        "notes": [
            "All simulations are short, local, and for mechanism exploration only; they are not production free-energy calculations.",
            "AutoDock Vina scores are not binding free energies. GROMACS/CP2K results depend on protonation, force field and box setup.",
            "CP2K uses a single-point PBE calculation on the ligand; it does not include the protein pocket.",
            "HADDOCK3 scores are arbitrary units from its scoring function; they are not measured binding free energies.",
            "Protein-polysaccharide HADDOCK3 runs depend on carbohydrate residue templates, linkage geometry and protonation; inspect the generated inputs.",
        ],
        "generated_at": _now(),
    }


def _resolve(query: str, options: dict[str, Any], *, require_receptor: bool = True, require_ligand: bool = True) -> dict[str, Any]:
    text = (query or "") + " " + json.dumps(options, ensure_ascii=False)
    selected = options.get("design_target") if isinstance(options.get("design_target"), dict) else {}
    pdb_id = str(options.get("pdb_id") or "").upper()
    protein = str(options.get("protein") or "")
    uniprot = str(options.get("uniprot") or "")
    if not pdb_id:
        pdb_match = re.search(r"(?<![0-9A-Za-z])([0-9][0-9A-Za-z]{3})(?![0-9A-Za-z])", text)
        if pdb_match and re.search(r"[A-Za-z]", pdb_match.group(1)):
            pdb_id = pdb_match.group(1).upper()
            protein = protein or pdb_id
    if not pdb_id:
        for key, (candidate, name, accession) in PROTEIN_MAP.items():
            if key.lower() in text.lower():
                pdb_id, protein, uniprot = candidate, protein or name, uniprot or accession
                break
    if not pdb_id:
        hinted = str(selected.get("pdb_id") or "").strip().upper()
        if re.fullmatch(r"[0-9A-Z]{4}", hinted):
            pdb_id = hinted
            protein = protein or str(selected.get("name") or selected.get("cn_name") or "")
            uniprot = uniprot or str(selected.get("uniprot") or "")
    if not pdb_id and require_receptor:
        known = ", ".join(sorted({item[0] for item in PROTEIN_MAP.values()}))
        raise ValueError(
            "未识别受体。请填写 4 位 PDB ID、蛋白名称或 UniProt 映射；"
            f"当前本地映射包括 {known}。不会再用 1BEB 代替。"
        )
    ligand_name = str(options.get("ligand") or "")
    if not ligand_name:
        for key, value in LIGAND_MAP.items():
            if key.lower() in text.lower():
                ligand_name = value
                break
    if not ligand_name and str(selected.get("kind") or "").lower() == "compound":
        ligand_name = str(selected.get("id") or selected.get("name") or selected.get("cn_name") or "")
    if not ligand_name and require_ligand:
        raise ValueError(
            "未识别配体。请填写配体名称、化合物 ID 或 SMILES；"
            "不会再用 quercetin 代替。若只想做蛋白短 MD，请关闭对接/QM 后另行确认。"
        )
    smiles = str(options.get("smiles") or LIGAND_SMILES.get(ligand_name) or "")
    if not smiles:
        for item in data.compounds():
            if item["id"] == ligand_name or item.get("name", "").lower() == ligand_name.lower():
                smiles = item.get("smiles") or ""
                break
    if require_ligand and not smiles:
        raise ValueError(f"no SMILES for ligand {ligand_name!r}; pass options.smiles")
    return {
        "pdb_id": pdb_id, "protein": protein, "uniprot": uniprot,
        "ligand": ligand_name, "smiles": smiles,
    }


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,;\n]+", value) if item.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _looks_like_smiles(text: str) -> bool:
    text = text.strip()
    if not text or " " in text or len(text) < 4 or len(text) > 500:
        return False
    if not re.fullmatch(r"[A-Za-z0-9@+\-\[\]\(\)=#$:/\\.%]+", text):
        return False
    return any(char in text for char in "=()[]#@+") or len(text) > 14


def _resolve_receptor(raw: str, base: dict[str, Any]) -> dict[str, Any]:
    value = (raw or "").strip()
    if not value:
        raise ValueError("receptor must not be empty")
    if value.lower() in {"auto", "default"}:
        return {"pdb_id": base["pdb_id"], "protein": base["protein"], "uniprot": base["uniprot"]}
    for key, (candidate, name, accession) in PROTEIN_MAP.items():
        if key.lower() == value.lower():
            return {"pdb_id": candidate, "protein": name, "uniprot": accession}
    clean = re.sub(r"[^0-9A-Za-z]", "", value).upper()
    if len(clean) == 4:
        if clean == base.get("pdb_id"):
            return {"pdb_id": base["pdb_id"], "protein": base["protein"], "uniprot": base["uniprot"]}
        return {"pdb_id": clean, "protein": clean, "uniprot": ""}
    raise ValueError(f"unknown receptor {value!r}; use a 4-character PDB ID or one of: " + ", ".join(sorted({item[0] for item in PROTEIN_MAP.values()})))


def _resolve_ligand(raw: str, base: dict[str, Any]) -> dict[str, Any]:
    value = (raw or "").strip()
    if not value:
        raise ValueError("ligand must not be empty")
    if value.lower() in {"auto", "default"}:
        return {"ligand": base["ligand"], "smiles": base["smiles"]}
    key = value.lower()
    if key in LIGAND_MAP:
        canonical = LIGAND_MAP[key]
        return {"ligand": canonical, "smiles": LIGAND_SMILES.get(canonical, base["smiles"])}
    for canonical, smiles in LIGAND_SMILES.items():
        if key == canonical.lower():
            return {"ligand": canonical, "smiles": smiles}
    for item in data.compounds():
        names = {str(item.get("id", "")).lower(), str(item.get("name", "")).lower()}
        if key in names:
            smiles = str(item.get("smiles") or "")
            if smiles:
                return {"ligand": str(item.get("name") or item.get("id")), "smiles": smiles}
    if _looks_like_smiles(value):
        return {"ligand": "custom:" + value[:24], "smiles": value}
    raise ValueError(f"unknown ligand {value!r}; use a known name/SMILES or pass a valid SMILES string")


def _split_pdb_chain(raw: str) -> tuple[str, str]:
    value = (raw or "").strip()
    match = re.fullmatch(r"([0-9A-Za-z]{4})(?:\s*[:/]\s*([A-Za-z0-9]))?", value)
    if not match:
        return "", ""
    pdb_id, chain = match.group(1).upper(), (match.group(2) or "").upper()
    if not re.fullmatch(r"[0-9][0-9A-Za-z]{3}", pdb_id) and not pdb_id.isupper():
        return "", ""
    return pdb_id, chain


def _pdb_altloc_ok(line: str) -> bool:
    return line[16:17] in {" ", "A", ""}


def _pdb_chain(line: str) -> str:
    value = line[21:22] if len(line) > 21 else ""
    return value if value.strip() else ""


def _pdb_chain_ids(text: str, records: tuple[str, ...] = ("ATOM",), residues: set[str] | None = None, exclude: set[str] | None = None) -> list[str]:
    found: list[str] = []
    for line in text.splitlines():
        if not line.startswith(records) or not _pdb_altloc_ok(line):
            continue
        resname = line[17:20].strip().upper()
        if residues is not None and resname not in residues:
            continue
        if exclude is not None and resname in exclude:
            continue
        chain = _pdb_chain(line)
        if chain not in found:
            found.append(chain)
    return found


def _filter_chain_pdb(
    text: str,
    chain: str,
    *,
    records: tuple[str, ...] = ("ATOM",),
    residues: set[str] | None = None,
    exclude: set[str] | None = None,
    new_chain: str = "A",
) -> tuple[str, str, int]:
    selected: list[str] = []
    available: list[str] = []
    for line in text.splitlines():
        if not line.startswith(records) or not _pdb_altloc_ok(line):
            continue
        resname = line[17:20].strip().upper()
        if residues is not None and resname not in residues:
            continue
        if exclude is not None and resname in exclude:
            continue
        current = _pdb_chain(line)
        if current not in available:
            available.append(current)
        if chain and current != chain:
            continue
        selected.append(line)
    if not selected:
        if chain:
            raise ValueError(f"chain {chain!r} has no matching atoms for this workflow")
        raise ValueError("no matching atoms were found")
    if not chain:
        chain = _pdb_chain(selected[0])
        selected = [line for line in selected if _pdb_chain(line) == chain]
    rewritten = []
    for line in selected:
        line = line.ljust(80)
        rewritten.append(line[:21] + new_chain + line[22:])
    body = "\n".join(rewritten)
    if not body.rstrip().endswith("TER"):
        body += "\nTER"
    return body + "\nEND\n", chain, len(rewritten)


def _haddock_receptor(raw: str, config: dict[str, Any]) -> dict[str, Any]:
    value = (raw or "").strip()
    if not value:
        raise ValueError("HADDOCK3 受体不能为空：请填写 PDB ID、蛋白名称或 UniProt 映射。")
    pdb_id, chain = _split_pdb_chain(value)
    protein = ""
    uniprot = ""
    if not pdb_id:
        for key, (candidate, name, accession) in PROTEIN_MAP.items():
            if key.lower() in value.lower():
                pdb_id, protein, uniprot = candidate, name, accession
                break
        else:
            match = re.search(r"\b([0-9][0-9A-Za-z]{3})\b", value)
            if match:
                pdb_id = match.group(1).upper()
        if not pdb_id:
            known = ", ".join(sorted({item[0] for item in PROTEIN_MAP.values()}))
            raise ValueError(f"无法从 {value!r} 解析 HADDOCK3 受体；请填写 4 位 PDB ID 或本地映射（{known}）。")
    else:
        protein, uniprot = "", ""
    if pdb_id:
        mapped = next((item for item in PROTEIN_MAP.values() if item[0] == pdb_id), None)
        if mapped:
            protein = protein or mapped[1]
            uniprot = uniprot or mapped[2]
    chain = chain or config.get("haddock_receptor_chain") or ""
    return {"pdb_id": pdb_id, "protein": protein or pdb_id, "uniprot": uniprot, "source_chain": chain}


def _resolve_haddock_target(query: str, options: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    workflow = config["haddock_workflow"]
    if workflow not in HADDOCK_WORKFLOWS:
        raise ValueError("haddock_workflow 必须是 protein-protein、protein-ligand 或 protein-polysaccharide")
    receptor = _haddock_receptor(config.get("haddock_receptor") or query, config)
    receptor_text = _download_pdb(receptor["pdb_id"]).read_text(encoding="utf-8", errors="ignore")
    receptor_chain = receptor["source_chain"] or (_pdb_chain_ids(receptor_text, ("ATOM",), exclude=CARBOHYDRATE_RESIDUES) or [""])[0]
    partner_raw = config.get("haddock_partner") or ""
    partner: dict[str, Any] = {}
    if workflow == "protein-ligand":
        if partner_raw:
            ligand = _resolve_ligand(partner_raw, {"ligand": "", "smiles": ""})
        else:
            found = ""
            for key, value in LIGAND_MAP.items():
                if key.lower() in (query or "").lower():
                    found = value
                    break
            if not found and config.get("smiles"):
                ligand = {"ligand": "custom-ligand", "smiles": str(config["smiles"])}
            elif found:
                ligand = {"ligand": found, "smiles": LIGAND_SMILES.get(found, "")}
            else:
                raise ValueError("protein-ligand 工作流需要配体名称或 SMILES；请填写对接伙伴。")
        if not ligand.get("smiles"):
            raise ValueError("HADDOCK3 配体缺少 SMILES，无法生成 3D 结构。")
        partner = {"partner_pdb_id": "", "partner": ligand["ligand"], "smiles": ligand["smiles"], "source_chain": "B"}
        partner_chain = "B"
    else:
        if not partner_raw:
            raise ValueError("protein-protein / protein-polysaccharide 工作流需要填写对接伙伴 PDB ID。")
        pdb_id, chain = _split_pdb_chain(partner_raw)
        if not pdb_id:
            resolved = _resolve_receptor(partner_raw, receptor)
            pdb_id = resolved["pdb_id"]
        partner_text = _download_pdb(pdb_id).read_text(encoding="utf-8", errors="ignore")
        if workflow == "protein-polysaccharide":
            chain = chain or config.get("haddock_partner_chain") or (_pdb_chain_ids(partner_text, ("ATOM", "HETATM"), residues=CARBOHYDRATE_RESIDUES) or [""])[0]
            if not chain or not _pdb_chain_ids(partner_text, ("ATOM", "HETATM"), residues=CARBOHYDRATE_RESIDUES):
                raise ValueError(f"PDB {pdb_id} 中未找到可识别的碳水化合物链；请指定糖链 PDB/链。")
            partner = {"partner_pdb_id": pdb_id, "partner": f"{pdb_id} glycan", "smiles": "", "source_chain": chain}
        else:
            chain = chain or config.get("haddock_partner_chain") or (_pdb_chain_ids(partner_text, ("ATOM",), exclude=CARBOHYDRATE_RESIDUES) or [""])[0]
            partner = {"partner_pdb_id": pdb_id, "partner": pdb_id, "smiles": "", "source_chain": chain}
        partner_chain = "B"
    if workflow == "protein-protein" and partner.get("partner_pdb_id") == receptor["pdb_id"] and partner.get("source_chain") == receptor_chain:
        raise ValueError("HADDOCK3 蛋白-蛋白对接的受体和伙伴不能是同一 PDB 的同一链。")
    return {
        "engine": "haddock",
        "workflow": workflow,
        "pdb_id": receptor["pdb_id"],
        "protein": receptor["protein"],
        "uniprot": receptor["uniprot"],
        "source_chain": receptor_chain,
        "receptor_chain": "A",
        "partner_pdb_id": partner.get("partner_pdb_id", ""),
        "partner": partner.get("partner", ""),
        "partner_chain": partner_chain,
        "partner_source_chain": partner.get("source_chain", ""),
        "ligand": partner.get("partner", ""),
        "smiles": partner.get("smiles", ""),
        "pair_id": f"HADDOCK_{workflow}_{receptor['pdb_id']}",
    }


def _parse_residues(raw: str) -> list[int]:
    values: set[int] = set()
    for token in re.split(r"[,;\s]+", raw or ""):
        token = token.strip()
        if not token:
            continue
        match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", token)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            if start > end:
                start, end = end, start
            if end - start > 5000:
                raise ValueError("残基范围过大；请缩小 HADDOCK3 活性残基范围。")
            values.update(range(start, end + 1))
            continue
        if not token.isdigit():
            raise ValueError(f"无法解析残基编号 {token!r}；请使用 12,15,20-25 格式。")
        values.add(int(token))
    return sorted(values)


def _passive_residues(pdb_path: Path, chain: str, active: list[int], radius: float) -> list[int]:
    if not active or radius <= 0:
        return []
    tool = str(Path(HADDOCK).with_name("haddock3-restraints"))
    if not Path(tool).exists():
        return []
    cmd = [tool, "passive_from_active", str(pdb_path), ",".join(str(x) for x in active), "-r", str(radius)]
    if chain:
        cmd.extend(["-c", chain])
    try:
        result = _run(cmd, pdb_path.parent, timeout=60)
    except Exception:
        return []
    if result.returncode != 0:
        return []
    for line in reversed((result.stdout or "").splitlines()):
        text = line.strip()
        if re.fullmatch(r"(?:\d+\s+)*\d+", text):
            return sorted({int(x) for x in text.split()})
    return []


def _haddock_ambig(
    work: Path,
    receptor_pdb: Path,
    partner_pdb: Path,
    receptor_chain: str,
    partner_chain: str,
    active_receptor: list[int],
    active_partner: list[int],
    config: dict[str, Any],
    *,
    expand_passive: bool,
) -> dict[str, Any] | None:
    if not active_receptor and not active_partner:
        return None
    if not active_receptor or not active_partner:
        raise ValueError("HADDOCK3 活性残基必须同时提供受体侧和伙伴侧；或全部留空使用 cmrest/ranair。")
    passive_receptor = _passive_residues(receptor_pdb, receptor_chain, active_receptor, float(config["haddock_restraint_radius"])) if expand_passive else []
    passive_partner = _passive_residues(partner_pdb, partner_chain, active_partner, float(config["haddock_restraint_radius"])) if expand_passive else []
    target_b = sorted(set(active_partner + passive_partner))
    target_a = sorted(set(active_receptor + passive_receptor))
    blocks: list[str] = ["! HADDOCK3 ambiguous interaction restraints generated by BioForge Studio"]
    limit = int(config["haddock_max_restraints"])
    for source in active_receptor:
        inner = "\n or\n".join(f"       (resi {target} and segid {partner_chain})" for target in target_b)
        blocks.append(f"assign (resi {source} and segid {receptor_chain})\n(\n{inner}\n) 2.0 2.0 0.0\n")
        if len(blocks) >= limit:
            break
    if len(blocks) < limit:
        for source in active_partner:
            inner = "\n or\n".join(f"       (resi {target} and segid {receptor_chain})" for target in target_a)
            blocks.append(f"assign (resi {source} and segid {partner_chain})\n(\n{inner}\n) 2.0 2.0 0.0\n")
            if len(blocks) >= limit:
                break
    path = work / "ambig.tbl"
    path.write_text("\n".join(blocks) + "\n", encoding="utf-8")
    return {
        "file": "ambig.tbl",
        "active_receptor": active_receptor,
        "active_partner": active_partner,
        "passive_receptor": passive_receptor,
        "passive_partner": passive_partner,
        "restraint_count": len(blocks) - 1,
    }


def _write_haddock_ligand_pdb(smiles: str, path: Path, seed: int) -> int:
    code = """
import sys
from rdkit import Chem
from rdkit.Chem import AllChem
smiles, out, seed = sys.argv[1], sys.argv[2], int(sys.argv[3])
m = Chem.AddHs(Chem.MolFromSmiles(smiles))
if m is None:
    raise SystemExit('invalid SMILES')
if AllChem.EmbedMolecule(m, randomSeed=seed) != 0:
    if AllChem.EmbedMolecule(m, randomSeed=seed, useRandomCoords=True) != 0:
        raise SystemExit('3D embedding failed')
AllChem.MMFFOptimizeMolecule(m)
block = Chem.MolToPDBBlock(m)
lines = []
for line in block.splitlines():
    if line.startswith(('ATOM', 'HETATM')):
        line = line.ljust(80)
        lines.append(line[:17] + 'LIG' + line[20:21] + 'B' + line[22:])
lines.append('TER')
lines.append('END')
open(out, 'w').write('\\n'.join(lines) + '\\n')
print(len([x for x in lines if x.startswith(('ATOM', 'HETATM'))]))
"""
    result = _run([MOLECULE_PYTHON, "-c", code, smiles, str(path), str(seed)], path.parent, timeout=60)
    if result.returncode != 0:
        raise RuntimeError("HADDOCK3 ligand 3D generation failed: " + (result.stderr or result.stdout)[-500:])
    try:
        return int((result.stdout or "0").strip().splitlines()[-1])
    except Exception:
        return 0


def _haddock_config_text(config: dict[str, Any], *, has_ambig: bool, workflow: str) -> str:
    sampling = max(1, int(config["haddock_sampling"]))
    select_top = max(1, min(int(config["haddock_select_top"]), sampling))
    top_models = max(1, min(int(config["haddock_top_models"]), select_top))
    min_population = max(1, min(int(config["haddock_min_population"]), select_top))
    tolerance = float(config["haddock_tolerance"])
    common = [
        f"tolerance = {tolerance}",
        f"w_vdw = {float(config['haddock_w_vdw'])}",
        f"w_elec = {float(config['haddock_w_elec'])}",
        f"epsilon = {float(config['haddock_epsilon'])}",
        f"iniseed = {int(config['haddock_seed'])}",
    ]
    rigidbody_common = [*common, f"inter_rigid = {float(config['haddock_inter_rigid'])}"]
    if has_ambig:
        common.append('ambig_fname = "ambig.tbl"')
        rigidbody_common.append('ambig_fname = "ambig.tbl"')
    lines = [
        f'run_dir = "run1"',
        'mode = "local"',
        f"ncores = {int(config['haddock_ncores'])}",
        'molecules = ["receptor.pdb", "partner.pdb"]',
        "",
        "[topoaa]",
        "autohis = true",
        "delenph = false",
    ]
    if workflow == "protein-ligand":
        lines.append("autotoppar = true")
    lines += ["", "[rigidbody]", f"sampling = {sampling}", "crossdock = false", *rigidbody_common]
    if not has_ambig:
        if config["haddock_cmrest"]:
            lines.append("cmrest = true")
        elif config["haddock_ranair"]:
            lines.append("ranair = true")
        else:
            raise ValueError("未提供活性残基时必须启用 cmrest 或 ranair。")
    lines += ["", "[caprieval]"]
    refine = bool(config["haddock_flexref"] or config["haddock_emref"])
    if refine:
        lines += ["", "[seletop]", f"select = {select_top}"]
    if config["haddock_flexref"]:
        lines += ["", "[flexref]", *common, f"mdsteps_rigid = {int(config['haddock_mdsteps_rigid'])}", f"mdsteps_cool1 = {int(config['haddock_mdsteps_cool1'])}", "", "[caprieval]"]
    if config["haddock_emref"]:
        if not config["haddock_flexref"]:
            lines += ["", "[seletop]", f"select = {select_top}"]
        lines += ["", "[emref]", *common, "", "[caprieval]"]
    if config["haddock_cluster"]:
        if workflow == "protein-ligand":
            lines += ["", "[ilrmsdmatrix]", "", "[clustrmsd]", "criterion = 'distance'", "linkage = 'average'", f"min_population = {min_population}", f"clust_cutoff = {float(config['haddock_clust_cutoff'])}"]
        else:
            lines += ["", "[clustfcc]", f"min_population = {min_population}"]
        lines += ["", "[seletopclusts]", f"top_models = {top_models}", "", "[caprieval]"]
    return "\n".join(lines) + "\n"


def _parse_capri(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8", errors="ignore", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for raw in reader:
            model = (raw.get("model") or "").strip()
            if not model:
                continue
            try:
                score = float(raw.get("score") or "nan")
            except ValueError:
                score = float("nan")
            if score != score or score >= 9999:
                continue
            try:
                cluster_id = int(float(raw.get("cluster_id") or 0))
            except ValueError:
                cluster_id = 0
            try:
                cluster_rank = int(float(raw.get("cluster_ranking") or 0))
            except ValueError:
                cluster_rank = 0
            rows.append({
                "model": model,
                "score": score,
                "cluster_id": cluster_id,
                "cluster_rank": cluster_rank,
                "caprieval_rank": raw.get("caprieval_rank") or "",
            })
    rows.sort(key=lambda row: row["score"])
    return rows


def _read_capri_clusters(path: Path) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []
    if not path.exists():
        return clusters
    with path.open(encoding="utf-8", errors="ignore", newline="") as handle:
        reader = csv.DictReader((line for line in handle if not line.startswith("#")), delimiter="\t")
        for raw in reader:
            try:
                score = float(raw.get("score") or "nan")
                if score != score or score >= 9999:
                    continue
                clusters.append({
                    "cluster_rank": int(float(raw.get("cluster_rank") or 0)),
                    "cluster_id": int(float(raw.get("cluster_id") or 0)),
                    "population": int(float(raw.get("n") or 0)),
                    "score": score,
                })
            except ValueError:
                continue
    clusters.sort(key=lambda row: row["cluster_rank"])
    return clusters


def _resolve_model_file(capri_dir: Path, model: str, run_root: Path) -> Path:
    base = (capri_dir / model).resolve()
    root = run_root.resolve()
    if not str(base).startswith(str(root) + os.sep):
        raise ValueError("HADDOCK3 result model path escaped the run directory")
    if base.exists():
        return base
    if base.with_suffix(base.suffix + ".gz").exists():
        target = base.with_suffix(base.suffix + ".gz")
        unpacked = capri_dir / (base.name)
        with gzip.open(target, "rb") as source, unpacked.open("wb") as destination:
            shutil.copyfileobj(source, destination)
        return unpacked
    raise FileNotFoundError(f"HADDOCK3 model not found: {model}")


def _haddock_results(run_root: Path) -> dict[str, Any]:
    capris = []
    for path in run_root.glob("**/capri_ss.tsv"):
        if "analysis" in path.parts:
            continue
        match = re.match(r"(\d+)_caprieval", path.parent.name)
        capris.append((int(match.group(1)) if match else -1, path.stat().st_mtime, path))
    if not capris:
        raise RuntimeError("HADDOCK3 finished but no capri_ss.tsv was produced")
    _, _, capri_path = sorted(capris, key=lambda item: (item[0], item[1]))[-1]
    rows = _parse_capri(capri_path)
    if not rows:
        raise RuntimeError("HADDOCK3 caprieval produced no scored models")
    clusters = _read_capri_clusters(capri_path.with_name("capri_clt.tsv"))
    cluster_population = {row["cluster_id"]: row["population"] for row in clusters}
    models = []
    for index, row in enumerate(rows[:20], start=1):
        model_path = _resolve_model_file(capri_path.parent, row["model"], run_root)
        cluster_id = row["cluster_id"] if clusters else None
        models.append({
            "rank": index,
            "model": str(model_path.relative_to(run_root)),
            "score": round(float(row["score"]), 3),
            "cluster_id": cluster_id,
            "cluster_rank": row["cluster_rank"] if clusters else None,
            "cluster_population": cluster_population.get(cluster_id) if cluster_id is not None else None,
        })
    best_path = _resolve_model_file(capri_path.parent, rows[0]["model"], run_root)
    return {
        "score": round(float(rows[0]["score"]), 3),
        "models": models,
        "clusters": clusters,
        "best_model_path": best_path,
        "capri_ss": capri_path,
        "capri_clt": capri_path.with_name("capri_clt.tsv") if capri_path.with_name("capri_clt.tsv").exists() else None,
    }


def _resolve_pairs(query: str, options: dict[str, Any], limit: int = 12) -> list[dict[str, Any]]:
    raw_receptors = _as_list(options.get("receptors"))
    raw_ligands = _as_list(options.get("ligands"))
    base = _resolve(
        query, options,
        require_receptor=not raw_receptors,
        require_ligand=not raw_ligands and not options.get("smiles"),
    )
    receptors = [_resolve_receptor(item, base) for item in (raw_receptors or [base["pdb_id"]])]
    if raw_ligands:
        ligands = [_resolve_ligand(item, base) for item in raw_ligands]
    elif options.get("smiles"):
        ligands = [{"ligand": str(options.get("ligand") or "custom-ligand")[:40], "smiles": str(options["smiles"]).strip()}]
    else:
        ligands = [_resolve_ligand(base["ligand"], base)]
    receptors = list({item["pdb_id"]: item for item in receptors}.values())
    ligands = list({(item["ligand"], item["smiles"]): item for item in ligands}.values())
    if len(receptors) * len(ligands) > limit:
        raise ValueError(f"too many receptor x ligand pairs ({len(receptors)} x {len(ligands)}); limit is {limit}")
    pairs = []
    for receptor in receptors:
        for ligand in ligands:
            pairs.append({
                **receptor,
                **ligand,
                "pair_id": f"{receptor['pdb_id']}_{re.sub(r'[^0-9A-Za-z]+', '-', ligand['ligand']).strip('-')[:32]}",
            })
    return pairs


def _download_pdb(pdb_id: str) -> Path:
    PDB_CACHE.mkdir(parents=True, exist_ok=True)
    path = PDB_CACHE / f"{pdb_id}.pdb"
    if path.exists() and path.stat().st_size > 1000:
        return path
    url = f"https://files.rcsb.org/download/{pdb_id}.pdb"
    with httpx.Client(timeout=25, headers={"User-Agent": "BioForgeStudio/2.0"}) as client:
        response = client.get(url)
    response.raise_for_status()
    path.write_text(response.text, encoding="utf-8")
    return path


_TRAJ_LOCK = threading.Lock()


def trajectory_pdb(job_id: str, artifact: str) -> Path:
    base = (data.COMPUTE_DIR / job_id).resolve()
    target = (base / artifact).resolve()
    if not str(target).startswith(str(base) + os.sep) or target == base:
        raise ValueError("invalid trajectory path")
    if target.suffix.lower() != ".xtc" or not target.is_file():
        raise FileNotFoundError("trajectory not found")
    tpr = target.with_name("md.tpr")
    if not tpr.is_file():
        raise FileNotFoundError("md.tpr not found next to trajectory")
    if not Path(GMX).exists():
        raise RuntimeError("GROMACS is not available for trajectory conversion")
    cache_dir = base / "viewer"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / (artifact.replace("/", "__").replace("\\", "__") + "-v2.pdb")
    with _TRAJ_LOCK:
        if cache.is_file() and cache.stat().st_mtime >= target.stat().st_mtime and cache.stat().st_size > 0:
            return cache
        tmp = cache.with_suffix(".tmp.pdb")
        index = cache.with_suffix(".ndx")
        last = ""
        try:
            selected = _run(
                [GMX, "select", "-s", str(tpr), "-select", 'group "Protein" or resname MOL or resname LIG or resname UNL', "-on", str(index)],
                target.parent,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            selected = None
        groups = ("0",) if selected is not None and selected.returncode == 0 and index.is_file() else ("1", "0")
        for group in groups:
            cmd = [GMX, "trjconv", "-f", str(target), "-s", str(tpr), "-o", str(tmp), "-pbc", "mol"]
            if groups == ("0",):
                cmd.extend(["-n", str(index)])
            try:
                result = _run(cmd, target.parent, timeout=300, input_text=group + "\n")
            except subprocess.TimeoutExpired:
                last = "trajectory conversion timed out"
                break
            text = (result.stdout or "") + "\n" + (result.stderr or "")
            if result.returncode == 0 and tmp.is_file() and tmp.stat().st_size > 200:
                tmp.replace(cache)
                index.unlink(missing_ok=True)
                return cache
            last = text.strip()[-500:] or "trajectory conversion failed"
        tmp.unlink(missing_ok=True)
        index.unlink(missing_ok=True)
        raise RuntimeError(f"GROMACS trjconv failed: {last}")


def pdb_text(pdb_id: str) -> str:
    clean = re.sub(r"[^0-9A-Za-z]", "", pdb_id or "").upper()
    if len(clean) != 4:
        raise ValueError("PDB ID must contain four letters/digits")
    path = _download_pdb(clean)
    text = path.read_text(encoding="utf-8", errors="ignore")
    if len(text) > 12_000_000:
        raise ValueError("PDB file is too large to display")
    return text


def _write_ligand_sdf(smiles: str, path: Path) -> None:
    code = f"""
import sys
from rdkit import Chem
from rdkit.Chem import AllChem
smiles = sys.argv[1]
out = sys.argv[2]
m = Chem.AddHs(Chem.MolFromSmiles(smiles))
if m is None:
    raise SystemExit('invalid SMILES')
AllChem.EmbedMolecule(m, randomSeed=42)
AllChem.MMFFOptimizeMolecule(m)
Chem.MolToMolFile(m, out)
"""
    result = _run([MOLECULE_PYTHON, "-c", code, smiles, str(path)], path.parent, timeout=60)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout)[-500:])


def _center_from_pdb(path: Path) -> list[float]:
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith(("ATOM", "HETATM")) and line[76:78].strip() != "H":
            try:
                xs.append(float(line[30:38]))
                ys.append(float(line[38:46]))
                zs.append(float(line[46:54]))
            except ValueError:
                continue
    if not xs:
        raise ValueError("no coordinates in PDB")
    return [sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs)]


def _clean_protein(pdb_path: Path, target: Path) -> None:
    lines = [line for line in pdb_path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.startswith("ATOM")]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _gro_parts(path: Path) -> tuple[list[str], int, str]:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    count = int(lines[1].strip())
    atoms = lines[2:2 + count]
    box = lines[2 + count] if len(lines) > 2 + count else "1.0 1.0 1.0"
    return atoms, count, box


def _merge_gro(protein_gro: Path, ligand_gro: Path, out_path: Path) -> int:
    protein_atoms, protein_count, box = _gro_parts(protein_gro)
    ligand_atoms, ligand_count, _ = _gro_parts(ligand_gro)
    atoms = protein_atoms + ligand_atoms
    out_path.write_text(f"Protein-ligand complex\n{protein_count + ligand_count}\n" + "\n".join(atoms) + f"\n{box}\n", encoding="utf-8")
    return protein_count + ligand_count


def _add_complex_topology(top_path: Path, include: str = "LIG.acpype/LIG_GMX.itp", ligand_name: str = "LIG") -> None:
    text = top_path.read_text(encoding="utf-8", errors="ignore")
    if include not in text:
        text = re.sub(r'(#include\s+"[^"]*forcefield\.itp"\s*\n)', r'\1#include "' + include + '"\n', text, count=1)
    lines = text.splitlines()
    try:
        molecules = next(index for index, line in enumerate(lines) if line.strip().startswith("[ molecules ]"))
    except StopIteration as exc:
        raise ValueError("protein topology has no [ molecules ] section") from exc
    insert_at = len(lines)
    for index in range(molecules + 1, len(lines)):
        if lines[index].lstrip().startswith("#"):
            insert_at = index
            break
    while insert_at > molecules + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    lines.insert(insert_at, f"{ligand_name:<20}1")
    top_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _em_status(text: str) -> dict[str, Any]:
    force = re.search(r"Maximum force\s*=\s*([-0-9.eE+]+)\s+on atom\s+(\d+)", text)
    steps = re.search(r"in (\d+) steps", text)
    status: dict[str, Any] = {}
    if force:
        status["em_fmax"] = float(force.group(1))
        status["em_fmax_atom"] = int(force.group(2))
    if steps:
        status["em_actual_steps"] = int(steps.group(1))
    if "did not converge" in text:
        status["em_converged"] = False
    elif re.search(r"converged to Fmax < [-0-9.eE+]+ in \d+ steps", text):
        status["em_converged"] = True
    return status


def _potential_from_log(text: str) -> float | None:
    direct = re.findall(r"Potential Energy\s*=\s*([-0-9.eE+]+)", text)
    if direct:
        return float(direct[-1])
    tables = re.findall(r"Potential\s*\n\s*(?:[-0-9.eE+]+\s+){4}([-0-9.eE+]+)", text)
    return float(tables[-1]) if tables else None


def _complex_ligand_metrics(em_gro: Path, md_gro: Path) -> dict[str, float]:
    em_atoms, _, _ = _gro_parts(em_gro)
    md_atoms, _, _ = _gro_parts(md_gro)
    em_coords = [(float(line[20:28]) * 10, float(line[28:36]) * 10, float(line[36:44]) * 10) for line in em_atoms]
    md_coords = [(float(line[20:28]) * 10, float(line[28:36]) * 10, float(line[36:44]) * 10) for line in md_atoms]
    residues = [line[5:10].strip() for line in md_atoms]
    ligand = [index for index, residue in enumerate(residues) if residue == "MOL"]
    if not ligand:
        return {}
    em_center = tuple(sum(em_coords[index][axis] for index in ligand) / len(ligand) for axis in range(3))
    md_center = tuple(sum(md_coords[index][axis] for index in ligand) / len(ligand) for axis in range(3))
    drift = sum((em_center[axis] - md_center[axis]) ** 2 for axis in range(3)) ** 0.5
    rmsd = (sum(sum((em_coords[index][axis] - md_coords[index][axis]) ** 2 for axis in range(3)) for index in ligand) / len(ligand)) ** 0.5
    protein = [index for index, residue in enumerate(residues) if residue not in {"MOL", "SOL", "NA", "CL"}]
    minimum = min(
        sum((md_coords[left][axis] - md_coords[right][axis]) ** 2 for axis in range(3)) ** 0.5
        for left in ligand for right in protein
    )
    return {
        "ligand_centroid_drift_angstrom": round(drift, 3),
        "ligand_atom_rmsd_angstrom": round(rmsd, 3),
        "ligand_min_protein_distance_angstrom": round(minimum, 3),
    }


def _write_gmx_mdp(gm: Path, config: dict[str, Any]) -> None:
    (gm / "em.mdp").write_text(f"""integrator = steep
nsteps = {int(config['em_steps'])}
emtol = 500
emstep = 0.01
cutoff-scheme = Verlet
coulombtype = PME
rcoulomb = 1.0
rvdw = 1.0
pbc = xyz
""", encoding="utf-8")
    (gm / "md.mdp").write_text(f"""integrator = md
dt = {float(config['dt_ps'])}
nsteps = {int(config['md_steps'])}
nstxout-compressed = 250
nstenergy = 100
nstlog = 100
continuation = no
gen_vel = yes
gen_seed = {int(config['docking_seed'])}
gen_temp = {float(config['temperature_k'])}
tcoupl = V-rescale
tc-grps = System
tau_t = 0.1
ref_t = {float(config['temperature_k'])}
constraints = h-bonds
constraint-algorithm = lincs
cutoff-scheme = Verlet
coulombtype = PME
rcoulomb = 1.0
rvdw = 1.0
pbc = xyz
""", encoding="utf-8")
    (gm / "ions.mdp").write_text("""integrator = steep
nsteps = 0
cutoff-scheme = Verlet
coulombtype = PME
rcoulomb = 1.0
rvdw = 1.0
pbc = xyz
""", encoding="utf-8")


def _set_step(job: dict[str, Any], step_id: str, status: str, detail: str = "", artifacts: list[str] | None = None) -> None:
    with _LOCK:
        job["updated_utc"] = _now()
        for step in job["steps"]:
            if step["id"] == step_id:
                step["status"] = status
                if detail:
                    step["detail"] = detail
                if artifacts:
                    step["artifacts"] = artifacts
                break
        _write_job(job)


def _write_job(job: dict[str, Any]) -> None:
    path = data.COMPUTE_DIR / job["id"] / "job.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _artifact(job: dict[str, Any], path: Path) -> str:
    try:
        return str(path.relative_to(data.COMPUTE_DIR / job["id"]))
    except ValueError:
        return str(path)


def _prepare_structures(job: dict[str, Any], work: Path, target: dict[str, Any]) -> None:
    _set_step(job, "prepare", "running", "Downloading PDB and writing receptor/ligand structures")
    pdb_path = _download_pdb(target["pdb_id"])
    _clean_protein(pdb_path, work / "receptor.pdb")
    _write_ligand_sdf(target["smiles"], work / "ligand.sdf")
    _set_step(job, "prepare", "done", "Receptor/ligand files ready")


def _docking(job: dict[str, Any], work: Path, target: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    receptor_pdb = work / "receptor.pdb"
    if not receptor_pdb.exists() or not (work / "ligand.sdf").exists():
        raise RuntimeError("receptor/ligand files are missing")
    result = _run([MK_RECEPTOR, "--read_pdb", str(receptor_pdb), "-o", "receptor.json", "-p", "receptor.pdbqt", "-x"], work, timeout=config["timeout_prepare"])
    (work / "receptor_prep.log").write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    if result.returncode != 0 or not (work / "receptor.pdbqt").exists():
        raise RuntimeError("receptor preparation failed")
    result = _run([MK_LIGAND, "-i", str(work / "ligand.sdf"), "-o", "ligand.pdbqt"], work, timeout=config["timeout_prepare"])
    (work / "ligand_prep.log").write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    if result.returncode != 0 or not (work / "ligand.pdbqt").exists():
        raise RuntimeError("ligand preparation failed")
    _set_step(job, "prepare", "done", "Receptor/ligand prepared")
    _set_step(job, "docking", "running", f"Vina exhaustiveness={config['docking_exhaustiveness']}, seed={config['docking_seed']}")
    center = _center_from_pdb(receptor_pdb)
    box = float(config["docking_box_size"])
    poses = int(config["docking_poses"])
    code = f"""
import json
from vina import Vina
center = {center!r}
box_size = {[box, box, box]!r}
v = Vina(sf_name='vina', cpu={max(1, min(8, int(config['threads'])))}, seed={int(config['docking_seed'])})
v.set_receptor('receptor.pdbqt')
v.set_ligand_from_file('ligand.pdbqt')
v.compute_vina_maps(center=center, box_size=box_size)
v.dock(exhaustiveness={int(config['docking_exhaustiveness'])}, n_poses={poses})
v.write_poses('poses.pdbqt', n_poses={poses}, overwrite=True)
energies = v.energies(n_poses={poses}).tolist()
json.dump({{'energies': energies, 'center': center, 'box_size': box_size, 'seed': {int(config['docking_seed'])}, 'exhaustiveness': {int(config['docking_exhaustiveness'])}}}, open('vina_result.json', 'w'), indent=2)
print(json.dumps(energies[:2]))
"""
    try:
        result = _run([MOLECULE_PYTHON, "-c", code], work, timeout=config["timeout_docking"])
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Vina docking timed out after {config['timeout_docking']} s; lower exhaustiveness or raise the timeout")
    (work / "vina.log").write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    if result.returncode != 0 or not (work / "vina_result.json").exists():
        raise RuntimeError("Vina docking failed: " + (result.stderr or result.stdout)[-500:])
    payload = json.loads((work / "vina_result.json").read_text(encoding="utf-8"))
    best = payload["energies"][0] if payload.get("energies") else None
    pose_note = ""
    try:
        converted = _run([OBABEL, "poses.pdbqt", "-O", "best_pose.pdb", "-f", "1", "-l", "1"], work, timeout=60)
        if converted.returncode == 0 and (work / "best_pose.pdb").exists():
            _complex_pdb(work / "receptor.pdb", work / "best_pose.pdb", work / "complex.pdb", target)
            pose_note = "best pose converted to complex.pdb"
        else:
            pose_note = "best pose PDB conversion failed"
    except Exception as exc:
        pose_note = f"complex.pdb not generated: {str(exc)[:200]}"
    _set_step(job, "docking", "done", (f"Vina best affinity: {best[0]:.2f} kcal/mol; " if best else "Vina completed; ") + pose_note, ["receptor.pdb", "receptor.pdbqt", "ligand.pdbqt", "poses.pdbqt", "vina_result.json", "vina.log", "complex.pdb"])
    return {
        "best_affinity": best[0] if best else None,
        "energies": payload.get("energies", [])[:poses],
        "seed": config["docking_seed"],
        "exhaustiveness": config["docking_exhaustiveness"],
        "box_size": box,
        "complex_pdb": "complex.pdb" if (work / "complex.pdb").exists() else None,
        "complex_note": pose_note,
    }


def _element_from_atom(atom_name: str) -> str:
    letters = re.sub(r"[^A-Za-z]", "", atom_name or "").strip()
    if not letters:
        return ""
    two = letters[:2].capitalize()
    if two in {"Cl", "Br", "Na", "Mg", "Zn", "Fe", "Ca", "Mn", "Cu", "Co", "Ni", "Se", "Si"}:
        return two
    return letters[0].upper()


def _complex_pdb(receptor_path: Path, pose_path: Path, out_path: Path, target: dict[str, Any]) -> None:
    receptor_lines = [
        line for line in receptor_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.startswith("ATOM")
    ]
    if not receptor_lines:
        raise ValueError("receptor has no ATOM records")
    pose_lines = [
        line for line in pose_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.startswith(("ATOM", "HETATM"))
    ]
    if not pose_lines:
        raise ValueError("pose has no atom records")
    used = []
    for line in receptor_lines:
        try:
            used.append(int(line[6:11]))
        except ValueError:
            continue
    serial = max(used + [0]) + 1
    output = list(receptor_lines)
    output.append("TER")
    for line in pose_lines:
        try:
            x = float(line[30:38])
            y = float(line[38:46])
            z = float(line[46:54])
        except ValueError:
            continue
        name = line[12:16].strip() or "X"
        element = (line[76:78].strip() if len(line) >= 78 else "") or _element_from_atom(name)
        if serial > 99999:
            serial = 1
        output.append(
            f"HETATM{serial:5d} {name:<4} LIG L   1    {x:8.3f}{y:8.3f}{z:8.3f}{1.0:6.2f}{0.0:6.2f}          {element:>2}"
        )
        serial += 1
    output.extend(["END", ""])
    out_path.write_text("\n".join(output), encoding="utf-8")


def _gromacs_protein(job: dict[str, Any], work: Path, config: dict[str, Any]) -> dict[str, Any]:
    if not Path(GMX).exists():
        _set_step(job, "gromacs", "skipped", "GROMACS binary not found")
        return {"available": False, "error": "GROMACS binary not found"}
    _set_step(job, "gromacs", "running", "pdb2gmx, solvation, energy minimization and short NVT")
    gm = work / "gromacs"
    gm.mkdir(exist_ok=True)
    _clean_protein(work / "receptor.pdb", gm / "protein.pdb")
    ff_source = Path(GMXLIB) / "amber99sb-ildn.ff"
    ff_target = gm / "amber99sb-ildn.ff"
    if ff_source.exists() and not ff_target.exists():
        try:
            shutil.copytree(ff_source, ff_target)
        except OSError:
            pass
    threads = str(config["threads"])
    env = {"GMXLIB": None, "OMP_NUM_THREADS": threads}
    commands = [
        ([GMX, "pdb2gmx", "-f", "protein.pdb", "-o", "processed.gro", "-water", "tip3p", "-ff", "amber99sb-ildn", "-ignh"], config["timeout_prepare"], "pdb2gmx"),
        ([GMX, "editconf", "-f", "processed.gro", "-o", "boxed.gro", "-c", "-d", str(config["box_padding_nm"]), "-bt", "cubic"], config["timeout_prepare"], "editconf"),
        ([GMX, "solvate", "-cp", "boxed.gro", "-cs", "spc216.gro", "-o", "solvated.gro", "-p", "topol.top"], config["timeout_prepare"], "solvate"),
    ]
    for cmd, timeout, label in commands:
        try:
            result = _run(cmd, gm, timeout=timeout, env=env)
        except subprocess.TimeoutExpired:
            _set_step(job, "gromacs", "error", f"{label} timed out after {timeout} s")
            return {"available": True, "error": f"{label} timed out after {timeout} s"}
        with (gm / "commands.log").open("a", encoding="utf-8") as log:
            log.write(" ".join(cmd) + "\n" + result.stdout[-3000:] + "\n" + result.stderr[-3000:] + "\n")
        if result.returncode != 0:
            _set_step(job, "gromacs", "error", f"GROMACS {label} failed")
            return {"available": True, "error": (result.stderr or result.stdout)[-500:]}
    (gm / "em.mdp").write_text(f"""integrator = steep
nsteps = {int(config['em_steps'])}
emtol = 500
emstep = 0.01
cutoff-scheme = Verlet
coulombtype = PME
rcoulomb = 1.0
rvdw = 1.0
pbc = xyz
""", encoding="utf-8")
    (gm / "md.mdp").write_text(f"""integrator = md
dt = {float(config['dt_ps'])}
nsteps = {int(config['md_steps'])}
nstxout-compressed = 250
nstenergy = 100
nstlog = 100
continuation = no
gen_vel = yes
gen_seed = {int(config['docking_seed'])}
gen_temp = {float(config['temperature_k'])}
tcoupl = V-rescale
tc-grps = System
tau_t = 0.1
ref_t = {float(config['temperature_k'])}
constraints = h-bonds
constraint-algorithm = lincs
cutoff-scheme = Verlet
coulombtype = PME
rcoulomb = 1.0
rvdw = 1.0
pbc = xyz
""", encoding="utf-8")
    def grompp(label: str, mdp: str, structure: str, tpr: str, logfile: str) -> dict[str, Any] | None:
        try:
            result = _run([GMX, "grompp", "-f", mdp, "-c", structure, "-p", "topol.top", "-o", tpr, "-maxwarn", "2"], gm, timeout=config["timeout_prepare"], env=env)
        except subprocess.TimeoutExpired:
            _set_step(job, "gromacs", "error", f"grompp {label} timed out after {config['timeout_prepare']} s")
            return {"available": True, "error": f"grompp {label} timeout"}
        (gm / logfile).write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
        if result.returncode != 0:
            _set_step(job, "gromacs", "error", f"grompp {label} failed")
            return {"available": True, "error": f"grompp {label} failed: " + (result.stderr or result.stdout)[-400:]}
        return None

    def mdrun(label: str, deffnm: str, timeout: int, description: str) -> dict[str, Any] | None:
        try:
            result = _run([GMX, "mdrun", "-deffnm", deffnm, "-nt", threads, "-nb", "cpu"], gm, timeout=timeout, env=env)
        except subprocess.TimeoutExpired:
            _set_step(job, "gromacs", "error", f"{description} timed out after {timeout} s; raise timeout or lower steps")
            return {"available": True, "error": f"{description} timed out after {timeout} s"}
        (gm / f"{label}_mdrun.log").write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
        if result.returncode != 0:
            _set_step(job, "gromacs", "error", f"{description} failed")
            return {"available": True, "error": f"{description} failed: " + (result.stderr or result.stdout)[-400:]}
        return None

    failure = grompp("em", "em.mdp", "solvated.gro", "em.tpr", "em_grompp.log")
    if failure:
        return failure
    failure = mdrun("em", "em", config["timeout_em"], "energy minimization")
    if failure:
        return failure
    failure = grompp("md", "md.mdp", "em.gro", "md.tpr", "md_grompp.log")
    if failure:
        return failure
    failure = mdrun("md", "md", config["timeout_md"], "short MD")
    if failure:
        return failure
    summary: dict[str, Any] = {
        "available": True, "engine": "GROMACS", "forcefield": "amber99sb-ildn/tip3p",
        "steps": int(config["md_steps"]), "em_steps": int(config["em_steps"]),
        "dt_ps": float(config["dt_ps"]), "time_ps": round(int(config["md_steps"]) * float(config["dt_ps"]), 3),
        "temperature_k": float(config["temperature_k"]), "seed": int(config["docking_seed"]),
        "threads": int(config["threads"]),
    }
    for label, file in (("em", "em.log"), ("md", "md.log")):
        text = (gm / file).read_text(encoding="utf-8", errors="ignore") if (gm / file).exists() else ""
        potential = _potential_from_log(text)
        if potential is not None:
            summary[f"{label}_potential_kj_mol"] = potential
        if label == "em" and text:
            summary.update(_em_status(text))
    _set_step(job, "gromacs", "done", f"EM + {summary['time_ps']} ps NVT MD complete", ["gromacs/em.gro", "gromacs/md.gro", "gromacs/md.xtc", "gromacs/md.edr", "gromacs/md.log", "gromacs/em.log"])
    return summary


def _gromacs_complex(job: dict[str, Any], work: Path, config: dict[str, Any]) -> dict[str, Any]:
    if not Path(ACPYPE).exists():
        return {"available": True, "error": "ACPYPE binary not found"}
    complex_pdb = work / "complex.pdb"
    pose_pdb = work / "best_pose.pdb"
    ligand_sdf = work / "ligand.sdf"
    if not complex_pdb.exists() or not pose_pdb.exists() or not ligand_sdf.exists():
        return {"available": True, "error": "complex, pose or ligand file is missing"}
    _set_step(job, "gromacs", "running", "ACPYPE/GAFF2 topology, complex solvation, EM and short NVT")
    gm = work / "gromacs_complex"
    if gm.exists():
        shutil.rmtree(gm)
    gm.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(complex_pdb, gm / "complex_input.pdb")
    shutil.copyfile(pose_pdb, gm / "pose.pdb")
    shutil.copyfile(ligand_sdf, gm / "ligand_template.sdf")
    _clean_protein(gm / "complex_input.pdb", gm / "protein.pdb")
    threads = str(config["threads"])
    env = {"OMP_NUM_THREADS": threads}
    prep_timeout = config["timeout_prepare"]
    try:
        prepared = _run([
            MOLECULE_PYTHON,
            str(Path(__file__).with_name("ligand_pose.py")),
            str(gm / "ligand_template.sdf"),
            str(gm / "pose.pdb"),
            str(gm / "ligand_pose.sdf"),
        ], gm, timeout=prep_timeout)
    except subprocess.TimeoutExpired:
        return {"available": True, "error": f"ligand pose preparation timed out after {prep_timeout} s"}
    (gm / "ligand_pose.log").write_text(prepared.stdout + "\n" + prepared.stderr, encoding="utf-8")
    if prepared.returncode != 0:
        return {"available": True, "error": (prepared.stderr or prepared.stdout)[-500:]}
    info_path = gm / "ligand_pose.json"
    if not info_path.exists():
        return {"available": True, "error": "ligand pose metadata was not written"}
    info = json.loads(info_path.read_text(encoding="utf-8"))
    charge = int(info.get("charge") or 0)
    try:
        acpype = _run([ACPYPE, "-i", "ligand_pose.sdf", "-b", "LIG", "-c", "bcc", "-a", "gaff2", "-n", str(charge), "-o", "gmx"], gm, timeout=prep_timeout)
    except subprocess.TimeoutExpired:
        return {"available": True, "error": f"ACPYPE timed out after {prep_timeout} s"}
    (gm / "acpype.log").write_text(acpype.stdout + "\n" + acpype.stderr, encoding="utf-8")
    if acpype.returncode != 0:
        return {"available": True, "error": (acpype.stderr or acpype.stdout)[-500:]}
    ligand_itp = gm / "LIG.acpype" / "LIG_GMX.itp"
    ligand_gro = gm / "LIG.acpype" / "LIG_GMX.gro"
    if not ligand_itp.exists() or not ligand_gro.exists():
        return {"available": True, "error": "ACPYPE did not produce GROMACS topology files"}
    ff_source = Path(GMXLIB) / "amber99sb-ildn.ff"
    ff_target = gm / "amber99sb-ildn.ff"
    if ff_source.exists() and not ff_target.exists():
        try:
            shutil.copytree(ff_source, ff_target)
        except OSError:
            pass
    if ff_target.exists():
        env["GMXLIB"] = None
    commands = [
        ([GMX, "pdb2gmx", "-f", "protein.pdb", "-o", "processed.gro", "-water", "tip3p", "-ff", "amber99sb-ildn", "-ignh"], "pdb2gmx"),
        ([GMX, "editconf", "-f", "complex.gro", "-o", "boxed.gro", "-c", "-d", str(config["box_padding_nm"]), "-bt", "cubic"], "editconf"),
        ([GMX, "solvate", "-cp", "boxed.gro", "-cs", "spc216.gro", "-o", "solvated.gro", "-p", "topol.top"], "solvate"),
    ]
    for cmd, label in commands:
        try:
            result = _run(cmd, gm, timeout=prep_timeout, env=env)
        except subprocess.TimeoutExpired:
            return {"available": True, "error": f"{label} timed out after {prep_timeout} s"}
        with (gm / "commands.log").open("a", encoding="utf-8") as log:
            log.write(" ".join(cmd) + "\n" + result.stdout[-3000:] + "\n" + result.stderr[-3000:] + "\n")
        if result.returncode != 0:
            return {"available": True, "error": f"GROMACS {label} failed: " + (result.stderr or result.stdout)[-400:]}
        if label == "pdb2gmx":
            _merge_gro(gm / "processed.gro", ligand_gro, gm / "complex.gro")
            _add_complex_topology(gm / "topol.top")
    _write_gmx_mdp(gm, config)
    try:
        ion_topology = _run([GMX, "grompp", "-f", "ions.mdp", "-c", "solvated.gro", "-p", "topol.top", "-o", "ions.tpr", "-maxwarn", "2"], gm, timeout=prep_timeout, env=env)
    except subprocess.TimeoutExpired:
        return {"available": True, "error": f"grompp ions timed out after {prep_timeout} s"}
    (gm / "ions_grompp.log").write_text(ion_topology.stdout + "\n" + ion_topology.stderr, encoding="utf-8")
    if ion_topology.returncode != 0:
        return {"available": True, "error": "grompp ions failed: " + (ion_topology.stderr or ion_topology.stdout)[-400:]}
    try:
        genion = _run([GMX, "genion", "-s", "ions.tpr", "-o", "solvated_ions.gro", "-p", "topol.top", "-pname", "NA", "-nname", "CL", "-neutral"], gm, timeout=prep_timeout, env=env, input_text="SOL\n")
    except subprocess.TimeoutExpired:
        return {"available": True, "error": f"genion timed out after {prep_timeout} s"}
    (gm / "genion.log").write_text(genion.stdout + "\n" + genion.stderr, encoding="utf-8")
    ion_count = None
    structure = "solvated.gro"
    ion_note = "neutralization skipped"
    if genion.returncode == 0 and (gm / "solvated_ions.gro").exists():
        structure = "solvated_ions.gro"
        ion_note = "neutralized with NA/CL"
        match = re.search(r"add\s+(\d+)\s+NA\s+ions\s+and\s+(\d+)\s+CL\s+ions", genion.stdout)
        if match:
            ion_count = int(match.group(1)) + int(match.group(2))
    def grompp(label: str, mdp: str, coordinates: str, tpr: str, logfile: str) -> dict[str, Any] | None:
        try:
            result = _run([GMX, "grompp", "-f", mdp, "-c", coordinates, "-p", "topol.top", "-o", tpr, "-maxwarn", "2"], gm, timeout=prep_timeout, env=env)
        except subprocess.TimeoutExpired:
            return {"available": True, "error": f"grompp {label} timed out after {prep_timeout} s"}
        (gm / logfile).write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
        if result.returncode != 0:
            return {"available": True, "error": f"grompp {label} failed: " + (result.stderr or result.stdout)[-400:]}
        return None
    def mdrun(label: str, deffnm: str, timeout: int, description: str) -> dict[str, Any] | None:
        try:
            result = _run([GMX, "mdrun", "-deffnm", deffnm, "-nt", threads, "-nb", "cpu"], gm, timeout=timeout, env=env)
        except subprocess.TimeoutExpired:
            return {"available": True, "error": f"{description} timed out after {timeout} s; raise timeout or lower steps"}
        (gm / f"{label}_mdrun.log").write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
        if result.returncode != 0:
            return {"available": True, "error": f"{description} failed: " + (result.stderr or result.stdout)[-400:]}
        return None
    failure = grompp("em", "em.mdp", structure, "em.tpr", "em_grompp.log")
    if failure:
        return failure
    failure = mdrun("em", "em", config["timeout_em"], "complex energy minimization")
    if failure:
        return failure
    em_coordinates = "em.gro"
    em_log = "em.log"
    em_continuation = False
    em_first = _em_status((gm / "em.log").read_text(encoding="utf-8", errors="ignore"))
    if em_first.get("em_converged") is False:
        failure = grompp("em2", "em.mdp", "em.gro", "em2.tpr", "em2_grompp.log")
        if failure is None:
            failure = mdrun("em2", "em2", config["timeout_em"], "complex energy minimization continuation")
        if failure is None:
            em_coordinates = "em2.gro"
            em_log = "em2.log"
            em_continuation = True
    failure = grompp("md", "md.mdp", em_coordinates, "md.tpr", "md_grompp.log")
    if failure:
        return failure
    failure = mdrun("md", "md", config["timeout_md"], "complex short MD")
    if failure:
        return failure
    protein_atoms, protein_count, _ = _gro_parts(gm / "processed.gro")
    _, ligand_count, _ = _gro_parts(ligand_gro)
    _, complex_count, box = _gro_parts(gm / "complex.gro")
    summary: dict[str, Any] = {
        "available": True, "engine": "GROMACS", "system": "protein-ligand complex", "md_mode": "complex",
        "forcefield": "amber99sb-ildn/tip3p + GAFF2/AM1-BCC",
        "ligand_atoms": ligand_count, "protein_atoms": protein_count, "complex_atoms": complex_count,
        "ligand_charge": charge, "ligand_topology": "ACPYPE GAFF2/AM1-BCC", "box_nm": box.split()[:3],
        "ions": ion_count, "ion_note": ion_note, **_complex_ligand_metrics(gm / em_coordinates, gm / "md.gro"),
        "steps": int(config["md_steps"]), "em_steps": int(config["em_steps"]),
        "dt_ps": float(config["dt_ps"]), "time_ps": round(int(config["md_steps"]) * float(config["dt_ps"]), 3),
        "temperature_k": float(config["temperature_k"]), "seed": int(config["docking_seed"]),
        "threads": int(config["threads"]),
    }
    if em_continuation:
        summary["em_continuation"] = True
        summary["em_initial_converged"] = em_first.get("em_converged")
        summary["em_initial_fmax"] = em_first.get("em_fmax")
        summary["em_initial_steps"] = em_first.get("em_actual_steps")
    for label, file in (("em", em_log), ("md", "md.log")):
        text = (gm / file).read_text(encoding="utf-8", errors="ignore") if (gm / file).exists() else ""
        potential = _potential_from_log(text)
        if potential is not None:
            summary[f"{label}_potential_kj_mol"] = potential
        if label == "em" and text:
            summary.update(_em_status(text))
    _set_step(job, "gromacs", "done", f"Complex EM + {summary['time_ps']} ps NVT MD complete", ["gromacs_complex/complex.gro", "gromacs_complex/em.gro", "gromacs_complex/em2.gro", "gromacs_complex/md.gro", "gromacs_complex/md.xtc", "gromacs_complex/md.edr", "gromacs_complex/md.log", "gromacs_complex/em.log", "gromacs_complex/em2.log", "gromacs_complex/LIG.acpype/LIG_GMX.itp"])
    return summary


def _gromacs(job: dict[str, Any], work: Path, config: dict[str, Any]) -> dict[str, Any]:
    complex_error = None
    if config.get("md_mode") == "complex" and (work / "complex.pdb").exists():
        try:
            complex_result = _gromacs_complex(job, work, config)
            if not complex_result.get("error"):
                return complex_result
            complex_error = complex_result.get("error")
        except Exception as exc:
            complex_error = str(exc)[:500]
        _set_step(job, "gromacs", "running", "Complex MD failed; falling back to protein-only MD")
    summary = _gromacs_protein(job, work, config)
    if complex_error:
        summary["requested_md_mode"] = "complex"
        summary["md_mode"] = "protein"
        summary["complex_error"] = complex_error
    elif not summary.get("error"):
        summary["md_mode"] = "protein"
    return summary


def _cp2k(job: dict[str, Any], work: Path, target: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    if not Path(CP2K).exists():
        _set_step(job, "cp2k", "skipped", "CP2K binary not found")
        return {"available": False}
    _set_step(job, "cp2k", "running", "Preparing ligand and running PBE/DZVP single point")
    qm = work / "cp2k"
    qm.mkdir(exist_ok=True)
    xyz = qm / "ligand.xyz"
    result = _run([OBABEL, str(work / "ligand.sdf"), "-O", "ligand.xyz"], qm, timeout=60)
    if result.returncode != 0 or not xyz.exists():
        _set_step(job, "cp2k", "error", "ligand XYZ conversion failed")
        return {"available": True, "error": "obabel conversion failed"}
    lines = xyz.read_text(encoding="utf-8").splitlines()
    count = int(lines[0].strip())
    atoms = [line.split() for line in lines[2:2 + count]]
    allowed = {"C", "H", "O", "N", "S", "P", "F", "Cl", "Br", "I"}
    if any(atom[0] not in allowed for atom in atoms):
        _set_step(job, "cp2k", "skipped", "Elements outside the C/H/O/N/S/P/halogen set")
        return {"available": True, "skipped": True}
    basis = Path(CP2K_DATA) / "BASIS_MOLOPT"
    potential = Path(CP2K_DATA) / "GTH_POTENTIALS"
    if basis.exists():
        try:
            (qm / "BASIS_MOLOPT").symlink_to(basis)
            (qm / "GTH_POTENTIALS").symlink_to(potential)
        except OSError:
            pass
    element_potential = {"H": "GTH-PBE-q1", "C": "GTH-PBE-q4", "N": "GTH-PBE-q5", "O": "GTH-PBE-q6", "S": "GTH-PBE-q6", "P": "GTH-PBE-q5", "F": "GTH-PBE-q7", "Cl": "GTH-PBE-q7", "Br": "GTH-PBE-q7", "I": "GTH-PBE-q7"}
    body = [f"      {atom[0]} {float(atom[1]):.6f} {float(atom[2]):.6f} {float(atom[3]):.6f}" for atom in atoms]
    kinds = []
    for element in sorted({atom[0] for atom in atoms}):
        kinds.append(f"""    &KIND {element}
      BASIS_SET DZVP-MOLOPT-GTH
      POTENTIAL {element_potential.get(element, 'GTH-PBE-q6')}
    &END KIND""")
    input_text = f"""&GLOBAL
  PROJECT ligand
  RUN_TYPE ENERGY
  PRINT_LEVEL LOW
&END GLOBAL
&FORCE_EVAL
  METHOD QS
  &DFT
    CHARGE 0
    MULTIPLICITY 1
    UKS .FALSE.
    BASIS_SET_FILE_NAME BASIS_MOLOPT
    POTENTIAL_FILE_NAME GTH_POTENTIALS
    &MGRID
      CUTOFF {int(config['qm_cutoff_ry'])}
      REL_CUTOFF 40
      NGRIDS 4
    &END MGRID
    &QS
      EPS_DEFAULT 1.0E-10
    &END QS
    &SCF
      MAX_SCF {int(config['qm_max_scf'])}
      EPS_SCF 1.0E-5
    &END SCF
    &XC
      &XC_FUNCTIONAL PBE
      &END XC_FUNCTIONAL
    &END XC
    &POISSON
      PERIODIC XYZ
    &END POISSON
  &END DFT
  &SUBSYS
    &CELL
      ABC 16 16 16
    &END CELL
    &COORD
{chr(10).join(body)}
    &END COORD
{chr(10).join(kinds)}
  &END SUBSYS
&END FORCE_EVAL
"""
    (qm / "cp2k.inp").write_text(input_text, encoding="utf-8")
    started = time.time()
    try:
        result = _run([CP2K, "-i", "cp2k.inp", "-o", "cp2k.out"], qm, timeout=config["timeout_qm"])
        (qm / "cp2k.log").write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    except subprocess.TimeoutExpired:
        _set_step(job, "cp2k", "error", f"CP2K timed out after {config['timeout_qm']} s")
        return {"available": True, "error": "timeout"}
    text = (qm / "cp2k.out").read_text(encoding="utf-8", errors="ignore") if (qm / "cp2k.out").exists() else ""
    energy = re.findall(r"ENERGY\| Total FORCE_EVAL \( QS \) energy \[a\.u\.\]:\s*([-0-9.]+)", text)
    if result.returncode != 0 or not energy:
        _set_step(job, "cp2k", "error", "CP2K did not return a total energy")
        return {"available": True, "error": (text[-500:] or result.stderr[-500:])}
    ev = float(energy[-1]) * 27.211386245988
    summary = {"available": True, "engine": "CP2K 2023.2", "method": "PBE/DZVP-MOLOPT-GTH", "energy_hartree": float(energy[-1]), "energy_ev": ev, "seconds": round(time.time() - started, 1), "atoms": len(atoms)}
    _set_step(job, "cp2k", "done", f"PBE single point: {ev:.3f} eV", ["cp2k/cp2k.inp", "cp2k/cp2k.out", "cp2k/ligand.xyz"])
    return summary


def _write_haddock_inputs(job: dict[str, Any], work: Path, target: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    root = work / "haddock"
    inputs = root / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    _set_step(job, "prepare", "running", f"准备 HADDOCK3 {target['workflow']} 输入")
    receptor_text = _download_pdb(target["pdb_id"]).read_text(encoding="utf-8", errors="ignore")
    receptor_pdb, receptor_source, receptor_atoms = _filter_chain_pdb(
        receptor_text,
        target.get("source_chain") or "",
        records=("ATOM",),
        exclude=CARBOHYDRATE_RESIDUES,
        new_chain="A",
    )
    if receptor_atoms < 10:
        raise ValueError("HADDOCK3 receptor chain has too few atoms")
    (root / "receptor.pdb").write_text(receptor_pdb, encoding="utf-8")
    (inputs / "receptor.pdb").write_text(receptor_pdb, encoding="utf-8")
    partner_atoms = 0
    partner_source = target.get("partner_source_chain") or ""
    if target["workflow"] == "protein-ligand":
        partner_atoms = _write_haddock_ligand_pdb(target["smiles"], root / "partner.pdb", int(config["haddock_seed"]))
        shutil.copyfile(root / "partner.pdb", inputs / "partner.pdb")
        partner_source = "B"
    else:
        partner_text = _download_pdb(target["partner_pdb_id"]).read_text(encoding="utf-8", errors="ignore")
        if target["workflow"] == "protein-polysaccharide":
            partner_pdb, partner_source, partner_atoms = _filter_chain_pdb(
                partner_text,
                partner_source,
                records=("ATOM", "HETATM"),
                residues=CARBOHYDRATE_RESIDUES,
                new_chain="B",
            )
        else:
            partner_pdb, partner_source, partner_atoms = _filter_chain_pdb(
                partner_text,
                partner_source,
                records=("ATOM",),
                exclude=CARBOHYDRATE_RESIDUES,
                new_chain="B",
            )
        (root / "partner.pdb").write_text(partner_pdb, encoding="utf-8")
        (inputs / "partner.pdb").write_text(partner_pdb, encoding="utf-8")
    if partner_atoms < 3:
        raise ValueError("HADDOCK3 partner has too few atoms")
    active_receptor = _parse_residues(config.get("haddock_active_receptor") or "")
    active_partner = _parse_residues(config.get("haddock_active_partner") or "")
    if target["workflow"] == "protein-ligand" and active_receptor and not active_partner:
        active_partner = [1]
    ambig = _haddock_ambig(
        root,
        root / "receptor.pdb",
        root / "partner.pdb",
        "A",
        "B",
        active_receptor,
        active_partner,
        config,
        expand_passive=target["workflow"] != "protein-ligand",
    )
    config_text = _haddock_config_text(config, has_ambig=bool(ambig), workflow=target["workflow"])
    (root / "haddock.cfg").write_text(config_text, encoding="utf-8")
    manifest = {
        "workflow": target["workflow"],
        "receptor": {
            "pdb_id": target["pdb_id"],
            "name": target["protein"],
            "source_chain": receptor_source,
            "haddock_chain": "A",
            "atoms": receptor_atoms,
            "sha256": hashlib.sha256((root / "receptor.pdb").read_bytes()).hexdigest(),
        },
        "partner": {
            "pdb_id": target.get("partner_pdb_id") or "",
            "name": target.get("partner") or target.get("ligand") or "",
            "source_chain": partner_source,
            "haddock_chain": "B",
            "atoms": partner_atoms,
            "sha256": hashlib.sha256((root / "partner.pdb").read_bytes()).hexdigest(),
            "smiles": target.get("smiles") or "",
        },
        "restraints": ambig or {"mode": "cmrest" if config["haddock_cmrest"] else "ranair"},
        "config": config_text,
        "created_utc": _now(),
    }
    (root / "haddock_inputs.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _set_step(job, "prepare", "done", f"HADDOCK3 输入就绪：受体 {receptor_atoms} 原子，伙伴 {partner_atoms} 原子")
    return {"root": root, "manifest": manifest, "ambig": ambig}


def _haddock(job: dict[str, Any], work: Path, target: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    if not Path(HADDOCK).exists():
        _set_step(job, "haddock", "skipped", "HADDOCK3 binary not found")
        return {"available": False, "error": "HADDOCK3 binary not found"}
    prepared = _write_haddock_inputs(job, work, target, config)
    root = prepared["root"]
    run_root = root / "run1"
    _set_step(
        job,
        "haddock",
        "running",
        f"HADDOCK3 {target['workflow']}：sampling={config['haddock_sampling']}，select={config['haddock_select_top']}，"
        f"flexref={bool(config['haddock_flexref'])}，emref={bool(config['haddock_emref'])}，cluster={bool(config['haddock_cluster'])}",
    )
    started = time.time()
    try:
        result = _run(
            [HADDOCK, "haddock.cfg"],
            root,
            timeout=int(config["haddock_timeout"]),
            env={"OMP_NUM_THREADS": str(int(config["haddock_ncores"]))},
        )
    except subprocess.TimeoutExpired as exc:
        log = (exc.stdout or "") + "\n" + (exc.stderr or "")
        (root / "stdout.log").write_text(log, encoding="utf-8", errors="ignore")
        _set_step(job, "haddock", "error", f"HADDOCK3 超时（{config['haddock_timeout']} s）")
        return {"available": True, "error": f"timeout after {config['haddock_timeout']} s"}
    (root / "stdout.log").write_text((result.stdout or "") + "\n" + (result.stderr or ""), encoding="utf-8", errors="ignore")
    if result.returncode != 0:
        detail = ((result.stderr or "") + "\n" + (result.stdout or "")).strip()[-1200:]
        _set_step(job, "haddock", "error", "HADDOCK3 失败；请查看 stdout.log")
        return {"available": True, "error": detail or "HADDOCK3 returned a non-zero exit code"}
    try:
        parsed = _haddock_results(run_root)
    except Exception as exc:
        _set_step(job, "haddock", "error", f"HADDOCK3 输出解析失败：{str(exc)[:200]}")
        return {"available": True, "error": f"HADDOCK3 output parse failed: {str(exc)[:500]}"}
    best_target = root / "best_model.pdb"
    shutil.copyfile(parsed["best_model_path"], best_target)
    capri_copy = root / "capri_ss.tsv"
    shutil.copyfile(parsed["capri_ss"], capri_copy)
    capri_clt_copy = None
    if parsed["capri_clt"]:
        capri_clt_copy = root / "capri_clt.tsv"
        shutil.copyfile(parsed["capri_clt"], capri_clt_copy)
    analysis = sorted(run_root.glob("analysis/*/report.html"), key=lambda item: item.stat().st_mtime, reverse=True)
    analysis_copy = None
    if analysis:
        analysis_copy = root / "haddock_analysis.html"
        shutil.copyfile(analysis[0], analysis_copy)
    models = []
    for row in parsed["models"]:
        models.append({
            **row,
            "artifact": str(Path("haddock") / "run1" / row["model"]),
        })
    summary = {
        "available": True,
        "engine": "HADDOCK3",
        "workflow": target["workflow"],
        "score": parsed["score"],
        "score_unit": "HADDOCK score (a.u., lower is better)",
        "models": models,
        "clusters": parsed["clusters"],
        "best_model": "haddock/best_model.pdb",
        "capri_ss": "haddock/capri_ss.tsv",
        "capri_clt": "haddock/capri_clt.tsv" if capri_clt_copy else None,
        "analysis_html": "haddock/haddock_analysis.html" if analysis_copy else None,
        "config_file": "haddock/haddock.cfg",
        "inputs_manifest": "haddock/haddock_inputs.json",
        "stdout": "haddock/stdout.log",
        "run_dir": "haddock/run1",
        "restraints": prepared["ambig"] or {"mode": "cmrest" if config["haddock_cmrest"] else "ranair"},
        "sampling": int(config["haddock_sampling"]),
        "select_top": int(config["haddock_select_top"]),
        "top_models": int(config["haddock_top_models"]),
        "flexref": bool(config["haddock_flexref"]),
        "emref": bool(config["haddock_emref"]),
        "cluster": bool(config["haddock_cluster"]),
        "ncores": int(config["haddock_ncores"]),
        "seed": int(config["haddock_seed"]),
        "duration_s": round(time.time() - started, 1),
        "reference_used": False,
        "target": {key: target.get(key) for key in ("pdb_id", "protein", "partner_pdb_id", "partner", "ligand", "smiles", "workflow")},
    }
    _set_step(
        job,
        "haddock",
        "done",
        f"HADDOCK3 最佳 score {summary['score']:.3f} a.u.；{len(summary['models'])} 个模型；{len(summary['clusters'])} 个簇",
        ["haddock/best_model.pdb", "haddock/haddock.cfg", "haddock/haddock_inputs.json", "haddock/stdout.log", "haddock/capri_ss.tsv", "haddock/capri_clt.tsv", "haddock/haddock_analysis.html"],
    )
    return summary


def _haddock_report(job: dict[str, Any], work: Path, target: dict[str, Any], result: dict[str, Any]) -> None:
    haddock = result.get("haddock") or {}
    lines = [
        f"# HADDOCK3 docking report {job['id']}",
        "",
        f"- Query: {job.get('query') or ''}",
        f"- Workflow: {haddock.get('workflow') or target.get('workflow')}",
        f"- Receptor: {target.get('protein')} (PDB {target.get('pdb_id')}, source chain {target.get('source_chain') or 'auto'} -> HADDOCK chain A)",
        f"- Partner: {target.get('partner') or target.get('ligand') or ''}",
    ]
    if target.get("partner_pdb_id"):
        lines.append(f"- Partner PDB: {target.get('partner_pdb_id')} (source chain {target.get('partner_source_chain') or 'auto'} -> HADDOCK chain B)")
    if target.get("smiles"):
        lines.append(f"- Ligand SMILES: {target.get('smiles')}")
    haddock_settings = {key: value for key, value in (job.get("config") or {}).items() if key.startswith("haddock_")}
    lines += [
        f"- Generated: {_now()}",
        f"- Parameter fingerprint: {job.get('parameter_fingerprint')}",
        "- Engine scope: HADDOCK3 only; Vina, GROMACS and CP2K are not executed for this job.",
        "",
        "## Settings",
        "```json",
        json.dumps(haddock_settings, ensure_ascii=False, indent=2),
        "```",
        "",
        "## HADDOCK3 result",
        "",
        f"- Best HADDOCK score: {haddock.get('score')} a.u. (lower is better; not a binding free energy)",
        f"- Ranked models returned: {len(haddock.get('models') or [])}",
        f"- Clusters: {len(haddock.get('clusters') or [])}",
        f"- Sampling: {haddock.get('sampling')}; selected for refinement: {haddock.get('select_top')}; top models: {haddock.get('top_models')}",
        f"- Flexref: {haddock.get('flexref')}; EM refinement: {haddock.get('emref')}; clustering: {haddock.get('cluster')}",
        f"- Seed: {haddock.get('seed')}; cores: {haddock.get('ncores')}; duration: {haddock.get('duration_s')} s",
        f"- Restraints: {json.dumps(haddock.get('restraints') or {}, ensure_ascii=False)}",
        "",
        "## Ranked models",
        "",
        "| Rank | HADDOCK score (a.u.) | Cluster | Cluster population | Model |",
        "|---|---|---|---|---|",
    ]
    for row in haddock.get("models") or []:
        lines.append(f"| {row.get('rank')} | {row.get('score')} | {row.get('cluster_id')} | {row.get('cluster_population') if row.get('cluster_population') is not None else '-'} | {row.get('artifact') or row.get('model')} |")
    if not haddock.get("models"):
        lines.append("| - | - | - | - | no scored models |")
    lines += [
        "",
        "## Interpretation limits",
        "- HADDOCK score is a weighted scoring-function value in arbitrary units; lower is better, but it is not a measured or absolute binding free energy.",
        "- No experimental reference structure was supplied, so CAPRI RMSD/FNAT/DockQ values are not used as validation and are intentionally omitted from this summary.",
        "- HADDOCK3 sampling, restraint selection, protonation, missing residues, glycan linkage and ligand tautomer/charge choices can change the ranking.",
        "- The best model is a docking/refinement hypothesis for visual inspection and follow-up experiments; it does not prove binding, affinity or safety.",
        "- Protein-polysaccharide runs depend on carbohydrate residue templates and linkage definitions; inspect the HADDOCK log and input PDB before interpretation.",
        "",
        "## Artifacts",
        "- haddock/best_model.pdb",
        "- haddock/haddock.cfg",
        "- haddock/haddock_inputs.json",
        "- haddock/stdout.log",
        "- haddock/capri_ss.tsv",
    ]
    if (work / "haddock/capri_clt.tsv").exists():
        lines.append("- haddock/capri_clt.tsv")
    if (work / "haddock/haddock_analysis.html").exists():
        lines.append("- haddock/haddock_analysis.html")
    (work / "report.md").write_text("\n".join(lines), encoding="utf-8")
    html = "<html><head><meta charset='utf-8'><title>HADDOCK3 report</title></head><body><pre>" + "\n".join(lines).replace("&", "&amp;").replace("<", "&lt;") + "</pre></body></html>"
    (work / "report.html").write_text(html, encoding="utf-8")
    with (work / "haddock_models.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["rank", "haddock_score_au", "cluster_id", "cluster_population", "model"])
        for row in haddock.get("models") or []:
            writer.writerow([row.get("rank"), row.get("score"), row.get("cluster_id"), row.get("cluster_population"), row.get("artifact") or row.get("model")])
    job["result"]["report"] = "report.html"


def _run_haddock_job(job_id: str) -> None:
    job = _JOBS[job_id]
    work = data.COMPUTE_DIR / job_id
    config = job["config"]
    target = job.get("haddock_target") or {}
    with _LOCK:
        job["status"] = "running"
        _write_job(job)
    job["parameter_fingerprint"] = _fingerprint(target, config)
    try:
        _set_step(job, "resolve", "done", f"HADDOCK3 {target.get('workflow')} 目标已解析：{target.get('pdb_id')} + {target.get('partner') or target.get('ligand')}")
        haddock = _haddock(job, work, target, config)
        job["result"]["haddock"] = haddock
        job["result"]["engine"] = "haddock"
        job["result"]["best_pair"] = target.get("pair_id")
        job["result"]["complex_pdb"] = haddock.get("best_model")
        job["result"]["advanced_scope"] = "haddock"
        if haddock.get("error"):
            job["status"] = "error"
            job["error"] = haddock["error"]
            job["finished_utc"] = _now()
            with _LOCK:
                _write_job(job)
            return
        _set_step(job, "report", "running", "正在生成 HADDOCK3 报告")
        _haddock_report(job, work, target, job["result"])
        artifacts = [
            "job.json", "report.md", "report.html", "haddock_models.csv",
            "haddock/best_model.pdb", "haddock/haddock.cfg", "haddock/haddock_inputs.json",
            "haddock/stdout.log", "haddock/capri_ss.tsv",
        ]
        if haddock.get("capri_clt"):
            artifacts.append(haddock["capri_clt"])
        if haddock.get("analysis_html"):
            artifacts.append(haddock["analysis_html"])
        for row in haddock.get("models") or []:
            if row.get("artifact"):
                artifacts.append(row["artifact"])
        artifacts = list(dict.fromkeys(artifacts))
        _set_step(job, "report", "done", "HADDOCK3 报告已生成", ["report.md", "report.html", "haddock_models.csv"])
        with _LOCK:
            job["status"] = "complete"
            job["finished_utc"] = _now()
            job["result"]["artifacts"] = artifacts
            _write_job(job)
    except Exception as exc:
        with _LOCK:
            job["status"] = "error"
            job["error"] = str(exc)[:1000]
            job["finished_utc"] = _now()
            _write_job(job)
        for step in job.get("steps") or []:
            if step.get("status") in {"running", "pending"}:
                _set_step(job, step["id"], "error", str(exc)[:300])
                break


def _report(job: dict[str, Any], work: Path, target: dict[str, Any]) -> None:
    result = job.get("result", {})
    pairs = [pair for pair in job.get("pairs", []) if pair.get("docking") or pair.get("prepare_error")]
    ranking = result.get("ranking") or []
    lines = [
        f"# Mechanism report {job['id']}",
        "",
        f"- Query: {job['query']}",
        f"- Best receptor: {target['protein']} (PDB {target['pdb_id']}, UniProt {target['uniprot'] or 'n/a'})",
        f"- Best ligand: {target['ligand']}",
        f"- Pair count: {len(job.get('pairs', []))}",
        f"- Generated: {_now()}",
        f"- Parameter fingerprint: {job.get('parameter_fingerprint')}",
        "",
        "## Parameters",
        "```json",
        json.dumps(job.get("config", {}), ensure_ascii=False, indent=2),
        "```",
        "",
        "## Docking matrix",
        "",
        "| Rank | Receptor | Ligand | Vina best (kcal/mol) | Complex |",
        "|---|---|---|---|---|",
    ]
    for row in ranking:
        affinity = row.get("best_affinity")
        affinity_text = f"{affinity:.2f}" if isinstance(affinity, (int, float)) else "not available"
        lines.append(f"| {row.get('rank')} | {row.get('pdb_id')} | {row.get('ligand')} | {affinity_text} | {row.get('complex_pdb') or '-'} |")
    if not ranking:
        lines.append("| - | - | - | no successful docking | - |")
    lines += ["", "## Results"]
    docking = result.get("docking") or {}
    if docking.get("best_affinity") is not None:
        lines.append(f"- AutoDock Vina best affinity: {docking.get('best_affinity')} kcal/mol for {docking.get('pdb_id')} + {docking.get('ligand')} (seed {docking.get('seed')}, exhaustiveness {docking.get('exhaustiveness')})")
    elif docking.get("error"):
        lines.append(f"- AutoDock Vina: error - {docking.get('error')}")
    if result.get("complex_pdb"):
        lines.append(f"- Complex structure: {result.get('complex_pdb')} (receptor ATOM records + first docked pose as HETATM LIG; not a minimized complex).")
    gmx = result.get("gromacs") or {}
    if gmx.get("available") and gmx.get("time_ps") is not None:
        if gmx.get("md_mode") == "complex":
            lines.append(f"- GROMACS complex MD: {gmx.get('time_ps')} ps, {gmx.get('steps')} steps, {gmx.get('temperature_k')} K, {gmx.get('ligand_atoms')} ligand atoms, charge {gmx.get('ligand_charge')}, EM potential {gmx.get('em_potential_kj_mol')} kJ/mol, MD potential {gmx.get('md_potential_kj_mol')} kJ/mol")
            lines.append(f"  - Ligand topology: {gmx.get('ligand_topology')}; force field: {gmx.get('forcefield')}; ions: {gmx.get('ion_note')}")
            if gmx.get("ligand_centroid_drift_angstrom") is not None:
                lines.append(f"  - Ligand centroid drift: {gmx.get('ligand_centroid_drift_angstrom')} Angstrom; ligand atom RMSD: {gmx.get('ligand_atom_rmsd_angstrom')} Angstrom; closest protein contact: {gmx.get('ligand_min_protein_distance_angstrom')} Angstrom.")
        else:
            lines.append(f"- GROMACS: {gmx.get('time_ps')} ps, {gmx.get('steps')} steps, {gmx.get('temperature_k')} K, EM potential {gmx.get('em_potential_kj_mol')} kJ/mol, MD potential {gmx.get('md_potential_kj_mol')} kJ/mol")
            lines.append(f"  - Scope: {result.get('advanced_scope')} selection; GROMACS is protein-only, not a receptor-ligand complex simulation.")
        if gmx.get("em_continuation"):
            lines.append(f"  - EM required a second minimization: initial Fmax {gmx.get('em_initial_fmax')} kJ/mol/nm after {gmx.get('em_initial_steps')} steps; continuation converged to Fmax {gmx.get('em_fmax')} in {gmx.get('em_actual_steps')} steps.")
        if gmx.get("em_converged") is False:
            lines.append(f"  - Warning: EM did not converge within {gmx.get('em_actual_steps')} steps; Fmax {gmx.get('em_fmax')} kJ/mol/nm on atom {gmx.get('em_fmax_atom')}. Treat the short NVT as a stability check, not a converged simulation.")
        if gmx.get("complex_error"):
            lines.append(f"  - Complex MD fallback reason: {gmx.get('complex_error')}")
    elif gmx.get("error"):
        lines.append(f"- GROMACS: {gmx.get('error')}")
    qm = result.get("cp2k") or {}
    if qm.get("available") and qm.get("energy_ev") is not None:
        lines.append(f"- CP2K: {qm.get('method')}, ligand single point {qm.get('energy_ev'):.3f} eV ({qm.get('seconds')} s)")
    elif qm.get("error"):
        lines.append(f"- CP2K: {qm.get('error')}")
    receptor_runs = result.get("receptor_runs") or []
    ligand_runs = result.get("ligand_runs") or []
    if receptor_runs or ligand_runs:
        lines += ["", "## Advanced runs", ""]
        for run in receptor_runs:
            mode = run.get("md_mode") or "protein"
            lines.append(f"- GROMACS / {run.get('run_id') or run.get('pdb_id')} ({mode}): {run.get('status')}" + (f" - {run.get('error')}" if run.get("error") else ""))
        for run in ligand_runs:
            lines.append(f"- CP2K / {run.get('ligand')}: {run.get('status')}" + (f" - {run.get('error')}" if run.get("error") else ""))
    lines += [
        "",
        "## Interpretation limits",
        "- Vina affinity is a scoring function, not a measured binding free energy; rankings are only comparable within this matrix and these settings.",
        "- The complex PDB is assembled for visualisation from the rigid receptor and the first docked pose; the docked pose itself is not a binding free energy or a relaxed complex.",
        "- Complex MD uses ACPYPE/GAFF2/AM1-BCC ligand charges and a short NVT run; it is not a converged production simulation and does not prove binding.",
        "- Protein-only GROMACS runs are clearly labelled and must not be presented as receptor-ligand complex simulations.",
        "- CP2K is a gas-phase ligand single point; it does not include the protein environment.",
        "- Changing seeds or sampling settings changes stochastic results; compare only runs with documented parameter fingerprints.",
        "- Protonation, missing residues, cofactors, membrane, and ligand tautomers must be checked before drawing biological conclusions.",
        "",
        "## Artifacts",
    ]
    for step in job["steps"]:
        for artifact in step.get("artifacts", []):
            lines.append(f"- {artifact}")
    (work / "report.md").write_text("\n".join(lines), encoding="utf-8")
    html = "<html><head><meta charset='utf-8'><title>Mechanism report</title></head><body><pre>" + "\n".join(lines).replace("&", "&amp;").replace("<", "&lt;") + "</pre></body></html>"
    (work / "report.html").write_text(html, encoding="utf-8")
    job["result"]["report"] = "report.html"


def _write_screening_csv(work: Path, ranking: list[dict[str, Any]]) -> None:
    with (work / "screening.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["rank", "receptor_pdb", "receptor", "ligand", "smiles", "vina_best_kcal_mol", "complex_pdb"])
        for row in ranking:
            writer.writerow([
                row.get("rank"), row.get("pdb_id"), row.get("protein"), row.get("ligand"),
                row.get("smiles"), row.get("best_affinity"), row.get("complex_pdb") or "",
            ])


def _run_job(job_id: str) -> None:
    job = _JOBS[job_id]
    work = data.COMPUTE_DIR / job_id
    config = job["config"]
    pairs = job.get("pairs") or []
    with _LOCK:
        job["status"] = "running"
        _write_job(job)
    if not pairs:
        with _LOCK:
            job["status"] = "error"
            job["error"] = "no receptor/ligand pairs"
            job["finished_utc"] = _now()
            _write_job(job)
        return
    job["parameter_fingerprint"] = _fingerprint(pairs, config)
    try:
        for index, pair in enumerate(pairs, start=1):
            pair_dir = work / "pairs" / f"{index:02d}_{pair['pair_id']}"
            pair_dir.mkdir(parents=True, exist_ok=True)
            pair["dir"] = str(pair_dir.relative_to(work))
            try:
                _prepare_structures(job, pair_dir, pair)
                pair["prepared"] = True
            except Exception as exc:
                pair["prepare_error"] = str(exc)[:500]
                pair["prepared"] = False
        prepared = [pair for pair in pairs if pair.get("prepared")]
        if not prepared:
            raise RuntimeError("all receptor/ligand preparations failed")
        _set_step(job, "resolve", "done", f"Resolved {len(pairs)} receptor x ligand pair(s)")
        _set_step(job, "prepare", "done", f"{len(prepared)}/{len(pairs)} pair(s) prepared")
        with _LOCK:
            _write_job(job)
    except Exception as exc:
        with _LOCK:
            job["status"] = "error"
            job["error"] = str(exc)[:1000]
            job["finished_utc"] = _now()
            _write_job(job)
        _set_step(job, "resolve", "error", str(exc)[:300])
        return

    if config["docking_enabled"]:
        for pair in prepared:
            pair_dir = work / pair["dir"]
            try:
                result = _docking(job, pair_dir, pair, config)
                result["pair_id"] = pair["pair_id"]
                result["pdb_id"] = pair["pdb_id"]
                result["protein"] = pair["protein"]
                result["ligand"] = pair["ligand"]
                result["smiles"] = pair["smiles"]
                pair["docking"] = result
            except Exception as exc:
                pair["docking"] = {"error": str(exc)[:800]}
                _set_step(job, "docking", "error", f"{pair['pair_id']}: {str(exc)[:200]}")
            with _LOCK:
                _write_job(job)
        valid = [pair for pair in prepared if pair.get("docking") and pair["docking"].get("best_affinity") is not None]
        valid.sort(key=lambda pair: float(pair["docking"]["best_affinity"]))
        ranking = []
        for rank, pair in enumerate(valid, start=1):
            docking = pair["docking"]
            ranking.append({
                "rank": rank,
                "pair_id": pair["pair_id"],
                "pdb_id": pair["pdb_id"],
                "protein": pair["protein"],
                "ligand": pair["ligand"],
                "smiles": pair["smiles"],
                "best_affinity": docking.get("best_affinity"),
                "complex_pdb": str(Path(pair["dir"]) / "complex.pdb") if docking.get("complex_pdb") else None,
            })
        job["result"]["ranking"] = ranking
        if valid:
            best_pair = valid[0]
            job["result"]["best_pair"] = best_pair["pair_id"]
            job["result"]["docking"] = {**best_pair["docking"], "pair_id": best_pair["pair_id"]}
            best_complex = work / best_pair["dir"] / "complex.pdb"
            if best_complex.exists():
                shutil.copyfile(best_complex, work / "complex.pdb")
                job["result"]["complex_pdb"] = "complex.pdb"
        else:
            best_pair = prepared[0]
            job["result"]["best_pair"] = best_pair["pair_id"]
            job["result"]["docking"] = {"error": "all docking attempts failed"}
            job["result"]["complex_pdb"] = None
        _set_step(job, "docking", "done", f"{len(valid)}/{len(prepared)} pair(s) docked; best {valid[0]['docking']['best_affinity']:.2f} kcal/mol" if valid else "No successful docking", ["complex.pdb"] if job["result"].get("complex_pdb") else [])
    else:
        best_pair = prepared[0]
        job["result"]["best_pair"] = best_pair["pair_id"]
        job["result"]["ranking"] = []
        job["result"]["docking"] = {"available": False, "skipped": True}
        job["result"]["complex_pdb"] = None
        _set_step(job, "docking", "skipped", "Docking disabled in parameters")

    selected = prepared if config["advanced_scope"] == "all" else [best_pair]
    gromacs_runs: dict[str, dict[str, Any]] = {}
    cp2k_runs: dict[tuple[str, str], dict[str, Any]] = {}
    if config["md_enabled"]:
        complex_requested = config.get("md_mode") == "complex"
        _set_step(job, "gromacs", "running", f"GROMACS for {len(selected)} selected pair(s); {'protein-ligand complex' if complex_requested else 'protein-only'} MD")
        for pair in selected:
            pair_dir = work / pair["dir"]
            use_complex = complex_requested and (pair_dir / "complex.pdb").exists()
            key = pair["pair_id"] if use_complex else pair["pdb_id"]
            pair["md_key"] = key
            if key not in gromacs_runs:
                try:
                    gromacs_runs[key] = _gromacs(job, pair_dir, config)
                except Exception as exc:
                    gromacs_runs[key] = {"available": True, "error": str(exc)[:800]}
                with _LOCK:
                    _write_job(job)
            pair["gromacs"] = gromacs_runs[key]
        failures = [value for value in gromacs_runs.values() if value.get("error")]
        complex_runs = sum(1 for value in gromacs_runs.values() if value.get("md_mode") == "complex")
        _set_step(job, "gromacs", "error" if failures and len(failures) == len(gromacs_runs) else "done", f"{len(gromacs_runs) - len(failures)}/{len(gromacs_runs)} run(s) completed; {complex_runs} complex system(s)")
    else:
        _set_step(job, "gromacs", "skipped", "MD disabled in parameters")
        for pair in selected:
            pair["gromacs"] = {"available": False, "skipped": True}

    if config["qm_enabled"]:
        _set_step(job, "cp2k", "running", f"CP2K for {len({(pair['ligand'], pair['smiles']) for pair in selected})} unique ligand(s); gas-phase single point")
        for pair in selected:
            key = (pair["ligand"], pair["smiles"])
            if key not in cp2k_runs:
                try:
                    cp2k_runs[key] = _cp2k(job, work / pair["dir"], pair, config)
                except Exception as exc:
                    cp2k_runs[key] = {"available": True, "error": str(exc)[:800]}
                with _LOCK:
                    _write_job(job)
            pair["cp2k"] = cp2k_runs[key]
        failures = [value for value in cp2k_runs.values() if value.get("error")]
        _set_step(job, "cp2k", "error" if failures and len(failures) == len(cp2k_runs) else "done", f"{len(cp2k_runs) - len(failures)}/{len(cp2k_runs)} ligand run(s) completed")
    else:
        _set_step(job, "cp2k", "skipped", "QM disabled in parameters")
        for pair in selected:
            pair["cp2k"] = {"available": False, "skipped": True}

    if config["advanced_scope"] == "all":
        for pair in prepared:
            pair.setdefault("gromacs", gromacs_runs.get(pair.get("md_key") or pair["pdb_id"], {"available": False, "skipped": True}))
            pair.setdefault("cp2k", cp2k_runs.get((pair["ligand"], pair["smiles"]), {"available": False, "skipped": True}))

    job["result"]["advanced_scope"] = config["advanced_scope"]
    job["result"]["receptor_runs"] = [
        {"run_id": key, "pdb_id": key, "md_mode": value.get("md_mode") or ("complex" if config.get("md_mode") == "complex" else "protein"), "status": "error" if value.get("error") else ("skipped" if value.get("skipped") else "complete"), "error": value.get("error"), "summary": value}
        for key, value in gromacs_runs.items()
    ]
    job["result"]["ligand_runs"] = [
        {"ligand": key[0], "status": "error" if value.get("error") else ("skipped" if value.get("skipped") else "complete"), "error": value.get("error"), "summary": value}
        for key, value in cp2k_runs.items()
    ]
    job["result"]["gromacs"] = best_pair.get("gromacs") or {"available": False, "skipped": True}
    job["result"]["cp2k"] = best_pair.get("cp2k") or {"available": False, "skipped": True}
    job["result"]["pairs"] = prepared
    _write_screening_csv(work, job["result"].get("ranking") or [])

    _set_step(job, "report", "running", "Writing report")
    try:
        _report(job, work, best_pair)
        _set_step(job, "report", "done", "Report written", ["report.md", "report.html", "screening.csv"])
    except Exception as exc:
        _set_step(job, "report", "error", f"Report failed: {str(exc)[:200]}")
        with _LOCK:
            job["status"] = "error"
            job["error"] = f"report failed: {str(exc)[:800]}"
            job["finished_utc"] = _now()
            _write_job(job)
        return
    artifacts = ["job.json", "report.md", "report.html", "screening.csv"]
    if (work / "complex.pdb").exists():
        artifacts.append("complex.pdb")
    for pair in prepared:
        for name in ("receptor.pdb", "ligand.sdf", "poses.pdbqt", "vina_result.json", "complex.pdb", "gromacs/em.gro", "gromacs/md.gro", "gromacs/md.xtc", "gromacs_complex/complex.gro", "gromacs_complex/em.gro", "gromacs_complex/em2.gro", "gromacs_complex/md.gro", "gromacs_complex/md.xtc", "gromacs_complex/LIG.acpype/LIG_GMX.itp"):
            rel = str(Path(pair["dir"]) / name)
            if (work / rel).exists():
                artifacts.append(rel)
    with _LOCK:
        job["status"] = "complete"
        job["finished_utc"] = _now()
        job["result"]["artifacts"] = artifacts
        _write_job(job)


def _failed_job(query: str, design_id: str | None, options: dict[str, Any], error: str) -> dict[str, Any]:
    job_id = "C" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    try:
        config = _normalize_options(options)
    except Exception:
        config = {}
    job = {
        "id": job_id,
        "status": "error",
        "query": query,
        "design_id": design_id,
        "created_utc": _now(),
        "updated_utc": _now(),
        "steps": [{"id": "validate", "label": "Validate receptor and ligand", "status": "error", "detail": error}],
        "options": options,
        "config": config,
        "pairs": [],
        "target": None,
        "result": {},
        "error": error,
        "failed_validation": True,
    }
    _write_job(job)
    return job


def record_rejected(design: dict[str, Any] | None, options: dict[str, Any] | None, error: str) -> dict[str, Any]:
    design = design or {}
    query = (design.get("brief") or {}).get("query") or design.get("query") or ""
    return _failed_job(query, design.get("design_id"), dict(options or {}), error)


def start_job(design: dict[str, Any], options: dict[str, Any] | None = None) -> dict[str, Any]:
    data.ensure_dirs()
    options = dict(options or {})
    selected = design.get("selected") if isinstance(design.get("selected"), dict) else {}
    if selected and not options.get("design_target"):
        options["design_target"] = {
            "id": selected.get("id"),
            "name": selected.get("name"),
            "cn_name": selected.get("cn_name"),
            "kind": selected.get("kind"),
            "pdb_id": selected.get("pdb_id"),
            "uniprot": selected.get("uniprot"),
        }
    config = _normalize_options(options)
    query = (design.get("brief") or {}).get("query") or design.get("query") or ""
    if config["haddock_enabled"]:
        config["docking_enabled"] = False
        config["md_enabled"] = False
        config["qm_enabled"] = False
        config["advanced_scope"] = "haddock"
        target = _resolve_haddock_target(query, options, config)
        job_id = "C" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        work = data.COMPUTE_DIR / job_id
        work.mkdir(parents=True, exist_ok=True)
        steps = [
            {"id": "resolve", "label": "解析 HADDOCK3 受体与伙伴", "status": "pending", "detail": ""},
            {"id": "prepare", "label": "准备 HADDOCK3 结构与约束", "status": "pending", "detail": ""},
            {"id": "haddock", "label": "HADDOCK3 对接与精修", "status": "pending", "detail": ""},
            {"id": "report", "label": "生成 HADDOCK3 报告", "status": "pending", "detail": ""},
        ]
        job = {
            "id": job_id,
            "status": "queued",
            "engine": "haddock",
            "query": query,
            "design_id": design.get("design_id"),
            "created_utc": _now(),
            "updated_utc": _now(),
            "steps": steps,
            "options": options,
            "config": config,
            "pairs": [],
            "target": target,
            "haddock_target": target,
            "result": {},
            "error": None,
        }
        _JOBS[job_id] = job
        _write_job(job)
        thread = threading.Thread(target=_run_haddock_job, args=(job_id,), daemon=True)
        thread.start()
        return {"id": job_id, "status": "queued", "engine": "haddock", "steps": steps, "config": config, "target": target}
    pairs = _resolve_pairs(query, options, config["max_pairs"])
    job_id = "C" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    if config["docking_seed"] is None:
        config["docking_seed"] = int(uuid.uuid4().hex[:8], 16) % (2**31 - 1)
    work = data.COMPUTE_DIR / job_id
    work.mkdir(parents=True, exist_ok=True)
    steps = [
        {"id": "resolve", "label": f"Resolve {len(pairs)} receptor x ligand pair(s)", "status": "pending", "detail": ""},
        {"id": "prepare", "label": "Prepare structures", "status": "pending", "detail": ""},
        {"id": "docking", "label": "AutoDock Vina docking matrix", "status": "pending", "detail": ""},
        {"id": "gromacs", "label": "GROMACS EM + short MD (representative)", "status": "pending", "detail": ""},
        {"id": "cp2k", "label": "CP2K PBE single point (representative)", "status": "pending", "detail": ""},
        {"id": "report", "label": "Mechanism report", "status": "pending", "detail": ""},
    ]
    job = {
        "id": job_id,
        "status": "queued",
        "query": query,
        "design_id": design.get("design_id"),
        "created_utc": _now(),
        "updated_utc": _now(),
        "steps": steps,
        "options": options,
        "config": config,
        "pairs": pairs,
        "target": pairs[0],
        "result": {},
        "error": None,
    }
    _JOBS[job_id] = job
    _write_job(job)
    thread = threading.Thread(target=_run_job, args=(job_id,), daemon=True)
    thread.start()
    return {"id": job_id, "status": "queued", "steps": steps, "config": config, "pairs": pairs}


def get_job(job_id: str) -> dict[str, Any]:
    if job_id in _JOBS:
        return _JOBS[job_id]
    path = data.COMPUTE_DIR / job_id / "job.json"
    if not path.exists():
        raise FileNotFoundError(job_id)
    return json.loads(path.read_text(encoding="utf-8"))


def list_jobs(limit: int = 100) -> list[dict[str, Any]]:
    items = []
    limit = max(1, min(500, int(limit)))
    if data.COMPUTE_DIR.exists():
        for path in sorted(data.COMPUTE_DIR.glob("*/job.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
            try:
                items.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
    return items
