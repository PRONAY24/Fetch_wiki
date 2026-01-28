# 🗺️ Distributed Systems Learning Roadmap

A quick reference for the distributed systems concepts being implemented in the Wikipedia Agent project.

---

## 📋 Phase Overview

| Phase | Technology | Status | Key Files |
|-------|------------|--------|-----------|
| **1** | Redis Caching | ✅ Complete | `cache.py`, `mcp_server.py` |
| **2** | PostgreSQL Database | ✅ Complete | `database.py`, `models.py`, `repository.py` |
| **3** | Message Queues | ⏳ Pending | `worker.py` |
| **4** | Docker | ⏳ Pending | `Dockerfile`, `docker-compose.yml` |
| **5** | Observability | ⏳ Pending | `observability.py` |
| **6** | Resilience Patterns | ⏳ Pending | Circuit breakers in `mcp_server.py` |
| **7** | Kubernetes | ⏳ Pending | `k8s/` directory |

---

## 🎯 What Each Phase Teaches

### Phase 1: Redis Caching ✅
**Concept**: Store frequently accessed data in memory for fast retrieval.

| Pattern | Implementation |
|---------|---------------|
| Cache-aside | Check cache → fetch on miss → store |
| TTL | 1hr for searches, 2hr for sections |
| Graceful degradation | Works without Redis |

**Endpoints**: `GET /api/cache/stats`, `DELETE /api/cache`

---

### Phase 2: PostgreSQL Database 🔄
**Concept**: Persist conversation history with ACID guarantees.

| Pattern | Implementation |
|---------|---------------|
| ORM | SQLAlchemy models |
| Connection pooling | Async connection pool |
| Migrations | Alembic |

**Tables**: `conversations`, `messages`

---

### Phase 3: Message Queues ⏳
**Concept**: Decouple long-running LLM calls from HTTP requests.

| Pattern | Implementation |
|---------|---------------|
| Producer-Consumer | FastAPI → Redis Queue → Worker |
| Job Status | Polling endpoint |
| Retry logic | Dead letter queue |

---

### Phase 4: Docker ⏳
**Concept**: Package application for consistent deployment.

| Component | Container |
|-----------|-----------|
| App | Python FastAPI |
| Cache | Redis |
| Database | PostgreSQL |
| Worker | Python worker |

---

### Phase 5: Observability ⏳
**Concept**: Understand system behavior through metrics, logs, traces.

| Pillar | Tool |
|--------|------|
| Metrics | Prometheus |
| Logs | Structured JSON |
| Traces | OpenTelemetry |
| Dashboards | Grafana |

---

### Phase 6: Resilience ⏳
**Concept**: Handle failures gracefully.

| Pattern | Purpose |
|---------|---------|
| Circuit Breaker | Stop calling failing services |
| Rate Limiting | Prevent overload |
| Retry + Backoff | Recover from transient failures |

---

### Phase 7: Kubernetes ⏳
**Concept**: Orchestrate containers at scale.

| Feature | Implementation |
|---------|---------------|
| Deployments | App replicas |
| Services | Internal networking |
| Ingress | External access |
| ConfigMaps/Secrets | Configuration |

---

## 🔗 Documentation Links

| Phase | Learning Guide |
|-------|---------------|
| 1 | [PHASE1_CACHING.md](./PHASE1_CACHING.md) |
| 2 | [PHASE2_DATABASE.md](./PHASE2_DATABASE.md) *(coming)* |
| 3 | [PHASE3_QUEUES.md](./PHASE3_QUEUES.md) *(coming)* |
| 4 | [PHASE4_DOCKER.md](./PHASE4_DOCKER.md) *(coming)* |
| 5 | [PHASE5_OBSERVABILITY.md](./PHASE5_OBSERVABILITY.md) *(coming)* |
| 6 | [PHASE6_RESILIENCE.md](./PHASE6_RESILIENCE.md) *(coming)* |
| 7 | [PHASE7_KUBERNETES.md](./PHASE7_KUBERNETES.md) *(coming)* |
