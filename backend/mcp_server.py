#!/usr/bin/env python3
"""Minimal Model Context Protocol (stdio JSON-RPC) server for BioForge Studio.

Run with:  python -m backend.mcp_server
The server writes protocol messages to stdout and logs to stderr only.
"""
from __future__ import annotations

import json
import sys
import traceback
from typing import Any

from . import __version__, data, engine, training, validation

PROTOCOL_VERSION = "2024-11-05"
MAX_LINE = 8 * 1024 * 1024


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


TOOLS: list[dict[str, Any]] = [
    {
        "name": "bioforge_design",
        "description": "Design a fluorescent protein, small molecule, or food/beverage formulation from a natural-language brief. Returns candidates, protective blend, virtual stability/spectra predictions, warnings, and an evidence chain. Research use only.",
        "inputSchema": _schema(
            {
                "query": {"type": "string", "minLength": 1, "maxLength": 6000, "description": "Natural-language design brief in Chinese or English."},
                "options": {"type": "object", "description": "Optional engine overrides (matrix_id, weights, target_kind...)."},
                "generate_artifacts": {"type": "boolean", "default": False, "description": "Generate report/PDF/CSV/GIF/MP4 and ZIP artifacts on the server."},
                "full": {"type": "boolean", "default": False, "description": "Return the complete result instead of the compact summary."},
            },
            ["query"],
        ),
    },
    {
        "name": "bioforge_parse",
        "description": "Parse a natural-language design brief into structured constraints (conditions, spectral targets, matrix, weights, warnings) without running a design.",
        "inputSchema": _schema({"query": {"type": "string", "minLength": 1, "maxLength": 6000}}, ["query"]),
    },
    {
        "name": "bioforge_spectra_match",
        "description": "Match measured UV-Vis/IR/MS/1H-NMR peaks against the curated BioForge reference library. Approximate references only; confirm with standards.",
        "inputSchema": _schema(
            {
                "peaks": {"type": "array", "minItems": 1, "maxItems": 500, "items": {"type": "array", "items": {"type": "number"}}},
                "type": {"type": "string", "enum": ["UV-Vis", "IR", "MS", "1H-NMR"], "default": "UV-Vis"},
                "tolerance": {"type": "number", "minimum": 0.001, "maximum": 1000},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
            },
            ["peaks"],
        ),
    },
    {
        "name": "bioforge_quick_validate",
        "description": "Run fast RDKit molecular-mechanics sanity checks (MMFF94s) and optional PySCF QM check. This is not production MD/QM validation.",
        "inputSchema": _schema(
            {
                "smiles": {"type": "string", "maxLength": 2000},
                "kind": {"type": "string", "enum": ["compound", "protein"], "default": "compound"},
            }
        ),
    },
    {
        "name": "bioforge_feedback",
        "description": "Record one real measured retention result in the local SQLite feedback store for later calibration.",
        "inputSchema": _schema(
            {
                "candidate_id": {"type": "string", "minLength": 1, "maxLength": 120},
                "kind": {"type": "string", "default": "protein", "maxLength": 30},
                "measured_retention": {"type": "number", "minimum": 0, "maximum": 1},
                "process_temp_c": {"type": "number", "minimum": -20, "maximum": 200, "default": 25},
                "ph": {"type": "number", "minimum": 0, "maximum": 14, "default": 7},
                "n_replicates": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 1},
                "notes": {"type": "string", "maxLength": 2000},
                "job_id": {"type": "string", "maxLength": 80},
            },
            ["candidate_id", "measured_retention"],
        ),
    },
    {
        "name": "bioforge_model_card",
        "description": "Return the current feedback-calibration model card and dataset statistics.",
        "inputSchema": _schema({}),
    },
    {
        "name": "bioforge_train",
        "description": "Train the Ridge calibration model on recorded real feedback (synthetic excluded by default) and return LOO metrics.",
        "inputSchema": _schema({"include_synthetic": {"type": "boolean", "default": False}}),
    },
    {
        "name": "bioforge_get_job",
        "description": "Load a previously generated design job (result.json + artifact manifest) by job id.",
        "inputSchema": _schema({"job_id": {"type": "string", "minLength": 10, "maxLength": 80}}, ["job_id"]),
    },
    {
        "name": "bioforge_dataset",
        "description": "Read a curated BioForge dataset: proteins.json, protectants.json, compounds.json, matrices.json, or spectra.json.",
        "inputSchema": _schema(
            {"name": {"type": "string", "enum": ["proteins.json", "protectants.json", "compounds.json", "matrices.json", "spectra.json"]}},
            ["name"],
        ),
    },
]


def _compact(result: dict[str, Any]) -> dict[str, Any]:
    metrics = (result.get("selected") or {}).get("metrics", {})
    virtual = result.get("virtual_experiment", {})
    mc = virtual.get("monte_carlo", {})
    return {
        "job_id": result.get("job_id"),
        "offline": result.get("offline", False),
        "brief": result.get("brief"),
        "selected": {
            "id": (result.get("selected") or {}).get("id"),
            "name": (result.get("selected") or {}).get("name"),
            "cn_name": (result.get("selected") or {}).get("cn_name"),
            "kind": (result.get("selected") or {}).get("kind"),
            "score": (result.get("selected") or {}).get("score"),
            "meets_spec": (result.get("selected") or {}).get("meets_spec"),
            "metrics": metrics,
            "blend": (result.get("selected") or {}).get("blend"),
        },
        "candidates": [
            {"id": c.get("id"), "cn_name": c.get("cn_name"), "score": c.get("score"), "meets_spec": c.get("meets_spec"), "metrics": c.get("metrics")}
            for c in (result.get("candidates") or [])[:6]
        ],
        "formulation": result.get("formulation"),
        "decision_summary": result.get("decision_summary"),
        "warnings": result.get("warnings"),
        "assumptions": result.get("assumptions"),
        "logic_chain": result.get("logic_chain"),
        "virtual_experiment": {
            "monte_carlo": {k: mc.get(k) for k in ("n", "mean", "p05", "p50", "p95", "prob_meet_target")},
            "sensitivity": virtual.get("sensitivity"),
            "process_retention": virtual.get("process_retention"),
            "storage_retention": virtual.get("storage_retention"),
            "overall_retention": virtual.get("overall_retention"),
        },
        "spectra": {"invariance": (result.get("spectra") or {}).get("invariance"), "note": (result.get("spectra") or {}).get("note")},
        "validation": {"summary": (result.get("validation") or {}).get("summary"), "quick_checks": (result.get("validation") or {}).get("quick_checks")},
        "provenance": result.get("provenance"),
        "artifacts": result.get("artifacts"),
    }


def _tool_call(name: str, arguments: dict[str, Any]) -> Any:
    if name == "bioforge_design":
        result = engine.design(arguments["query"], arguments.get("options"), bool(arguments.get("generate_artifacts", False)))
        return result if arguments.get("full") else _compact(result)
    if name == "bioforge_parse":
        brief = engine.parse_brief(arguments["query"])
        brief.pop("matrix", None)
        return brief
    if name == "bioforge_spectra_match":
        return engine.match_spectra(arguments["peaks"], arguments.get("type", "UV-Vis"), arguments.get("tolerance"), int(arguments.get("top_k", 5)))
    if name == "bioforge_quick_validate":
        smiles = arguments.get("smiles")
        return {
            "kind": arguments.get("kind", "compound"),
            "molecular_mechanics": validation.quick_mm(smiles),
            "quantum_mechanics": validation.quick_qm(smiles),
            "note": "Fast sanity checks only; production MD/QM and experimental validation are separate.",
        }
    if name == "bioforge_feedback":
        payload = dict(arguments)
        payload.setdefault("source", "real")
        return training.record_feedback(payload)
    if name == "bioforge_model_card":
        return {"card": training.load_card(), "stats": training.feedback_stats()}
    if name == "bioforge_train":
        return training.train_model(bool(arguments.get("include_synthetic", False)))
    if name == "bioforge_get_job":
        return engine.load_job(arguments["job_id"])
    if name == "bioforge_dataset":
        return data.load(arguments["name"])
    raise ValueError(f"unknown tool: {name}")


def _response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    if method is None:
        return None
    if request_id is None and method != "initialize":
        return None
    if method == "initialize":
        return _response(request_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "bioforge-studio", "version": __version__},
            "instructions": "BioForge Studio: hypothesis-generating design for fluorescent proteins, small molecules, and food/beverage formulations. All outputs are research priors and require experimental validation; never present them as regulatory or food-safety approval.",
        })
    if method == "ping":
        return _response(request_id, {})
    if method == "tools/list":
        return _response(request_id, {"tools": TOOLS})
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            payload = _tool_call(str(name), arguments)
            return _response(request_id, {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}], "isError": False})
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            return _response(request_id, {"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}], "isError": True})
    if method in {"notifications/initialized", "notifications/cancelled"}:
        return None
    return _error(request_id, -32601, f"method not found: {method}")


def main() -> None:
    print(f"BioForge MCP server v{__version__} listening on stdio", file=sys.stderr, flush=True)
    for raw in sys.stdin.buffer:
        if len(raw) > MAX_LINE:
            print("dropped oversized request", file=sys.stderr, flush=True)
            continue
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps(_error(None, -32700, "parse error")) + "\n")
            sys.stdout.flush()
            continue
        if not isinstance(message, dict):
            sys.stdout.write(json.dumps(_error(None, -32600, "invalid request")) + "\n")
            sys.stdout.flush()
            continue
        try:
            response = handle(message)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            response = _error(message.get("id"), -32603, "internal error")
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
