from __future__ import annotations

import hashlib
import hmac
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, urlparse

import httpx

from app.config import get_settings, object_dir_path

logger = logging.getLogger("skillradar.objects")


class ObjectStore(Protocol):
    backend: str

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str: ...
    def get(self, key: str) -> bytes | None: ...
    def status(self) -> dict: ...


def _safe_key(key: str) -> str:
    cleaned = (key or "").strip().lstrip("/")
    if not cleaned or ".." in cleaned.split("/"):
        raise ValueError("invalid object key")
    return cleaned


class LocalObjectStore:
    backend = "local"

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        rel = _safe_key(key)
        path = self.root / rel
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            meta = path.with_suffix(path.suffix + ".ctype")
            meta.write_text(content_type, encoding="utf-8")
        return rel

    def get(self, key: str) -> bytes | None:
        path = self.root / _safe_key(key)
        if not path.is_file():
            return None
        return path.read_bytes()

    def status(self) -> dict:
        n = 0
        if self.root.exists():
            n = sum(1 for p in self.root.rglob("*") if p.is_file() and not p.name.endswith(".ctype"))
        return {"backend": self.backend, "connected": True, "objects": n, "root": str(self.root)}


def aws_v4_headers(
    method: str,
    url: str,
    body: bytes,
    access: str,
    secret: str,
    content_type: str,
) -> dict[str, str]:
    parsed = urlparse(url)
    host = parsed.netloc
    path = parsed.path or "/"
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body).hexdigest()
    canonical_headers = (
        f"content-type:{content_type}\n"
        f"host:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"
    canonical_request = f"{method}\n{path}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    region = "us-east-1"
    scope = f"{datestamp}/{region}/s3/aws4_request"
    string_to_sign = (
        "AWS4-HMAC-SHA256\n"
        f"{amz_date}\n{scope}\n{hashlib.sha256(canonical_request.encode()).hexdigest()}"
    )

    def _sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    k_date = _sign(("AWS4" + secret).encode("utf-8"), datestamp)
    k_region = hmac.new(k_date, region.encode(), hashlib.sha256).digest()
    k_service = hmac.new(k_region, b"s3", hashlib.sha256).digest()
    k_signing = hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()
    signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()
    return {
        "Host": host,
        "Content-Type": content_type,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={access}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
    }


class MinioObjectStore:
    backend = "minio"

    def __init__(self, endpoint: str, access: str, secret: str, bucket: str, secure: bool) -> None:
        ep = endpoint.strip()
        if ep.startswith("http://") or ep.startswith("https://"):
            self.base = ep.rstrip("/")
        else:
            scheme = "https" if secure else "http"
            self.base = f"{scheme}://{ep}"
        self.access = access
        self.secret = secret
        self.bucket = bucket.strip() or "skillradar"
        self._ensure_bucket()

    def _object_url(self, key: str) -> str:
        encoded = "/".join(quote(part, safe="") for part in _safe_key(key).split("/"))
        return f"{self.base}/{self.bucket}/{encoded}"

    def _ensure_bucket(self) -> None:
        url = f"{self.base}/{self.bucket}"
        headers = aws_v4_headers("PUT", url, b"", self.access, self.secret, "application/octet-stream")
        with httpx.Client(timeout=8.0) as client:
            resp = client.put(url, headers=headers, content=b"")
            if resp.status_code not in {200, 201, 204, 409}:
                raise RuntimeError(f"minio bucket failed: {resp.status_code} {resp.text[:200]}")

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        rel = _safe_key(key)
        url = self._object_url(rel)
        headers = aws_v4_headers("PUT", url, data, self.access, self.secret, content_type)
        with httpx.Client(timeout=20.0) as client:
            resp = client.put(url, headers=headers, content=data)
            resp.raise_for_status()
        return rel

    def get(self, key: str) -> bytes | None:
        url = self._object_url(key)
        headers = aws_v4_headers("GET", url, b"", self.access, self.secret, "application/octet-stream")
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.content

    def status(self) -> dict:
        url = f"{self.base}/{self.bucket}"
        headers = aws_v4_headers("GET", url, b"", self.access, self.secret, "application/octet-stream")
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(url, headers=headers)
            ok = resp.status_code < 500
            return {"backend": self.backend, "connected": ok, "bucket": self.bucket}
        except Exception as exc:
            logger.warning("minio ping failed: %s", exc)
            return {"backend": self.backend, "connected": False, "bucket": self.bucket, "error": str(exc)}


_store: ObjectStore | None = None


def get_object_store() -> ObjectStore:
    global _store
    if _store is not None:
        return _store
    _store = build_object_store()
    return _store


def reset_object_store() -> None:
    global _store
    _store = None


def build_object_store() -> ObjectStore:
    settings = get_settings()
    endpoint = (settings.minio_endpoint or "").strip()
    if endpoint and settings.minio_access_key and settings.minio_secret_key:
        try:
            store = MinioObjectStore(
                endpoint,
                settings.minio_access_key,
                settings.minio_secret_key,
                settings.minio_bucket,
                settings.minio_secure,
            )
            logger.info("object store: minio %s", endpoint)
            return store
        except Exception as exc:
            logger.warning("minio unavailable (%s), falling back to local", exc)
    logger.info("object store: local")
    return LocalObjectStore(object_dir_path(settings))


def store_prd(repo_id: int, markdown: str) -> str:
    key = f"prd/{int(repo_id)}.md"
    get_object_store().put(key, (markdown or "").encode("utf-8"), "text/markdown")
    return key


def store_bytes(key: str, data: bytes, content_type: str = "text/markdown") -> str:
    return get_object_store().put(key, data, content_type)
