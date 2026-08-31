# Recon: Future Improvements & Roadmap

This document outlines planned capabilities, architectural enhancements, and feature milestones for upcoming versions of **Recon** (`recon-qa`).

---

## 🎯 High-Priority Roadmap (`v0.1.3` - `v0.2.0`)

### 1. Smart Session & State Chaining (Autonomous Auth & Seeding)
- **Current Limitation**: Secured endpoints require manually extracting a JWT token and passing `-H "Authorization: Bearer <TOKEN>"`.
- **Target Feature**:
  - Automatically detect login/registration endpoints (`/api/v1/auth/register`, `/api/v1/auth/login`) from OpenAPI specs.
  - Execute automatic pre-flight registration + login, capture the returned JWT/session cookie, and inject it across all downstream authenticated test cases automatically.
  - Automatically chain dependencies (e.g., create a resource first, extract its `id`, and use it in `GET /documents/{id}` and `DELETE /documents/{id}`).

---

### 2. Semantic Data Synthesizer & Multipart Fixtures
- **Current Limitation**: Generic string fuzzer sends arbitrary strings, which fails schema validations on strict formats like UUIDs, datetimes, and multipart file uploads.
- **Target Feature**:
  - **Format-Aware Generators**: Auto-generate valid `uuid4` for `format: uuid`, valid RFC-5322 emails for `format: email`, and ISO-8601 strings for `format: date-time`.
  - **Synthetic File Fixture Generator**: Generate in-memory synthetic PDF, PNG, DOCX, and CSV files on the fly for `multipart/form-data` upload endpoints (e.g., `POST /documents`).

---

### 3. Interactive Web Dashboard (`recon serve` / `recon ui`)
- **Target Feature**:
  - Launch a local web dashboard via `recon serve --port 4100` (or `recon ui`).
  - **Live Test Stream**: Real-time websocket stream of test executions, latencies, and status transitions.
  - **Visual Diff Inspector**: Review AI-generated unified diff patches side-by-side with Monaco Editor before applying.
  - **One-Click Healing**: "Approve Patch", "Run Verification", and "Rollback" buttons in the UI.
  - **Historical Run Comparisons**: Side-by-side regression comparisons across runs over time.

---

### 4. Reusable GitHub Action (`ttnhan227/recon-action@v1`)
- **Target Feature**:
  - Package Recon as a GitHub Action for marketplace distribution:
    ```yaml
    - name: Recon Autonomous QA
      uses: ttnhan227/recon-action@v1
      with:
        target: http://localhost:8000
        fail-on-regression: true
        comment-on-pr: true
    ```
  - Automatically comments an interactive test summary table, failure root causes, and regression diffs directly onto GitHub Pull Requests.

---

## 🚀 Medium-Term Enhancements (`v0.3.0`+)

### 5. Multi-Step User Journey Generation (State Graph Testing)
- **Target Feature**:
  - Instead of testing isolated endpoints independently, generate topological user journeys (e.g., *Register User ➔ Create Workspace ➔ Upload PDF ➔ Run Extraction ➔ Verify Deliverable ➔ Delete Workspace*).
  - Assert end-to-end business invariants across stateful sequences.

---

### 6. Standard CI/CD Export Formats (JUnit & SARIF)
- **Target Feature**:
  - Export test results to `--format junit` (`junit.xml`) for integration with GitHub Actions Test Summary, GitLab CI, and Jenkins.
  - Export security and failure findings to `--format sarif` (`results.sarif`) for GitHub Code Scanning Alerts.

---

### 7. Multi-Language Self-Healing Engines
- **Target Feature**:
  - Extend code self-healing beyond Python to:
    - **TypeScript / Node.js**: AST verification using Babel/TypeScript parser (Express, NestJS, Fastify).
    - **Go**: AST verification using `go/parser` (Gin, Fiber, Echo).
    - **Rust**: Compilation verification via `cargo check` (Actix, Axum).

---

### 8. Semantic Failure Deduplication & Clustering
- **Target Feature**:
  - When 500+ tests fail due to 2 underlying bugs (e.g., missing database migration or changed auth middleware), use vector embeddings of stack traces and error messages to group failures into distinct root cause clusters.
  - Rank issues by blast radius and severity.

---

## 📋 Quick Feature Summary

| Milestone | Feature Area | Description | Impact |
|---|---|---|---|
| **v0.1.3** | Autonomous Auth Chaining | Auto-register + login to test secured routes without manual token | High 🔥 |
| **v0.1.3** | Synthetic File Fixtures | Auto-generate fake PDF/DOCX for upload testing | High 🔥 |
| **v0.2.0** | Web UI Dashboard | `recon serve` local dashboard with visual patch diff reviewer | High 🔥 |
| **v0.2.0** | GitHub Action | `recon-action` for 1-click CI/CD integration and PR comments | Medium ⚡ |
| **v0.3.0** | Multi-Step Journeys | State-graph chaining for full lifecycle end-to-end tests | Medium ⚡ |
| **v0.3.0** | JUnit / SARIF Export | Native integration with enterprise test reporting tools | Medium ⚡ |
| **v0.4.0** | Multi-Language Healing | Self-healing support for TypeScript, Go, and Rust codebases | High 🔥 |
