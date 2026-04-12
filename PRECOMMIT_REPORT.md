# Pre-Commit Cleanup Report

Generated: 2026-04-12

---

## Status: ⚠ MANUAL ACTION REQUIRED

Two issues must be resolved before the first `git commit` (see §8 below).

---

## Step 1 — `.gitignore`

**Result: MODIFIED**

| Entry required | Was present | Action |
|---|---|---|
| `.env` | ✓ | — |
| `*.edf` (project-wide) | ✗ | Added |
| `*.edf.st` (project-wide) | ✗ | Added |
| `data/**/*.txt` (data/ only) | ✗ | Added |
| `data/raw/*` | ✗ (was `data/raw/*.edf` only) | Replaced with `data/raw/*` |
| `data/features/*` | ✗ (was `data/features/*.parquet` only) | Replaced with `data/features/*` |
| `!data/raw/.gitkeep` | ✗ | Added |
| `!data/features/.gitkeep` | ✗ | Added |
| `__pycache__/` | ✓ | — |
| `*.pyc` / `*.pyo` | ✓ (covered by `*.py[cod]`) | Added explicit `*.pyc` / `*.pyo` alongside |
| `.pytest_cache/` | ✗ | Added |
| `node_modules/` | ✓ | — |
| `dist/` | ✓ | — |
| `.vite/` | ✓ | — |
| `*.log` | ✓ | — |
| `.DS_Store` | ✓ | — |
| `Thumbs.db` | ✓ | — |

Also removed `data/raw/*.edf.gz` (no such files in this project; superseded by `data/raw/*`).

---

## Step 2 — `.env.example`

**Result: MODIFIED**

Previous content contained only the API key placeholder with a comment line.
Updated to the exact canonical form with no comment and all 4 required variables:

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
REDIS_URL=redis://redis:6379
RAW_DIR=/data/raw
FEATURES_DIR=/data/features
```

Changes:
- Placeholder changed from `sk-ant-...` → `sk-ant-your-key-here`
- Added `REDIS_URL`, `RAW_DIR`, `FEATURES_DIR`
- Removed leading comment line (`# Copy to .env and fill in values`)

No real credentials present in this file. ✓

---

## Step 3 — Secrets Scan

**Result: ⚠ ONE FINDING (non-blocking for git, but requires key rotation)**

### Source files (`.py`, `.js`, `.jsx`, `.ts`, `.yml`, `.json`, `.md`) — CLEAN

| Pattern searched | Findings in source files |
|---|---|
| `sk-ant-` | Only in safe locations (see table below) |
| `sk-` (other) | None |
| Hardcoded passwords | None |
| Personal file paths (`C:\Users\`, `/home/`) | None |
| Non-loopback IPs (other than `0.0.0.0`, `127.0.0.1`) | None |

Safe `sk-ant-` occurrences in source files:

| File | Line | Content | Safe? |
|---|---|---|---|
| `.env.example` | 1 | `sk-ant-your-key-here` | ✓ Placeholder |
| `AUDIT.md` | 115 | old placeholder in audit table | ✓ Historical report |
| `README.md` | 44 | instruction to replace placeholder | ✓ Docs |
| `ApiKeyModal.jsx` | 10–11 | format validation (`startsWith('sk-ant-')`) | ✓ Code logic |
| `ApiKeyModal.jsx` | 49 | `placeholder="sk-ant-api03-…"` | ✓ UX placeholder |

### `.env` — REAL KEY PRESENT

```
File:  .env
Line:  2
Value: ANTHROPIC_API_KEY=sk-ant-api03-ZXa-i1lY...  (truncated)
```

**This file is listed in `.gitignore` and will NOT be committed.** However, the key
has been present in a local file and may have appeared in shell history, Docker env
dumps, or container inspection output.

> **MANUAL ACTION:** Rotate this key at https://console.anthropic.com/settings/keys
> and update `.env` with the new value. The old key should be considered potentially
> exposed.

---

## Step 4 — Debug Artifacts

**Result: CLEAN**

| Artifact type | Files scanned | Findings |
|---|---|---|
| `print()` in Python files | `services/ingestor/main.py`, `services/api/main.py` | None |
| `console.log()` in JS/JSX | All files under `services/frontend/src/` | None |
| TODO comments with credentials | All files | None |
| Test files with real patient filenames | All files | None |

---

## Step 5 — Data Directory Git Tracking

**Result: NOT APPLICABLE — no git repository initialised yet**

```
$ git status
fatal: not a git repository (or any of the parent directories): .git
```

Files present on disk in `data/` that will be protected by `.gitignore` once `git init` is run:

| File | Ignored by rule |
|---|---|
| `data/raw/ins1.edf` | `*.edf` and `data/raw/*` |
| `data/raw/ins1.edf.st` | `*.edf.st` and `data/raw/*` |
| `data/raw/ins1.txt` | `data/**/*.txt` and `data/raw/*` |
| `data/features/ins1.parquet` | `data/features/*` |
| `data/features/ins1_summary.parquet` | `data/features/*` |
| `data/raw/.gitkeep` | Explicitly un-ignored by `!data/raw/.gitkeep` |
| `data/features/.gitkeep` | Explicitly un-ignored by `!data/features/.gitkeep` |

> **MANUAL ACTION:** Run `git init` before the first commit. The `.gitignore` is correct
> and will protect all data files automatically.

---

## Step 6 — README.md

**Result: MODIFIED**

| Section required | Was present | Action |
|---|---|---|
| Project overview (one paragraph) | ✓ (one line only) | Expanded to full paragraph |
| Architecture diagram or description | ✗ | Added ASCII diagram + service table |
| Prerequisites (Docker Desktop, API key) | ✗ | Added §Prerequisites |
| Setup instructions referencing `.env.example` | ✓ (partial) | Expanded to numbered steps |
| How to run: `docker compose up --build` | ✗ (had `make up` only) | Added `docker compose up --build` as primary command |
| How to add new EDF files | ✓ (one sentence) | Expanded with prefix table and restart instructions |
| Data privacy note | ✗ | Added §Data Privacy |
| License section (MIT) | ✗ | Added §License with MIT declaration and medical disclaimer |

---

## Step 7 — DECISIONS.md

**Result: MODIFIED**

| Decision required | Was present | Action |
|---|---|---|
| YASA for sleep staging (not custom ML) | ✓ ADR-001 | — |
| Claude API for narrative only (not classification) | ✓ ADR-003 | — |
| API key via `.env` as primary source | ✗ | Added **ADR-010** |
| EDF files excluded from git | ✗ | Added **ADR-011** |
| Parquet as feature cache format | ✓ ADR-008 | — |
| Redis for narrative caching with 24 hr TTL | Partial (ADR-009 lacked TTL) | Updated ADR-009 to include TTL |

**Note on ADR-010:** The original architecture spec called for `.env`-only key handling.
A subsequent UX feature added browser-side key entry (stored in `localStorage`, forwarded
as `X-Anthropic-Api-Key` header). ADR-010 documents both the primary `.env` path and the
browser override, and notes the security caveat for production use. No code was changed.

---

## Summary of Files Modified

| File | Change type |
|---|---|
| `.gitignore` | Updated — added 7 missing entries, replaced 2 patterns |
| `.env.example` | Updated — added 3 missing vars, fixed placeholder text |
| `README.md` | Updated — added 5 missing sections, expanded 2 existing |
| `DECISIONS.md` | Updated — added ADR-010, ADR-011; updated ADR-009 with TTL detail |
| `PRECOMMIT_REPORT.md` | Created (this file) |

No logic, implementation, or configuration files were changed.

---

## Issues Requiring Manual Action

### 1. CRITICAL — Rotate the Anthropic API key

The `.env` file contains a real API key (`sk-ant-api03-ZXa-...`). Although `.env` is
gitignored and will never be committed, the key should be considered potentially exposed
(shell history, `docker inspect`, container env dumps).

**Action:** Log in to https://console.anthropic.com/settings/keys, revoke the current
key, generate a new one, and update `.env`.

### 2. REQUIRED — Initialise the git repository

The project directory has no `.git` folder. The pre-commit steps above assume a git
repository will be created before the first commit.

**Action:**
```bash
cd sleep-dashboard
git init
git add .
git status   # verify no EDF/Parquet/secrets are staged
git commit -m "Initial commit — Sleep Dashboard PoC"
```

After `git add .`, run `git status` and confirm **no files from `data/raw/` or
`data/features/`** are listed under "Changes to be committed".

---

## Conclusion

Once the two manual actions above are completed the repository is **SAFE TO COMMIT**.
All source files are free of secrets, debug statements, and personal paths. All data
files are covered by `.gitignore`. Documentation is complete.
