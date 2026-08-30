import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { api, tokenStorage, refreshToken } from "./api";

function jsonResponse(body, { ok = true, status = 200 } = {}) {
  return {
    ok,
    status,
    text: async () => JSON.stringify(body),
    json: async () => body,
  };
}

describe("api.js", () => {
  beforeEach(() => {
    tokenStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns parsed data on a successful response", async () => {
    global.fetch = vi.fn().mockResolvedValue(jsonResponse({ hello: "world" }));
    const data = await api.get("/api/whatever/");
    expect(data).toEqual({ hello: "world" });
  });

  it("prefers data.detail as the error message", async () => {
    global.fetch = vi.fn().mockResolvedValue(jsonResponse({ detail: "Nope." }, { ok: false, status: 400 }));
    await expect(api.get("/api/whatever/")).rejects.toThrow("Nope.");
  });

  it("flattens a DRF field-error dict into one message", async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValue(jsonResponse({ email: ["Already in use."] }, { ok: false, status: 400 }));
    await expect(api.get("/api/whatever/")).rejects.toThrow("Already in use.");
  });

  it("falls back to a generic message for a non-JSON error body", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      text: async () => "<html>Internal Server Error</html>",
    });
    await expect(api.get("/api/whatever/")).rejects.toThrow("Request failed (500)");
  });

  it("normalizes a network failure via safeFetch", async () => {
    global.fetch = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(api.get("/api/whatever/")).rejects.toThrow("Network error");
  });

  it("retries once after a silent refresh on 401, then succeeds", async () => {
    tokenStorage.set("stale-token");
    global.fetch = vi
      .fn()
      // Original request: 401.
      .mockResolvedValueOnce({ ok: false, status: 401, text: async () => "" })
      // refreshToken()'s call to /api/auth/token/refresh/.
      .mockResolvedValueOnce(jsonResponse({ access: "fresh-token" }))
      // Retried original request: succeeds.
      .mockResolvedValueOnce(jsonResponse({ ok: true }));

    const data = await api.get("/api/protected/");
    expect(data).toEqual({ ok: true });
    expect(tokenStorage.get()).toBe("fresh-token");
    expect(global.fetch).toHaveBeenCalledTimes(3);
  });

  it("does not retry when the silent refresh itself fails", async () => {
    tokenStorage.set("stale-token");
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 401, text: async () => "" })
      .mockResolvedValueOnce({ ok: false, status: 401, text: async () => "" }); // refresh fails too

    await expect(api.get("/api/protected/")).rejects.toThrow();
    expect(tokenStorage.get()).toBeNull();
  });

  it("refreshToken() sends credentials so the httpOnly cookie is included", async () => {
    global.fetch = vi.fn().mockResolvedValue(jsonResponse({ access: "new-token" }));
    const ok = await refreshToken();
    expect(ok).toBe(true);
    expect(tokenStorage.get()).toBe("new-token");
    const [, options] = global.fetch.mock.calls[0];
    expect(options.credentials).toBe("include");
  });
});
