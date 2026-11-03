from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.base import BaseHTTPMiddleware

from . import __version__, auth, compute, data, datasources, engine, food, graph, training, validation

LOG_PATH = data.LOGS_DIR / "bioforge.log"
TOKEN_PATH = data.RUNTIME_DIR / ".token"
JOB_ID_RE = re.compile(r"^[0-9A-Za-z:_\-]{10,80}$")
ALLOWED_JOB_FILES = {
    "result.json", "manifest.json", "report.html", "report.pdf", "protocol.md",
    "dataset.csv", "README.txt", "animation.gif", "animation.mp4", "package.zip",
}
ALLOWED_PREFIXES = ("charts/", "tables/")
OUTBOUND_ALLOWLIST = {
    "rest.uniprot.org": "https://rest.uniprot.org",
    "rest.kegg.jp": "https://rest.kegg.jp",
    "pubchem.ncbi.nlm.nih.gov": "https://pubchem.ncbi.nlm.nih.gov",
    "www.ebi.ac.uk": "https://www.ebi.ac.uk",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_token() -> str:
    env_token = os.environ.get("BIOFORGE_TOKEN")
    if env_token:
        return env_token.strip()
    data.ensure_dirs()
    if TOKEN_PATH.exists():
        return TOKEN_PATH.read_text(encoding="utf-8").strip()
    token = secrets.token_urlsafe(32)
    TOKEN_PATH.write_text(token + "\n", encoding="utf-8")
    try:
        os.chmod(TOKEN_PATH, 0o600)
    except OSError:
        pass
    return token


def _auth_required() -> bool:
    return os.environ.get("BIOFORGE_REQUIRE_AUTH", "1").strip() not in {"0", "false", "no"}


class JsonLogger:
    def __init__(self, path: Path):
        data.ensure_dirs()
        self.path = path
        self.logger = logging.getLogger("bioforge")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.FileHandler(path, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)

    def write(self, payload: dict[str, Any]) -> None:
        safe = {key: value for key, value in payload.items() if key.lower() not in {"authorization", "token", "x-api-key"}}
        self.logger.info(json.dumps(safe, ensure_ascii=False))


json_log = JsonLogger(LOG_PATH)


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0):
        self.limit = limit
        self.window = window_seconds
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self.hits[key]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return False
        bucket.append(now)
        return True


general_limiter = RateLimiter(limit=120, window_seconds=60.0)
design_limiter = RateLimiter(limit=20, window_seconds=60.0)
db_limiter = RateLimiter(limit=40, window_seconds=60.0)


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = secrets.token_hex(8)
        request.state.request_id = request_id
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > 16 * 1024 * 1024:
            return JSONResponse({"detail": "payload too large"}, status_code=413)
        started = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - started) * 1000.0, 1)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        json_log.write({
            "ts": _now(), "request_id": request_id, "method": request.method,
            "path": request.url.path, "status": response.status_code, "duration_ms": duration_ms,
            "client": request.client.host if request.client else None,
        })
        return response


app = FastAPI(title="BioForge Studio API", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SecurityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


async def require_auth(request: Request, authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None)) -> None:
    client = request.client.host if request.client else "local"
    if not general_limiter.allow(f"ip:{client}"):
        raise HTTPException(status_code=429, detail="rate limit exceeded")
    session = request.cookies.get(auth.COOKIE_NAME)
    if session and auth.verify_session(session):
        return
    if not _auth_required():
        return
    token = _ensure_token()
    supplied = ""
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    elif x_api_key:
        supplied = x_api_key.strip()
    if not supplied or not secrets.compare_digest(supplied, token):
        raise HTTPException(status_code=401, detail="missing or invalid API token")


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class PasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class EvidenceRequest(BaseModel):
    query: str = Field(min_length=1, max_length=240)
    sources: list[str] | None = None
    entity: str | None = None
    context: str | None = Field(default=None, max_length=240)


class MechanismRequest(BaseModel):
    query: str | None = Field(default=None, max_length=6000)
    design_id: str | None = Field(default=None, max_length=80)
    options: dict[str, Any] | None = None


class DesignRequest(BaseModel):
    query: str = Field(min_length=1, max_length=6000)
    options: dict[str, Any] | None = None

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be empty")
        return value


class SpectraMatchRequest(BaseModel):
    peaks: list[Any] = Field(min_length=1, max_length=500)
    type: str = Field(default="UV-Vis", max_length=20)
    tolerance: float | None = Field(default=None, ge=0.001, le=1000)
    top_k: int = Field(default=5, ge=1, le=20)


class FeedbackRequest(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=120)
    kind: str = Field(default="protein", max_length=30)
    measured_retention: float = Field(ge=0, le=1)
    process_temp_c: float = Field(default=25, ge=-20, le=200)
    ph: float = Field(default=7, ge=0, le=14)
    tm_c: float | None = None
    dtm_c: float | None = None
    matrix_factor: float | None = None
    predicted_retention: float | None = None
    measured_tm_c: float | None = None
    n_replicates: int = Field(default=1, ge=1, le=1000)
    source: str = Field(default="real", pattern="^(real|synthetic)$")
    notes: str = Field(default="", max_length=2000)
    job_id: str | None = Field(default=None, max_length=80)


class TrainRequest(BaseModel):
    include_synthetic: bool = False


class ValidateRequest(BaseModel):
    smiles: str | None = Field(default=None, max_length=2000)
    kind: str = Field(default="compound", max_length=20)



@app.post("/api/auth/login")
async def auth_login(payload: LoginRequest, response: Response, request: Request) -> dict[str, Any]:
    client = request.client.host if request.client else "local"
    if not db_limiter.allow(f"login:{client}"):
        raise HTTPException(status_code=429, detail="login rate limit exceeded")
    if not auth.verify(payload.username, payload.password):
        json_log.write({"ts": _now(), "event": "login_failed", "client": client})
        raise HTTPException(status_code=401, detail="invalid username or password")
    token, expires = auth.issue_session(payload.username)
    response.set_cookie(
        auth.COOKIE_NAME, token, max_age=auth.SESSION_TTL, httponly=True, samesite="lax",
        secure=False, path="/",
    )
    json_log.write({"ts": _now(), "event": "login_ok", "client": client})
    return {"user": auth.public_account(), "expires": expires}


@app.get("/api/auth/me", dependencies=[Depends(require_auth)])
async def auth_me() -> dict[str, Any]:
    return {"user": auth.public_account(), "authenticated": True}


@app.post("/api/auth/logout")
async def auth_logout(response: Response) -> dict[str, Any]:
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"ok": True}


@app.post("/api/auth/password", dependencies=[Depends(require_auth)])
async def auth_password(payload: PasswordRequest) -> dict[str, Any]:
    try:
        return auth.change_password(payload.current_password, payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/api/v2/food/systems", dependencies=[Depends(require_auth)])
async def food_systems() -> dict[str, Any]:
    return {"items": data.food_systems()}


@app.get("/api/v2/ingredients", dependencies=[Depends(require_auth)])
async def ingredients(q: str = "", limit: int = 50) -> dict[str, Any]:
    items = data.search_ingredients(q, max(1, min(200, limit))) if q else data.ingredients()[:limit]
    return {"items": items}


@app.get("/api/v2/cases", dependencies=[Depends(require_auth)])
async def cases() -> dict[str, Any]:
    return {"items": data.cases()}


@app.get("/api/v2/db/status", dependencies=[Depends(require_auth)])
async def db_status() -> dict[str, Any]:
    return datasources.status()


@app.post("/api/v2/db/search", dependencies=[Depends(require_auth)])
async def db_search(payload: EvidenceRequest) -> dict[str, Any]:
    if not db_limiter.allow("db-v2"):
        raise HTTPException(status_code=429, detail="database rate limit exceeded")
    try:
        return await datasources.search_all(payload.query, payload.sources, payload.entity, payload.context)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/v2/design", dependencies=[Depends(require_auth)])
async def design_v2(payload: DesignRequest) -> dict[str, Any]:
    if not design_limiter.allow("design-v2"):
        raise HTTPException(status_code=429, detail="design rate limit exceeded")
    options = payload.options or {}
    mode = str(options.get("mode") or "auto")
    food_words = ("食品", "饮料", "面包", "酸奶", "肉", "酱", "软糖", "冰淇淋", "巧克力", "配方", "formulation", "food")
    if mode == "food" or (mode == "auto" and any(word in payload.query.lower() for word in food_words)):
        result = await asyncio.to_thread(food.design_food, payload.query, options)
    else:
        try:
            result = await asyncio.to_thread(engine.design, payload.query, options, False)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        result["mode"] = "biologic"
    data.ensure_dirs()
    path = data.DESIGNS_DIR / f"{result['design_id']}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


@app.get("/api/v2/designs/{design_id}", dependencies=[Depends(require_auth)])
async def get_design(design_id: str) -> dict[str, Any]:
    _validate_job_id(design_id)
    path = data.DESIGNS_DIR / f"{design_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="design not found")
    return json.loads(path.read_text(encoding="utf-8"))


@app.post("/api/v2/graph", dependencies=[Depends(require_auth)])
async def graph_v2(payload: dict[str, Any]) -> dict[str, Any]:
    design = payload.get("design")
    if not design and payload.get("design_id"):
        path = data.DESIGNS_DIR / f"{payload['design_id']}.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail="design not found")
        design = json.loads(path.read_text(encoding="utf-8"))
    if not design:
        raise HTTPException(status_code=422, detail="design or design_id required")
    return graph.build_design_graph(design, payload.get("online"))


@app.get("/api/v2/compute/capabilities", dependencies=[Depends(require_auth)])
async def compute_capabilities() -> dict[str, Any]:
    return await asyncio.to_thread(compute.capabilities)


@app.post("/api/v2/compute/mechanism", dependencies=[Depends(require_auth)])
async def compute_mechanism(payload: MechanismRequest) -> dict[str, Any]:
    design = None
    if payload.design_id:
        path = data.DESIGNS_DIR / f"{payload.design_id}.json"
        if path.exists():
            design = json.loads(path.read_text(encoding="utf-8"))
    if design is None:
        query = (payload.query or "").strip()
        if not query:
            error = "未关联配方，且没有输入体系描述。请先选择设计结果，或填写蛋白/受体与配体。"
            await asyncio.to_thread(compute.record_rejected, None, payload.options or {}, error)
            raise HTTPException(status_code=422, detail=error)
        design = {"brief": {"query": query}, "query": query, "design_id": payload.design_id}
    try:
        return await asyncio.to_thread(compute.start_job, design, payload.options or {})
    except ValueError as exc:
        await asyncio.to_thread(compute.record_rejected, design, payload.options or {}, str(exc))
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/api/v2/compute/jobs/{job_id}", dependencies=[Depends(require_auth)])
async def compute_job(job_id: str) -> dict[str, Any]:
    _validate_job_id(job_id)
    try:
        return compute.get_job(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="compute job not found")


@app.get("/api/v2/compute/jobs", dependencies=[Depends(require_auth)])
async def compute_jobs() -> dict[str, Any]:
    return {"items": compute.list_jobs()}


@app.get("/api/v2/compute/jobs/{job_id}/artifacts/{artifact:path}", dependencies=[Depends(require_auth)])
async def compute_artifact(job_id: str, artifact: str) -> FileResponse:
    _validate_job_id(job_id)
    base = (data.COMPUTE_DIR / job_id).resolve()
    target = (base / artifact).resolve()
    if not str(target).startswith(str(base) + os.sep) or not target.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(target)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "version": __version__, "engine": engine.ENGINE_VERSION, "food_engine": food.ENGINE_VERSION, "time": _now(), "auth_required": _auth_required(), "login_required": True, "mode": "food+biologic"}


@app.get("/api/meta", dependencies=[Depends(require_auth)])
async def meta() -> dict[str, Any]:
    return {
        "version": __version__,
        "engine_version": engine.ENGINE_VERSION,
        "datasets": data.dataset_manifest(),
        "model_card": training.load_card(),
        "feedback": training.feedback_stats(),
        "disclaimer": data.load("proteins.json")["disclaimer"],
        "food": {
            "systems": len(data.food_systems()),
            "ingredients": len(data.ingredients()),
            "interactions": len(data.food_interactions()),
            "cases": len(data.cases()),
        },
        "privacy": {
            "telemetry": False,
            "network": "only when the user explicitly calls an /api/db/* connector",
            "storage": str(data.RUNTIME_DIR),
            "auth": "bearer token in runtime/.token (chmod 600)",
        },
    }


@app.post("/api/parse", dependencies=[Depends(require_auth)])
async def parse(payload: DesignRequest) -> dict[str, Any]:
    brief = engine.parse_brief(payload.query, payload.options)
    brief.pop("matrix", None)
    return brief


@app.post("/api/design", dependencies=[Depends(require_auth)])
async def design(payload: DesignRequest) -> dict[str, Any]:
    if not design_limiter.allow("design"):
        raise HTTPException(status_code=429, detail="design rate limit exceeded; wait a minute")
    try:
        result = await asyncio.to_thread(engine.design, payload.query, payload.options, True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        json_log.write({"ts": _now(), "event": "design_error", "error": str(exc)[:300]})
        raise HTTPException(status_code=500, detail="design failed; see server log")
    return result


@app.get("/api/datasets/{name}", dependencies=[Depends(require_auth)])
async def datasets(name: str) -> dict[str, Any]:
    if name not in {"proteins.json", "protectants.json", "compounds.json", "matrices.json", "spectra.json"}:
        raise HTTPException(status_code=404, detail="unknown dataset")
    return data.load(name)


@app.get("/api/jobs/{job_id}", dependencies=[Depends(require_auth)])
async def get_job(job_id: str) -> dict[str, Any]:
    _validate_job_id(job_id)
    try:
        return engine.load_job(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="job not found")


@app.get("/api/jobs/{job_id}/download", dependencies=[Depends(require_auth)])
async def download_job(job_id: str) -> FileResponse:
    _validate_job_id(job_id)
    job_dir = data.JOBS_DIR / job_id
    zip_path = job_dir / "package.zip"
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="package not found")
    return FileResponse(zip_path, media_type="application/zip", filename=f"bioforge-{job_id}.zip")


@app.get("/api/jobs/{job_id}/artifacts/{artifact:path}", dependencies=[Depends(require_auth)])
async def job_artifact(job_id: str, artifact: str) -> FileResponse:
    _validate_job_id(job_id)
    job_dir = (data.JOBS_DIR / job_id).resolve()
    target = (job_dir / artifact).resolve()
    if not str(target).startswith(str(job_dir) + os.sep) or target == job_dir:
        raise HTTPException(status_code=403, detail="invalid artifact path")
    if not _artifact_allowed(artifact):
        raise HTTPException(status_code=403, detail="artifact not allowed")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(target)


@app.post("/api/spectra/match", dependencies=[Depends(require_auth)])
async def spectra_match(payload: SpectraMatchRequest) -> dict[str, Any]:
    return engine.match_spectra(payload.peaks, payload.type, payload.tolerance, payload.top_k)


@app.post("/api/feedback", dependencies=[Depends(require_auth)])
async def feedback(payload: FeedbackRequest) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(training.record_feedback, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/api/model/card", dependencies=[Depends(require_auth)])
async def model_card() -> dict[str, Any]:
    return {"card": training.load_card(), "stats": training.feedback_stats()}


@app.post("/api/model/train", dependencies=[Depends(require_auth)])
async def model_train(payload: TrainRequest) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(training.train_model, payload.include_synthetic)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/model/feedback", dependencies=[Depends(require_auth)])
async def model_feedback(limit: int = 50) -> dict[str, Any]:
    return {"stats": training.feedback_stats(), "items": training.list_feedback(limit)}


@app.delete("/api/model/feedback", dependencies=[Depends(require_auth)])
async def model_feedback_delete(confirm: str = "no") -> dict[str, Any]:
    if confirm != "yes-delete-all":
        raise HTTPException(status_code=400, detail="pass ?confirm=yes-delete-all to delete all feedback and the learned model")
    count = await asyncio.to_thread(training.delete_all_feedback)
    return {"deleted": count}


@app.get("/api/model/feedback.csv", dependencies=[Depends(require_auth)])
async def model_feedback_csv() -> PlainTextResponse:
    content = await asyncio.to_thread(training.export_csv)
    return PlainTextResponse(content, media_type="text/csv; charset=utf-8")


@app.post("/api/validate/quick", dependencies=[Depends(require_auth)])
async def validate_quick(payload: ValidateRequest) -> dict[str, Any]:
    smiles = payload.smiles
    result = await asyncio.to_thread(validation.quick_mm, smiles)
    qm = {"available": False, "reason": "quick QM disabled; set BIOFORGE_ENABLE_QM=1 to allow PySCF"}
    if os.environ.get("BIOFORGE_ENABLE_QM", "0") == "1":
        qm = await asyncio.to_thread(validation.quick_qm, smiles)
    return {"molecular_mechanics": result, "quantum_mechanics": qm}


@app.get("/api/db/uniprot", dependencies=[Depends(require_auth)])
async def db_uniprot(q: str) -> dict[str, Any]:
    if not db_limiter.allow("db"):
        raise HTTPException(status_code=429, detail="database rate limit exceeded")
    query = _safe_query(q)
    payload = await _cached_http(
        f"https://rest.uniprot.org/uniprotkb/search?query={query}&format=json&size=5",
        "uniprot",
    )
    results = []
    for entry in payload.get("results", [])[:5]:
        results.append({
            "accession": entry.get("primaryAccession"),
            "id": entry.get("uniProtkbId"),
            "protein": (entry.get("proteinDescription", {}).get("recommendedName", {}) or {}).get("fullName", {}).get("value"),
            "organism": entry.get("organism", {}).get("scientificName"),
            "length": entry.get("sequence", {}).get("length"),
            "keywords": [item.get("name") for item in entry.get("keywords", [])][:10],
        })
    return {"query": q, "source": "UniProt REST", "results": results}


@app.get("/api/db/kegg", dependencies=[Depends(require_auth)])
async def db_kegg(q: str) -> dict[str, Any]:
    if not db_limiter.allow("db"):
        raise HTTPException(status_code=429, detail="database rate limit exceeded")
    query = _safe_query(q)
    text = await _cached_text(f"https://rest.kegg.jp/find/genes/{query}", "kegg")
    lines = [line.strip() for line in text.splitlines() if line.strip()][:20]
    return {"query": q, "source": "KEGG REST", "results": lines, "note": "KEGG terms of use apply; do not redistribute."}


@app.get("/api/db/pubchem", dependencies=[Depends(require_auth)])
async def db_pubchem(name: str) -> dict[str, Any]:
    if not db_limiter.allow("db"):
        raise HTTPException(status_code=429, detail="database rate limit exceeded")
    query = _safe_query(name)
    payload = await _cached_http(
        f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{query}/property/MolecularFormula,MolecularWeight,ConnectivitySMILES,IUPACName/JSON",
        "pubchem",
    )
    results = []
    for item in (payload.get("PropertyTable", {}).get("Properties") or [])[:5]:
        results.append({
            "cid": item.get("CID"), "formula": item.get("MolecularFormula"), "mw": item.get("MolecularWeight"),
            "smiles": item.get("ConnectivitySMILES") or item.get("SMILES"), "iupac": item.get("IUPACName"),
        })
    return {"query": name, "source": "PubChem PUG REST", "results": results}


@app.get("/api/db/chebi", dependencies=[Depends(require_auth)])
async def db_chebi(q: str) -> dict[str, Any]:
    if not db_limiter.allow("db"):
        raise HTTPException(status_code=429, detail="database rate limit exceeded")
    query = _safe_query(q)
    payload = await _cached_http(
        f"https://www.ebi.ac.uk/chebi/backend/api/public/es_search/?term={query}&size=5",
        "chebi",
    )
    results = []
    for item in (payload.get("results") or [])[:5]:
        source = item.get("_source", {})
        results.append({"chebi_id": source.get("chebi_accession"), "name": source.get("name"), "stars": source.get("stars")})
    return {"query": q, "source": "ChEBI", "results": results}


def _safe_query(value: str) -> str:
    value = (value or "").strip()[:200]
    if not value or any(ord(char) < 32 for char in value):
        raise HTTPException(status_code=422, detail="invalid query")
    return httpx.QueryParams({"q": value})["q"]


async def _cached_http(url: str, cache_key: str) -> dict[str, Any]:
    host = url.split("/")[2]
    if host not in OUTBOUND_ALLOWLIST:
        raise HTTPException(status_code=403, detail="host not allowed")
    cache_dir = data.RUNTIME_DIR / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = re.sub(r"[^A-Za-z0-9]", "_", url)[-120:]
    cache_path = cache_dir / f"{cache_key}-{digest}.json"
    if cache_path.exists() and time.time() - cache_path.stat().st_mtime < 86400:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    try:
        async with httpx.AsyncClient(timeout=12.0, headers={"User-Agent": "BioForge/1.0 (research; local)"}) as client:
            response = await client.get(url)
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"upstream {host} returned {response.status_code}")
        if len(response.content) > 2_000_000:
            raise HTTPException(status_code=502, detail="upstream response too large")
        payload = response.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"upstream error: {str(exc)[:120]}")
    cache_path.write_text(json.dumps(payload, ensure_ascii=False)[:2_000_000], encoding="utf-8")
    return payload


async def _cached_text(url: str, cache_key: str) -> str:
    host = url.split("/")[2]
    if host not in OUTBOUND_ALLOWLIST:
        raise HTTPException(status_code=403, detail="host not allowed")
    cache_dir = data.RUNTIME_DIR / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = re.sub(r"[^A-Za-z0-9]", "_", url)[-120:]
    cache_path = cache_dir / f"{cache_key}-{digest}.txt"
    if cache_path.exists() and time.time() - cache_path.stat().st_mtime < 86400:
        return cache_path.read_text(encoding="utf-8")
    try:
        async with httpx.AsyncClient(timeout=12.0, headers={"User-Agent": "BioForge/1.0 (research; local)"}) as client:
            response = await client.get(url)
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"upstream {host} returned {response.status_code}")
        text = response.text[:500_000]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"upstream error: {str(exc)[:120]}")
    cache_path.write_text(text, encoding="utf-8")
    return text


def _validate_job_id(job_id: str) -> None:
    if not JOB_ID_RE.match(job_id):
        raise HTTPException(status_code=422, detail="invalid job id")


def _artifact_allowed(artifact: str) -> bool:
    normalized = artifact.replace("\\", "/")
    if normalized in ALLOWED_JOB_FILES:
        return True
    return any(normalized.startswith(prefix) for prefix in ALLOWED_PREFIXES) and ".." not in normalized


WEB_DIR = data.WEB_DIR
if WEB_DIR.exists() and (WEB_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
else:
    @app.get("/")
    async def root_placeholder() -> Response:
        return PlainTextResponse("BioForge web UI not built yet. See docs/SETUP.md.")


def main() -> None:
    import uvicorn
    host = os.environ.get("BIOFORGE_HOST", "127.0.0.1")
    port = int(os.environ.get("BIOFORGE_PORT", "8002"))
    token = _ensure_token()
    account = auth.ensure_account()
    print(f"BioForge Studio 2.1 API on http://{host}:{port}")
    print(f"Login: {account['username']} / see {auth.LOGIN_PATH}")
    print(f"API token file: {TOKEN_PATH} (optional bearer fallback)")
    if not _auth_required():
        print("WARNING: BIOFORGE_REQUIRE_AUTH=0 - API is unauthenticated; use only on a trusted local machine.")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
