import { describe, it, expect, beforeEach } from "vitest";
import { getInitialTheme, applyTheme } from "./ThemeToggle.jsx";

// jsdom lacks matchMedia
function stubMatchMedia(darkMode = false) {
  window.matchMedia = (query) => ({
    matches: darkMode && query === "(prefers-color-scheme: dark)",
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  });
}

describe("ThemeToggle", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    stubMatchMedia(false);
  });

  it("defaults to light when no stored preference and system is light", () => {
    // jsdom matchMedia defaults to not matching dark
    expect(getInitialTheme()).toBe("light");
  });

  it("returns stored theme from localStorage", () => {
    localStorage.setItem("reckon-theme", "dark");
    expect(getInitialTheme()).toBe("dark");

    localStorage.setItem("reckon-theme", "light");
    expect(getInitialTheme()).toBe("light");
  });

  it("ignores invalid localStorage values", () => {
    localStorage.setItem("reckon-theme", "blue");
    expect(getInitialTheme()).toBe("light");
  });

  it("applyTheme sets data-theme on documentElement", () => {
    applyTheme("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");

    applyTheme("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("applyTheme persists to localStorage", () => {
    applyTheme("dark");
    expect(localStorage.getItem("reckon-theme")).toBe("dark");

    applyTheme("light");
    expect(localStorage.getItem("reckon-theme")).toBe("light");
  });

  it("round-trips: apply then read back", () => {
    applyTheme("dark");
    expect(getInitialTheme()).toBe("dark");

    applyTheme("light");
    expect(getInitialTheme()).toBe("light");
  });
});
