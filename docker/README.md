# docker/

Containerization and local stack orchestration.

## Files

- `Dockerfile`: Python 3.11 runtime image for API/worker.
- `docker-compose.yml`: postgres + redis + api + celery worker services.

## Default Ports

- API: `8000`
- PostgreSQL: `5432`
- Redis: `6379`
