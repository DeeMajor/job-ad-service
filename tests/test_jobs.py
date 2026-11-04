import time

from fastapi.testclient import TestClient

from job_ad.api import app as appmod
from job_ad.api.jobs import JobRunner, SpendCap, Store

client = TestClient(appmod.app)
BRIEF = {"title": "Clerk", "company": {"name": "Acme"}, "responsibilities": ["Capture invoices in Sage"], "must_have": ["Sage"]}


def test_store_memory_roundtrip_and_spend():
    s = Store(None); assert s.backend == "memory"
    s.put("jobad:job:x", {"a": 1}); assert s.get("jobad:job:x") == {"a": 1}
    cap = SpendCap(s, cap_usd=1.0)
    assert cap.allow(); cap.add(0.6); assert cap.allow(); cap.add(0.5); assert not cap.allow()


def test_runner_runs_work_and_records_result():
    s = Store(None); r = JobRunner(s, SpendCap(s), max_workers=1)
    job = r.submit({"x": 1}, lambda: {"ok": True})
    for _ in range(50):
        if r.get(job["job_id"])["status"] == "done":
            break
        time.sleep(0.05)
    j = r.get(job["job_id"]); assert j["status"] == "done" and j["result"] == {"ok": True}
    def boom():
        raise RuntimeError("nope")
    job2 = r.submit({}, boom)
    for _ in range(50):
        if r.get(job2["job_id"])["status"] == "failed":
            break
        time.sleep(0.05)
    assert r.get(job2["job_id"])["status"] == "failed" and "nope" in r.get(job2["job_id"])["error"]


def test_recover_marks_inflight_failed():
    s = Store(None); s.put("jobad:job:old", {"job_id": "old", "status": "running", "created_at": 0})
    JobRunner(s, SpendCap(s), max_workers=1)
    assert s.get("jobad:job:old")["status"] == "failed" and "restarted" in s.get("jobad:job:old")["error"]


def test_metrics_and_health_expose_spend():
    assert client.get("/metrics").status_code == 200 and b"jobad_drafts_total" in client.get("/metrics").content
    h = client.get("/healthz").json(); assert "spend" in h and h["features"]["jobs_store"] == "memory"


def test_job_endpoints_validate_and_404():
    assert client.get("/v1/draft-jobs/does-not-exist").status_code == 404
    r = client.post("/v1/draft-jobs", json={"brief": {"title": "", "company": {}}}); assert r.status_code == 422


def test_spend_cap_refuses_drafts(monkeypatch):
    monkeypatch.setattr(appmod.spend_cap, "cap", 0.01); appmod.spend_cap.add(5.0)
    r = client.post("/v1/drafts", json={"brief": BRIEF}); assert r.status_code == 429 and r.json()["detail"]["error"] == "daily_spend_cap"
    r = client.post("/v1/draft-jobs", json={"brief": BRIEF}); assert r.status_code == 429
    monkeypatch.setattr(appmod.spend_cap, "cap", 0)  # 0 = no cap
    assert appmod.spend_cap.allow()
