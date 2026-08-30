import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import VerifyEmail from "./verifyemail";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({ api: { post: vi.fn() } }));

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/verify-email?email=player%40example.com"]}>
      <VerifyEmail />
    </MemoryRouter>,
  );
}

describe("VerifyEmail resend", () => {
  beforeEach(() => {
    api.post.mockReset();
  });

  it("shows an error and does not claim success when the resend request fails", async () => {
    api.post.mockRejectedValue(new Error("Too many requests. Try again later."));
    renderPage();

    fireEvent.click(screen.getByText(/resend code/i));

    await waitFor(() => {
      expect(screen.getByText("Too many requests. Try again later.")).toBeInTheDocument();
    });
    expect(screen.queryByText(/a new code has been sent/i)).not.toBeInTheDocument();
  });

  it("shows the success message when the resend request succeeds", async () => {
    api.post.mockResolvedValue({ detail: "ok" });
    renderPage();

    fireEvent.click(screen.getByText(/resend code/i));

    await waitFor(() => {
      expect(screen.getByText(/a new code has been sent/i)).toBeInTheDocument();
    });
  });
});
