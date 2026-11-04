#!/usr/bin/env python3
"""Optional DeepAgent reviewer.

Run this in a Python >=3.11 virtual environment. The main BioForge process
(Python 3.10) does not import deepagents; it may call this worker as a
subprocess after installing the optional environment.
"""
from __future__ import annotations

import json
import os
import sys

from deepagents import FilesystemPermission, create_deep_agent
from langchain_ollama import ChatOllama


SYSTEM = """You are an independent, evidence-grounded reviewer for BioForge Studio.
Review the supplied answer against the supplied evidence only.
Do not invent papers, DOIs, numbers, mechanisms, or safety conclusions.
Find unsupported claims, overstatements, missing citations, and confusion between
local-library evidence, external OA metadata, graph co-occurrence, workflow edges,
and experimental measurements. Return a short JSON object with:
{"verdict":"pass|revise|reject","issues":["..."],"missing_evidence":["..."],"safe_summary":"..."}.
Do not run shell commands, read files, or browse the web."""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError as exc:
        print(json.dumps({"error": f"invalid JSON: {exc}"}))
        return 2
    model = ChatOllama(
        model=os.environ.get("BIOFORGE_OLLAMA_MODEL", "qwen3.8:27b"),
        base_url=os.environ.get("BIOFORGE_OLLAMA_URL", "http://127.0.0.1:11434"),
        temperature=0,
        num_ctx=16384,
        timeout=120,
    )
    permissions = [
        FilesystemPermission(operations=["read", "write"], paths=["/**"], mode="deny"),
    ]
    agent = create_deep_agent(model=model, tools=[], system_prompt=SYSTEM, permissions=permissions)
    prompt = json.dumps(
        {
            "question": payload.get("question", ""),
            "answer": payload.get("answer", ""),
            "quality": payload.get("quality", {}),
            "verification": payload.get("verification", {}),
            "evidence": payload.get("evidence", [])[:8],
        },
        ensure_ascii=False,
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "Review this RAG record:\n" + prompt}]},
        config={"recursion_limit": 8},
    )
    messages = result.get("messages") or []
    content = getattr(messages[-1], "content", "") if messages else ""
    if isinstance(content, list):
        content = "\n".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in content)
    print(json.dumps({"review": content, "engine": "deepagents", "model": model.model}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
