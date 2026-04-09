# Deployment Guide

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Environment Variables](#environment-variables)
4. [Vercel Configuration](#vercel-configuration)
5. [Build and Deployment Steps](#build-and-deployment-steps)
6. [SQLite Considerations for Serverless](#sqlite-considerations-for-serverless)
7. [Static File Serving](#static-file-serving)
8. [Troubleshooting Common Issues](#troubleshooting-common-issues)

---

## Overview

ProjectForge is a Python + FastAPI application designed to be deployed on Vercel's serverless platform. This guide covers the complete deployment process, including environment configuration, Vercel setup, and handling SQLite in a serverless context.

---

## Prerequisites

- **Python 3.11+** installed locally
- **Node.js 18+** installed (required by Vercel CLI)
- **Vercel CLI** installed globally:
  ```bash
  npm install -g vercel
  ```
- A **Vercel account** linked to your Git provider (GitHub, GitLab, or Bitbucket)
- A `.env` file configured locally for testing before deployment

---

## Environment Variables

### Required Variables

Set these in the Vercel dashboard under **Project Settings → Environment Variables**:

| Variable | Description | Example |
|---|---|---|
| `SECRET_KEY` | Secret key for JWT signing and session security | `a-long-random-string-at-least-32-chars` |
| `DATABASE_URL` | SQLite connection string (or PostgreSQL for production) | `sqlite+aiosqlite:///./projectforge.db` |
| `ENVIRONMENT` | Deployment environment identifier | `production` |
| `ALLOWED_ORIGINS` | Comma-separated list of allowed CORS origins | `https://your-app.vercel.app` |

### Optional Variables

| Variable | Description | Default |
|---|---|---|
| `DEBUG` | Enable debug mode (never `true` in production) | `false` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT token expiration time in minutes | `30` |
| `LOG_LEVEL` | Python logging level | `INFO` |

### Setting Environment Variables on Vercel

**Via Vercel Dashboard:**

1. Navigate to your project on [vercel.com](https://vercel.com)
2. Go to **Settings** → **Environment Variables**
3. Add each variable with the appropriate value
4. Select the environments where each variable applies (Production, Preview, Development)
5. Click **Save**

**Via Vercel CLI:**

```bash
vercel env add SECRET_KEY production
vercel env add DATABASE_URL production
vercel env add ENVIRONMENT production
vercel env add ALLOWED_ORIGINS production
```

> **Security Note:** Never commit `.env` files to version control. The `.gitignore` file should already include `.env`. Always use Vercel's environment variable management for sensitive values like `SECRET_KEY`.

---

## Vercel Configuration

### vercel.json

The `vercel.json` file at the project root configures how Vercel builds and routes requests:

```json
{
  "version": 2,
  "builds": [
    {
      "src": "main.py",
      "use": "@vercel/python"
    },
    {
      "src": "static/**",
      "use": "@vercel/static"
    }
  ],
  "routes": [
    {
      "src": "/static/(.*)",
      "dest": "static/$1"
    },
    {
      "src": "/(.*)",
      "dest": "main.py"
    }
  ]
}
```

### Key Configuration Details

- **`@vercel/python` builder**: Compiles and serves the FastAPI application. It expects a `main.py` entry point that exposes an `app` object.
- **`@vercel/static` builder**: Serves files from the `static/` directory without going through the Python runtime.
- **Route ordering matters**: Static file routes must come before the catch-all route to ensure CSS, JS, and image files are served directly.

### Entry Point Requirements

Vercel's Python runtime looks for an ASGI/WSGI application object. Ensure `main.py` exposes the FastAPI app at module level:

```python
from fastapi import FastAPI

app = FastAPI(title="ProjectForge")

# ... routes, middleware, etc.
```

The variable **must** be named `app` for Vercel to detect it automatically.

---

## Build and Deployment Steps

### Local Testing

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Create a `.env` file** with your local configuration:
   ```env
   SECRET_KEY=local-dev-secret-key-change-in-production
   DATABASE_URL=sqlite+aiosqlite:///./projectforge.db
   ENVIRONMENT=development
   ALLOWED_ORIGINS=http://localhost:8000
   DEBUG=true
   ```

3. **Run the application locally:**
   ```bash
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

4. **Verify the application** at `http://localhost:8000`

### Deploying to Vercel

**First-time setup:**

```bash
# Login to Vercel
vercel login

# Link your project (run from the project root)
vercel link

# Deploy to preview
vercel

# Deploy to production
vercel --prod
```

**Subsequent deployments:**

If your repository is connected to Vercel via Git integration, every push to the main branch triggers an automatic production deployment. Pull requests create preview deployments.

**Manual deployment:**

```bash
# Preview deployment
vercel

# Production deployment
vercel --prod
```

### Build Process on Vercel

When Vercel builds the project, it:

1. Detects `requirements.txt` and installs Python dependencies
2. Processes the `vercel.json` configuration
3. Bundles the application using `@vercel/python`
4. Deploys static assets separately via `@vercel/static`
5. Creates serverless functions for the Python routes

### Verifying Deployment

After deployment, verify:

1. **Homepage loads**: Visit `https://your-app.vercel.app/`
2. **Static assets load**: Check browser DevTools Network tab for CSS/JS 200 responses
3. **API endpoints respond**: Test `https://your-app.vercel.app/api/health` or similar health check endpoint
4. **Authentication works**: Test login/logout flows
5. **Database operations work**: Create, read, update, and delete records

---

## SQLite Considerations for Serverless

### The Serverless Challenge

Vercel serverless functions are **ephemeral** — each invocation may run in a fresh container. This has critical implications for SQLite:

- **No persistent filesystem**: The writable filesystem (`/tmp`) is temporary and not shared across invocations
- **No shared state**: Two concurrent requests may execute in different containers with separate SQLite databases
- **Cold starts**: Each new container must initialize the database from scratch

### Development vs. Production Strategy

| Environment | Database | Notes |
|---|---|---|
| Local Development | SQLite (file-based) | Fast, zero-config, great for development |
| Vercel Preview | SQLite in `/tmp` | Ephemeral, acceptable for previews |
| Vercel Production | **PostgreSQL recommended** | Use a managed service like Vercel Postgres, Neon, Supabase, or Railway |

### Using SQLite on Vercel (Preview/Demo Only)

If you must use SQLite on Vercel (for demos or previews), configure the database path to use `/tmp`:

```python
import os

if os.environ.get("VERCEL"):
    DATABASE_URL = "sqlite+aiosqlite:////tmp/projectforge.db"
else:
    DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./projectforge.db")
```

**Limitations to understand:**

- Data is lost when the serverless function container is recycled (typically after ~5-15 minutes of inactivity)
- Concurrent requests may hit different containers with different database states
- Write-heavy workloads will experience poor performance

### Migrating to PostgreSQL for Production

1. **Provision a PostgreSQL database** (e.g., Vercel Postgres, Neon, Supabase)

2. **Update `DATABASE_URL`** in Vercel environment variables:
   ```
   postgresql+asyncpg://user:password@host:5432/dbname
   ```

3. **Add `asyncpg` to `requirements.txt`:**
   ```
   asyncpg>=0.29.0
   ```

4. **Update database engine creation** to handle both SQLite and PostgreSQL:
   ```python
   from sqlalchemy.ext.asyncio import create_async_engine

   if DATABASE_URL.startswith("sqlite"):
       engine = create_async_engine(DATABASE_URL, echo=False)
   else:
       engine = create_async_engine(
           DATABASE_URL,
           echo=False,
           pool_size=5,
           max_overflow=10,
       )
   ```

5. **Run migrations** against the production database before deploying

---

## Static File Serving

### Directory Structure

```
project-root/
├── static/
│   ├── css/
│   │   └── styles.css
│   ├── js/
│   │   └── app.js
│   └── images/
│       └── logo.png
├── templates/
│   ├── base.html
│   └── ...
├── main.py
├── vercel.json
└── requirements.txt
```

### How Static Files Are Served

On Vercel, static files are served in two ways:

1. **Via `@vercel/static` builder** (recommended for production): Files in `static/` are served directly by Vercel's CDN, bypassing the Python runtime entirely. This is configured in `vercel.json`.

2. **Via FastAPI's `StaticFiles` mount** (used in local development):
   ```python
   from fastapi.staticfiles import StaticFiles
   app.mount("/static", StaticFiles(directory="static"), name="static")
   ```

### Template References

In Jinja2 templates, reference static files using the `/static/` prefix:

```html
<link rel="stylesheet" href="/static/css/styles.css">
<script src="/static/js/app.js"></script>
<img src="/static/images/logo.png" alt="Logo">
```

### Tailwind CSS

If using Tailwind CSS, ensure the compiled CSS file is committed to the `static/css/` directory or built during the Vercel build step. Add a build command in `vercel.json` if needed:

```json
{
  "buildCommand": "npx tailwindcss -i ./static/css/input.css -o ./static/css/styles.css --minify"
}
```

---

## Troubleshooting Common Issues

### 1. `ModuleNotFoundError: No module named 'xyz'`

**Cause:** A dependency is missing from `requirements.txt`.

**Fix:** Ensure all dependencies are listed in `requirements.txt`:
```bash
pip freeze > requirements.txt
```
Or manually verify that every imported third-party package is listed.

### 2. `Internal Server Error` (500) with No Logs

**Cause:** The application crashes during startup, often due to missing environment variables.

**Fix:**
- Check that all required environment variables are set in Vercel dashboard
- Verify `pydantic-settings` is using `extra="ignore"` in `SettingsConfigDict` to prevent crashes from Vercel-injected variables:
  ```python
  model_config = SettingsConfigDict(env_file=".env", extra="ignore")
  ```

### 3. `TypeError: unhashable type: 'dict'` from TemplateResponse

**Cause:** Using the old Starlette `TemplateResponse` API.

**Fix:** Use the new API format:
```python
# WRONG
return templates.TemplateResponse("page.html", {"request": request, "data": data})

# CORRECT
return templates.TemplateResponse(request, "page.html", context={"data": data})
```

### 4. Static Files Return 404

**Cause:** Incorrect `vercel.json` route configuration or missing static files.

**Fix:**
- Verify `vercel.json` has the static route BEFORE the catch-all route
- Confirm files exist in the `static/` directory
- Check that file paths in templates match the actual directory structure (case-sensitive)

### 5. `MissingGreenlet: greenlet_spawn has not been called`

**Cause:** SQLAlchemy lazy loading triggered in an async context.

**Fix:** Add `lazy="selectin"` to ALL `relationship()` declarations, and use `selectinload()` in queries where templates access related objects:
```python
from sqlalchemy.orm import selectinload

result = await db.execute(
    select(Model).options(selectinload(Model.related_items))
)
```

### 6. Database Resets on Every Request (Vercel)

**Cause:** SQLite database is stored in the ephemeral `/tmp` directory on Vercel.

**Fix:** This is expected behavior with SQLite on serverless. Migrate to PostgreSQL for persistent data. See [Migrating to PostgreSQL](#migrating-to-postgresql-for-production).

### 7. CORS Errors in Browser Console

**Cause:** The frontend origin is not in the `ALLOWED_ORIGINS` list.

**Fix:** Add the exact origin (including protocol and port) to the `ALLOWED_ORIGINS` environment variable:
```
ALLOWED_ORIGINS=https://your-app.vercel.app,https://your-custom-domain.com
```

### 8. `ValidationError` on Startup from Pydantic Settings

**Cause:** Vercel injects extra environment variables (e.g., `VERCEL`, `VERCEL_ENV`, `VERCEL_URL`) that Pydantic Settings does not expect.

**Fix:** Add `extra="ignore"` to your Settings class:
```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    # ... your fields
```

### 9. Slow Cold Starts

**Cause:** Large dependency tree or heavy initialization logic.

**Fix:**
- Minimize dependencies in `requirements.txt` — remove unused packages
- Defer heavy initialization (database table creation, embedding model loading) to first request rather than module import time
- Consider using Vercel's **Fluid Compute** or **Edge Functions** if available for your plan

### 10. Build Fails with `No module named 'main'`

**Cause:** The entry point file is not at the project root or is named differently.

**Fix:** Ensure `main.py` exists at the project root and matches the `src` field in `vercel.json`:
```json
{
  "builds": [
    {
      "src": "main.py",
      "use": "@vercel/python"
    }
  ]
}
```

---

## Production Checklist

Before deploying to production, verify:

- [ ] `SECRET_KEY` is set to a strong, unique random value (not the development default)
- [ ] `DEBUG` is set to `false`
- [ ] `ALLOWED_ORIGINS` contains only your production domain(s)
- [ ] `DATABASE_URL` points to a persistent database (PostgreSQL recommended)
- [ ] All passwords are hashed (never stored in plain text)
- [ ] `requirements.txt` contains all necessary dependencies with pinned versions
- [ ] `vercel.json` is properly configured with correct routes
- [ ] Static files are present and correctly referenced in templates
- [ ] Error handling returns appropriate HTTP status codes (not 200 for errors)
- [ ] Logging is configured at `INFO` level (not `DEBUG` in production)
- [ ] No `.env` file is committed to version control