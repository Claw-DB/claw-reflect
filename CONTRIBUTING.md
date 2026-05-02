# Contributing

## Development Setup

1. Copy .env.example to .env and configure values.
2. Start dependencies:

```bash
docker-compose up --build
```

## Run Tests

```bash
pytest tests/ -x --cov=claw_reflect --cov-report=xml
```

## Lint and Type Check

```bash
ruff check .
ruff format --check .
mypy claw_reflect --strict
```

## PR Checklist

- [ ] Tests added or updated
- [ ] Migrations added (if schema changed)
- [ ] Security implications documented
- [ ] Backward compatibility reviewed
