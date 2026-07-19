# Reckon design direction

## Audience

1. **Non-technical business owners** (home services, trades). They want to see revenue, call outcomes, and trends at a glance. No jargon.

## Visual direction

Bento grid layout. Bold, oversized numbers as heroes. Restrained color: semantic meaning only. Clean, warm-neutral backgrounds. The data is the hero, not the chrome.

## Palette (light)

| Token | Value | Use |
|---|---|---|
| --bg | #F1EFE8 | Page background |
| --card | #FFFFFF | Card surface |
| --hero | #141020 | Hero panel |
| --ink | #151220 | Primary text |
| --ink-2 | #565064 | Secondary text |
| --ink-3 | #8B8698 | Tertiary text, labels |
| --line | #E6E2D8 | Borders |
| --accent | #6C4CF0 | Violet accent |
| --accent-2 | #9B82FF | Lighter violet |
| --good | #12A26B | Positive (booked) |
| --warn | #E08A16 | Caution (escalated) |
| --bad | #E5503C | Negative (missed) |

Dark mode derives inverted ink, darker bg/card, brightened status colors. In dark mode --accent maps to #9B82FF for AA contrast on dark surfaces.

## Typography

- **Display and big numbers**: Bricolage Grotesque (700-800 weight). Variable optical size 12-96.
- **Body and labels**: Inter (400-600 weight).
- Numbers always use `font-variant-numeric: tabular-nums`.
- Labels are sentence case, never tracked all-caps.

## Spacing scale

- Border radius: 18px (cards), 11px (buttons/chips), 7-9px (small elements).
- Grid gap: 14px.
- Max content width: 1180px.

## Component principles

- **Hero panel**: dark, near-black with violet dot grid. Carries the headline number. Cursor-reactive canvas pauses offscreen and respects reduced motion.
- **Stat boxes**: one semantic color per box on the number only. Mini-bar or chip for context.
- **Charts**: stacked bar (funnel), area line (revenue). Token colors, custom tooltips.
- **Table**: inline relative-revenue bars, Bricolage for money figures, right-aligned tabular numerals.
- **Theme toggle**: sun/moon in the top bar. Persists to localStorage, defaults to system preference, applies before first paint.
