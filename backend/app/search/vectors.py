from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.config import get_settings
from app.search.embed import cosine, embed_text

logger = logging.getLogger("skillradar.vector")

COLLECTION = "skillradar_repos"
DIM = 64


class VectorStore(Protocol):
    backend: str

    def upsert(self, point_id: int | str, text: str, payload: dict[str, Any] | None = None) -> None: ...
    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]: ...
    def count(self) -> int: ...
    def status(self) -> dict[str, Any]: ...


def _point_key(point_id: int | str) -> str:
    return str(point_id)


class MemoryVectorStore:
    backend = "memory"

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.points: dict[str, dict[str, Any]] = {}
        self._load()

    def connected(self) -> bool:
        return True

    def upsert(self, point_id: int | str, text: str, payload: dict[str, Any] | None = None) -> None:
        key = _point_key(point_id)
        item = {
            "id": key,
            "vector": embed_text(text),
            "payload": {**(payload or {}), "text": text[:4000]},
        }
        with self._lock:
            self.points[key] = item
            self._save_locked()

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        qv = embed_text(query)
        with self._lock:
            ranked = []
            q_low = (query or "").lower()
            for item in self.points.values():
                score = cosine(qv, item["vector"])
                blob = str((item.get("payload") or {}).get("text") or "").lower()
                if q_low and q_low in blob:
                    score = max(score, 0.62)
                ranked.append(
                    {
                        "id": item["id"],
                        "score": round(float(score), 4),
                        "payload": item.get("payload") or {},
                    }
                )
        ranked.sort(key=lambda x: x["score"], reverse=True)
        return [r for r in ranked[: max(limit, 1)] if r["score"] > 0.05]

    def count(self) -> int:
        with self._lock:
            return len(self.points)

    def status(self) -> dict[str, Any]:
        return {"backend": self.backend, "connected": True, "points": self.count()}

    def _load(self) -> None:
        if self.path is None or not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("vector cache unreadable: %s", exc)
            return
        if not isinstance(raw, dict):
            return
        for key, item in raw.items():
            if isinstance(item, dict) and item.get("vector"):
                self.points[str(key)] = item

    def _save_locked(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.points), encoding="utf-8")
        tmp.replace(self.path)


class QdrantVectorStore:
    backend = "qdrant"

    def __init__(self, url: str) -> None:
        self.url = url.rstrip("/")
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        with httpx.Client(timeout=5.0) as client:
            ping = client.get(f"{self.url}/collections/{COLLECTION}")
            if ping.status_code == 200:
                return
            resp = client.put(
                f"{self.url}/collections/{COLLECTION}",
                json={"vectors": {"size": DIM, "distance": "Cosine"}},
            )
            if resp.status_code not in {200, 201, 409}:
                raise RuntimeError(f"qdrant create collection failed: {resp.status_code} {resp.text[:200]}")

    def upsert(self, point_id: int | str, text: str, payload: dict[str, Any] | None = None) -> None:
        raw_id: int | str = point_id
        if isinstance(point_id, str) and point_id.isdigit():
            raw_id = int(point_id)
        body = {
            "points": [
                {
                    "id": raw_id,
                    "vector": embed_text(text),
                    "payload": {**(payload or {}), "text": text[:4000]},
                }
            ]
        }
        with httpx.Client(timeout=8.0) as client:
            resp = client.put(f"{self.url}/collections/{COLLECTION}/points?wait=true", json=body)
            resp.raise_for_status()

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        payload = {"vector": embed_text(query), "limit": max(limit, 1), "with_payload": True}
        with httpx.Client(timeout=8.0) as client:
            resp = client.post(f"{self.url}/collections/{COLLECTION}/points/search", json=payload)
            resp.raise_for_status()
            data = resp.json()
        rows = data.get("result") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            return []
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            out.append(
                {
                    "id": row.get("id"),
                    "score": round(float(row.get("score") or 0), 4),
                    "payload": row.get("payload") or {},
                }
            )
        return [r for r in out if r["id"] is not None]

    def count(self) -> int:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{self.url}/collections/{COLLECTION}")
            resp.raise_for_status()
            body = resp.json()
        result = body.get("result") if isinstance(body, dict) else None
        if not isinstance(result, dict):
            return 0
        pts = result.get("points_count") or result.get("vectors_count") or 0
        try:
            return int(pts)
        except (TypeError, ValueError):
            return 0

    def status(self) -> dict[str, Any]:
        try:
            n = self.count()
            return {"backend": self.backend, "connected": True, "points": n}
        except Exception as exc:
            logger.warning("qdrant status failed: %s", exc)
            return {"backend": self.backend, "connected": False, "points": 0, "error": str(exc)}


_store: VectorStore | None = None


def vector_cache_path() -> Path:
    settings = get_settings()
    custom = (settings.vector_store_path or "").strip()
    if custom:
        return Path(custom)
    return Path(settings.clone_dir).resolve().parent / "vectors.json"


def get_vector_store() -> VectorStore:
    global _store
    if _store is not None:
        return _store
    _store = build_vector_store()
    return _store


def reset_vector_store() -> None:
    global _store
    _store = None
    path = vector_cache_path()
    if path.is_file():
        path.unlink(missing_ok=True)


def build_vector_store() -> VectorStore:
    settings = get_settings()
    url = (settings.qdrant_url or "").strip()
    if url:
        try:
            store = QdrantVectorStore(url)
            logger.info("vector store: qdrant %s", url)
            return store
        except Exception as exc:
            logger.warning("qdrant unavailable (%s), falling back to memory", exc)
    logger.info("vector store: memory")
    return MemoryVectorStore(vector_cache_path())
