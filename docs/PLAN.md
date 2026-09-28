# Network Security Operations Platform — Revised Plan

**Version 2 — revised from the original AGENT.md spec**
Owner: Khaled Sharafeddin · Date: 18 Sep 2026

---

## 0. How to read this document

Every technical term is explained the first time it appears, and again in the
**Glossary** at the end. If a term appears without explanation, that is a bug in
this document — flag it.

This plan replaces the original spec. Section 1 explains what changed and why.

---

## 1. Review of the original spec

The original spec is good. The core idea is coherent and the "don't
over-engineer" instincts in sections 29–31 are correct. But it has real gaps
for a project meant to be led by security, and it carries some weight it
doesn't need.

### 1.1 What was wrong or missing

| # | Issue | Why it matters | Fix |
|---|---|---|---|
| 1 | **No MITRE ATT&CK mapping** | ATT&CK is *the* shared vocabulary of the security industry. An alert that doesn't name a technique looks amateur to anyone who has worked a SOC shift. | Every detection rule carries a technique ID (e.g. `T1046`). Shown in the UI and the API. |
| 2 | **Detection rules hardcoded in application code** | Real detection engineers write rules as *data*, not code, so rules can be reviewed, versioned and shared without a rebuild. | Rules defined in YAML files, loaded at startup. Modelled on the Sigma open standard. |
| 3 | **No alert deduplication** | A single `nmap` scan produces thousands of events. A naive rule engine emits thousands of alerts. This is the #1 thing that separates a toy from a credible platform. | Deduplication key + suppression window per rule. One scan → one alert with an event count. |
| 4 | **No enrichment layer** | Raw IP addresses mean nothing to an analyst. Real pipelines add context before the analyst ever sees the alert. | Enrichment step: internal/external classification, asset lookup, GeoIP, threat-intel IOC match. This also gives the orphaned `threat_indicators` table a real purpose. |
| 5 | **No detection testing** | "Does the rule fire?" and "does it fire when it shouldn't?" is the actual daily job of detection engineering. The spec's testing section misses it entirely. | Every rule ships with fixture files: events that must fire it, and events that must not. Run in CI. |
| 6 | **Risk score never decays** | A device that got scanned once in March stays at 85/100 forever. Obviously wrong, and an interviewer will spot it in ten seconds. | Exponential decay with a configurable half-life. |
| 7 | **No audit trail on incidents** | Case management without an immutable record of who changed what is not case management. Cheap to add, reads as enterprise-grade. | `incident_audit_log` table, append-only. |
| 8 | **No investigation playbooks** | You already have real SOC investigation write-ups (Cloudora). Linking each rule to a written investigation procedure connects that existing work to this project. | Markdown playbook per rule, rendered in the alert detail view. |
| 9 | **Postgres used as a plain relational store for time-series data** | Network events are high-volume time-series. The spec never mentions partitioning or retention, so "how would you handle millions of events?" has no answer. | TimescaleDB — a PostgreSQL *extension*, not a different database. Adds automatic time partitioning and retention policies. |
| 10 | **Zeek AND Suricata both in scope** | They do different jobs and doubling up doubles the setup pain for no extra learning early on. | Zeek first (it produces the connection metadata the rules actually need). Suricata added later as a second sensor, to demonstrate multi-source correlation. |
| 11 | **Attack simulation buried as an afterthought** | The demo is the portfolio. Without reproducible attacks there is nothing to demo. | First-class component: an `attacker` container with one command per scenario. |
| 12 | **Windows development environment not addressed** | You develop on Windows/PowerShell. Zeek, packet capture and Docker networking need a real Linux kernel. This will block you on day one if unaddressed. | WSL2 is Phase 0. Non-negotiable. |
| 13 | **Frontend technology unspecified** | "Build a polished web dashboard" with no stack named is where portfolio projects go to die. | Decided below (§2.3). |

### 1.2 What to cut

| Cut | Reason |
|---|---|
| **Power BI** | Adds nothing you can't do in the dashboard. Licensing friction. |
| **Kubernetes** | No scaling problem exists here. Docker Compose is the honest answer. |
| **AWS deployment** | Costs money, adds no security or backend signal. A well-argued README section on *how* you would deploy it is worth nearly as much and costs nothing. |
| **Prometheus + Grafana** | The dashboard *is* the observability story for this project. Adding a second dashboard stack is duplicate work. Health endpoint + structured logs only. |
| **Machine learning / anomaly detection** | Correctly flagged as optional in the original. Keeping it cut. Statistical baselining (§Phase 9) is the honest version and is enough. |
| **WebSocket** | Server-Sent Events does the same job here with a fraction of the complexity. |
| **Separate `detection-engine/` service** | Now that the whole backend is Python, detection is a *module* in one codebase, not a service over a network boundary. Nothing is gained by splitting it. |

### 1.3 What to add

- MITRE ATT&CK technique mapping on every rule
- YAML-defined rules (Sigma-inspired)
- Alert deduplication and suppression windows
- Enrichment pipeline (asset, geo, threat intel)
- Rule test fixtures running in CI
- Risk score decay
- Incident audit log
- Investigation playbooks per rule
- Reproducible attack scenario runner
- A tuning/allowlist mechanism (suppress known-good behaviour — e.g. the monitoring server legitimately scans ports)

---

## 2. Technology decisions

### 2.1 Language: Python

**Decision: Python everywhere. No Java.**

Reasoning:

- Your Java/Spring Boot signal is already covered by the completed e-commerce
  microservices project. A second Spring Boot project adds repetition, not range.
- Security tooling is overwhelmingly Python. Every SOC job description that
  mentions scripting means Python. This project becomes *evidence* for that line
  on your resume instead of just a claim.
- The analytics layer stops being a separate integration problem. Same language,
  same process, same data models. This alone removes a whole category of work.
- Zeek log parsing, packet handling, threat-intel clients — all have mature
  Python libraries and awkward or absent Java ones.

**The cost, stated honestly:** a Java-shop interviewer in KSA will see one Java
project instead of two. That is an acceptable trade given the e-commerce project
exists and this one is security-led.

### 2.2 Backend stack

| Layer | Choice | What it is |
|---|---|---|
| Web framework | **FastAPI** | Python framework for building APIs. Generates interactive API documentation automatically (Swagger UI). |
| Data validation | **Pydantic** | Defines the shape of data (required fields, types, ranges) and rejects anything that doesn't match. Built into FastAPI. |
| Database access | **SQLAlchemy 2.0** | ORM — Object Relational Mapper. Lets you work with database rows as Python objects instead of writing raw SQL everywhere. |
| Schema migrations | **Alembic** | Tracks database schema changes as versioned scripts, so the schema can be rebuilt or rolled back reproducibly. |
| Database | **PostgreSQL 16 + TimescaleDB** | TimescaleDB is an extension that adds automatic time-based partitioning. Still ordinary Postgres. |
| Background jobs | **APScheduler** | Runs a function on a schedule (e.g. "evaluate detection rules every 30 seconds"). |
| Auth | **PyJWT + Argon2** | JWT for stateless login tokens; Argon2 for password hashing (stronger than bcrypt, current best practice). |
| Testing | **pytest + testcontainers** | testcontainers spins up a real throwaway Postgres in Docker for integration tests, instead of faking the database. |
| Analytics | **pandas + matplotlib** | Same codebase. |

### 2.3 Frontend

**Decision: Jinja2 templates + HTMX + Tailwind CSS, server-rendered.**

- **Jinja2** — Python's templating engine; HTML files with placeholders the
  server fills in.
- **HTMX** — a small JavaScript library that lets HTML elements request new HTML
  from the server and swap it into the page, without writing JavaScript. It also
  handles Server-Sent Events, which gives us live-updating alerts for free.
- **Tailwind CSS** — utility CSS classes, so the dashboard looks professional
  without designing a stylesheet from scratch.

Why not React: a React frontend is a second application with its own build
system, dependency tree and deployment. For a backend-and-security-led project
it consumes time that should go into detection logic, and it is not what you
are being hired for. HTMX gets a live dashboard in a fraction of the effort.

If, at the end, you want a React version for the frontend line on your resume,
it can be added as a separate consumer of the same API. Not before.

### 2.4 Everything else

Docker + Docker Compose, Git/GitHub, GitHub Actions, Zeek, WSL2 (Ubuntu), pytest.

---

## 3. Architecture

```text
┌───────────────────────────────────────────────────────────┐
│  LAB NETWORK  (Docker networks, isolated, no internet)     │
│                                                            │
│   10.0.20.0/24 workstations ──┐                            │
│                               ├──► 10.0.10.0/24 servers    │
│   attacker container ─────────┘     (web, ssh, db)         │
└───────────────────┬────────────────────────────────────────┘
                    │ mirrored traffic
                    ▼
        ┌────────────────────────┐
        │  ZEEK SENSOR            │  writes conn.log, ssh.log,
        │  (10.0.30.0/24)         │  dns.log, http.log as JSON
        └───────────┬─────────────┘
                    │ tails log files
                    ▼
        ┌────────────────────────────────────────────────┐
        │  PLATFORM  (one FastAPI application)            │
        │                                                 │
        │  ingest ──► enrich ──► store                    │
        │                          │                      │
        │              detection engine (every 30s)       │
        │              reads YAML rules, queries windows  │
        │                          │                      │
        │              dedupe ──► alert ──► risk scoring  │
        │                          │                      │
        │              analyst escalates ──► incident     │
        │                                                 │
        │  REST API  ·  SSE stream  ·  HTMX dashboard     │
        └───────────────────┬─────────────────────────────┘
                            ▼
                ┌────────────────────────┐
                │ PostgreSQL + Timescale │
                └────────────────────────┘
```

**One deployable application, five clean internal modules:** `ingest`,
`enrich`, `detect`, `respond` (alerts/incidents/risk), `api`.

---

## 4. Data model (revised)

```text
users                 analysts and admins
assets                known devices (renamed from "devices" — SOC term)
network_events        raw telemetry, Timescale hypertable, 30-day retention
detection_rules       rule metadata synced from the YAML files
alerts                rule output, deduplicated
alert_events          links an alert to the events that triggered it
incidents             analyst-owned cases
incident_alerts       many-to-many: an incident groups several alerts
incident_notes        analyst commentary
incident_audit_log    append-only: who changed what, when
threat_indicators     known-bad IPs/domains, used by enrichment
risk_scores           current score per asset
risk_score_history    time series, so we can chart risk over time
suppressions          tuning rules — known-good behaviour to ignore
```

Changes from the original: `devices` → `assets`, `incident_evidence` split into
`incident_alerts` + `incident_notes`, and four new tables (`alert_events`,
`incident_audit_log`, `risk_score_history`, `suppressions`,
`detection_rules`).

---

## 5. Phase plan

Each phase ends with something that **works and can be demonstrated**. No phase
depends on a later phase. Steps are small on purpose.

### Phase 0 — Environment (do this first, it will otherwise block you)

1. Install WSL2 with Ubuntu on Windows
2. Install Docker Desktop with the WSL2 backend
3. Install Python 3.12 inside WSL2
4. Confirm: `docker run hello-world` works from inside WSL2
5. Create the GitHub repository, `.gitignore`, `README.md` skeleton, LICENSE

**Done when:** you can run a Linux container from an Ubuntu shell on your Windows machine.

### Phase 1 — Walking skeleton

The smallest thing that is end-to-end real: one endpoint, one table, one test.

1. FastAPI project structure, virtual environment, dependencies
2. Docker Compose with `api` and `db` services
3. Postgres + TimescaleDB container running
4. Alembic configured, first migration creating `assets`
5. `GET /health` returning database connectivity status
6. Full CRUD for `/api/assets`
7. pytest + testcontainers, first integration test

**Done when:** `docker compose up` gives you a working API with Swagger docs.

### Phase 2 — Authentication and authorization

1. `users` table, Argon2 password hashing
2. `POST /api/auth/register`, `POST /api/auth/login` issuing a JWT
3. Token verification dependency
4. Roles: ADMIN, ANALYST, VIEWER — enforced per endpoint
5. Security tests: no token, expired token, wrong role, tampered token

**Done when:** a VIEWER token is rejected from a write endpoint, proven by a test.

### Phase 3 — Event ingestion

1. `network_events` as a Timescale hypertable with a retention policy
2. Pydantic model for a network event
3. `POST /api/events` — single and batch
4. `GET /api/events` with filtering, pagination and sorting
5. Indexes tuned for the queries the detection rules will run
6. A seed script generating realistic benign traffic

**Done when:** you can ingest 100,000 synthetic events and query them in under a second.

### Phase 4 — Enrichment

1. Internal vs. external IP classification
2. Asset lookup — attach the known asset record to each event
3. `threat_indicators` table + loader for a public IOC feed
4. IOC matching on ingest

**Done when:** ingested events arrive already annotated with asset and threat context.

### Phase 5 — Detection engine (the heart of the project)

1. YAML rule format design + loader + validator
2. Rule execution scheduler (every 30s, over a sliding time window)
3. Rule 1 — Port scan (ATT&CK `T1046`)
4. Rule 2 — SSH brute force (`T1110.001`)
5. Rule 3 — Suspicious outbound / possible C2 beaconing (`T1071`)
6. Rule 4 — Repeated connection failures (`T1046`)
7. Deduplication keys + suppression windows
8. Suppressions (tuning) table and enforcement
9. Test fixtures per rule: must-fire and must-not-fire event sets

**Done when:** a replayed scan produces exactly one HIGH alert, and benign traffic produces zero.

### Phase 6 — Risk scoring

1. Configurable weights per rule severity
2. Exponential decay with a configurable half-life
3. Recalculation on new alert + on a timer
4. `risk_score_history` written on every change
5. Unit tests for the decay maths

**Done when:** a scanned device's score spikes, then visibly decays over the following hours.

### Phase 7 — Alerts and incidents

1. Alert state machine: NEW → ACKNOWLEDGED → INVESTIGATING → RESOLVED / FALSE_POSITIVE
2. Incident creation from one or more alerts
3. Assignment, severity change, notes
4. Audit log written on every mutation
5. Investigation playbooks in markdown, linked per rule

**Done when:** you can run the full analyst workflow through the API alone.

### Phase 8 — Dashboard

1. Jinja2 + Tailwind base layout
2. Overview: counts, top attacked assets, attack type distribution
3. Alert queue with filters
4. Alert detail with triggering events and the playbook
5. Incident workspace
6. Asset risk table + risk-over-time chart
7. SSE live updates for new critical alerts

**Done when:** the demo story can be told entirely through the browser.

### Phase 9 — Network lab and real telemetry

1. Docker Compose lab: gateway, web server, ssh server, two workstations
2. Three segmented Docker networks (servers / workstations / monitoring)
3. Benign traffic generator container
4. Attacker container with named scenarios: `portscan`, `sshbrute`, `beacon`
5. Zeek sensor container with traffic mirrored to it
6. Zeek JSON log tailer feeding `POST /api/events`

**Done when:** running `make attack-portscan` produces a real alert in the dashboard, end to end, with no synthetic data anywhere in the path.

### Phase 10 — Analytics

1. Analysis notebook + scheduled report script
2. Most targeted assets, attack type distribution, peak hours
3. Mean time to acknowledge / mean time to resolve
4. False-positive rate per rule (this one is genuinely interesting — it tells you which rules need tuning)
5. Charts exported into the README

**Done when:** the README contains charts generated from real lab data.

### Phase 11 — Hardening and CI/CD

1. GitHub Actions: lint (ruff), type check (mypy), pytest, build image
2. Dependency vulnerability scanning (pip-audit)
3. Static security analysis (bandit)
4. Rate limiting on auth endpoints
5. Structured JSON logging
6. README: architecture, topology, detection methodology, screenshots, demo walkthrough

**Done when:** a push runs the full pipeline green, and a stranger can clone and run the project from the README alone.

### Phase 12 — Optional, only if Phases 0–11 are genuinely complete

Statistical baselining (z-score on per-asset traffic volume) · Suricata as a
second sensor · automated response actions · a written (not deployed) AWS
architecture section.

---

## 6. Deliberately not doing

Kubernetes · AWS deployment · Kafka · microservices · machine learning ·
Prometheus/Grafana · Power BI · React · WebSockets.

Each of these can be justified in an interview by explaining *why it wasn't
needed* — which is a stronger answer than having used it without cause.

---

## 7. Glossary

**Alert** — the output of a detection rule firing. Not yet confirmed as malicious.

**APScheduler** — Python library that runs functions on a schedule.

**Argon2** — password hashing algorithm; current best practice, winner of the Password Hashing Competition.

**Beaconing** — malware repeatedly phoning home to its operator at regular intervals. Detectable by the regularity of the timing.

**C2 (Command and Control)** — the infrastructure an attacker uses to control compromised machines.

**Deduplication** — collapsing many identical findings into one alert.

**Detection rule** — a definition of a pattern in telemetry that indicates suspicious behaviour.

**Enrichment** — adding context (asset owner, geography, threat intel) to raw events before an analyst sees them.

**False positive** — an alert that turned out to be benign activity.

**Hypertable** — TimescaleDB's name for a table automatically split into time-based chunks under the hood. You query it like a normal table.

**HTMX** — JavaScript library that lets HTML elements fetch and swap server-rendered HTML without you writing JavaScript.

**IDS / IPS** — Intrusion Detection System (alerts) / Intrusion Prevention System (alerts and blocks).

**Incident** — an analyst-owned case, usually grouping several related alerts.

**IOC (Indicator of Compromise)** — a concrete artefact associated with known malicious activity: an IP, domain, or file hash.

**JWT (JSON Web Token)** — a signed token proving who a user is, so the server doesn't need to store sessions.

**MITRE ATT&CK** — a public catalogue of adversary techniques with stable IDs (e.g. `T1110` = Brute Force). The industry's shared vocabulary.

**ORM (Object Relational Mapper)** — library that maps database rows to objects in your language.

**Playbook** — written step-by-step procedure for investigating a specific alert type.

**Port scan** — probing many ports on a target to find which services are running. Usually reconnaissance.

**Sigma** — an open YAML standard for writing detection rules portably across security tools.

**SOC (Security Operations Centre)** — the team that monitors, triages and responds to security alerts.

**SSE (Server-Sent Events)** — a one-way stream from server to browser over a normal HTTP connection. Simpler than WebSockets when you only need server-to-client push.

**Suppression / tuning** — deliberately silencing a rule for known-good behaviour, to reduce false positives.

**Telemetry** — the raw observational data a system emits about itself or its network.

**testcontainers** — library that starts real services in Docker for the duration of a test.

**TimescaleDB** — PostgreSQL extension for time-series data: automatic partitioning, retention policies, time-bucketing functions.

**WSL2 (Windows Subsystem for Linux 2)** — a real Linux kernel running on Windows. Required for Docker networking and Zeek.

**Zeek** — a network monitor that parses traffic and writes structured logs about connections, DNS, HTTP, SSH and more. It describes what happened; it does not itself decide what is malicious.

---

## 8. Immediate next step

**Phase 0, step 1: install WSL2.**

Nothing else can start until there is a Linux environment on the machine.
