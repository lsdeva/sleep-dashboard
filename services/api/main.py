"""
Sleep Dashboard API

Endpoints:
  GET  /health             — Redis connectivity + ingestion run status
  GET  /patients           — list all processed recordings with pathology + summary
  GET  /classify/{filename} — YASA distribution, anomalies, cached Claude narrative
  POST /classify/upload    — accept EDF, run ingestor inline, return classify result
"""

import asyncio
import json
import logging
import math
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import anthropic
import hvac
import pandas as pd
import pyarrow.parquet as pq
import redis as redis_lib
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FEATURES_DIR  = Path(os.getenv("FEATURES_DIR",  "/data/features"))
RAW_DIR       = Path(os.getenv("RAW_DIR",        "/data/raw"))
REDIS_URL     = os.getenv("REDIS_URL",            "redis://redis:6379")
VAULT_ADDR    = os.getenv("VAULT_ADDR",           "")
VAULT_TOKEN   = os.getenv("VAULT_TOKEN",          "")
VAULT_SECRET_PATH = os.getenv("VAULT_SECRET_PATH", "secret/data/sleepwell")
CLAUDE_MODEL  = "claude-sonnet-4-20250514"
NARRATIVE_TTL = 86_400  # 24 hours, in seconds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("api")


def _fetch_vault_secret(key: str) -> str:
    """Fetch a single secret value from HashiCorp Vault KV v2."""
    if not VAULT_ADDR or not VAULT_TOKEN:
        return ""
    try:
        client = hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN)
        resp = client.secrets.kv.v2.read_secret_version(
            path="sleepwell", mount_point="secret", raise_on_deleted_version=True,
        )
        value = resp["data"]["data"].get(key, "")
        if value:
            log.info("Fetched %s from Vault (%s)", key, VAULT_ADDR)
        return value
    except Exception as exc:
        log.warning("Vault lookup failed for %s: %s", key, exc)
        return ""


# Vault first, then fall back to env var for backwards compatibility
ANTHROPIC_KEY = _fetch_vault_secret("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY", "")

# ---------------------------------------------------------------------------
# App + lifespan
# ---------------------------------------------------------------------------

_redis:     redis_lib.Redis     | None = None
_anthropic: anthropic.Anthropic | None = None


@asynccontextmanager
async def lifespan(_app: "FastAPI"):
    global _redis, _anthropic

    # ── startup ──────────────────────────────────────────────────────────────
    try:
        _redis = redis_lib.from_url(REDIS_URL, decode_responses=True)
        _redis.ping()
        log.info("Redis connected at %s", REDIS_URL)
    except Exception as exc:
        log.warning("Redis unavailable (%s) — caching disabled", exc)
        _redis = None

    if ANTHROPIC_KEY:
        _anthropic = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        log.info("Anthropic client ready  model=%s", CLAUDE_MODEL)
    else:
        log.warning("ANTHROPIC_API_KEY not found in Vault or env — narratives will be disabled")

    yield  # ── app running ───────────────────────────────────────────────────

    # ── shutdown ─────────────────────────────────────────────────────────────
    if _redis is not None:
        _redis.close()


app = FastAPI(title="Sleep Dashboard API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Pathology inference from CAP Sleep Database filename prefixes
# Prefixes are ordered longest-first so "nfle" matches before "n".
# ---------------------------------------------------------------------------

_PATHOLOGY_MAP: list[tuple[str, str]] = [
    ("nfle", "Nocturnal Frontal Lobe Epilepsy"),
    ("brux", "Bruxism"),
    ("plm",  "Periodic Leg Movements"),
    ("rbd",  "REM Behavior Disorder"),
    ("sdb",  "Sleep-Disordered Breathing"),
    ("ins",  "Insomnia"),
    ("nar",  "Narcolepsy"),
    ("n",    "Normal"),
]


def _infer_pathology(recording_id: str) -> tuple[str, str]:
    """Return (code, label) inferred from the CAP filename stem."""
    stem = recording_id.lower()
    for prefix, label in _PATHOLOGY_MAP:
        if stem.startswith(prefix):
            return prefix, label
    return "unknown", "Unknown"

# ---------------------------------------------------------------------------
# Parquet helpers
# ---------------------------------------------------------------------------

def _sanitise(val: Any) -> Any:
    """Replace float NaN/Inf with None so JSON serialisation never throws."""
    if isinstance(val, float) and not math.isfinite(val):
        return None
    return val


def _read_summary(recording_id: str) -> dict | None:
    """
    Read the single-row summary Parquet produced by the ingestor.
    Returns None if the file does not exist.
    """
    path = FEATURES_DIR / f"{recording_id}_summary.parquet"
    if not path.exists():
        return None
    row = pq.read_table(str(path)).to_pandas().iloc[0].to_dict()
    # transition_detail is stored as a JSON string in Parquet
    if isinstance(row.get("transition_detail"), str):
        try:
            row["transition_detail"] = json.loads(row["transition_detail"])
        except json.JSONDecodeError:
            pass
    return {k: _sanitise(v) for k, v in row.items()}


def _read_epochs(recording_id: str) -> pd.DataFrame | None:
    """Read the per-epoch Parquet (stage / confidence / band powers)."""
    path = FEATURES_DIR / f"{recording_id}.parquet"
    if not path.exists():
        return None
    return pq.read_table(str(path)).to_pandas()

# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------

# Normal adult sleep architecture references (AASM scoring norms).
# Format: feature_key → (population_mean, population_std)
_NORMS: dict[str, tuple[float, float]] = {
    "sleep_efficiency_pct": (88.0,  5.0),
    "pct_W":                ( 5.0,  3.0),
    "pct_N1":               ( 5.0,  3.0),
    "pct_N2":               (50.0,  8.0),
    "pct_N3":               (17.0,  5.0),
    "pct_R":                (22.0,  5.0),
    "sol_minutes":          (10.0,  7.0),
    "rem_latency_minutes":  (100.0, 20.0),
    "n_transitions":        (45.0,  15.0),
}

_FEATURE_LABELS: dict[str, str] = {
    "sleep_efficiency_pct": "Sleep efficiency",
    "pct_W":                "Wake proportion",
    "pct_N1":               "N1 (light sleep) proportion",
    "pct_N2":               "N2 (core sleep) proportion",
    "pct_N3":               "N3 (slow-wave sleep) proportion",
    "pct_R":                "REM proportion",
    "sol_minutes":          "Sleep-onset latency",
    "rem_latency_minutes":  "REM latency",
    "n_transitions":        "Stage transition count",
}


def _detect_anomalies(summary: dict, top_n: int = 3) -> list[dict]:
    """
    Z-score each feature against AASM adult norms.
    Return the top_n most deviant features, sorted by |z|.
    """
    scored: list[tuple[float, dict]] = []

    for feat, (mean, std) in _NORMS.items():
        raw = summary.get(feat)
        if raw is None:
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue

        z = (val - mean) / std  # std is always > 0 per _NORMS
        scored.append((abs(z), {
            "feature":     feat,
            "label":       _FEATURE_LABELS.get(feat, feat),
            "value":       round(val, 2),
            "normal_mean": mean,
            "normal_std":  std,
            "z_score":     round(z, 2),
            "direction":   "elevated" if z > 0 else "reduced",
        }))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:top_n]]

# ---------------------------------------------------------------------------
# Claude narrative  (Redis-cached by recording_id)
# ---------------------------------------------------------------------------

def _narrative_key(recording_id: str) -> str:
    return f"narrative:{recording_id}"


async def _get_narrative(
    recording_id: str,
    pathology: str,
    summary: dict,
    anomalies: list[dict],
) -> tuple[str, bool]:
    """
    Fetch a Claude clinical narrative for the recording.
    Returns (text, was_cache_hit).
    """
    cache_key = _narrative_key(recording_id)

    # ── cache hit ─────────────────────────────────────────────────────────────
    if _redis is not None:
        cached = _redis.get(cache_key)
        if cached:
            log.debug("Narrative cache hit for %s", recording_id)
            return cached, True

    # ── no API key configured ─────────────────────────────────────────────────
    if _anthropic is None:
        return (
            "Narrative unavailable: add ANTHROPIC_API_KEY to Vault (localhost:8200) to enable clinical summaries.",
            False,
        )

    # ── build prompt ──────────────────────────────────────────────────────────
    anomaly_lines = "\n".join(
        f"  • {a['label']}: {a['value']} "
        f"(z={a['z_score']:+.1f}, {a['direction']}; "
        f"norm ≈ {a['normal_mean']} ± {a['normal_std']})"
        for a in anomalies
    )

    prompt = (
        "You are a clinical sleep scientist reviewing an automated polysomnography analysis.\n\n"
        f"Recording:           {recording_id}\n"
        f"Suspected pathology: {pathology}\n\n"
        "Sleep architecture:\n"
        f"  Wake:              {summary.get('pct_W', 'N/A')}%\n"
        f"  N1 (light):        {summary.get('pct_N1', 'N/A')}%\n"
        f"  N2 (core):         {summary.get('pct_N2', 'N/A')}%\n"
        f"  N3 (slow-wave):    {summary.get('pct_N3', 'N/A')}%\n"
        f"  REM:               {summary.get('pct_R', 'N/A')}%\n"
        f"  Sleep efficiency:  {summary.get('sleep_efficiency_pct', 'N/A')}%\n"
        f"  Total sleep time:  {summary.get('tst_minutes', 'N/A')} min\n"
        f"  Sleep-onset latency: {summary.get('sol_minutes', 'N/A')} min\n"
        f"  REM latency:       {summary.get('rem_latency_minutes', 'N/A')} min\n\n"
        f"Top anomalies vs. AASM adult norms:\n{anomaly_lines}\n\n"
        "Write a concise clinical narrative (3–4 sentences) summarising the sleep "
        "architecture, the notable deviations from normal, and how they are consistent "
        f"(or inconsistent) with the suspected {pathology} diagnosis. "
        "Use plain clinical language. Do not add safety disclaimers or caveats."
    )

    # ── call Claude (blocking SDK call → thread) ──────────────────────────────
    try:
        response = await asyncio.to_thread(
            _anthropic.messages.create,
            model=CLAUDE_MODEL,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
    except anthropic.AuthenticationError:
        return "Narrative unavailable: the configured ANTHROPIC_API_KEY is invalid.", False
    except anthropic.APIStatusError as exc:
        log.warning("Anthropic API error %s for %s: %s", exc.status_code, recording_id, exc.message)
        return f"Narrative unavailable: Anthropic API returned {exc.status_code}.", False
    except Exception as exc:
        log.warning("Narrative generation failed for %s: %s", recording_id, exc)
        return "Narrative unavailable: unexpected error calling Claude.", False

    # ── cache miss → write ─────────────────────────────────────────────────────
    if _redis is not None:
        _redis.setex(cache_key, NARRATIVE_TTL, text)

    return text, False

# ---------------------------------------------------------------------------
# Shared classify logic  (used by both GET and POST classify endpoints)
# ---------------------------------------------------------------------------

async def _classify(recording_id: str) -> dict:
    summary = _read_summary(recording_id)
    if summary is None:
        raise HTTPException(
            404,
            detail=(
                f"No features found for '{recording_id}'. "
                "Run the ingestor first, or upload the EDF via POST /classify/upload."
            ),
        )

    _, pathology   = _infer_pathology(recording_id)
    anomalies      = _detect_anomalies(summary)
    narrative, hit = await _get_narrative(recording_id, pathology, summary, anomalies)

    return {
        "recording_id": recording_id,
        "pathology":    pathology,
        "stage_distribution": {
            stage: summary.get(f"pct_{stage}", 0.0)
            for stage in ("W", "N1", "N2", "N3", "R")
        },
        "sleep_efficiency_pct": summary.get("sleep_efficiency_pct"),
        "tst_minutes":          summary.get("tst_minutes"),
        "tib_minutes":          summary.get("tib_minutes"),
        "sol_minutes":          summary.get("sol_minutes"),
        "rem_latency_minutes":  summary.get("rem_latency_minutes"),
        "n_transitions":        summary.get("n_transitions"),
        "eeg_channel":          summary.get("eeg_channel"),
        "n_epochs":             summary.get("n_epochs"),
        "anomalies":            anomalies,
        "narrative":            narrative,
        "narrative_cached":     hit,
    }

# ---------------------------------------------------------------------------
# On-demand ingestion for the upload endpoint
#
# The ingestor code lives in a separate container, but for single-file
# processing we load it dynamically into the API process via importlib.
# The API service mounts ./services/ingestor as /ingestor (see docker-compose).
# Heavy deps (yasa, mne, scipy) are included in this container's requirements.
# ---------------------------------------------------------------------------

_INGESTOR_PATH = Path("/ingestor/main.py")
_ingestor_process_file = None  # lazily loaded; safe for single-upload PoC


def _load_ingestor_process_file():
    """
    Load process_file from the ingestor module exactly once.
    Thread-safe for PoC usage (single upload at a time).
    """
    global _ingestor_process_file
    if _ingestor_process_file is not None:
        return _ingestor_process_file

    if not _INGESTOR_PATH.exists():
        raise RuntimeError(
            f"{_INGESTOR_PATH} not found. "
            "Check that ./services/ingestor is mounted into the API container."
        )

    import importlib.util

    spec = importlib.util.spec_from_file_location("_ingestor", str(_INGESTOR_PATH))
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # runs module-level imports once
    _ingestor_process_file = mod.process_file
    log.info("Ingestor module loaded from %s", _INGESTOR_PATH)
    return _ingestor_process_file


def _ingest_sync(edf_path: Path) -> dict:
    """
    Blocking wrapper called from asyncio.to_thread.
    Loads the ingestor module lazily, then processes a single EDF file.
    """
    process_file = _load_ingestor_process_file()
    result = process_file(edf_path)
    if result.get("status") not in ("ok",):
        raise RuntimeError(
            f"Ingestor returned non-ok status for {edf_path.name}: {result}"
        )
    return result

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", summary="Redis connectivity and last ingest run status")
async def health():
    redis_ok = False
    ingest:  dict = {}

    if _redis is not None:
        try:
            _redis.ping()
            redis_ok = True
            ingest = {
                k: _redis.hget("ingest:status", f"__{k}")
                for k in ("last_run", "total", "ok", "skipped", "error")
            }
        except Exception:
            pass

    return {
        "status":              "ok",
        "redis":               "connected" if redis_ok else "unavailable",
        "anthropic_ready":     _anthropic is not None,
        "ingest_status":       ingest,
        "features_dir_exists": FEATURES_DIR.exists(),
    }


@app.get("/patients", summary="List all processed recordings")
async def list_patients():
    """
    Returns one record per processed EDF. Pathology is inferred from the
    CAP Sleep Database filename prefix (e.g. 'ins3' → Insomnia).
    """
    summary_files = sorted(FEATURES_DIR.glob("*_summary.parquet"))
    patients = []

    for f in summary_files:
        recording_id = f.stem.removesuffix("_summary")
        summary = _read_summary(recording_id)
        if summary is None:
            continue
        _, pathology = _infer_pathology(recording_id)
        patients.append({
            "recording_id":         recording_id,
            "pathology":            pathology,
            "sleep_efficiency_pct": summary.get("sleep_efficiency_pct"),
            "tst_minutes":          summary.get("tst_minutes"),
            "tib_minutes":          summary.get("tib_minutes"),
            "n_epochs":             summary.get("n_epochs"),
            "pct_W":                summary.get("pct_W"),
            "pct_N1":               summary.get("pct_N1"),
            "pct_N2":               summary.get("pct_N2"),
            "pct_N3":               summary.get("pct_N3"),
            "pct_R":                summary.get("pct_R"),
            "sol_minutes":          summary.get("sol_minutes"),
            "rem_latency_minutes":  summary.get("rem_latency_minutes"),
            "n_transitions":        summary.get("n_transitions"),
            "eeg_channel":          summary.get("eeg_channel"),
        })

    return patients


@app.get(
    "/classify/{filename:path}",
    summary="Stage distribution, anomalies, and clinical narrative for a recording",
)
async def classify(filename: str):
    """
    `filename` accepts the bare stem (e.g. `n1`) or with extension (`n1.edf`).
    The response includes the Claude narrative, served from Redis cache on repeat calls.
    """
    recording_id = Path(filename).stem
    return await _classify(recording_id)


@app.post(
    "/classify/upload",
    summary="Upload a new EDF file, ingest it, and return classify results",
    status_code=200,
)
async def upload_and_classify(file: UploadFile = File(...)):
    """
    Accepts an EDF file, saves it to /data/raw/, runs YASA staging
    (blocking, up to 10 min), then returns the full classify payload.

    Note: the first call for a large recording may take several minutes
    because YASA stages the full overnight PSG.  Subsequent calls are fast
    since Parquet and Redis caches are populated.
    """
    if not file.filename or not file.filename.lower().endswith(".edf"):
        raise HTTPException(400, "Only .edf files are accepted.")

    dest = RAW_DIR / file.filename
    try:
        with dest.open("wb") as fout:
            shutil.copyfileobj(file.file, fout)
        log.info("Saved upload: %s (%d bytes)", dest.name, dest.stat().st_size)
    except OSError as exc:
        raise HTTPException(500, f"Could not save uploaded file: {exc}")
    finally:
        await file.close()

    # Run YASA staging in a thread (blocks for minutes on a full PSG).
    try:
        await asyncio.to_thread(_ingest_sync, dest)
    except RuntimeError as exc:
        raise HTTPException(422, str(exc))
    except Exception as exc:
        log.exception("Unexpected ingest error for %s", dest.name)
        raise HTTPException(500, f"Ingestion failed: {exc}")

    return await _classify(dest.stem)
