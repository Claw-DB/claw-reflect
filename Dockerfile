FROM python:3.14.5-slim-bookworm AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md ./
RUN uv pip install --system --prefix /install .


FROM python:3.14.5-slim-bookworm AS final

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY . /app

RUN useradd -m -u 1000 reflect
USER reflect

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8090/api/v1/health || exit 1

CMD ["uvicorn", "claw_reflect.main:app", "--host", "0.0.0.0", "--port", "8090"]
