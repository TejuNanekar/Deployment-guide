# Register another application

The retrieval engine is shared. The project's files, labels, and collection are not. Do not add a second application's deploy commands to `corpus/matrimony.yaml`.

## Isolation

Every query filters `project_id` in Qdrant. The catalog hides other projects. That filter is the guard inside one collection.

Use a separate `COLLECTION_NAME` for the new project as well. A missing filter cannot leak vectors that live in a different collection. One local Qdrant directory can hold both collections. Point `QDRANT_PATH` at it, or point `QDRANT_URL` at a server.

Production stays blocked for every project. There is no per-project switch that turns production answers on.

## What you add

1. Copy `backend/corpus/matrimony.yaml` to a new manifest, for example `backend/corpus/billing.yaml`.
2. Set a new `project_id`, such as `billing-api`. Keep it stable.
3. Point `PROJECT_ID`, `MANIFEST_PATH`, and `COLLECTION_NAME` at the new project. Use a collection name that is not `matrimony_deployment`.
4. Replace the repository roots. Today the loader knows three root ids: `matrimony-platform`, `matrimony-platform-ui`, and `deployment-guide`. A project whose checkouts use different ids needs those ids added to the root map in `backend/app/manifest.py` before the manifest can name them. The search and safety code does not need a new copy.
5. List the runbook, scripts, workflows, and example config. Give each file `document_type`, `component`, `environment`, and `status`.
6. Use `status: current` or `status: proposed` only for text that may be quoted. Anything else, including `outdated` and `unassigned`, is stored and excluded from answers.
7. Transcribe a procedure into Markdown with the existing heading tags if you want ordered steps. A heading looks like `[deploy|billing-api] Step 1 — Local: build`. The scopes are component ids. A heading whose third field is `note` is a prerequisite, not a shell step. Put the command in a fence under that heading. Without these tags, the assistant falls back to fenced commands in deployment documents and does not invent missing steps.

8. Redact or keep secrets out of the files. Real `.env` files and private keys are skipped. Example env files are indexed with values replaced.
9. Run `python -m app.ingest` and check `/health`. `index` should become `ready` and `embedding_id` should start with `fastembed:`.

## What you do not copy

Do not start a second FastAPI app. Do not add a second embedding model unless you re-index that collection and check the eval file. Do not point two projects at the same `COLLECTION_NAME` unless you accept that a bug in the filter would be the only wall between them.

The chat screen still offers the Matrimony applications. A second project's names need a registry entry before the UI can ask for them. Until that exists, call `POST /ask` with the new `PROJECT_ID` process (its own manifest, collection, and port) so the Matrimony process never loads the other corpus.

## Server details

Record host names and paths in the runbook. Do not put passwords, keys, or SSH private keys in the manifest. The assistant does not connect to the host.
