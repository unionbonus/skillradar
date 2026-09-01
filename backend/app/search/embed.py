from __future__ import annotations

import hashlib
import math
import re

DIM = 64
_TOKEN = re.compile(r"[a-z0-9_\-]+", re.I)


def embed_text(text: str) -> list[float]:
    """Deterministic hashed n-gram embedding. No model download required."""
    blob = (text or "").lower()
    vec = [0.0] * DIM
    if not blob.strip():
        return vec
    padded = f"  {blob}  "
    for i in range(len(padded) - 2):
        gram = padded[i : i + 3]
        digest = hashlib.md5(gram.encode("utf-8")).digest()
        vec[digest[0] % DIM] += 1.0 + digest[1] / 255.0
    for tok in _TOKEN.findall(blob):
        digest = hashlib.md5(tok.encode("utf-8")).digest()
        vec[digest[0] % DIM] += 2.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def cosine(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    return float(sum(a[i] * b[i] for i in range(n)))
