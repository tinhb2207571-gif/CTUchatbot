"""Chia sẻ model SentenceTransformer giữa chat và importer trong một process."""

from threading import Lock

_models = {}
_lock = Lock()


def get_sentence_transformer(name, device, *, local_files_only=False):
    key = (name, device, local_files_only)
    with _lock:
        if key not in _models:
            from sentence_transformers import SentenceTransformer

            _models[key] = SentenceTransformer(
                name, device=device, trust_remote_code=True,
                local_files_only=local_files_only,
            )
        return _models[key]
