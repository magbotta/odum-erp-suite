FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# --- dependencies layer ---
FROM base AS deps
COPY requirements/base.txt requirements/base.txt
RUN pip install -r requirements/base.txt

# --- production image ---
FROM deps AS production
COPY requirements/production.txt requirements/production.txt
RUN pip install -r requirements/production.txt

COPY . .

RUN python manage.py collectstatic --noinput --settings=config.settings.production

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120"]

# --- development image ---
FROM deps AS development
COPY requirements/development.txt requirements/development.txt
RUN pip install -r requirements/development.txt

COPY . .
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
