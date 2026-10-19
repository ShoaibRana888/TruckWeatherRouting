# Loom walkthrough script (target ≈ 7 minutes)

Have the hosted app open in one tab and the repo in your editor. Pick a long trip with some weather (e.g. Dallas → Denver, 42,000 lb, departing in a few hours). Do one dry run first.

**0:00 – Problem and approach (30s)**
- "A driver needs the safest route, not just the fastest. This app compares three routes by weather risk, load weight and travel time."
- Stack: React + Django, Mapbox for routes/geocoding, Open-Meteo for forecasts.

**0:30 – Live demo (2 min)**
- Enter origin and destination using the autocomplete; set departure and load weight; choose the 25-mile checkpoint interval.
- Plan routes. Point out: three route cards, the Recommended badge, the one-line reason, miles at each risk level, drive time and arrival time.
- On the map: risk-coloured route segments, checkpoint dots; click a checkpoint → ETA, wind/rain/snow and which rule fired.
- Click another route to compare; mention how the selection highlights.
- Change to 10 mi and re-plan to show denser sampling.

**2:30 – Heatmap and slider (1 min)**
- Drag the 0–48 h slider; explain it is one request with all 49 hours, and the slider only swaps a paint expression, so it stays smooth.
- "Jump to departure" returns to the departure hour.

**3:30 – Risk and recommendation logic (1.5 min)** — open `backend/planner/domain/`
- `risk.py`: thresholds, worst-of-three, load rules; boundary convention (lower-bound inclusive) and why.
- `sampling.py`: haversine walk, ETA from per-segment durations.
- `recommend.py`: ranking order from the brief (with No Travel first), rounding for ties, the generated explanation.
- Show a test or two (`test_risk.py` boundaries, `test_recommend.py` tie-breaks).

**5:00 – Code quality and architecture (1 min)**
- Pure domain layer vs services vs thin views; upstream calls mocked in tests; validation and error handling (502/404).
- Frontend: typed API client, lazy-loaded map, derived state in the form.

**6:00 – Trade-offs and next steps (1 min)**
- No truck-specific routing profile; Mapbox may return fewer than 3 alternatives (fallback queries).
- Sustained wind only; US-only; free-tier forecast limits mitigated by chunking, grid snapping and caching.
- Next: HGV routing, gusts, "leave later" comparison, shared cache.

**6:45 – Wrap-up (15s)**
- Repo link and hosted URL.
