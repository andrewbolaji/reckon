# Reckon handbook

A plain-language guide for anyone using or demoing Reckon.

## Dashboard

### What it shows

The dashboard surfaces two data streams: **voice agent calls** (from Aria) and **payments** (from Stripe). It answers three questions:

1. **How much revenue came in?** The hero panel shows total revenue for the last 30 days. The revenue trend chart shows it day by day. The table breaks it down by service type.
2. **How are calls converting?** The stat boxes show booking rate, booked jobs, escalated calls, and missed calls. The funnel chart shows the daily breakdown.
3. **Is performance improving?** Chips on the stat boxes show rates relative to total calls.

### How to read it

- **Hero panel** (top left, dark): the big number is total revenue. Below it, three secondary stats give context: total calls handled, jobs booked, and average caller sentiment (0 to 1, higher is better).
- **Stat boxes** (top right): each box highlights one metric. The number color tells you the category: violet for a rate, green for good outcomes, amber for escalations, red for missed calls.
- **Call funnel chart**: a stacked bar chart. Each bar is one day. Green is booked (good), violet is qualified, amber is escalated, red is missed.
- **Revenue trend chart**: a line chart of daily revenue. The shaded area under the line helps you see the trend.
- **Revenue by service table**: each row is a service your business offers. The small bar shows relative revenue at a glance. Revenue and average ticket are shown in dollars.

### Theme toggle

The sun/moon button in the top-right corner switches between light and dark mode. Your choice is saved and will persist across sessions. On your first visit, it matches your system setting.
