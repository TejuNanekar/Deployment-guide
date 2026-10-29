# Indexing and query pipelines

The assistant answers from files listed in a project manifest. It does not open SSH and it does not run a deploy. Retrieved passages are context for the language model. The reply is the model's text. If the model does not answer, those passages are not shown in its place.

## Indexing

1. `backend/corpus/matrimony.yaml` names the project, the files, and the label for each file: repository, component, environment, status, and document type.
2. A `watch` glob picks up new workflow files. They are stored as `unassigned` and are not used in answers until the manifest gives them a component and a status of `current` or `proposed`.
3. `.env` files that are not examples, private keys, `examples/`, and `node_modules` are skipped. The PDF beside the guide is not in the manifest and is not parsed. The transcribed Markdown guide is the indexed procedure.
4. File text is redacted before it is chunked, embedded, or stored. Redaction covers private keys, assignment-style secrets, credential URLs, bearer tokens, and common token prefixes such as `gsk_` and `AKIA`.
5. Markdown is split on headings. A fenced command stays with the paragraph that says where to run it. Shell, YAML, and config files are split on blank lines, near 1,000 characters.
6. Each chunk is embedded and upserted. The payload keeps `project_id`, `component`, `environment`, `status`, `source_path`, `git_ref`, `content_hash`, and `embedding_id`.
7. Unchanged chunks are not embedded again. After a successful upsert, chunk ids that no longer belong to that file are deleted. A missing file is removed from the index.
8. If the live collection was built with a different embedder or vector size, ingest writes a staging collection named `<collection>__next`. The active pointer moves only after that collection has points. A failed rebuild leaves the previous collection in place.

`/health` reports `embedding_id` and `index`. `ready` means the stored id matches the process. `unlabeled-dense` means the vectors look like FastEmbed but were written before identity was stored; re-index to stamp them. `dimension-mismatch`, `identity-mismatch`, `unlabeled-sparse`, and a dense index opened with `EMBEDDING_PROVIDER=hash` refuse questions until re-index.

`hash` embeddings are for tests. They are not semantic. They are also 384-dimensional, which is why identity is stored separately from the vector size.

## Query

1. The server checks the index. A blocked index returns an explanation and no commands.
2. Production is refused. That includes `environment=production` and any question that says production or prod, even when the selector says UAT. Staging is not an alias of UAT.
3. The only answerable environment today is UAT.
4. Every search filters `project_id`, `environment`, `component`, and `status` (`current` or `proposed`). Similarity cannot override those filters. Another project's points are not returned and do not appear in the catalog.
5. A question that is not a location question, and that does not name an application, asks which application. It does not search every component.
6. Search retrieves passages for the selected application. BM25 ranks chunks, and exact filenames, flags, and paths are kept as tokens. When the embedder is semantic, dense search is fused with reciprocal rank fusion. There is no score cutoff.
7. Those passages are sent to Groq or the other configured model. The model's text is the answer. The passages are not copied into the reply.
8. If the model is not configured, or it returns nothing, the reply says so. The retrieved document text is not shown in its place.

## Debugging

Set `LOG_LEVEL=INFO`. Each query logs project, environment, application, embedding id, index status, source paths, outcome, latency, and a redacted question preview. Document text is not logged.

`POST /ask` with `"debug": true` returns the same facts in `trace`.

## What this pass did not change

Qdrant, BM25, dense search, RRF, and `BAAI/bge-small-en-v1.5` stay. A cross-encoder reranker was not added: there is no measured gain yet. LlamaIndex and LangChain were not added. Production refusals stay in this application so they can be tested without a framework.

