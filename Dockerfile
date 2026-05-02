FROM python:3.11.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency specification first for layer caching
COPY pyproject.toml ./

# Install project dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir ".[dev]"

# Copy application source
COPY . .

# Create non-root user
RUN addgroup --system app && adduser --system --ingroup app app
USER app

EXPOSE 8090

CMD ["uvicorn", "claw_reflect.main:app", "--host", "0.0.0.0", "--port", "8090"]
