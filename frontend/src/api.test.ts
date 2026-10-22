import { afterEach, expect, test, vi } from "vitest";
import { request, RequestError } from "./api";

afterEach(() => vi.unstubAllGlobals());

test("JSON requests preserve identity and payload", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(new Response('{"id":"run-1"}', { status: 202 }));
  vi.stubGlobal("fetch", fetch);
  await expect(
    request(
      "/api/sync",
      { access: "signed-token", tenant: "BANK001", username: "demo" },
      { force: true },
    ),
  ).resolves.toEqual({ id: "run-1" });
  expect(fetch).toHaveBeenCalledWith(
    "/api/sync",
    expect.objectContaining({
      method: "POST",
      headers: expect.objectContaining({
        Authorization: "Bearer signed-token",
      }),
      body: '{"force":true}',
    }),
  );
});

test.each([
  [401, { detail: "Expired token" }, "Expired token"],
  [409, { title: "Snapshot changed" }, "Snapshot changed"],
  [503, null, "HTTP 503"],
  [400, { detail: { field: "invalid" } }, "HTTP 400"],
])(
  "HTTP %s JSON errors keep their status and a readable message",
  async (status, data, message) => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify(data), { status })),
    );
    const error = await request("/api/data").catch((error) => error);
    if (!(error instanceof RequestError))
      throw new Error("Expected a RequestError");
    expect(error.status).toBe(status);
    expect(error.message).toContain(message);
  },
);

test.each([502, 200])(
  "non-JSON HTTP %s responses produce an actionable error",
  async (status) => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response("<html>gateway failure</html>", { status }),
        ),
    );
    const error = await request("/api/data").catch((error) => error);
    if (!(error instanceof RequestError))
      throw new Error("Expected a RequestError");
    expect(error.status).toBe(status);
    expect(error.message).toContain("yeniden deneyin");
    expect(error.message).not.toContain("<html>");
  },
);
