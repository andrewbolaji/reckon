# Reckon decisions log

Decisions are logged per Block with date, what was decided, and why.

| Date | Block | Decision | Rationale |
|---|---|---|---|
| 2026-07-16 | Dashboard v2 | Bento grid layout (4-col, hero 2x2) | Mockup approach is more visually striking than a uniform card grid. Gives the headline number real estate. |
| 2026-07-16 | Dashboard v2 | Bricolage Grotesque for display, Inter for body | Bricolage has personality without being decorative. Inter is a workhorse body font with tabular numeral support. |
| 2026-07-16 | Dashboard v2 | Semantic color on numbers only | Color carries meaning (good/warn/bad), not decoration. Keeps the interface calm. |
| 2026-07-16 | Dashboard v2 | Dark mode via data-theme attribute + CSS tokens | Avoids CSS-in-JS complexity. Blocking script in head prevents flash. Charts update via MutationObserver on data-theme. |
| 2026-07-16 | Dashboard v2 | Use --accent-2 (#9B82FF) as --accent in dark mode | #6C4CF0 fails AA contrast on near-black backgrounds. #9B82FF passes. |
| 2026-07-16 | Dashboard v2 | Canvas dot grid with IntersectionObserver pause | Keeps the hero panel visually interesting without wasting GPU when offscreen or tab is hidden. Static fallback for reduced motion. |
| 2026-07-16 | Dashboard v2 | 4 stat boxes (not 6 KPI cards) + hero | Total revenue, calls, booked, and sentiment move into the hero. Stat boxes carry the four actionable metrics with semantic color. Reduces clutter. |
| 2026-07-16 | MongoDB + Metabase | Deterministic Aria seed + pre-generated job JSON | Fixed seed (42) makes call_ids stable across runs. A Python script generates the job seed JSON using the same Aria generator, then Mongo loads it at init. Keeps Mongo as a genuine source while guaranteeing referential consistency. |
| 2026-07-16 | MongoDB + Metabase | Idempotent lake writes (clear before extract) | On re-runs, the lake writer clears prior files for each source before writing new ones. Prevents duplicate rows when the loader reads all lake files. |
| 2026-07-16 | MongoDB + Metabase | 1:1 call-to-job, aggregate before join | One job per booked call, enforced by a unique test on stg_jobs.related_call_id. mart_call_funnel aggregates jobs to the daily grain before the left join, so fanout is impossible even if the relationship changes. |
| 2026-07-16 | MongoDB + Metabase | Metabase as self-serve BI layer, not replacement | Metabase runs alongside the React dashboard. Setup script provisions the admin user and warehouse connection via the setup API. Pre-built dashboards are documented, not auto-provisioned. |
| 2026-07-16 | MongoDB + Metabase | Source freshness on jobs | The jobs source has the same freshness checks (warn 24h, error 48h) as calls and payments, using scheduled_at as the loaded_at field. |
