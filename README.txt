Project Notes

The old Gaudi/Habana Med42 TGI deployment and its helper scripts have been
retired from this repository.

What changed:
- The previous `serve/` scripts for starting and checking a `tgi-med42`
  container on `guell` are no longer part of the active stack.
- The current `rag_service` generation flow uses the configured local/cloud LLM
  providers from `rag_service/src/config.py`.
- The default local setup is Ollama-based, as documented in
  `rag_service/README.md`.

Current reference:
- For running and developing the RAG service, use `rag_service/README.md`.
- For backend setup and integration, use the main project docs in this repo.

Legacy note:
- If you need the retired Gaudi/TGI deployment details, recover them from git
  history rather than this working tree.
