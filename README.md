# Sleep Disorder AI Dashboard

![License](https://img.shields.io/badge/license-MIT-green)
![Docker](https://img.shields.io/badge/docker-required-blue)
![Python](https://img.shields.io/badge/python-3.11-blue)
![Claude](https://img.shields.io/badge/Claude-API-orange)
![YASA](https://img.shields.io/badge/YASA-sleep%20staging-purple)

*AI-augmented clinical sleep study analysis — from raw EDF to clinician-ready narrative in minutes.*



## Demo

![Sleep Disorder Intelligence Dashboard — screen](docs/sleep%20well.png)


## How It Works

1. **Ingest** — Drop any `.edf` polysomnography file into the dashboard (or `data/raw/`)
2. **Stage** — [YASA](https://raphaelvallat.com/yasa/) classifies every 30 s epoch into W / N1 / N2 / N3 / REM using a pretrained LightGBM model
3. **Extract** — Per-epoch band powers (delta, theta, alpha, sigma, beta) and patient-level sleep architecture metrics are computed and cached as Parquet
4. **Score** — Each metric is z-scored against AASM adult reference norms; the top anomalies are surfaced
5. **Narrate** — The structured results are sent to the Anthropic Claude API, which returns a concise clinical narrative summary

## Architecture

![Sleep Disorder Intelligence Dashboard — architecture](docs/sleep_dashboard_readme_architecture.svg)

Four-service Docker Compose stack, all communication internal to the Docker network:

| Service    | Description                                              |
|------------|----------------------------------------------------------|
| ingestor   | Reads EDF files, runs YASA sleep staging, writes Parquet |
| api        | FastAPI — serves features, triggers Claude narratives    |
| frontend   | React + Vite + Plotly dashboard                          |
| redis      | Narrative cache keyed by filename                        |

## Prerequisites

- **Docker Desktop** 4.x or later (with Compose v2)
- **Anthropic API key** — obtain at [console.anthropic.com](https://console.anthropic.com/settings/keys)
- EDF files from the [PhysioNet CAP Sleep Database](https://physionet.org/content/capslpdb/)
  (download separately; files are never committed to this repository)

## Setup

```bash
# 1. Clone the repository
git clone https://github.com/lsdeva/sleep-dashboard.git
cd sleep-dashboard

# 2. Create your environment file from the example
cp .env.example .env
# Edit .env and replace sk-ant-your-key-here with your real Anthropic API key

# 3. Place EDF files in the data directory (optional — you can also upload via the UI)
#    Example: data/raw/ins1.edf
```

## How to Run

```bash
docker compose up --build
```

- Dashboard: http://localhost:5173
- API docs: http://localhost:8000/docs

The ingestor runs automatically on startup and stages all EDF files found in `data/raw/`.
Subsequent `docker compose up` calls skip already-processed files (Parquet cache present).

Alternatively, use the Makefile shortcuts:

```bash
make build   # docker compose build
make up      # docker compose up -d
make down    # docker compose down
make logs    # docker compose logs -f
```

## Adding EDF Files

**Option A — Upload via the dashboard** (recommended for individual files):
Use the **Upload EDF** button in the sidebar. The file is staged immediately and results
appear without restarting anything.

**Option B — Bulk load at startup**:
Copy any `.edf` files into `./data/raw/`, then restart the ingestor:
```bash
docker compose restart ingestor
```
The ingestor processes every EDF file it finds in that folder.

Any EDF file is accepted regardless of filename. If the filename matches a
[PhysioNet CAP Sleep Database](https://physionet.org/content/capslpdb/) prefix
(e.g. `ins`, `nfle`, `rbd`) the pathology label is inferred automatically;
otherwise it is shown as **Unknown**.

## Token Usage

Each clinical narrative consumes approximately **400 output tokens** via the Anthropic API
(`claude-sonnet-4-20250514`). Narratives are cached in Redis with a 24-hour TTL, so
repeat views of the same recording incur no additional API cost. With caching enabled,
analysing 10 unique recordings costs roughly 4 000 tokens (~$0.01 at current Sonnet pricing).

## Data Privacy

EDF sleep study files contain sensitive biometric data. This project is designed so that:

- EDF files are **never committed to git** (excluded by `.gitignore`)
- EDF files are **never sent to any remote server** — all signal processing (YASA staging,
  band power extraction) runs entirely on your local machine inside Docker containers
- Only de-identified aggregate statistics (stage percentages, latencies, transition counts)
  are sent to the Anthropic Claude API to generate the clinical narrative
- The Anthropic API key is stored only in `.env` (gitignored) and read by the API
  container at startup; it is never sent to the browser, never logged, and never persisted elsewhere

## Contributing

Contributions are welcome. Please open an issue first to discuss what you would like to change.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-change`)
3. Commit your changes
4. Open a pull request

## License

MIT License — see [LICENSE](LICENSE) for full text.

> This software is provided for portfolio and educational purposes only.
> It is not a medical device and must not be used for clinical diagnosis or treatment decisions.

## See Also

- [DECISIONS.md](DECISIONS.md) — recorded architecture decisions
