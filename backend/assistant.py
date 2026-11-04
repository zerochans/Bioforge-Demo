from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from . import data

OLLAMA_URL = os.environ.get("BIOFORGE_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("BIOFORGE_OLLAMA_MODEL", "qwen3.8:27b")
OLLAMA_NUM_CTX = max(8192, int(os.environ.get("BIOFORGE_OLLAMA_NUM_CTX", "16384")))
DOCS_CONTEXT_CHARS = max(2000, int(os.environ.get("BIOFORGE_ASSISTANT_DOCS_CHARS", "6000")))
ASSISTANT_DIR = data.RUNTIME_DIR / "assistant"
BACKUP_DIR = ASSISTANT_DIR / "backup"
HISTORY_PATH = ASSISTANT_DIR / "history.jsonl"
_LOCK = threading.Lock()

SYSTEM_PROMPT = """你是 BioForge Studio 的本地使用助手。只回答与 BioForge 软件使用、数据解释、计算边界和合法文献获取有关的问题。
规则：
1. 不索取、复述或记录密码、Cookie、API Token、学号等凭据；提醒用户在设置中保护凭据。
2. 不提供 Sci-Hub、付费墙绕过、验证码规避或未授权批量下载；只建议 DOI、PubMed、出版社、机构 SSO/CARSI/EZproxy 和合法 OA 入口。
3. 不编造软件未实现的功能，不声称已经运行计算、已经检索数据库或已经看到用户未提供的数据。
4. 明确区分“工作流关系”“本地策展证据”“在线记录”“模型预测”和“实测结果”；Vina 打分不是自由能，短 MD/QM 不是生产级结论。
5. 用户用中文提问就用中文回答，用英文提问就用英文回答；先给直接答案，再给 2-5 个可操作步骤或边界说明。
6. 不要输出你的内部推理过程，只给最终回答。"""

APP_CONTEXT = """当前软件事实（2026-11-03，BioForge Studio 3.3.0 开发版）：
- 页面顺序：设计、案例、在线证据、机制计算、模型实验室、资源库、使用指南、设置。
- 资源库约 45 条合法入口，新增光谱与波谱证据组：NIST WebBook、SDBS、MassBank、HMDB、MetaboLights、GNPS、NMReDATA、PDB CCD；只提供入口，不抓取受限谱库。
- 案例库覆盖 20 个食品体系 + 1 个乳清蛋白-槲皮素机制案例；UI 数字应从 API 动态读取，不写死。
- 证据图谱节点/边按 provenance 标注：workflow 只表示流程/决策；curated 是本地策展先验；verified 是标识符级交叉验证；model 是规则预测；online 是本次在线记录；reference 只是参考。没有公开引用的边会显示“无外部引用”和原因。
- 机制计算支持多受体 × 多配体 Vina 筛选（最多 12 对），生成复合物 PDB；GROMACS/CP2K 默认只跑代表项，选择“全部”才逐项运行。Vina 打分不是结合自由能；GROMACS 默认是短时蛋白 MD；CP2K 是配体气相单点，不含蛋白口袋。
- 3D 查看器支持 PDB/PDBQT/GRO，以及 GROMACS XTC 轨迹转多帧 PDB 查看；全部链的序列换行展示，支持元素、链、二级结构、残基极性、序列彩虹、B-factor、深度着色；复合物文件可同时看到受体和配体。
- 设计结果附 curated 光谱参考峰（IR/UV-Vis/荧光/MS/NMR），明确标注参考谱不是同条件实测；资源库含合法公开谱库入口，不抓取受限谱库。
- 模型实验室是表格模型与交叉验证，不是通用大模型；合成/模拟数据不能替代湿实验。实测回灌会写入证据图谱（lab_feedback → model/dataset → retrained model）。
- 文献库是 Europe PMC OA 元数据和本地 BM25 索引；Obsidian 笔记可在指南页只读浏览，无法原样嵌入 Obsidian 桌面 UI。
- 3.3.0 新增 LangGraph RAG：本地 BM25/图谱优先，证据不足时调用 Europe PMC/OpenAlex OA API，随后逐句核验；所有回答进入人工审核队列，可回滚。DeepAgent 需要 Python ≥3.11，当前主进程未启用，不能声称已运行 DeepAgent。
- 默认演示账号是 admin，密码在 runtime/login.txt；生产前必须修改。服务端口 8010，8003 属于 RustDesk，不要占用。"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_docs_context(limit: int | None = None) -> str:
    budget = DOCS_CONTEXT_CHARS if limit is None else max(0, int(limit))
    if not budget:
        return ""
    parts = []
    per_file = max(1200, budget // 2)
    for rel in ("docs/USER_GUIDE.md", "docs/LIMITATIONS.md"):
        path = data.ROOT / rel
        if path.exists():
            try:
                parts.append(path.read_text(encoding="utf-8", errors="ignore")[:per_file])
            except OSError:
                pass
    return "\n\n".join(parts)[:budget]


def _build_system(compact: bool = False) -> str:
    if compact:
        docs = _read_docs_context(2400)
        base = SYSTEM_PROMPT + "\n\n" + APP_CONTEXT.split("\n", 1)[0]
    else:
        docs = _read_docs_context()
        base = SYSTEM_PROMPT + "\n\n" + APP_CONTEXT
    return base + ("\n\n已批准的本地指南摘录：\n" + docs if docs else "")


def _models() -> list[dict[str, Any]]:
    try:
        with httpx.Client(timeout=4.0) as client:
            response = client.get(f"{OLLAMA_URL}/api/tags")
            response.raise_for_status()
            payload = response.json()
        return payload.get("models", []) if isinstance(payload, dict) else []
    except Exception:
        return []


def status() -> dict[str, Any]:
    models = _models()
    names = [item.get("name") for item in models if item.get("name")]
    selected = OLLAMA_MODEL if OLLAMA_MODEL in names else (names[0] if names else OLLAMA_MODEL)
    return {
        "available": bool(models),
        "url": OLLAMA_URL,
        "model": selected,
        "configured_model": OLLAMA_MODEL,
        "models": names,
        "records": _count_history(),
        "history_path": str(HISTORY_PATH),
        "backup_dir": str(BACKUP_DIR),
        "privacy": "问答会写入服务器本地记录；不要输入密码、Token 或未公开数据。",
    }


def _save(record: dict[str, Any]) -> None:
    ASSISTANT_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with _LOCK:
        with HISTORY_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line)
        try:
            os.chmod(HISTORY_PATH, 0o600)
        except OSError:
            pass
        backup = BACKUP_DIR / f"{datetime.now(timezone.utc).strftime('%Y-%m')}.jsonl"
        with backup.open("a", encoding="utf-8") as handle:
            handle.write(line)
        try:
            os.chmod(backup, 0o600)
        except OSError:
            pass


def _count_history() -> int:
    if not HISTORY_PATH.exists():
        return 0
    try:
        with HISTORY_PATH.open("r", encoding="utf-8", errors="ignore") as handle:
            return sum(1 for line in handle if line.strip())
    except OSError:
        return 0


def recent(limit: int = 200, query: str = "") -> list[dict[str, Any]]:
    if not HISTORY_PATH.exists():
        return []
    try:
        lines = [line for line in HISTORY_PATH.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
    except OSError:
        return []
    limit = max(1, min(500, int(limit)))
    needle = (query or "").strip().lower()
    items = []
    for line in reversed(lines):
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "")
        answer = str(item.get("answer") or "")
        if needle and needle not in question.lower() and needle not in answer.lower():
            continue
        items.append({
            "id": item.get("id"),
            "ts": item.get("ts"),
            "question": question,
            "answer": answer,
            "model": item.get("model"),
        })
        if len(items) >= limit:
            break
    return items


def ask(question: str) -> dict[str, Any]:
    question = (question or "").strip()
    if not question:
        raise ValueError("question must not be empty")
    if len(question) > 2000:
        raise ValueError("question is too long (max 2000 characters)")
    models = _models()
    if not models:
        raise RuntimeError(f"Ollama is not reachable at {OLLAMA_URL}")
    names = [item.get("name") for item in models if item.get("name")]
    model = OLLAMA_MODEL if OLLAMA_MODEL in names else (names[0] if names else OLLAMA_MODEL)
    last_error = ""
    answer = ""
    body: dict[str, Any] = {}
    cjk = re.compile(r"[\u3400-\u9fff]")
    english_question = not cjk.search(question)
    language_suffix = "\n\nAnswer in English only. Do not use Chinese characters." if english_question else ""
    attempts = (
        {"compact": False, "num_predict": 1600, "temperature": 0.2, "suffix": "", "think": False},
        {"compact": True, "num_predict": 2400, "temperature": 0.1, "suffix": "\n\n请直接给出最终回答，不要输出思考过程或空内容。", "think": False},
        {"compact": True, "num_predict": 4096, "temperature": 0.0, "suffix": "\n\nDo not think step by step. Output only the final answer.", "think": None},
    )
    diagnostics = []
    for attempt in attempts:
        request_payload = {
            "model": model,
            "stream": False,
            "keep_alive": "10m",
            "messages": [
                {"role": "system", "content": _build_system(compact=attempt["compact"])},
                {"role": "user", "content": question + attempt["suffix"] + language_suffix},
            ],
            "options": {
                "temperature": attempt["temperature"],
                "num_ctx": OLLAMA_NUM_CTX,
                "num_predict": attempt["num_predict"],
            },
        }
        if attempt["think"] is not None:
            request_payload["think"] = attempt["think"]
        try:
            with httpx.Client(timeout=httpx.Timeout(240.0, connect=5.0)) as client:
                response = client.post(f"{OLLAMA_URL}/api/chat", json=request_payload)
                if response.status_code == 400 and "think" in response.text.lower():
                    request_payload.pop("think", None)
                    response = client.post(f"{OLLAMA_URL}/api/chat", json=request_payload)
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPStatusError as exc:
            last_error = f"Ollama returned HTTP {exc.response.status_code}: {exc.response.text[:500]}"
            diagnostics.append(last_error)
            continue
        except httpx.RequestError as exc:
            last_error = f"Ollama request failed: {exc}"
            diagnostics.append(last_error)
            continue
        message = body.get("message") if isinstance(body, dict) else None
        answer = (message or {}).get("content") if isinstance(message, dict) else body.get("response")
        answer = (answer or "").strip()
        hidden = ((message or {}).get("thinking") or "") if isinstance(message, dict) else ""
        if answer and english_question and cjk.search(answer):
            last_error = "Ollama returned a non-English answer for an English question"
            diagnostics.append(last_error)
            answer = ""
            continue
        if answer:
            break
        done_reason = body.get("done_reason") if isinstance(body, dict) else ""
        last_error = "Ollama returned an empty answer"
        if hidden:
            last_error += f" (hidden reasoning only: {len(hidden)} chars, done_reason={done_reason or 'unknown'})"
        elif done_reason:
            last_error += f" (done_reason={done_reason})"
        diagnostics.append(last_error)
    if not answer:
        reason = body.get("done_reason") if isinstance(body, dict) else ""
        hint = f"（done_reason={reason}）" if reason else ""
        detail = "；".join(dict.fromkeys(diagnostics[-3:]))
        if english_question:
            raise RuntimeError(f"The local model returned no English answer after {len(attempts)} attempts{hint}. {detail}. Retry later or check the Ollama model; the question was not saved.")
        raise RuntimeError(f"本地模型连续 {len(attempts)} 次返回空回答{hint}。{detail}。请稍后重试或检查 Ollama 模型；问题未写入历史。")
    record = {
        "id": "A" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8],
        "ts": _now(),
        "question": question,
        "answer": answer,
        "model": body.get("model") or model,
        "done_reason": body.get("done_reason"),
        "eval_count": body.get("eval_count"),
    }
    _save(record)
    return {**record, "saved_to": str(HISTORY_PATH), "privacy": "已保存到服务器本地；可在 runtime/assistant/ 查看和备份。"}
