import { describe, it, expect } from "vitest";
import {
  describeFreshness,
  formatAge,
  WARN_AFTER_HOURS,
  STALE_AFTER_HOURS,
} from "./FreshnessBanner.jsx";

const payload = (status, age_hours, sources = []) => ({
  status,
  age_hours,
  sources,
});

describe("formatAge", () => {
  it("reads naturally under an hour", () => {
    expect(formatAge(0.4)).toBe("under an hour");
  });

  it("singularises one hour", () => {
    expect(formatAge(1)).toBe("1 hour");
    expect(formatAge(2)).toBe("2 hours");
  });

  it("switches to days once hours stop being useful", () => {
    expect(formatAge(51)).toBe("2 days");
    expect(formatAge(170)).toBe("7 days");
  });

  it("says unknown rather than guessing when nothing has loaded", () => {
    expect(formatAge(null)).toBe("unknown");
  });
});

describe("describeFreshness", () => {
  it("renders nothing while the fetch is in flight", () => {
    // Returning null keeps a banner from flashing before the data arrives.
    expect(describeFreshness(null)).toBeNull();
    expect(describeFreshness(undefined)).toBeNull();
    expect(describeFreshness({})).toBeNull();
  });

  it("is quiet when the data is current", () => {
    const state = describeFreshness(payload("fresh", 2));
    expect(state.level).toBe("fresh");
    expect(state.title).toBe("Data is current, loaded 2 hours ago");
  });

  it("warns past 24 hours without claiming the data is wrong", () => {
    const state = describeFreshness(
      payload("warn", 31, [
        { name: "aria_calls", status: "fresh" },
        { name: "stripe_payments", status: "warn" },
      ]),
    );
    expect(state.level).toBe("warn");
    expect(state.title).toBe("Data is 31 hours old");
    expect(state.detail).toContain("stripe_payments");
  });

  it("says plainly that the numbers are not current past 48 hours", () => {
    const state = describeFreshness(
      payload("stale", 51, [
        { name: "aria_calls", status: "fresh" },
        { name: "stripe_payments", status: "stale" },
      ]),
    );
    expect(state.level).toBe("stale");
    expect(state.title).toContain("stale");
    expect(state.detail).toContain("not current");
    expect(state.detail).toContain("stripe_payments");
  });

  it("names the worst source, not the first one", () => {
    const state = describeFreshness(
      payload("stale", 51, [
        { name: "aria_calls", status: "warn" },
        { name: "jobs", status: "stale" },
      ]),
    );
    expect(state.detail).toContain("jobs");
    expect(state.detail).not.toContain("aria_calls");
  });

  it("still reports staleness when no source detail came back", () => {
    const state = describeFreshness(payload("stale", 60));
    expect(state.level).toBe("stale");
    expect(state.detail).toBe("These numbers are not current.");
  });

  it("uses the same thresholds as the copilot and the trust gate", () => {
    expect(WARN_AFTER_HOURS).toBe(24);
    expect(STALE_AFTER_HOURS).toBe(48);
  });
});
