"""Per-topic "before vs after" analysis studies.

Each module answers one question: *what does this formula actually buy
you?* — by comparing a baseline (naive / open-loop / no constraint /
no filter) against the principled formulation from the article, and
plotting the gap.

All analyses:

- run in < 10 s on a laptop,
- save a PNG + a short CSV to ``analysis/artifacts/`` so you can eyeball
  the result,
- print a one-line summary so they can be wired into a CI.

Run a single study :
    python -m analysis.s01_lossless_convex
Run them all     :
    python -m analysis.run_all
"""
