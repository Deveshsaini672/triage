# AI-Powered Support Ticket Triage

A backend service that classifies incoming support tickets using Google Gemini and routes them to the appropriate team. Tickets are processed in the background, so the API can respond without waiting for the LLM.

**Stack:** Python, FastAPI, PostgreSQL, SQLAlchemy, Redis, Celery, Docker, Google Gemini

## How it works

1. A client submits a ticket using an API key.
2. The API saves it as `pending`, queues a Celery task, and returns `202 Accepted`.
3. A worker checks Redis for a cached result before calling Gemini.
4. The classification and routing history are saved to PostgreSQL, and the ticket is assigned to a team.
5. Agents log in with JWT authentication and access tickets belonging to their team.

### Failure handling

- Failed tasks are retried with exponential backoff.
- Tickets that exhaust their retries are routed to the fallback **Triage** team.
- Rate-limited tasks are rescheduled without consuming retry attempts.
- Celery Beat requeues tickets that remain pending for more than five minutes.

## Getting started

### Requirements

- Docker and Docker Compose
- A Google Gemini API key

### Run with Docker

Clone the repository and enter the project directory:

```bash
git clone https://github.com/Deveshsaini672/triage.git
cd triage
```

Create your environment file:

```bash
cp .env.example .env
```

Add your Gemini API key to `.env` and replace the default secrets.

Start the services:

```bash
docker compose up -d --build
```

Seed the database with development users:

```bash
docker compose exec api python -m scripts.seed
```

API documentation: http://localhost:8000/docs

## Running locally

You can run the API and Celery processes locally while using Docker for PostgreSQL and Redis.

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
docker compose up -d postgres redis
```

Start the API:

```bash
uvicorn app.main:app --reload
```

In separate terminals, start the Celery worker and scheduler:

```bash
celery -A app.celery_app worker -l info
```

```bash
celery -A app.celery_app beat -l info
```

Seed the database:

```bash
python -m scripts.seed
```

When running locally, configure `.env` to use `localhost` for PostgreSQL and Redis. Inside Docker, use the corresponding service hostnames.

## API endpoints

| Method | Endpoint | Authentication |
|---|---|---|
| `POST` | `/tickets` | API key |
| `GET` | `/tickets` | JWT |
| `GET` | `/tickets/{id}` | JWT |
| `PATCH` | `/tickets/{id}/reassign` | JWT |
| `GET` | `/teams` | JWT |
| `POST` | `/auth/login` | Username and password |
| `GET` | `/auth/me` | JWT |
| `GET` | `/health` | None |

Agents can only access tickets belonging to their team. Requests for tickets outside their team's scope return `404`.

The ticket listing endpoint supports `status`, `limit`, and `offset` query parameters.

## Development accounts

The seed script creates development accounts for the billing, tech, general, and triage teams.

Default development password: `password123`

These credentials are for local development only. Do not use them in production.

## Tests

Install the development dependencies:

```bash
pip install -r requirements-dev.txt
```

Run the tests:

```bash
pytest
```

The test suite uses SQLite, fakeredis, and a fake LLM, so Docker and a Gemini API key are not required.

## limitations

- Database tables are created using SQLAlchemy `create_all`; migrations are not configured.
- The fixed-window rate limiter can allow bursts around window boundaries.
- Cached summaries may contain ticket-specific details from the original ticket.
- Simultaneous identical tickets can both miss the cache and trigger separate LLM calls.
- Login throttling, HTTPS/CORS configuration, and application metrics are not implemented.
