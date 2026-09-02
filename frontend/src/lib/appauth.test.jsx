import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { AppAuthProvider, useAuth } from "./appauth";
import { api, tokenStorage, refreshToken } from "./api";

vi.mock("./api", async () => {
  const actual = await vi.importActual("./api");
  return {
    ...actual,
    api: { get: vi.fn(), post: vi.fn() },
    refreshToken: vi.fn(),
  };
});

function Probe() {
  const { user, loading } = useAuth();
  if (loading) return <div>loading</div>;
  return <div>{user ? `logged in as ${user.email}` : "logged out"}</div>;
}

function renderProvider() {
  return render(
    <AppAuthProvider>
      <Probe />
    </AppAuthProvider>,
  );
}

describe("AppAuthProvider mount behavior", () => {
  beforeEach(() => {
    tokenStorage.clear();
    api.get.mockReset();
    api.post.mockReset();
    refreshToken.mockReset();
  });

  it("attempts a silent refresh via the httpOnly cookie when no in-memory token exists", async () => {
    // Simulates a page reload: the in-memory access token is gone, but the
    // refresh cookie is still valid.
    refreshToken.mockResolvedValue(true);
    api.get.mockResolvedValue({ email: "restored@example.com" });

    renderProvider();

    await waitFor(() => {
      expect(screen.getByText("logged in as restored@example.com")).toBeInTheDocument();
    });
    expect(refreshToken).toHaveBeenCalled();
  });

  it("ends up logged out, without ever calling /api/auth/me/, when the silent refresh fails", async () => {
    refreshToken.mockResolvedValue(false);

    renderProvider();

    await waitFor(() => {
      expect(screen.getByText("logged out")).toBeInTheDocument();
    });
    expect(api.get).not.toHaveBeenCalled();
  });

  it("skips the silent refresh when an in-memory access token is already present", async () => {
    tokenStorage.set("already-have-one");
    api.get.mockResolvedValue({ email: "existing@example.com" });

    renderProvider();

    await waitFor(() => {
      expect(screen.getByText("logged in as existing@example.com")).toBeInTheDocument();
    });
    expect(refreshToken).not.toHaveBeenCalled();
  });
});
