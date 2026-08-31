# Logos

A backend service for turning YouTube sermons into a searchable, personal knowledge base.

## Overview

Logos helps individuals capture and organize insights from audio messages without having to take manual notes. It takes a video input, processes the transcript to extract key teachings, and allows users to query their entire listening history using natural language. This removes the friction of revisiting past lessons and makes personal study highly accessible without requiring complicated setup.

## System Architecture

```mermaid
flowchart LR
  Client["Web Client"]
  API["API Server"]
  Queue["Redis Queue"]
  Worker["Celery Worker"]
  DB[("PostgreSQL")]
  External["External Services"]

  Client --> API
  API --> DB
  API --> Queue
  Queue --> Worker
  Worker --> External
  Worker --> DB

  style Client fill:#1e1b4b,stroke:#6366f1,stroke-width:2px,color:#fff
  style API fill:#2e1065,stroke:#8b5cf6,stroke-width:2px,color:#fff
  style Queue fill:#4c0519,stroke:#ef4444,stroke-width:2px,color:#fff
  style Worker fill:#2e1065,stroke:#8b5cf6,stroke-width:2px,color:#fff
  style DB fill:#0f172a,stroke:#3b82f6,stroke-width:2px,color:#fff
  style External fill:#451a03,stroke:#f59e0b,stroke-width:2px,color:#fff
```

## Features

* **Automated Sermon Analysis**: Automatically generates summaries, key teachings, and themes from a simple YouTube link.

```mermaid
sequenceDiagram
  actor User
  participant API as "API Server"
  participant Queue as "Redis Queue"
  participant Worker as "Celery Worker"
  participant DB as "Database"

  User->>API: Send YouTube link
  API->>DB: Mark status pending
  API->>Queue: Enqueue task
  API->>User: Confirm submission
  Worker->>Queue: Consume task
  Worker->>Worker: Fetch and process
  Worker->>DB: Save completed analysis
```

* **Contextual Q&A (RAG)**: Ask questions spanning multiple sermons and receive cited answers directly from the transcript content.

```mermaid
sequenceDiagram
  actor User
  participant API as "API Server"
  participant DB as "Database"
  participant LLM as "AI Model"

  User->>API: Ask question
  API->>DB: Find relevant chunks
  DB->>API: Return context
  API->>LLM: Generate cited answer
  LLM->>API: Return answer text
  API->>User: Display final response
```

* **Semantic Search**: Find specific moments across an entire library using meaning rather than exact keywords.
* **Personalized Notes**: Attach personal reflections to specific sermons alongside the generated AI analysis.

## Installation

Clone the Repository:

```bash
git clone https://github.com/DanielPopoola/logos.git
cd logos
```

Set up your local environment and dependencies using `uv`. You will also need Docker to run the database and cache.

```bash
uv sync --all-extras --dev
docker compose up -d
cp .env.example .env
```

Make sure to populate your `.env` file with your real LLM API keys and Google Client credentials.

Run the database migrations and install your pre-commit hooks.

```bash
uv run alembic upgrade head
uv run pre-commit install
```

## Usage

Once the infrastructure is up, start the FastAPI server and the Celery worker in separate terminals.

To start the API server:
```bash
uv run uvicorn app.main:app --reload
```

To start the background worker:
```bash
uv run celery -A app.workers.celery_app worker --loglevel=info
```

To submit a new sermon for processing, make a standard HTTP POST request.
```bash
curl -X POST http://localhost:8000/v1/sermons \
  -H "Content-Type: application/json" \
  -H "Cookie: session_token=YOUR_SESSION_TOKEN" \
  -d '{"youtube_url": "https://youtube.com/watch?v=ABC123"}'
```

If you prefer testing the pipeline directly without hitting the API endpoints, you can use the verification script provided.
```bash
uv run python scripts/verify_ingestion.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

## Technologies Used

| Technology | Purpose |
|------------|----------|
| **FastAPI** | High-performance Python web framework for building the REST API. |
| **PostgreSQL & pgvector** | Primary data storage and vector search engine for embeddings. |
| **SQLAlchemy & Alembic** | ORM for database interactions and migration management. |
| **Celery & Redis** | Task queue and broker for managing asynchronous video ingestion. |
| **Gemini LLM** | Powers transcript analysis, summaries, and query embeddings. |
| **pytest & uv** | Testing framework and fast Python package management. |

## Author Info

* Name: Daniel Popoola
* Email: iamuchihadaniel236@gmail.com
* GitHub: https://github.com/DanielPopoola

## Badges

[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Celery](https://img.shields.io/badge/celery-%2337814A.svg?style=for-the-badge&logo=celery&logoColor=white)](https://docs.celeryq.dev/)
[![Redis](https://img.shields.io/badge/redis-%23DD0031.svg?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io/)

[![Readme was generated by Dokugen](https://img.shields.io/badge/Readme%20was%20generated%20by-Dokugen-brightgreen)](https://dokugen.samueltuoyo.com)