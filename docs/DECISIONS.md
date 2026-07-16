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
| 2026-07-16 | MongoDB + Metabase | Source freshness on jobs | The jobs source has the same freshness checks (warn 24h, error 48h) as calls and payments. Originally used scheduled_at; now uses _loaded_at (pipeline load time) for all sources. |
| 2026-07-16 | CI | Pin vitest to 2.x for vite 5 compatibility | vitest 4.x requires vite >=6 which pulls in esbuild 0.28.x, creating cross-platform lockfile conflicts that break npm ci on CI runners. Do not bump vitest past 2.x without also upgrading vite. |
| 2026-07-16 | MCP Copilot | Package named copilot/, not mcp/ | A local package named mcp/ shadows the installed mcp SDK. copilot/ avoids the collision. |
| 2026-07-16 | MCP Copilot | reckon_reader DB role scoped to marts SELECT only | String-based SQL validation is a good first layer but bypassable in principle. The DB role is the load-bearing control: even if the validator misses something, the database blocks reads from raw/staging and all writes. |
| 2026-07-16 | MCP Copilot | Freshness gate uses _loaded_at, not event timestamps | Seed data has fixed event dates that drift into "stale" as real time passes. _loaded_at is set by the loader on every pipeline run, so freshness tracks when data was loaded, not when events happened. |
| 2026-07-16 | MCP Copilot | Warn (24-48h) adds caveat, error (>48h) refuses | A warn-level staleness should not block answers. The copilot notes the data age as a caveat. Only error-level staleness (>48h) produces a hard refusal. |
| 2026-07-16 | MCP Copilot | Freshness check cached per answer, not per tool call | A multi-tool answer should not hit the DB with 3 separate MAX() queries. The freshness result is cached and reused across tool calls within the same answer. |
| 2026-07-16 | MCP Copilot | Audit log to stderr (JSON), optional file via env var | Twelve-factor: logs go to stderr by default. COPILOT_AUDIT_LOG env var enables file output. No log files committed to repo (*.log in .gitignore). |
| 2026-07-16 | MCP Copilot | Grounding described as "auditable," not "cannot hallucinate" | The tools cannot prevent the model from rephrasing a number. But every answer is auditable: the tool called, the SQL, and the rows are shown alongside. Tests verify tool outputs match direct queries. |
| 2026-07-16 | MCP Copilot | 6 MCP tools: metric tools + guarded SQL + schema | Metric tools (revenue_summary, call_funnel, job_completion) are the safe fast path. query_marts is the locked-down fallback for edge cases. describe_schema grounds the model in real table metadata. check_freshness gives the user visibility into data recency. |
