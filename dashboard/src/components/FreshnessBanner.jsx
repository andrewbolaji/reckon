/*
  Freshness banner.

  A dashboard that quietly serves last week's numbers as if they were current
  is worse than one that is down, because nobody checks. This band says how old
  the data is on every load, and escalates on the same thresholds the copilot
  refuses on and Dagster's mart freshness policies use: 24h warn, 48h stale.

  The describe/format helpers are exported and pure so the wording and the
  thresholds are testable without rendering anything.
*/

export const WARN_AFTER_HOURS = 24;
export const STALE_AFTER_HOURS = 48;

export function formatAge(hours) {
  if (hours == null) return "unknown";
  if (hours < 1) return "under an hour";
  const rounded = Math.round(hours);
  if (rounded < 48) return `${rounded} hour${rounded === 1 ? "" : "s"}`;
  const days = Math.round(hours / 24);
  return `${days} days`;
}

function stalest(sources) {
  const rank = { fresh: 0, warn: 1, stale: 2 };
  return (sources || []).reduce(
    (worst, s) => (worst === null || rank[s.status] > rank[worst.status] ? s : worst),
    null,
  );
}

/*
  Turn the /api/freshness payload into what the band should say.
  Returns null while the fetch is still in flight, so nothing flashes.
*/
export function describeFreshness(freshness) {
  if (!freshness || !freshness.status) return null;

  const age = formatAge(freshness.age_hours);
  const worst = stalest(freshness.sources);
  const source = worst && worst.status !== "fresh" ? worst.name : null;

  if (freshness.status === "stale") {
    return {
      level: "stale",
      title: `Data is stale: ${age} old`,
      detail: source
        ? `${source} has not loaded since then. These numbers are not current.`
        : "These numbers are not current.",
    };
  }

  if (freshness.status === "warn") {
    return {
      level: "warn",
      title: `Data is ${age} old`,
      detail: source
        ? `${source} is behind. The pipeline has not run recently.`
        : "The pipeline has not run recently.",
    };
  }

  return {
    level: "fresh",
    title: `Data is current, loaded ${age} ago`,
    detail: "",
  };
}

export default function FreshnessBanner({ freshness }) {
  const state = describeFreshness(freshness);
  if (!state) return null;

  return (
    <div className={`freshness freshness-${state.level}`} role="status">
      <span className="freshness-dot" aria-hidden="true" />
      <span className="freshness-title">{state.title}</span>
      {state.detail && <span className="freshness-detail">{state.detail}</span>}
    </div>
  );
}
