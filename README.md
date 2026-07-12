# Odum ERP Suite

An open-source, fully self-hosted ERP platform designed to compete with Odoo, ERPNext, and Salesforce — with no license traps, no phone-home, and no paid tier.

**Stack:** Python 3.12 · Django 4.2 · Django Ninja · PostgreSQL 16 · Redis · Celery · React/TypeScript

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Module Catalogue](#module-catalogue)
- [Prerequisites](#prerequisites)
- [Local Development Setup](#local-development-setup)
- [Environment Variables](#environment-variables)
- [Running Tests](#running-tests)
- [Production Deployment — Docker Compose](#production-deployment--docker-compose)
- [Production Deployment — Kubernetes / Helm](#production-deployment--kubernetes--helm)
- [Bare-Metal Install (no Docker)](#bare-metal-install-no-docker)
- [First-Time Configuration](#first-time-configuration)
- [API Documentation](#api-documentation)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

Odum ERP Suite is a **modular monolith**: one deployable application, one database cluster, but internally organised into strictly bounded apps with no cross-app direct SQL joins. All cross-app interaction goes through internal service calls or the domain event bus.

Key differentiators:

| | Odoo | ERPNext | Salesforce | **Odum ERP Suite** |
|---|---|---|---|---|
| License | LGPL core / proprietary Enterprise | GPLv3 | Proprietary SaaS | **Apache-2.0, fully open** |
| Self-host | Community free; Enterprise paid | Yes, free | No | **Always free, always self-hosted** |
| Phone-home / license server | Enterprise requires it | No | N/A | **Never** |
| Metadata-driven entities | Partial | Yes (Frappe DocTypes) | No | **Yes — generates API, UI, migrations** |
| Mobile SDKs | No | No | Partial | **Auto-generated from OpenAPI schema** |

---

## Architecture

```
Clients (React SPA · PWA · Mobile SDKs · n8n)
        │
        ▼
  API Gateway (Django Ninja — typed REST + OpenAPI + GraphQL)
        │
  Auth & RBAC ──► Metadata Engine (entity definitions → schema, API, UI)
        │
  ┌─────┴────────────────────────────────────┐
  │  Core Apps          Industry Apps        │
  │  Accounting         Manufacturing        │
  │  CRM                POS / Retail         │
  │  HRM                Education SIS        │
  │  Payroll            Healthcare HIS       │
  │  Project Mgmt       Agriculture          │
  │  Purchasing         Nonprofit            │
  │  Sales              Telecom              │
  │  Warehouse          Government           │
  │  Asset Mgmt         Microfinance         │
  │  Website/CMS        Legal Services       │
  └─────┬────────────────────────────────────┘
        │
  Internal Event Bus (Celery + Redis)
        │
  PostgreSQL 16 (+ pgvector) · Redis · S3-compatible object storage
```

Every business entity is declared as a YAML **Entity Definition**. The metadata engine auto-generates the PostgreSQL migration, typed REST endpoint, OpenAPI docs, and CRUD UI — developers only write Python for the actual business-logic hooks.

---

## Module Catalogue

### Core Apps (installed by default)

| App | Key capabilities |
|---|---|
| **Accounting** | Multi-company GL, AR/AP, bank reconciliation, tax engine, budgeting, financial statements |
| **CRM** | Leads, pipeline, 360° account view, quoting/CPQ, territory & quota, case management |
| **HRM** | Employee lifecycle, leave, attendance (geo-fenced check-in, biometric bridge), shift scheduling |
| **Payroll** | Salary structures, payroll runs, statutory compliance packs, GL posting |
| **Project Management** | Gantt, kanban, timesheets, milestone billing, client portal |
| **Purchasing** | Requisition-to-PO, RFQ/RFx, 3-way match, vendor scorecarding, spend analytics |
| **Sales** | Order management, price lists, commissions, subscription billing, RMA |
| **Warehouse / Inventory** | Multi-warehouse, serial/batch/lot tracking, FIFO/FEFO/LIFO, MRP reorder |
| **Asset Management** | Lifecycle, depreciation schedules (SL/DDB), maintenance, RFID/barcode audit |
| **Website / CMS** | Drag-and-drop pages, e-commerce storefront, blog, web-to-CRM lead forms |

### Industry Apps (installable)

| App | Key capabilities |
|---|---|
| **Manufacturing** | BOM (multi-level), Work Orders, Work Centers, MRP |
| **POS / Retail** | Offline-first terminal, device bridge (scanners/printers/card terminals), till reconciliation |
| **Education SIS** | Admissions, scheduling, grading, IEP/504 case management, fee invoicing |
| **Healthcare HIS** | Patient records, CPOE, ADT ward/bed management, eMAR, insurance claims |
| **Agriculture** | Farm/plot registry with geo-boundaries, crop cycles, input tracking, harvest → Warehouse |
| **Nonprofit** | Fund accounting (restricted/unrestricted), donor moves management, grants, beneficiaries |
| **Telecom** | Subscriber/service registry, CDR rating, prepaid/postpaid billing |
| **Government** | OCDS tenders, GASB fund accounting with encumbrance, 311 case management, FOIA requests |
| **Microfinance** | Loan products (flat/declining/reducing amortisation), group lending, KYC/AML, teller cash |
| **Legal Services** | Matter management, IOLTA trust accounting, conflict-of-interest checks, LEDES billing |

---

## Prerequisites

| Tool | Minimum version | Notes |
|---|---|---|
| Python | 3.9+ | 3.12 recommended; 3.9 required for `.venv` on macOS Monterey |
| PostgreSQL | 16 | 15 works but 16 recommended for performance improvements |
| Redis | 7 | Session cache, Celery broker, pub/sub |
| Node.js | 18 LTS | Frontend build only |
| Docker + Compose | 24 / 2.20 | For containerised setup |
| Git | 2.x | |

---

## Local Development Setup

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/magbotta/odum-erp-suite.git
cd odum-erp-suite
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
```

### 2. Install Python dependencies

```bash
pip install -r requirements/development.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` — at minimum set:

```dotenv
SECRET_KEY=your-random-secret-key-here
DATABASE_URL=postgres://ochre:ochre@localhost:5432/ochre
REDIS_URL=redis://localhost:6379/0
```

Generate a secure secret key:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 4. Start PostgreSQL and Redis

If you have them installed locally:

```bash
# macOS (Homebrew)
brew services start postgresql@16
brew services start redis

# Linux (systemd)
sudo systemctl start postgresql redis
```

Or spin them up with Docker:

```bash
docker run -d --name ochre-db \
  -e POSTGRES_DB=ochre -e POSTGRES_USER=ochre -e POSTGRES_PASSWORD=ochre \
  -p 5432:5432 postgres:16-alpine

docker run -d --name ochre-redis -p 6379:6379 redis:7-alpine
```

### 5. Create the database and run migrations

```bash
createdb -U ochre ochre          # skip if using Docker above
python manage.py migrate
```

### 6. Create a superuser

```bash
python manage.py createsuperuser
```

### 7. Start the development server

```bash
# Terminal 1 — Django dev server
python manage.py runserver

# Terminal 2 — Celery worker (background jobs)
celery -A config worker -l info

# Terminal 3 — Celery Beat (scheduled tasks)
celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

The API is available at `http://localhost:8000/api/v1/` with interactive docs at `http://localhost:8000/api/v1/docs`.

### 8. (Optional) Docker Compose dev stack

All services in one command:

```bash
docker compose -f deploy/docker-compose/docker-compose.dev.yml up
```

---

## Environment Variables

All configuration is read from `.env` via `python-decouple`. Copy `.env.example` to `.env` and adjust.

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | Yes | — | Django secret key — generate with `get_random_secret_key()` |
| `DATABASE_URL` | Yes | `postgres://ochre:ochre@localhost:5432/ochre` | PostgreSQL connection string |
| `REDIS_URL` | No | `redis://localhost:6379/0` | Redis connection (cache) |
| `CELERY_BROKER_URL` | No | `redis://localhost:6379/1` | Celery broker |
| `CELERY_RESULT_BACKEND` | No | `redis://localhost:6379/2` | Celery result backend |
| `ALLOWED_HOSTS` | No | `localhost` | Comma-separated allowed host headers |
| `CORS_ALLOWED_ORIGINS` | No | `http://localhost:3000,http://localhost:5173` | Frontend origins |
| `DEFAULT_FROM_EMAIL` | No | `noreply@ochre.local` | Outbound email sender |
| `DJANGO_SETTINGS_MODULE` | No | `config.settings.development` | Settings module |
| `POSTGRES_PASSWORD` | No | `ochre` | Used by Docker Compose for the DB container |

---

## Running Tests

```bash
# All tests
pytest

# With coverage report
pytest --cov=apps --cov=core --cov-report=term-missing

# A single app
pytest apps/accounting/

# Keep the test database between runs (faster)
pytest --reuse-db
```

---

## Production Deployment — Docker Compose

This is the recommended path for single-server and small-team deployments (up to ~500 users).

### 1. Prepare the server

```bash
# Install Docker and Docker Compose (Ubuntu 22.04 example)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

### 2. Clone the repository

```bash
git clone https://github.com/magbotta/odum-erp-suite.git
cd odum-erp-suite
```

### 3. Configure environment

```bash
cp .env.example .env
```

Set production values in `.env`:

```dotenv
SECRET_KEY=<long-random-string>
DATABASE_URL=postgres://ochre:<strong-password>@db:5432/ochre
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
POSTGRES_PASSWORD=<strong-password>
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DJANGO_SETTINGS_MODULE=config.settings.production
```

### 4. Configure TLS (Caddy)

Edit `deploy/docker-compose/caddy/Caddyfile` and replace the placeholder domain:

```
yourdomain.com {
    reverse_proxy app:8000
    handle /static/* {
        root * /srv
        file_server
    }
    handle /media/* {
        root * /srv
        file_server
    }
}
```

Caddy automatically provisions and renews a Let's Encrypt certificate when the domain resolves to your server's public IP.

### 5. Build and start

```bash
docker compose -f deploy/docker-compose/docker-compose.yml up -d --build
```

This starts:
- `db` — PostgreSQL 16
- `redis` — Redis 7
- `app` — Django/Gunicorn (runs `migrate` on startup)
- `worker` — Celery worker (4 concurrent tasks)
- `beat` — Celery Beat scheduler
- `caddy` — Reverse proxy with automatic TLS

### 6. Create the first admin user

```bash
docker compose -f deploy/docker-compose/docker-compose.yml \
  exec app python manage.py createsuperuser
```

### Updating

```bash
git pull
docker compose -f deploy/docker-compose/docker-compose.yml up -d --build
```

Migrations run automatically on container start.

### Backups

```bash
# Dump the database
docker compose -f deploy/docker-compose/docker-compose.yml \
  exec db pg_dump -U ochre ochre > ochre_$(date +%Y%m%d).sql

# Restore
docker compose -f deploy/docker-compose/docker-compose.yml \
  exec -T db psql -U ochre ochre < ochre_20240101.sql
```

---

## Production Deployment — Kubernetes / Helm

For high-availability and larger deployments.

### Prerequisites

- A Kubernetes cluster (1.28+)
- `helm` 3.x installed
- A PostgreSQL instance (managed or in-cluster)
- A Redis instance (managed or in-cluster)
- An S3-compatible object store for media files

### Install

```bash
cd deploy/helm

# Customise values
cp values.yaml values.local.yaml
# Edit values.local.yaml with your image, DB/Redis URLs, ingress host, etc.

helm install ochre . -f values.local.yaml --namespace ochre --create-namespace
```

### Upgrade

```bash
helm upgrade ochre . -f values.local.yaml --namespace ochre
```

### Key Helm values

```yaml
image:
  repository: ghcr.io/magbotta/odum-erp-suite
  tag: "latest"

env:
  SECRET_KEY: "..."
  DATABASE_URL: "postgres://..."
  REDIS_URL: "redis://..."
  ALLOWED_HOSTS: "yourdomain.com"

ingress:
  enabled: true
  host: yourdomain.com
  tls: true

replicaCount:
  app: 2
  worker: 2
```

---

## Bare-Metal Install (no Docker)

For environments where containers are not permitted (some government/regulated-industry deployments).

```bash
# 1. Install system dependencies (Ubuntu/Debian)
sudo apt-get update && sudo apt-get install -y \
  python3.12 python3.12-venv python3.12-dev \
  libpq-dev gcc nginx redis-server postgresql-16

# 2. Create a system user
sudo useradd --system --create-home --shell /bin/bash ochre

# 3. Clone and install
sudo -u ochre git clone https://github.com/magbotta/odum-erp-suite.git /opt/odum-erp-suite
cd /opt/odum-erp-suite
sudo -u ochre python3.12 -m venv .venv
sudo -u ochre .venv/bin/pip install -r requirements/production.txt

# 4. Configure environment
sudo -u ochre cp .env.example .env
# Edit /opt/odum-erp-suite/.env

# 5. Migrate and collect static files
sudo -u ochre .venv/bin/python manage.py migrate
sudo -u ochre .venv/bin/python manage.py collectstatic --noinput

# 6. Create systemd service files for app, worker, and beat
# (example unit files are in deploy/systemd/ — copy and enable them)
sudo systemctl enable --now ochre-app ochre-worker ochre-beat
```

Serve with nginx as a reverse proxy pointed at Gunicorn on `127.0.0.1:8000`.

---

## First-Time Configuration

After the server is running and you have logged in as a superuser, do the following from the Django admin (`/admin/`) or the API:

1. **Create a Company** — set your company name, currency, and fiscal year start.
2. **Configure a Chart of Accounts** — import a country-specific COA template from Accounting, or build one manually.
3. **Set up document numbering series** — in Numbering, define series prefixes for Invoices, POs, Payroll runs, etc.
4. **Add users and assign roles** — create users and assign them roles (Accountant, Sales Rep, HR Manager, etc.) scoped to the company.
5. **Install industry apps** — activate only the apps your deployment needs. An education nonprofit installs Core + Nonprofit + Education SIS and skips Manufacturing, Telecom, and Microfinance.

---

## API Documentation

Interactive OpenAPI (Swagger) docs are available at:

```
http(s)://yourdomain.com/api/v1/docs
```

The API uses **JWT Bearer tokens** for authentication:

```bash
# Obtain a token
curl -X POST https://yourdomain.com/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "yourpassword"}'

# Use the token
curl https://yourdomain.com/api/v1/accounting/sales-invoice \
  -H "Authorization: Bearer <access_token>"
```

**API key authentication** is also supported for service-to-service integrations (n8n, webhooks, etc.) — create an API key from the admin panel and pass it as `Authorization: Api-Key <key>`.

All entity endpoints follow a consistent pattern:

| Method | Path | Action |
|---|---|---|
| `GET` | `/api/v1/{app}/{entity}` | List (paginated, filterable) |
| `POST` | `/api/v1/{app}/{entity}` | Create |
| `GET` | `/api/v1/{app}/{entity}/{id}` | Retrieve |
| `PUT` | `/api/v1/{app}/{entity}/{id}` | Update |
| `DELETE` | `/api/v1/{app}/{entity}/{id}` | Soft-delete |

Workflow action endpoints use `POST` with a verb path, e.g.:

```
POST /api/v1/accounting/sales-invoices/{id}/submit
POST /api/v1/microfinance/loans/{id}/disburse
POST /api/v1/government/tenders/{id}/award
```

---

## Project Structure

```
odum-erp-suite/
├── config/                  # Django settings (base, development, production)
│   ├── settings/
│   ├── urls.py
│   └── wsgi.py / asgi.py
│
├── core/                    # Platform foundation
│   ├── auth/                # OchreUser, Company, RBAC, JWT/API key auth, SSO
│   ├── audit/               # Universal audit trail (every write versioned)
│   ├── metadata_engine/     # Entity definition parser → schema, API, UI generator
│   ├── numbering/           # Atomic document number series
│   └── platform_api/        # Main NinjaAPI instance; all routers mounted here
│
├── apps/                    # Business apps (core + industry)
│   ├── accounting/          # GL, AR, AP, banking, tax, budgeting
│   ├── crm/                 # Leads, pipeline, cases, quoting
│   ├── hrm/                 # Employees, leave, attendance, recruitment
│   ├── payroll/             # Salary structures, payroll runs, slips
│   ├── project/             # Tasks, timesheets, milestones
│   ├── purchasing/          # Requisitions, POs, GRN, vendor management
│   ├── sales/               # Orders, quotations, commissions
│   ├── warehouse/           # Stock, items, stock entries, ledger
│   ├── asset_management/    # Assets, depreciation, maintenance
│   ├── website/             # Pages, blog, web forms
│   ├── manufacturing/       # BOM, work orders, MRP
│   ├── pos/                 # POS terminal, sessions, offline queue
│   ├── education_sis/       # Students, enrollment, grading, fees
│   ├── healthcare_his/      # Patients, appointments, clinical orders
│   ├── agriculture/         # Farms, plots, crop cycles, harvests
│   ├── nonprofit/           # Donors, donations, grants, beneficiaries
│   ├── telecom/             # Subscribers, plans, CDR, billing
│   ├── government/          # Tenders (OCDS), GASB funds, 311, FOIA
│   ├── microfinance/        # Loans, savings, group lending, KYC, teller
│   └── legal_services/      # Matters, trust accounts, time & billing
│
├── frontend/                # React/TypeScript SPA (metadata-driven views)
├── deploy/
│   ├── docker-compose/      # Production + dev Compose files, Caddyfile
│   └── helm/                # Kubernetes Helm chart
├── Dockerfile               # Multi-stage: base → deps → production/development
├── manage.py
├── pyproject.toml           # Ruff, mypy, pytest config
└── requirements/
    ├── base.txt
    ├── development.txt
    └── production.txt
```

Each app directory follows the same layout:

```
apps/<app>/
├── __init__.py
├── apps.py          # AppConfig with entity_dir = "entities"
├── models.py        # Django models (all extend BaseEntity)
├── api.py           # Django Ninja Router — workflow action endpoints
├── entities/        # YAML entity definitions (auto-generate CRUD API + UI)
│   └── *.yaml
├── hooks/           # Business logic called from entity lifecycle events
│   └── *.py
└── migrations/
    └── 0001_initial.py
```

---

## Contributing

1. Fork the repository and create a feature branch off `main`.
2. Follow the app layout above — new modules are self-contained apps.
3. Entity YAML field types must be one of: `string`, `text`, `integer`, `float`, `boolean`, `date`, `datetime`, `currency`, `link`, `table`, `select`, `multiselect`, `email`, `phone`, `url`, `json`, `geopoint`, `geofence`, `route`.
4. Cross-app references use `UUIDField` (loose coupling) — never import another app's models directly.
5. Run `python manage.py check` (0 issues) and `pytest` before opening a PR.
6. All PRs are checked by the CI pipeline: linting (Ruff), type checking (mypy), tests, migration safety, and import-boundary contracts.

---

## License

Apache License 2.0 — see [LICENSE](LICENSE) for the full text.

Odum ERP Suite is free to use, modify, and self-host forever. There is no Enterprise tier, no license server, and no phone-home.
