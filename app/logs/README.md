# app/logs/

Observability utilities.

## Files

- `logger.py`: lightweight structured logger wrapper.
- `metrics.py`: in-memory Prometheus-format counters/histograms.
- `tracing.py`: span lifecycle manager with DB persistence hooks.

## Usage

- HTTP middleware increments request/error counters and latency histogram.
- Orchestration pipeline creates planner/executor/verifier/task spans.
