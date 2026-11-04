# Optional DeepAgent reviewer

The active BioForge RAG path is **LangGraph** because the production Python
environment is 3.10 and `deepagents` requires Python >= 3.11. This worker is an
optional, separately installed reviewer.

```bash
python3.12 -m venv .venv-deepagent
.venv-deepagent/bin/pip install -r rag_worker/requirements.txt
BIOFORGE_DEEPAGENT_PYTHON="$PWD/.venv-deepagent/bin/python" \
  .venv-deepagent/bin/python rag_worker/deep_review.py < record.json
```

It does not expose filesystem or shell access; it receives one JSON record on
stdin and returns a JSON review. It is **not** imported by the main app and is
not required for normal operation.
