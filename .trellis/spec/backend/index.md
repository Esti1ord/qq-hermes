# Backend Development Guidelines

> Best practices for backend development in this project.

---

## Overview

This directory captures executable backend contracts for the QQ Hermes bridge.
The most important current contracts are runtime module organization,
content-safe observability, and command fallback quality.

---

## Pre-Development Checklist

Before changing backend runtime, configuration, logging, or metrics:

1. Read [Directory Structure](./directory-structure.md) if touching `bridge.py`,
   `qq_hermes_bridge/runtime.py`, module layout, or deployment imports.
2. Read [Logging Guidelines](./logging-guidelines.md) if touching runtime stats,
   content analysis logs, `/metrics`, or observability env vars.
3. Read [Quality Guidelines](./quality-guidelines.md) for testing expectations
   once populated.
4. Always read shared guides in `.trellis/spec/guides/index.md`.

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Directory Structure](./directory-structure.md) | Module organization, runtime split, `bridge:app` compatibility contract | Active |
| [Database Guidelines](./database-guidelines.md) | ORM patterns, queries, migrations | Not applicable yet |
| [Error Handling](./error-handling.md) | Error types, handling strategies | To fill |
| [Quality Guidelines](./quality-guidelines.md) | Code standards, forbidden patterns | To fill |
| [Logging Guidelines](./logging-guidelines.md) | JSONL runtime stats and Prometheus `/metrics` contracts | Active |

---

**Language**: All documentation should be written in **English**.
