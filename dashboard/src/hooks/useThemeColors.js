import { useState, useEffect } from "react";

const TOKEN_NAMES = [
  "--accent",
  "--accent-2",
  "--good",
  "--warn",
  "--bad",
  "--ink-3",
  "--faint",
  "--line",
  "--line-2",
  "--card",
  "--ink",
  "--ink-2",
];

function readTokens() {
  const style = getComputedStyle(document.documentElement);
  const tokens = {};
  for (const name of TOKEN_NAMES) {
    tokens[name.replace(/^--/, "")] = style.getPropertyValue(name).trim();
  }
  return tokens;
}

export default function useThemeColors() {
  const [colors, setColors] = useState(readTokens);

  useEffect(() => {
    const observer = new MutationObserver(() => {
      setColors(readTokens());
    });

    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });

    return () => observer.disconnect();
  }, []);

  return colors;
}
