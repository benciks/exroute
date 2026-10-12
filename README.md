# exroute

Motorcycle route planning from natural language. Describe the ride, get back a routed track you can export as GPX.

```
"150 km twisty loop from Brno past a couple of castles, no motorways"
"Brno to Prague and back, coffee somewhere on the way back"
```

## Features

- **Prompt to intent** – an LLM turns the request into a structured intent: start, end, target distance or duration, stops, curvature and avoid preferences.
- **Three route shapes** – one-way A → B, A → B and back, and generated loops sized to a target distance or time.
- **Exact and discovered stops** – named places ("via Mikulov") are geocoded directly. Categories ("a nice cafe") are suggested by the LLM along the route, then filtered by detour distance and position (early, middle, late).
- **Motorcycle costing** – routed with Valhalla, with curvature preference and motorway and toll avoidance.
- **Saved routes** – routes are stored per user and can be exported as GPX.

## Stack

FastAPI, async SQLAlchemy on PostgreSQL, Alembic, JWT auth.
External services:

- LLM – OpenAI API, model set by `LLM_MODEL`
- [Pelias](https://github.com/pelias/pelias) via openrouteservice – forward geocoding
- [Mapbox](https://docs.mapbox.com/api/search/geocoding/) – reverse geocoding
- [Valhalla](https://github.com/valhalla/valhalla) – routing, with the `/round_trip` endpoint for loops

## Running

Requires Python 3.14, [uv](https://docs.astral.sh/uv/), Docker and a running Valhalla instance.

```sh
uv sync
docker compose up -d   # PostgreSQL on :5432
cp .env.example .env   # then fill in the keys
uv run fastapi dev app/main.py
```

Migrations run on startup. API docs are at http://localhost:8000/docs.

For the bundled database, set `DATABASE_URL=postgresql+asyncpg://simon:password@localhost:5432/exroute`.

## API

| Method | Path                  | Description                                     |
| ------ | --------------------- | ----------------------------------------------- |
| POST   | `/v1/auth/register`   | Create an account                               |
| POST   | `/v1/auth/login`      | Get a token (form fields `username` = email, `password`) |
| GET    | `/v1/auth/me`         | Current user                                    |
| POST   | `/v1/routes`          | Plan a route from `{"instructions": "..."}`     |
| GET    | `/v1/routes`          | List your routes                                |
| GET    | `/v1/routes/{id}/gpx` | Download a route as GPX                         |

Route endpoints require `Authorization: Bearer <token>`.
