"""
Ingestor service — EDF → YASA sleep staging → Parquet feature cache.

For each .edf file in RAW_DIR:
  1. Load with MNE
  2. Select the best available EEG channel (C3-A2 preferred)
  3. Optionally detect EOG / EMG channels to improve YASA accuracy
  4. Run YASA pretrained SleepStaging
  5. Compute per-epoch band powers (Welch PSD, relative power)
  6. Compute patient-level sleep architecture summary
  7. Write {recording_id}.parquet        — per-epoch features
         {recording_id}_summary.parquet — patient-level summary
  8. Report status to Redis hash  ingest:status
"""

import warnings
# YASA's pretrained model was serialised with scikit-learn 0.24.2.
# InconsistentVersionWarning is benign for LabelEncoder across versions.
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import mne
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import redis as redis_lib
import yasa
from scipy.signal import welch

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RAW_DIR      = Path(os.getenv("RAW_DIR",      "/data/raw"))
FEATURES_DIR = Path(os.getenv("FEATURES_DIR", "/data/features"))
REDIS_URL    = os.getenv("REDIS_URL",          "redis://redis:6379")
EPOCH_SEC    = 30.0  # YASA always works in 30-second epochs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("ingestor")

# ---------------------------------------------------------------------------
# Channel candidate lists
# Ordered by preference; matching is case-insensitive.
# ---------------------------------------------------------------------------

# Linked-mastoid channels give YASA the best staging accuracy.
# Plain scalp channels are fallbacks.
EEG_CANDIDATES: list[str] = [
    "C3-A2", "C3:A2", "C3_A2", "EEG C3-A2", "C3A2",
    "C4-A1", "C4:A1", "C4_A1", "EEG C4-A1", "C4A1",
    "F3-A2", "F4-A1",
    "O1-A2", "O2-A1",
    "C3", "C4", "Cz",
    "F3", "F4",
    "O1", "O2",
    "Fp1", "Fp2",
]

EOG_CANDIDATES: list[str] = [
    "ROC-A1", "LOC-A2", "ROC", "LOC",
    "EOG left", "EOG right", "EOG-L", "EOG-R",
    "Left EOG", "Right EOG",
    "EOG", "E1", "E2",
]

EMG_CANDIDATES: list[str] = [
    "EMG Chin", "Chin EMG", "EMG chin",
    "EMG", "Chin", "EMG1",
    "Submental", "Submental EMG",
]

# ---------------------------------------------------------------------------
# Channel selection
# ---------------------------------------------------------------------------

def _pick_channel(ch_names: list[str], candidates: list[str]) -> str | None:
    """Return the first candidate that exists in ch_names (case-insensitive)."""
    lookup = {ch.lower(): ch for ch in ch_names}
    for candidate in candidates:
        match = lookup.get(candidate.lower())
        if match is not None:
            return match
    return None

# ---------------------------------------------------------------------------
# Per-epoch band power (Welch PSD, relative power in 0.5–30 Hz)
# ---------------------------------------------------------------------------

_BANDS: dict[str, tuple[float, float]] = {
    "bp_delta": (0.5,  4.0),
    "bp_theta": (4.0,  8.0),
    "bp_alpha": (8.0,  12.0),
    "bp_sigma": (12.0, 16.0),
    "bp_beta":  (16.0, 30.0),
}


def compute_band_powers(eeg_uv: np.ndarray, sf: float) -> list[dict[str, float]]:
    """
    Split eeg_uv into 30-second epochs and compute relative band powers via
    Welch's method.  Returns one dict per epoch with keys in _BANDS.
    """
    epoch_samples = int(EPOCH_SEC * sf)
    n_epochs      = len(eeg_uv) // epoch_samples
    # Welch window: 4 s or one epoch — whichever is shorter
    nperseg = min(epoch_samples, int(sf * 4))

    rows: list[dict[str, float]] = []
    for i in range(n_epochs):
        epoch = eeg_uv[i * epoch_samples : (i + 1) * epoch_samples]
        freqs, psd = welch(epoch, sf, nperseg=nperseg)

        total_mask  = (freqs >= 0.5) & (freqs <= 30.0)
        total_power = float(np.trapz(psd[total_mask], freqs[total_mask]))

        row: dict[str, float] = {}
        for name, (lo, hi) in _BANDS.items():
            mask   = (freqs >= lo) & (freqs <= hi)
            band_p = float(np.trapz(psd[mask], freqs[mask])) if mask.any() else 0.0
            row[name] = band_p / total_power if total_power > 0.0 else 0.0
        rows.append(row)

    return rows

# ---------------------------------------------------------------------------
# Patient-level sleep architecture summary
# ---------------------------------------------------------------------------

_STAGE_LABELS = ("W", "N1", "N2", "N3", "R")


def compute_sleep_summary(
    stages: np.ndarray,
    recording_id: str,
    eeg_channel: str,
    sf: float,
) -> dict:
    """
    Derive sleep architecture metrics from the per-epoch stage array.

    Metrics:
      pct_W/N1/N2/N3/R      — percentage of total time in each stage
      n_W/N1/N2/N3/R        — epoch counts per stage
      tib_minutes           — time in bed (all epochs)
      tst_minutes           — total sleep time (non-Wake epochs)
      sleep_efficiency_pct  — TST / TIB * 100
      sol_minutes           — sleep-onset latency (first non-W epoch)
      rem_latency_minutes   — REM latency from sleep onset (None if no REM)
      n_transitions         — total stage transitions
      transition_detail     — JSON object with per-pair counts
    """
    total = len(stages)

    summary: dict = {
        "recording_id":  recording_id,
        "eeg_channel":   eeg_channel,
        "sf_hz":         float(sf),
        "n_epochs":      total,
        "tib_minutes":   round(total * EPOCH_SEC / 60, 2),
    }

    for label in _STAGE_LABELS:
        n = int(np.sum(stages == label))
        summary[f"n_{label}"]   = n
        summary[f"pct_{label}"] = round(n / total * 100, 2) if total > 0 else 0.0

    n_sleep = int(np.sum(stages != "W"))
    summary["tst_minutes"]          = round(n_sleep * EPOCH_SEC / 60, 2)
    summary["sleep_efficiency_pct"] = round(n_sleep / total * 100, 2) if total > 0 else 0.0

    non_wake_idx = np.where(stages != "W")[0]
    summary["sol_minutes"] = (
        round(float(non_wake_idx[0]) * EPOCH_SEC / 60, 2)
        if len(non_wake_idx) > 0
        else round(total * EPOCH_SEC / 60, 2)
    )

    rem_idx = np.where(stages == "R")[0]
    if len(non_wake_idx) > 0 and len(rem_idx) > 0:
        summary["rem_latency_minutes"] = round(
            float(rem_idx[0] - non_wake_idx[0]) * EPOCH_SEC / 60, 2
        )
    else:
        summary["rem_latency_minutes"] = None

    # Transition counts
    n_transitions: int = int(np.sum(stages[:-1] != stages[1:]))
    summary["n_transitions"] = n_transitions

    pair_counts: dict[str, int] = {}
    for a, b in zip(stages[:-1], stages[1:]):
        if a != b:
            key = f"{a}->{b}"
            pair_counts[key] = pair_counts.get(key, 0) + 1
    summary["transition_detail"] = json.dumps(pair_counts)

    return summary

# ---------------------------------------------------------------------------
# Per-file processing
# ---------------------------------------------------------------------------

def process_file(edf_path: Path) -> dict:
    """
    Ingest one EDF recording.  Returns a status dict written to Redis.
    Never raises — all errors are caught and reported in the return value.
    """
    recording_id = edf_path.stem
    epoch_out   = FEATURES_DIR / f"{recording_id}.parquet"
    summary_out = FEATURES_DIR / f"{recording_id}_summary.parquet"

    log.info("▶  %s", recording_id)

    # ── 1. Load EDF ──────────────────────────────────────────────────────────
    try:
        raw = mne.io.read_raw_edf(str(edf_path), preload=True, verbose=False)
    except Exception as exc:
        log.error("   load failed: %s", exc)
        return {"status": "error", "stage": "load", "reason": str(exc)}

    sf = float(raw.info["sfreq"])
    log.info("   channels=%d  sf=%.1f Hz  duration=%.1f min",
             len(raw.ch_names), sf, raw.times[-1] / 60)

    # Guard: need at least one full epoch
    if raw.times[-1] < EPOCH_SEC:
        log.warning("   recording shorter than one epoch — skipping")
        return {"status": "skipped", "reason": "too_short"}

    # ── 2. Channel selection ─────────────────────────────────────────────────
    eeg_ch = _pick_channel(raw.ch_names, EEG_CANDIDATES)
    if eeg_ch is None:
        log.warning("   no suitable EEG channel (available: %s) — skipping",
                    raw.ch_names)
        return {"status": "skipped", "reason": "no_eeg_channel"}

    eog_ch = _pick_channel(raw.ch_names, EOG_CANDIDATES)
    emg_ch = _pick_channel(raw.ch_names, EMG_CANDIDATES)
    log.info("   EEG=%-12s  EOG=%-12s  EMG=%s",
             eeg_ch, eog_ch or "—", emg_ch or "—")

    # ── 3. YASA sleep staging ────────────────────────────────────────────────
    try:
        sls = yasa.SleepStaging(
            raw,
            eeg_name=eeg_ch,
            eog_name=eog_ch,  # None is fine — YASA uses EEG-only model
            emg_name=emg_ch,  # None is fine
        )
        stages   = sls.predict()       # ndarray[str]: 'W','N1','N2','N3','R'
        proba_df = sls.predict_proba() # DataFrame shape (n_epochs, 5)
    except Exception as exc:
        log.error("   YASA staging failed: %s", exc)
        return {"status": "error", "stage": "yasa", "reason": str(exc)}

    n_yasa = len(stages)
    log.info("   YASA → %d epochs", n_yasa)

    # ── 4. Per-epoch band powers ─────────────────────────────────────────────
    try:
        eeg_uv    = raw.get_data(picks=[eeg_ch])[0] * 1e6  # V → µV
        band_rows = compute_band_powers(eeg_uv, sf)
    except Exception as exc:
        log.warning("   band power computation failed (%s) — filling zeros", exc)
        zero      = {k: 0.0 for k in _BANDS}
        band_rows = [zero.copy() for _ in range(n_yasa)]

    # ── 5. Align epoch counts ────────────────────────────────────────────────
    # YASA drops the last incomplete epoch; band_rows uses floor division too,
    # so they should match — take the minimum to be safe.
    n_epochs = min(n_yasa, len(band_rows))
    stages   = stages[:n_epochs]
    proba_v  = proba_df.values[:n_epochs]        # (n_epochs, 5) float64
    band_rows = band_rows[:n_epochs]

    confidence = proba_v.max(axis=1)             # scalar per epoch

    # ── 6. Build per-epoch DataFrame ─────────────────────────────────────────
    epoch_df = pd.DataFrame({
        "epoch":      np.arange(n_epochs, dtype=np.int32),
        "stage":      stages,
        "confidence": confidence.astype(np.float32),
    })
    # Per-stage probabilities
    for col in proba_df.columns:
        epoch_df[f"proba_{col}"] = proba_df[col].values[:n_epochs].astype(np.float32)
    # Band powers
    bp_df    = pd.DataFrame(band_rows).astype(np.float32)
    epoch_df = pd.concat([epoch_df, bp_df], axis=1)

    # ── 7. Sleep architecture summary ────────────────────────────────────────
    summary    = compute_sleep_summary(stages, recording_id, eeg_ch, sf)
    summary_df = pd.DataFrame([summary])

    # ── 8. Write Parquet ─────────────────────────────────────────────────────
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.Table.from_pandas(epoch_df,   preserve_index=False), str(epoch_out))
    pq.write_table(
        pa.Table.from_pandas(summary_df, preserve_index=False), str(summary_out))

    log.info("   ✓ %s  (%d epochs, TST=%.0f min, eff=%.0f%%)",
             epoch_out.name, n_epochs,
             summary["tst_minutes"], summary["sleep_efficiency_pct"])

    return {
        "status":               "ok",
        "n_epochs":             n_epochs,
        "eeg_channel":          eeg_ch,
        "eog_channel":          eog_ch,
        "emg_channel":          emg_ch,
        "tst_minutes":          summary["tst_minutes"],
        "sleep_efficiency_pct": summary["sleep_efficiency_pct"],
    }

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("=== Ingestor starting ===")
    log.info("RAW_DIR=%s  FEATURES_DIR=%s  REDIS_URL=%s",
             RAW_DIR, FEATURES_DIR, REDIS_URL)

    # Connect to Redis (non-fatal if unavailable)
    redis_client: redis_lib.Redis | None = None
    try:
        redis_client = redis_lib.from_url(REDIS_URL, decode_responses=True)
        redis_client.ping()
        log.info("Redis connected")
    except Exception as exc:
        log.warning("Redis unavailable (%s) — status will not be written", exc)
        redis_client = None

    # Discover EDF files.
    # Glob "*.edf" already excludes ".edf.st" sidecar files on case-sensitive
    # filesystems; the endswith guard handles any edge cases.
    edf_files = sorted(
        p for p in RAW_DIR.glob("*.edf")
        if not p.name.lower().endswith(".edf.st")
    )

    if not edf_files:
        log.warning("No .edf files found in %s — nothing to do", RAW_DIR)
        return

    log.info("Found %d EDF file(s)", len(edf_files))

    results: dict[str, dict] = {}
    for edf_path in edf_files:
        results[edf_path.stem] = process_file(edf_path)

    # ── Write aggregate status to Redis ──────────────────────────────────────
    if redis_client is not None:
        payload: dict[str, str] = {
            rid: json.dumps(res) for rid, res in results.items()
        }
        n_ok      = sum(1 for r in results.values() if r["status"] == "ok")
        n_skipped = sum(1 for r in results.values() if r["status"] == "skipped")
        n_error   = sum(1 for r in results.values() if r["status"] == "error")
        payload["__last_run"] = datetime.now(timezone.utc).isoformat()
        payload["__total"]    = str(len(results))
        payload["__ok"]       = str(n_ok)
        payload["__skipped"]  = str(n_skipped)
        payload["__error"]    = str(n_error)
        redis_client.hset("ingest:status", mapping=payload)
        log.info("Status written to Redis hash 'ingest:status'")

    n_ok      = sum(1 for r in results.values() if r["status"] == "ok")
    n_skipped = sum(1 for r in results.values() if r["status"] == "skipped")
    n_error   = sum(1 for r in results.values() if r["status"] == "error")
    log.info("=== Done — ok=%d  skipped=%d  error=%d ===",
             n_ok, n_skipped, n_error)


if __name__ == "__main__":
    main()
