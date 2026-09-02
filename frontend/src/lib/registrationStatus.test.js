import { describe, it, expect } from "vitest";
import { canCheckIn, TERMINAL_NEGATIVE_STATUSES } from "./registrationStatus";

function reg(overrides = {}) {
  return { status: "approved", checked_in: false, ...overrides };
}

describe("canCheckIn", () => {
  it("is false for a missing registration", () => {
    expect(canCheckIn(null, false)).toBe(false);
  });

  it("is false once already checked in", () => {
    expect(canCheckIn(reg({ checked_in: true }), false)).toBe(false);
  });

  it.each(TERMINAL_NEGATIVE_STATUSES)("is false for a %s registration, fee or not", (status) => {
    expect(canCheckIn(reg({ status }), false)).toBe(false);
    expect(canCheckIn(reg({ status }), true)).toBe(false);
  });

  it("is true for a pending, no-fee registration", () => {
    expect(canCheckIn(reg({ status: "pending" }), false)).toBe(true);
  });

  it("is false for a fee tournament until the registration is approved", () => {
    expect(canCheckIn(reg({ status: "pending" }), true)).toBe(false);
    expect(canCheckIn(reg({ status: "approved" }), true)).toBe(true);
  });

  it("is true for an approved, no-fee registration", () => {
    expect(canCheckIn(reg({ status: "approved" }), false)).toBe(true);
  });
});
