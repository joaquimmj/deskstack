---
name: quick-dcf
description: One-shot quick DCF for a public company with cited deskstack data: builds the workbook with the analyst skill's defaults, then suggests /associate and /vp-review.
argument-hint: "<company>"
---

# Quick DCF

Run the `analyst` skill's DCF workflow with these defaults:

- 3 filed years, 5 projected years, end-of-year discounting;
- growth fading from the last filed year toward ~3%;
- margins and reinvestment at their 3-year averages;
- WACC from `risk_free_rate` (10y) + beta × ERP (`valuation_inputs`).

**Show the assumptions table and wait for the user's OK before building.** Then build, run the self-check, and offer
the review steps (`/associate`, `/vp-review`). Follow the `conventions` skill: cite every number, and end with
"Draft for human review. Not investment advice."
