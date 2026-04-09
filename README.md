# ProjectForge

A comprehensive project management platform built with Python and FastAPI, featuring task tracking, sprint management, team collaboration, and real-time project insights.

## Features

- **User Authentication & Authorization** — Secure login/registration with role-based access control (Super Admin, Project Manager, Developer, QA, Viewer)
- **Project Management** — Create, configure, and manage multiple projects with customizable workflows
- **Sprint Planning** — Plan and track sprints with backlog grooming, capacity planning, and burndown charts
- **Ticket/Task Tracking** — Full-featured ticket system with priorities, labels, assignments, and status transitions
- **Team Collaboration** — Comments, activity feeds, mentions, and notifications
- **Dashboard & Analytics** — Real-time project health metrics, velocity tracking, and team performance insights
- **Audit Logging** — Complete activity trail for compliance and accountability
- **Document & Knowledge Base** — RAG-powered search across project documentation using vector embeddings

## Tech Stack

- **Backend:** Python 3.11+, FastAPI
- **Database:** SQLite (via aiosqlite for async), SQLAlchemy 2.0 (async)
- **Templating:** Jinja2 with Tailwind CSS
- **Authentication:** JWT (python-jose) + bcrypt password hashing
- **Vector Search:** ChromaDB for RAG-powered document search
- **Embeddings:** OpenAI API
- **Task Queue:** FastAPI BackgroundTasks
- **Server:** Uvicorn (ASGI)

## Folder Structure

```
projectforge/
├── main.py                  # FastAPI application entry point
├── config.py                # Pydantic Settings configuration
├── database.py              # Async SQLAlchemy engine & session setup
├── requirements.txt         # Python dependencies
├── .env                     # Environment variables (not committed)
├── .env.example             # Environment variable template
├── models/
│   ├── __init__.py          # Model re-exports
│   ├── user.py              # User model
│   ├── project.py           # Project model
│   ├── sprint.py            # Sprint model
│   ├── ticket.py            # Ticket model
│   ├── comment.py           # Comment model
│   ├── label.py             # Label model
│   ├── audit_log.py         # Audit log model
│   └── document.py          # Document model
├── schemas/
│   ├── __init__.py
│   ├── user.py              # User request/response schemas
│   ├── project.py           # Project schemas
│   ├── sprint.py            # Sprint schemas
│   ├── ticket.py            # Ticket schemas
│   ├── comment.py           # Comment schemas
│   └── document.py          # Document schemas
├── routes/
│   ├── __init__.py
│   ├── auth.py              # Authentication routes
│   ├── users.py             # User management routes
│   ├── projects.py          # Project routes
│   ├── sprints.py           # Sprint routes
│   ├── tickets.py           # Ticket routes
│   ├── comments.py          # Comment routes
│   ├── dashboard.py         # Dashboard & analytics routes
│   └── documents.py         # Document & search routes
├── services/
│   ├── __init__.py
│   ├── auth_service.py      # Authentication logic
│   ├── user_service.py      # User business logic
│   ├── project_service.py   # Project business logic
│   ├── sprint_service.py    # Sprint business logic
│   ├── ticket_service.py    # Ticket business logic
│   ├── embedding_service.py # Vector embedding generation
│   └── search_service.py    # RAG search logic
├── dependencies/
│   ├── __init__.py
│   ├── auth.py              # Auth dependency (get_current_user)
│   └── database.py          # DB session dependency
├── templates/
│   ├── base.html            # Base layout with Tailwind
│   ├── login.html           # Login page
│   ├── register.html        # Registration page
│   ├── dashboard.html       # Main dashboard
│   ├── projects/
│   │   ├── list.html
│   │   ├── detail.html
│   │   └── form.html
│   ├── sprints/
│   │   ├── list.html
│   │   ├── detail.html
│   │   └── form.html
│   ├── tickets/
│   │   ├── list.html
│   │   ├── detail.html
│   │   └── form.html
│   └── documents/
│       ├── list.html
│       └── search.html
├── static/
│   └── css/
│       └── styles.css       # Custom styles (if any)
└── tests/
    ├── conftest.py          # Pytest fixtures
    ├── test_auth.py
    ├── test_projects.py
    ├── test_tickets.py
    └── test_sprints.py
```

## Setup Instructions

### Prerequisites

- Python 3.11 or higher
- pip (Python package manager)
- Git

### 1. Clone the Repository

```bash
git clone <repository-url>
cd projectforge
```

### 2. Create a Virtual Environment

```bash
python -m venv venv

# Activate on macOS/Linux
source venv/bin/activate

# Activate on Windows
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` with your configuration (see [Environment Variables](#environment-variables) below).

### 5. Run the Application

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The application will be available at [http://localhost:8000](http://localhost:8000).

## Environment Variables

| Variable | Description | Default | Required |
|---|---|---|---|
| `DATABASE_URL` | SQLite database connection string | `sqlite+aiosqlite:///./projectforge.db` | No |
| `SECRET_KEY` | JWT signing secret (use a strong random string) | — | **Yes** |
| `ALGORITHM` | JWT algorithm | `HS256` | No |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT token expiry in minutes | `1440` (24 hours) | No |
| `OPENAI_API_KEY` | OpenAI API key for embeddings | — | No (required for RAG search) |
| `CHROMA_DB_PATH` | Path to ChromaDB persistent storage | `./chroma_data` | No |
| `CORS_ORIGINS` | Comma-separated allowed origins | `http://localhost:3000,http://localhost:8000` | No |
| `ENVIRONMENT` | Runtime environment (`development`, `production`) | `development` | No |
| `LOG_LEVEL` | Logging level | `INFO` | No |

### Example `.env` File

```env
DATABASE_URL=sqlite+aiosqlite:///./projectforge.db
SECRET_KEY=your-super-secret-key-change-this-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
OPENAI_API_KEY=sk-your-openai-api-key
CHROMA_DB_PATH=./chroma_data
CORS_ORIGINS=http://localhost:3000,http://localhost:8000
ENVIRONMENT=development
LOG_LEVEL=INFO
```

## Default Credentials

On first startup, the application seeds a default Super Admin account:

| Field | Value |
|---|---|
| **Email** | `admin@projectforge.com` |
| **Password** | `admin123456` |
| **Role** | `Super Admin` |

> ⚠️ **Important:** Change the default admin password immediately after first login in production environments.

## Usage Guide

### Getting Started

1. **Log in** with the default admin credentials at `/auth/login`
2. **Create a project** from the Projects page — set a name, description, and key prefix
3. **Invite team members** by creating user accounts and assigning roles
4. **Create sprints** within your project to organize work into iterations
5. **Add tickets** with priorities, labels, and assignees to track tasks
6. **Track progress** on the Dashboard with velocity charts and sprint burndowns

### User Roles

| Role | Permissions |
|---|---|
| **Super Admin** | Full system access — manage all users, projects, and settings |
| **Project Manager** | Manage assigned projects, sprints, and team members |
| **Developer** | Create/update tickets, log work, comment on tasks |
| **QA** | Create bug reports, update ticket statuses, add comments |
| **Viewer** | Read-only access to assigned projects |

### API Documentation

FastAPI auto-generates interactive API documentation:

- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

## Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_auth.py

# Run with coverage
pytest --cov=. --cov-report=html
```

## Deployment

### Vercel Deployment

1. Install the Vercel CLI:
   ```bash
   npm install -g vercel
   ```

2. Create a `vercel.json` in the project root:
   ```json
   {
     "builds": [
       {
         "src": "main.py",
         "use": "@vercel/python"
       }
     ],
     "routes": [
       {
         "src": "/(.*)",
         "dest": "main.py"
       }
     ]
   }
   ```

3. Set environment variables in the Vercel dashboard (Project Settings → Environment Variables). Ensure `SECRET_KEY` and all required variables are configured.

4. Deploy:
   ```bash
   vercel --prod
   ```

> **Note:** SQLite is ephemeral on Vercel's serverless platform. For production deployments on Vercel, consider using an external PostgreSQL database (e.g., Vercel Postgres, Supabase, or Neon) and update `DATABASE_URL` accordingly. ChromaDB persistent storage also requires a persistent filesystem — consider using a managed vector database service for production.

### Docker Deployment

```bash
# Build the image
docker build -t projectforge .

# Run the container
docker run -d \
  --name projectforge \
  -p 8000:8000 \
  -e SECRET_KEY=your-production-secret \
  -e DATABASE_URL=sqlite+aiosqlite:///./data/projectforge.db \
  -v projectforge_data:/app/data \
  projectforge
```

## License

**Private** — All rights reserved. This software is proprietary and confidential. Unauthorized copying, distribution, or modification is strictly prohibited.