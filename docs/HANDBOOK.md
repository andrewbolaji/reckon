# Reckon handbook

A plain-language guide for anyone using or demoing Reckon.

## Dashboard

### What it shows

The dashboard surfaces three data streams: **voice agent calls** (from Aria), **payments** (from Stripe), and **service jobs** (from MongoDB). It answers four questions:

1. **How much revenue came in?** The hero panel shows total revenue for the last 30 days. The revenue trend chart shows it day by day. The table breaks it down by service type.
2. **How are calls converting?** The stat boxes show booking rate, booked jobs, escalated calls, and missed calls. The funnel chart shows the daily breakdown.
3. **Are jobs getting completed?** The hero panel shows completed jobs alongside booked calls, so you can see the booked-to-completed conversion at a glance.
4. **Is performance improving?** Chips on the stat boxes show rates relative to total calls.

### How to read it

- **Hero panel** (top left, dark): the big number is total revenue. Below it, four secondary stats give context: total calls handled, jobs booked, jobs completed, and average caller sentiment (0 to 1, higher is better).
- **Stat boxes** (top right): each box highlights one metric. The number color tells you the category: violet for a rate, green for good outcomes, amber for escalations, red for missed calls.
- **Call funnel chart**: a stacked bar chart. Each bar is one day. Green is booked (good), violet is qualified, amber is escalated, red is missed.
- **Revenue trend chart**: a line chart of daily revenue. The shaded area under the line helps you see the trend.
- **Revenue by service table**: each row is a service your business offers. The small bar shows relative revenue at a glance. Revenue and average ticket are shown in dollars.

### Theme toggle

The sun/moon button in the top-right corner switches between light and dark mode. Your choice is saved and will persist across sessions. On your first visit, it matches your system setting.

## Metabase

Metabase is a self-serve BI tool that runs alongside the React dashboard. Use it to explore data, build custom charts, or answer ad-hoc questions without writing code.

### Access

- URL: http://localhost:3001
- First-time setup: run `bash metabase/setup.sh` after Metabase is healthy
- Default admin: the email and password you set in `MB_ADMIN_EMAIL` / `MB_ADMIN_PASSWORD` env vars

### Building the starter dashboards

After setup, Metabase auto-scans the warehouse schemas. You can build these two starter dashboards:

**Call funnel dashboard**
1. Click "New" then "Question"
2. Pick "Reckon Warehouse" as the database, then "Native query"
3. Paste: `SELECT call_date, total_calls, booked, qualified, escalated, missed, completed_jobs FROM marts.mart_call_funnel ORDER BY call_date`
4. Click "Visualize", switch to a stacked bar chart
5. Save as "Call funnel" in a new dashboard called "Reckon"

**Revenue dashboard**
1. New question, native query
2. Paste: `SELECT payment_date, sum(revenue_dollars) as revenue, sum(net_revenue_dollars) as net_revenue FROM marts.mart_revenue GROUP BY payment_date ORDER BY payment_date`
3. Visualize as an area chart
4. Save to the same "Reckon" dashboard

### What data is available

| Schema | Table | What it contains |
|---|---|---|
| marts | mart_call_funnel | Daily call metrics: volume, outcomes, booking rate, job completions |
| marts | mart_revenue | Daily revenue by service and payment method |
| marts | mart_jobs | Job completion metrics by service category |
| staging | stg_aria_calls | Cleaned call records |
| staging | stg_stripe_payments | Cleaned payment records |
| staging | stg_jobs | Cleaned job records |

## Data pipeline

The pipeline runs automatically when you start the stack with `docker compose up`. It:

1. Extracts call records from Aria (generated with a fixed seed for consistency)
2. Extracts payment records from Stripe (generated sample data)
3. Extracts job records from MongoDB (seeded at container init)
4. Loads all three into the PostgreSQL warehouse
5. Runs dbt to build staging views and mart tables
6. Runs all data quality tests (uniqueness, not-null, accepted values, freshness)

If any test fails, downstream models are blocked. This is the data trust gate.

## AI Copilot

The copilot lets you ask questions about your business data in plain English. It connects to the same warehouse marts the dashboard uses and shows you the exact query behind every answer.

### How to use it

1. Make sure the docker stack is running (`docker compose up --build`)
2. Install copilot dependencies: `pip install -r copilot/requirements.txt`
3. Set your Anthropic API key: `export ANTHROPIC_API_KEY=sk-ant-...`
4. Run the REPL: `python -m copilot.cli`

### Questions it can answer

- "How much revenue last week?" -- uses the revenue_summary tool
- "Which service makes the most money?" -- uses revenue_summary grouped by service
- "What's my booking rate?" -- uses the call_funnel tool
- "How are job completions looking?" -- uses the job_completion tool
- "Is my data fresh?" -- uses the check_freshness tool
- "What's the average ticket size for plumbing?" -- falls back to the guarded SQL tool

### Questions it will refuse

- **Stale data**: if the pipeline has not run in over 48 hours, the copilot tells you the data is stale and asks you to run the pipeline. It will not guess.
- **Out-of-scope questions**: if the marts do not have the data to answer (for example, "who is my biggest customer by name"), the copilot says so instead of making something up.
- **Adversarial prompts**: asking it to "ignore your instructions" or "just estimate a number" will not work. The tools enforce what data is available, and every number must come from a tool result.

### How it stays safe

- The copilot connects to the database with a restricted role (`reckon_reader`) that can only SELECT from the marts schema. It cannot read raw data, staging data, or system tables.
- Every SQL query is validated before execution: no DDL, no DML, no multi-statement input, no tables outside the marts allowlist.
- Every tool call is logged as structured JSON for audit.
- The freshness gate checks when the pipeline last loaded data (not when events happened), so the check stays accurate even with fixed seed data.

### Warn vs. error

- **24 to 48 hours since last load**: the copilot answers but includes a note about the data age.
- **Over 48 hours**: the copilot refuses and tells you to run the pipeline.

### Using with Claude Desktop

You can also wire the copilot into Claude Desktop as an MCP server. See the README for the config JSON to add to your `claude_desktop_config.json`.
