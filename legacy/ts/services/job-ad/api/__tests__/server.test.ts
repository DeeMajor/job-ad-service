import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { AddressInfo } from "node:net";
import { createServer } from "../server.js";
import { GOOD_AD, BAD_AD } from "../../metrics/__tests__/fixtures.js";

// No Anthropic calls in these tests: judge=false paths and validation only. A dummy client avoids reading credentials.
const server = createServer({ client: {} as any });
let base = "";
beforeAll(async () => { await new Promise<void>((r) => server.listen(0, r)); base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`; });
afterAll(() => new Promise<void>((r) => server.close(() => r())));
const post = (path: string, body: unknown) => fetch(base + path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

describe("job-ad service", () => {
  it("healthz reports versions", async () => {
    const r = await fetch(base + "/healthz"); const j = await r.json();
    expect(r.status).toBe(200); expect(j.ok).toBe(true); expect(j.versions.spec).toMatch(/^\d+\.\d+\.\d+$/); expect(r.headers.get("x-request-id")).toBeTruthy();
  });
  it("serves the metric spec", async () => {
    const j = await (await fetch(base + "/v1/spec")).json();
    expect(j.metrics.length).toBeGreaterThan(30); expect(j.gates).toContain("honesty.grounding");
  });
  it("scores an ad deterministically when judge=false", async () => {
    const r = await post("/v1/scores", { ad: GOOD_AD, context: { jurisdiction: "ZA", designated_employer: true }, judge: false });
    const j = await r.json();
    expect(r.status).toBe(200); expect(j.scorecard.gates_passed).toBe(true); expect(j.scorecard.composite).toBeGreaterThan(80); expect(j.meta.judge).toBeNull();
    const bad = await (await post("/v1/scores", { ad: BAD_AD, judge: false })).json();
    expect(bad.scorecard.verdict).toBe("blocked");
  });
  it("rejects a malformed brief with field paths", async () => {
    const r = await post("/v1/drafts", { brief: { title: "", company: {} } });
    const j = await r.json();
    expect(r.status).toBe(400); expect(j.error).toBe("validation");
    expect(j.issues.map((i: any) => i.path.join("."))).toEqual(expect.arrayContaining(["brief.title", "brief.company.name"]));
  });
  it("404 and 405 and bad JSON", async () => {
    expect((await fetch(base + "/nope")).status).toBe(404);
    expect((await fetch(base + "/v1/scores")).status).toBe(405);
    const r = await fetch(base + "/v1/scores", { method: "POST", headers: { "content-type": "application/json" }, body: "{not json" });
    expect(r.status).toBe(400);
  });
});
