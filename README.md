# Weather-Aware Truck Routing

**Live app:** https://truck-weather-routing-x40x.onrender.com (hosted on Render's free plan, so the first request after idle can take up to a minute to wake the service)

A React + Django web app that helps a truck driver pick the safest of three routes using **weather, load weight and travel time**.

Enter an origin, destination, departure time and load weight. The app:

1. gets **3 route options** from Mapbox Directions,
2. samples weather every **10 / 25 / 50 miles** using the truck's **estimated arrival time** at each checkpoint (Open-Meteo hourly forecast),
3. scores each checkpoint with the provided risk and load rules,
4. **recommends** the best route, balancing weather risk and travel time, and says why,
5. shows every route, checkpoint, risk level, ETA and summary on a map, with a **weather heatmap over the trip corridor and a 0–48 hour forecast slider**.

## Architecture

```
React (Vite, TypeScript, mapbox-gl)  ──►  Django + DRF  ──►  Mapbox Directions / Geocoding
        one origin, no CORS                (stateless)  ──►  Open-Meteo hourly forecast
```

In production Django serves the built React app (WhiteNoise) and the API from a single service.

```
backend/
  planner/
    domain/            Pure, unit-tested logic: no I/O, no Django
      risk.py          thresholds + load rules -> risk level per checkpoint
      sampling.py      route polyline -> checkpoints with mile markers and ETAs
      recommend.py     per-route metrics, ranking and the "why" explanation
    services/
      mapbox.py        geocoding + directions (3 distinct routes, with fallback)
      openmeteo.py     batched, chunked, cached hourly forecasts
    planning.py        use cases: plan_trip(), build_heatmap()
    views.py           thin REST layer
frontend/src/
  components/          TripForm, PlaceInput, RouteList, MapView, ForecastSlider, Legend
  api.ts, risk.ts, format.ts, heatmap.ts
```

## How the logic works

### Risk rules

Each checkpoint is classified for wind, rain and snow; the checkpoint's level is the **worst** of the three, then the load rules are applied.

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind (mph) | <25 | 25–34 | 35–44 | 45–54 | ≥55 |
| Rain (in/hr) | <0.10 | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | >1.00 |
| Snow (in/hr) | <0.5 | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | >3.0 |

Load rules (these only ever raise the level):

- wind ≥ 55 mph → **No Travel** for any load
- wind 45–54 mph and load > 30,000 lb → **No Travel**
- wind 35–44 mph and load > 40,000 lb → **Severe**

Boundary conventions: bands are lower-bound inclusive (25 mph is Moderate, 0.25 in/hr rain is High), which also removes the gaps in the table (34.5 mph is Moderate). "No Travel" is inclusive for wind (≥55) and exclusive for rain/snow (>1.00, >3.0), exactly as written in the brief. Each is covered by a boundary test in `backend/planner/tests/test_risk.py`.

### Sampling and ETAs

The route polyline is walked with great-circle (haversine) distances. Checkpoints are placed at the origin, every N miles, and the destination. The ETA at a checkpoint is the departure time plus the cumulative travel time at that point, taken from Mapbox's per-segment duration annotations (not a constant average speed). The forecast hour nearest to the ETA is used. If an ETA falls outside the forecast window the nearest available hour is used and the checkpoint is flagged.

Each checkpoint's level applies to the miles from it to the next checkpoint, so "miles at High/Severe" and the distance-weighted average risk are well-defined for every route.

### Recommendation

Routes are ranked lexicographically, in the brief's order:

1. fewest **No Travel** miles (strictly worse than Severe, so it leads),
2. fewest **Severe** miles,
3. fewest **High** miles,
4. lowest **average risk** (0 = Low … 4 = No Travel, weighted by miles),
5. **shortest travel time**.

Values are rounded (0.1 mi, 0.01 risk, 1 minute) so sub-noise differences count as ties and the next criterion decides. The response includes a plain-English reason comparing the winner with the runner-up. If every route crosses No Travel conditions, the least-exposed route is recommended and the UI says so.

### Heatmap

`POST /api/heatmap` builds a grid along every route (every 30 mi, plus points 20 mi to each side) and returns, for each point, the risk level for **each of the next 49 forecast hours** (`r0`…`r48`) computed with the driver's load weight. The browser gets everything in one payload, and the slider only swaps a Mapbox paint expression (`setPaintProperty`), so dragging never refetches or re-uploads data.

## Run locally

Requirements: Python 3.12+, Node 20+, a Mapbox **public** token (`pk.…`).

```bash
cp .env.example .env            # then put your token in MAPBOX_TOKEN

# Backend (http://localhost:8000)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python manage.py runserver

# Frontend dev server with API proxy (http://localhost:5173)
cd frontend
npm ci
npm run dev
```

For a production-like run, `npm run build` in `frontend/` and open http://localhost:8000: Django serves the build.

### Tests and checks

```bash
cd backend  && pytest && ruff check . && ruff format --check .
cd frontend && npm test && npm run lint && npx tsc -b && npm run format:check
```

Backend tests cover the risk boundaries and every load rule, ETA interpolation, ranking and tie-breaks, and the API end to end with Mapbox and Open-Meteo mocked.

## Deploy (Render)

`render.yaml` defines one Docker web service (multi-stage `Dockerfile`: Node builds the frontend, Python serves everything).

1. In Render choose **New → Blueprint** and select this repo.
2. Set `MAPBOX_TOKEN` (a public `pk.` token) in the service's environment. `DJANGO_SECRET_KEY` is generated automatically.
3. Optional hardening: restrict the token to your Render URL in the Mapbox dashboard.

The server returns the public token to the browser at runtime (`/api/config/`), so there is nothing to rebuild when it changes. A secret (`sk.`) token is never exposed.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/geocode/?q=` | Address autocomplete (proxies Mapbox; US results) |
| `POST /api/plan/` | `{origin, destination, departure_time, load_weight_lb, interval_miles}` → scored routes, checkpoints, recommendation |
| `POST /api/heatmap/` | `{origin, destination, load_weight_lb}` → 49-hour risk grid for the corridor |
| `GET /api/config/` | Public map token and style |
| `GET /api/health/` | Health check |

Inputs are validated (load 0–80,000 lb, interval 10/25/50, departure within the next 72 hours, distinct origin/destination). Upstream failures return `502` with a readable message; no route returns `404`.

## Assumptions and limitations

- **US only.** Thresholds are in mph and inches, and geocoding is restricted to the US.
- **Wind uses sustained speed** (`wind_speed_10m`); gusts are shown in the checkpoint popup but are not scored.
- **Rain** is `rain + showers`; **snow** is hourly `snowfall` depth, matching the brief's in/hr.
- Routes come from Mapbox's standard `driving` profile. It has no truck-specific restrictions (height, weight, hazmat), and Mapbox may return fewer than 3 alternatives for some trips. In that case the server queries variants (`exclude=toll`, `motorway`) and keeps only distinct routes; if fewer than 3 exist, the UI shows what is available.
- Forecast data comes from Open-Meteo's free API (non-commercial limits). Requests are chunked, snapped to a ~3.5 mi grid and cached for 30 minutes to stay well under them.
- Departure must be within 72 hours so every checkpoint ETA has forecast coverage; ETAs are shown in the viewer's local time zone.
- The app is stateless and caches in process memory, so it runs as one gunicorn worker with threads.

## Possible next steps

Truck-specific routing (HGV profile / restrictions), gust-aware scoring, per-route "what if I leave later" comparison, and a shared cache (Redis) for multi-worker deployments.
