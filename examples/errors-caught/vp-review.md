## Model check: model.xlsx
Overall: Minor Issues — 0 blocker, 1 major, 0 minor, 0 info (deskstack_check 0.2.0).

| # | Sheet | Cell/Range | Severity | Category | Issue | Suggested Fix | Rule | Found by |
|---|---|---|---|---|---|---|---|---|
| 1 | Inputs | `B7` | major (Warning) | Placeholder | Looks like a placeholder 0: its label or source says 'NOT FOUND'. | Find the filed figure (verify_value), or leave the cell empty and say it is missing; never a 0 or a guess. | DS016 | deskstack |