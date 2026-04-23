# app/logs/ Technical Documentation

## Purpose
Provides logging, metrics, and tracing infrastructure.

## Modules
- `logger.py`: app logger wrapper with structured helper methods.
- `metrics.py`: in-memory Prometheus-compatible counters/histograms.
- `tracing.py`: trace/span lifecycle manager with DB persistence support.

## Runtime Behavior
- HTTP middleware in `app/main.py` increments request/error metrics.
- Orchestrator creates spans for planning, step execution, verification, and task execution.
- Trace data is queryable via task trace API.
