"""Async draft jobs, spend cap and metrics.

Job state lives in Redis when REDIS_URL is set (survives API restarts; TTL 24 h), else in memory (local dev).
Drafting runs in a bounded thread pool inside the API process; on startup any job still 'running' is marked failed
("service restarted") so clients re-submit rather than wait forever. A daily spend cap (USD, estimated from token
usage) refuses new drafts with 429 once reached. Prometheus metrics are exposed by the app at /metrics.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any, Callable, Optional

from prometheus_client import Counter, Gauge, Histogram

log = logging.getLogger("job_ad.jobs")

JOB_TTL_S = int(os.environ.get("JOB_TTL_S", 24 * 3600))
MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT_DRAFTS", "4"))
DAILY_CAP_USD = float(os.environ.get("DAILY_SPEND_CAP_USD", "20"))

DRAFTS = Counter("jobad_drafts_total", "Draft requests completed", ["status", "mode"])
JUDGE_CALLS = Counter("jobad_judge_calls_total", "Judge calls")
TOKENS = Counter("jobad_tokens_total", "Model tokens", ["model", "kind"])
SPEND = Counter("jobad_spend_usd_total", "Estimated spend in USD", ["model"])
LATENCY = Histogram("jobad_draft_latency_seconds", "End-to-end draft latency", buckets=(5, 10, 15, 20, 30, 45, 60, 90, 120))
JOBS_ACTIVE = Gauge("jobad_jobs_active", "Draft jobs queued or running")
CAP_REFUSALS = Counter("jobad_cap_refusals_total", "Requests refused by the daily spend cap")


class Store:
    """Redis-backed when available, else a process-local dict. Same interface either way."""

    def __init__(self, url: Optional[str]):
        self.r = None
        self._mem: dict[str, str] = {}
        self._lock = threading.Lock()
        if url:
            import redis
            self.r = redis.Redis.from_url(url, decode_responses=True)
            self.r.ping()

    @property
    def backend(self) -> str:
        return "redis" if self.r is not None else "memory"

    def put(self, key: str, value: dict, ttl: int = JOB_TTL_S) -> None:
        s = json.dumps(value, default=str)
        if self.r is not None:
            self.r.set(key, s, ex=ttl)
        else:
            with self._lock:
                self._mem[key] = s

    def get(self, key: str) -> Optional[dict]:
        s = self.r.get(key) if self.r is not None else self._mem.get(key)
        return json.loads(s) if s else None

    def incr_float(self, key: str, amount: float, ttl: int) -> float:
        if self.r is not None:
            v = self.r.incrbyfloat(key, amount)
            self.r.expire(key, ttl)
            return float(v)
        with self._lock:
            v = float(self._mem.get(key) or 0) + amount
            self._mem[key] = str(v)
            return v

    def keys(self, pattern: str) -> list[str]:
        if self.r is not None:
            return list(self.r.scan_iter(pattern))
        return [k for k in list(self._mem) if k.startswith(pattern.rstrip("*"))]


class SpendCap:
    def __init__(self, store: Store, cap_usd: float = DAILY_CAP_USD):
        self.store, self.cap = store, cap_usd

    def _key(self) -> str:
        return f"jobad:spend:{date.today().isoformat()}"

    def today(self) -> float:
        return float(self.store.get(self._key()) or 0) if self.store.r is None else float(self.store.r.get(self._key()) or 0)

    def allow(self) -> bool:
        return self.cap <= 0 or self.today() < self.cap

    def add(self, usd: float) -> float:
        return self.store.incr_float(self._key(), usd, ttl=3 * 24 * 3600)


class JobRunner:
    """Runs drafting callables in a bounded pool and records job state."""

    def __init__(self, store: Store, cap: SpendCap, max_workers: int = MAX_CONCURRENT):
        self.store, self.cap = store, cap
        self.pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="draft")
        self.recover()

    def recover(self) -> None:
        for k in self.store.keys("jobad:job:*"):
            j = self.store.get(k)
            if j and j.get("status") in ("queued", "running"):
                j.update(status="failed", error="service restarted while the job was in progress; re-submit", finished_at=time.time())
                self.store.put(k, j)

    def submit(self, request: dict, work: Callable[[], dict], callback_url: Optional[str] = None) -> dict:
        job_id = str(uuid.uuid4())
        job = {"job_id": job_id, "status": "queued", "created_at": time.time(), "started_at": None, "finished_at": None, "request": request, "callback_url": callback_url, "result": None, "error": None}
        self.store.put(f"jobad:job:{job_id}", job)
        JOBS_ACTIVE.inc()
        self.pool.submit(self._run, job_id, work)
        return job

    def _run(self, job_id: str, work: Callable[[], dict]) -> None:
        key = f"jobad:job:{job_id}"
        job = self.store.get(key) or {}
        job.update(status="running", started_at=time.time()); self.store.put(key, job)
        try:
            result = work()
            job.update(status="done", result=result, finished_at=time.time())
        except Exception as e:  # noqa: BLE001
            log.exception("job %s failed", job_id)
            job.update(status="failed", error=str(e)[:500], finished_at=time.time())
        finally:
            JOBS_ACTIVE.dec()
        self.store.put(key, job)
        if job.get("callback_url"):
            self._callback(job)

    def _callback(self, job: dict) -> None:
        try:
            import httpx
            httpx.post(job["callback_url"], json={"job_id": job["job_id"], "status": job["status"], "result": job.get("result"), "error": job.get("error")}, timeout=15)
        except Exception as e:  # noqa: BLE001
            log.warning("callback for job %s failed: %s", job["job_id"], e)

    def get(self, job_id: str) -> Optional[dict]:
        return self.store.get(f"jobad:job:{job_id}")
