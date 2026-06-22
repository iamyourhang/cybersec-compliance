# Global Country Source Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repeatable country-by-country official-source verification workflow for global cybersecurity regulation/certification coverage.

**Architecture:** Countries are tracked separately from compliance records. `countries` defines market coverage, `official_sources` defines allowed official discovery entry points, `country_source_coverage` records per-country verification status, and `source_records/source_artifacts/review_cases` handle candidate and evidence lifecycle. No researched item becomes `verified` until official URL + artifact/document + evidence note passes the review gate.

**Tech Stack:** PostgreSQL, Python scripts, existing `OfficialSourcePipeline`, `ComplianceRepository` review gate, web-verified official regulator/government/standards URLs.

---

### Task 1: Country Coverage Matrix

**Files:**
- Create: `database/migrations/V12__country_source_coverage.sql`
- Create: `scripts/refresh_country_source_coverage.py`

- [ ] **Step 1: Create coverage table migration**

```sql
CREATE TABLE IF NOT EXISTS country_source_coverage (
    country_code VARCHAR(10) PRIMARY KEY REFERENCES countries(code) ON UPDATE CASCADE,
    coverage_status VARCHAR(40) NOT NULL DEFAULT 'needs_source_research',
    official_source_count INTEGER NOT NULL DEFAULT 0,
    source_record_count INTEGER NOT NULL DEFAULT 0,
    verified_record_count INTEGER NOT NULL DEFAULT 0,
    suspicious_record_count INTEGER NOT NULL DEFAULT 0,
    quarantined_record_count INTEGER NOT NULL DEFAULT 0,
    review_note TEXT,
    next_action TEXT,
    last_checked_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- [ ] **Step 2: Apply migration on server**

Run:
```bash
docker exec -i cybersec-postgres psql -U compliance_user -d cybersec_compliance < database/migrations/V12__country_source_coverage.sql
```

Expected: `CREATE TABLE` or `CREATE TABLE IF NOT EXISTS` success.

- [ ] **Step 3: Refresh coverage rows**

Create `scripts/refresh_country_source_coverage.py` that upserts one row per country and sets:
- `verified_records_available` if verified records exist.
- `official_sources_seeded` if official source exists but no verified record yet.
- `needs_source_research` if no official source exists.

Run:
```bash
PYTHONPATH=/opt/cybersec-compliance .venv/bin/python scripts/refresh_country_source_coverage.py
```

Expected output includes country count and status summary.

### Task 2: Official Source Research Batch

**Files:**
- Modify: `scripts/seed_global_official_sources.py`

- [ ] **Step 1: Research only official domains**

Allowed evidence:
- Government or regulator pages, e.g. `ift.org.mx`, `ntc.gov.ph`, `icasa.org.za`.
- National standards/certification body pages, e.g. `standards.govt.nz`.
- Official PDF linked from official pages.

Rejected evidence:
- Consultants, labs, vendors, blogs, news articles, mirrors.
- Search snippets without opening the official page.

- [ ] **Step 2: Add confirmed official sources as discovery entries**

For each country add an `official_sources` row with:
- `country_code`
- `name`
- `base_url`
- `list_url`
- `allowed_domains`
- strict `url_patterns`
- `parser_config.official_evidence_url`

- [ ] **Step 3: Seed on server**

Run:
```bash
PYTHONPATH=/opt/cybersec-compliance .venv/bin/python scripts/seed_global_official_sources.py
```

Expected: `inserted=N, updated=M`.

### Task 3: Sync And Validate Candidates

**Files:**
- Existing: `collector/official_sources/pipeline.py`
- Existing: `collector/official_sources/fetchers.py`

- [ ] **Step 1: Sync only the newly researched source IDs**

Run a short Python script that queries the new source names and calls `OfficialSourcePipeline().sync_source(id)`.

Expected:
- `SYNC OK` for reachable official pages.
- Candidate count > 0 only when the official page exposes matching links.
- No `verified` writes.

- [ ] **Step 2: Inspect source candidates**

Run:
```sql
SELECT country_code, title, source_url
FROM source_records
ORDER BY created_at DESC
LIMIT 50;
```

Expected:
- No navigation anchors.
- No non-official domains.
- Candidate titles point to law, standard, certification scheme, type approval, cybersecurity guidance, or official program pages.

### Task 4: Coverage Summary

**Files:**
- Existing: `scripts/refresh_country_source_coverage.py`

- [ ] **Step 1: Refresh coverage after sync**

Run:
```bash
PYTHONPATH=/opt/cybersec-compliance .venv/bin/python scripts/refresh_country_source_coverage.py
```

Expected:
- Countries with newly inserted official sources move from `needs_source_research` to `official_sources_seeded`.
- Countries with existing verified records remain `verified_records_available`.

- [ ] **Step 2: Export summary for operator review**

Print:
- total countries
- enabled official sources
- countries with official sources
- countries still needing source research
- new candidates created in this batch

### Task 5: Continue Country Loop

**Files:**
- Modify: `scripts/seed_global_official_sources.py`
- Run: `scripts/refresh_country_source_coverage.py`

- [ ] **Step 1: Take next countries with `needs_source_research`**

Query:
```sql
SELECT country_code
FROM country_source_coverage
WHERE coverage_status='needs_source_research'
ORDER BY country_code
LIMIT 10;
```

- [ ] **Step 2: Search each country manually**

Use web search with country-specific official-domain queries:
- `site:<regulator-domain> cybersecurity IoT certification`
- `site:<government-domain> product cybersecurity`
- `site:<standards-body-domain> IoT cybersecurity standard`

- [ ] **Step 3: Write either a source or a review note**

If official source found: insert into `official_sources`.

If no product cybersecurity source found after official-domain searches: update `country_source_coverage.review_note` with the official bodies checked and set `coverage_status='researched_no_specific_source'`.

No record becomes `verified` in this step.
