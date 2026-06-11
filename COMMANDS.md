# LLM Engineer's Handbook — Command Reference

Quick reference for running the LLM Twin project (ZenML pipelines + MongoDB + Qdrant + OpenAI).

> Two entry points exist: `poe <task>` (Poethepoet shortcuts defined in `pyproject.toml`) and the raw
> `poetry run python -m tools.run <flags>` CLI. Both are shown below.

---

## 0. One-time / per-machine notes

- **Python env:** managed by Poetry. Prefix everything with `poetry run`, or `poetry shell` once.
- **macOS only:** ZenML's local server forks processes and needs this env var, or it errors out:
  ```bash
  export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
  ```
  Set it in your shell profile (`~/.zshrc`) so every pipeline run inherits it.

---

## 1. Infrastructure — databases (Docker) + ZenML server

### Local databases (MongoDB + Qdrant) via Docker
```bash
# Start Docker Desktop first (macOS): open -a Docker   (wait until `docker info` works)

docker compose up -d        # start Mongo (27017) + Qdrant (6333/6334) containers
docker ps                   # verify both are "Up"
docker compose stop         # stop containers (keeps data volumes)
docker compose down         # stop + remove containers (volumes persist)
docker compose down -v      # ALSO delete data volumes (wipes the DBs)
```
Containers (from `docker-compose.yml`):
- `llm_engineering_mongo`  → `mongodb://llm_engineering:llm_engineering@127.0.0.1:27017`
- `llm_engineering_qdrant` → REST `http://localhost:6333`, dashboard `http://localhost:6333/dashboard`

### Local ZenML server (required for any pipeline run)
```bash
poetry run zenml login --local      # start local ZenML server -> http://127.0.0.1:8237
poetry run zenml stack set default  # use the LOCAL orchestrator stack
poetry run zenml logout --local     # stop the local server
poetry run zenml status             # show current connection/stack
```
Poe equivalents:
```bash
poe local-infrastructure-up     # docker up + zenml server up
poe local-infrastructure-down   # docker stop + zenml server down
poe set-local-stack             # zenml stack set default
```

---

## 2. Choosing LOCAL vs CLOUD databases

Connection config lives in `.env` and is read by `llm_engineering/settings.py`.
**OS environment variables override `.env`** (pydantic-settings precedence), so you can switch
without editing the file.

### Use CLOUD (MongoDB Atlas + Qdrant Cloud) — set in `.env`:
```dotenv
DATABASE_HOST=mongodb+srv://<user>:<password>@<cluster>.xxxxx.mongodb.net/
DATABASE_NAME=twin
USE_QDRANT_CLOUD=true
QDRANT_CLOUD_URL=https://<cluster-id>.<region>.aws.cloud.qdrant.io
QDRANT_APIKEY=<qdrant-api-key>
OPENAI_API_KEY=<openai-key>
```

### Use LOCAL docker DBs — either set `.env`, or override per-run:
```bash
export DATABASE_HOST="mongodb://llm_engineering:llm_engineering@127.0.0.1:27017"
export USE_QDRANT_CLOUD=false
export QDRANT_DATABASE_HOST=localhost
export QDRANT_DATABASE_PORT=6333
```

### Test connections before running (handy after cloud clusters wake from sleep)
```bash
# MongoDB Atlas DNS resolves?
host -t SRV _mongodb._tcp.<cluster>.xxxxx.mongodb.net

# Full Mongo + Qdrant auth check via the app's settings:
poetry run python -c "
from llm_engineering.settings import settings
from pymongo import MongoClient
c = MongoClient(settings.DATABASE_HOST, serverSelectionTimeoutMS=90000)
print('Mongo ping:', c.admin.command('ping'))
from qdrant_client import QdrantClient
q = QdrantClient(url=settings.QDRANT_CLOUD_URL, api_key=settings.QDRANT_APIKEY)
print('Qdrant:', [x.name for x in q.get_collections().collections])
"
```
> Atlas free (M0) clusters auto-pause after inactivity and take ~1–2 min to elect a primary on
> resume. A first ping may fail with `ReplicaSetNoPrimary`; retry with a long `serverSelectionTimeoutMS`.

---

## 3. Required keys / credentials

| Service        | `.env` key(s)                                   | Needed for                          | Notes |
|----------------|-------------------------------------------------|-------------------------------------|-------|
| **OpenAI**     | `OPENAI_API_KEY`                                | generate-datasets (LLM synthesis)   | gpt-4o-mini by default; needs billing credit |
| **MongoDB**    | `DATABASE_HOST`, `DATABASE_NAME`               | ETL write, FE read                  | Atlas uses user:pass in URI + IP allowlist (NOT an API key) |
| **Qdrant**     | `QDRANT_CLOUD_URL`, `QDRANT_APIKEY`, `USE_QDRANT_CLOUD` | FE write, RAG retrieval     | Cloud requires an API key |
| HuggingFace    | `HUGGINGFACE_ACCESS_TOKEN`                     | pushing datasets / pulling models   | only if `push_to_huggingface: true` |
| Comet ML       | `COMET_API_KEY`                                | training experiment tracking        | training pipeline only |
| AWS SageMaker  | `AWS_ACCESS_KEY`, `AWS_SECRET_KEY`, `AWS_ARN_ROLE`, `AWS_REGION` | remote training/inference | only for the AWS stack |

Export `.env` values into the ZenML secret store (so remote runs can read them):
```bash
poe export-settings-to-zenml     # = python -m tools.run --export-settings
poe delete-settings-zenml        # remove the 'settings' secret
```

---

## 4. Running the pipelines

All read parameters from a YAML in `configs/`. The CLI maps each flag to a config file.

### The 3 data pipelines (FTI "Feature" stage)
```bash
# 1) ETL — crawl links -> MongoDB   (config: configs/digital_data_etl_<author>.yaml)
poe run-digital-data-etl-paul          # Paul Iusztin (+ harness articles)
poe run-digital-data-etl-maxime        # Maxime Labonne
poe run-digital-data-etl               # BOTH (runs the two configs sequentially)
#   raw CLI:
poetry run python -m tools.run --run-etl --no-cache \
    --etl-config-filename digital_data_etl_paul_iusztin.yaml

# 2) Feature engineering — clean/chunk/embed -> Qdrant   (config: configs/feature_engineering.yaml)
poe run-feature-engineering-pipeline
#   raw CLI:
poetry run python -m tools.run --no-cache --run-feature-engineering

# 3) Generate datasets — LLM-synthesize instruct/preference data (uses OpenAI)
poe run-generate-instruct-datasets-pipeline     # configs/generate_instruct_datasets.yaml
poe run-generate-preference-datasets-pipeline   # configs/generate_preference_datasets.yaml
#   raw CLI:
poetry run python -m tools.run --no-cache --run-generate-instruct-datasets
```

### End-to-end (all 3 above, BOTH authors, one command)
```bash
poe run-end-to-end-data-pipeline
#   raw CLI:
poetry run python -m tools.run --run-end-to-end-data --no-cache
#   config: configs/end_to_end_data.yaml  (author_links: Paul + Maxime; chains ETL->FE->datasets)
```

### Training & evaluation (FTI "Training" stage — needs AWS/Comet)
```bash
poe run-training-pipeline       # configs/training.yaml
poe run-evaluation-pipeline     # configs/evaluating.yaml
```

### Utilities
```bash
poe run-export-artifact-to-json-pipeline    # dump a ZenML artifact to output/*.json
poe run-export-data-warehouse-to-json       # dump raw Mongo data -> data/
poe run-import-data-warehouse-from-json     # load data/ -> Mongo
```

---

## 5. Inference / RAG (FTI "Inference" stage)

```bash
poe call-rag-retrieval-module        # python -m tools.rag : embed a query, retrieve from Qdrant
poe run-inference-ml-service         # uvicorn FastAPI on http://0.0.0.0:8000
```

---

## 6. Common flags

| Flag | Meaning |
|------|---------|
| `--no-cache` | disable ZenML step caching (force re-run of every step) |
| `--run-<x>` | select which pipeline(s) to run (see `python -m tools.run --help`) |
| `--etl-config-filename <f>` | pick the ETL YAML under `configs/` |

```bash
poetry run python -m tools.run --help    # full CLI help
```

---

## 7. Typical end-to-end demo flow (cloud)

```bash
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
# .env already points at Atlas + Qdrant Cloud, USE_QDRANT_CLOUD=true

poetry run zenml login --local && poetry run zenml stack set default   # ZenML server + local stack
# (test connections — section 2)

poetry run python -m tools.run --run-end-to-end-data --no-cache        # ETL -> FE -> datasets, both authors

poe call-rag-retrieval-module                                          # sanity-check RAG retrieval
```

> The ZenML dashboard (http://127.0.0.1:8237) shows every pipeline run, step, artifact, and the
> metadata each step logged (crawl counts, #documents, #chunks, embedding model id, etc.).
