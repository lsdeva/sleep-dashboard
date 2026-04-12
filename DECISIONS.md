# Architecture Decision Records

## ADR-001 — Sleep Staging: YASA (pretrained)

**Decision:** Use the YASA library for automated sleep staging with its pretrained model.

**Rationale:** YASA provides a validated, publication-grade sleep staging pipeline (LightGBM under the hood) that runs on standard EDF PSG files without requiring custom model training. Appropriate for a PoC where reproducibility and speed of iteration matter more than bespoke accuracy.

**Consequences:** Staging quality is bounded by YASA's pretrained weights; no fine-tuning on CAP-specific cohort.

---

## ADR-002 — Pathology Classification: Derived from YASA features

**Decision:** Derive pathology classifications (e.g. apnea index proxy, REM abnormalities) from the feature set produced by YASA's stage architecture rather than training a separate classifier.

**Rationale:** Keeps the pipeline self-contained and avoids labelled pathology data requirements. Feature-based heuristics are explainable and auditable.

**Consequences:** Classifications are approximations; not suitable for clinical use.

---

## ADR-003 — LLM Layer: Anthropic Claude API (claude-sonnet-4-20250514)

**Decision:** Use `claude-sonnet-4-20250514` via the Anthropic API solely for generating clinical narrative summaries from structured feature data.

**Rationale:** The LLM layer is intentionally narrow — it receives structured JSON features and returns a plain-language summary. Sonnet 4 provides high-quality medical prose at reasonable cost/latency.

**Consequences:** Narratives are cached in Redis by filename to minimise API spend. The LLM has no access to raw signal data; it only sees aggregated statistics.

---

## ADR-004 — Backend: FastAPI + Python 3.11

**Decision:** FastAPI as the API framework, Python 3.11 as the runtime.

**Rationale:** FastAPI's async support and automatic OpenAPI docs reduce boilerplate. Python 3.11 is the stable release compatible with YASA, MNE, and the Anthropic SDK.

---

## ADR-005 — Frontend: React + Vite + Plotly

**Decision:** React with Vite build tooling; Plotly.js for all signal and hypnogram visualisations.

**Rationale:** Vite gives fast HMR for development. Plotly covers hypnograms, power spectra, and time-series EEG traces without additional charting libraries.

---

## ADR-006 — Infrastructure: Docker Compose (4 services)

**Decision:** Four-service Docker Compose stack: `ingestor`, `api`, `frontend`, `redis`.

**Rationale:**  Clear service boundaries make it straightforward to extract individual services later.

**Services:**
- `ingestor` — batch EDF → Parquet pipeline
- `api` — FastAPI, serves features and narratives
- `frontend` — React/Vite dev server
- `redis` — narrative cache

---

## ADR-007 — Data Source: PhysioNet CAP Sleep Database

**Decision:** Use PhysioNet CAP Sleep Database EDF files mounted as a bind volume at `./data/raw/`.

**Rationale:** Openly licensed, well-documented PSG dataset with scored sleep studies. Bind mount avoids baking patient data into images.

---

## ADR-008 — Feature Cache: Parquet files at ./data/features/

**Decision:** Persist computed YASA features as Parquet files in `./data/features/`, one file per EDF recording.

**Rationale:** Parquet is columnar, compressed, and fast to read with pandas/pyarrow. Avoids re-running the staging pipeline on every API request.

---

## ADR-009 — API Cache: Redis keyed by filename, 24 hr TTL

**Decision:** Cache Claude narrative responses in Redis using the EDF filename as the cache key with a 24-hour TTL (`NARRATIVE_TTL = 86_400` seconds).

**Rationale:** Narrative generation is the only external API call with variable cost. A simple string key-value cache eliminates redundant calls for the same recording. The 24-hour TTL balances freshness against API cost for a PoC workload.

---

## ADR-010 — API Key Handling: .env only, never in frontend

**Decision:** The Anthropic API key is configured exclusively via the `ANTHROPIC_API_KEY` environment variable in `.env` (gitignored). The key is read by the API container at startup and is never sent to or stored in the browser.

**Rationale:** Keeping credentials server-side eliminates the risk of key exposure through browser storage, network traffic inspection, or JavaScript bundle analysis. `.env` is gitignored and `.env.example` contains only a placeholder value.

**Consequences:** Deployers must configure `.env` before starting the stack. There is no in-browser key-entry flow.

---

## ADR-011 — EDF Files Excluded from Version Control

**Decision:** All EDF files, EDF sidecar files (`.edf.st`), and derived Parquet features are excluded from git via `.gitignore`. Only `.gitkeep` marker files are committed to preserve the `data/raw/` and `data/features/` directory structure.

**Rationale:** EDF polysomnography files contain sensitive biometric data and can be hundreds of megabytes. Committing them would violate patient privacy expectations and make the repository impractically large. The PhysioNet CAP Sleep Database files are freely available for download separately.

**Consequences:** Contributors must obtain and place EDF files locally before the stack can process any recordings.
