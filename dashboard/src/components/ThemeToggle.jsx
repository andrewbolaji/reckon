const STORAGE_KEY = "reckon-theme";

export function getInitialTheme() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark") return stored;
  } catch {}
  if (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
  ) {
    return "dark";
  }
  return "light";
}

export function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {}
}

export default function ThemeToggle({ theme, onToggle }) {
  const next = theme === "dark" ? "light" : "dark";

  return (
    <button
      className="theme-toggle"
      onClick={onToggle}
      aria-label={`Switch to ${next} mode`}
      type="button"
    >
      {theme === "dark" ? (
        <svg viewBox="0 0 20 20" fill="currentColor">
          <path d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4.22 1.78a1 1 0 011.41 0l.71.71a1 1 0 11-1.42 1.42l-.7-.71a1 1 0 010-1.42zM18 9a1 1 0 110 2h-1a1 1 0 110-2h1zM3 9a1 1 0 110 2H2a1 1 0 110-2h1zm13.93 6.22a1 1 0 010 1.42l-.71.7a1 1 0 11-1.42-1.41l.71-.71a1 1 0 011.42 0zM4.78 15.22a1 1 0 010 1.42l-.71.7a1 1 0 01-1.41-1.41l.7-.71a1 1 0 011.42 0zM10 16a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zm0-2a4 4 0 100-8 4 4 0 000 8z" />
        </svg>
      ) : (
        <svg viewBox="0 0 20 20" fill="currentColor">
          <path d="M17.293 13.293A8 8 0 016.707 2.707a8.003 8.003 0 1010.586 10.586z" />
        </svg>
      )}
    </button>
  );
}
