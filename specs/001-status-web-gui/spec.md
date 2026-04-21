# Feature Specification: Status Web GUI

**Feature Branch**: `001-status-web-gui`
**Created**: 2026-04-21
**Status**: Draft
**Input**: User description: "add web GUI to be able to follow the system status"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — System Health Overview (Priority: P1)

A team member opens the status dashboard and immediately sees whether the system
is healthy: all background workers are running, the job queues are draining
normally, and no components (database, cache, message broker) are unreachable.
If anything is degraded, the affected component is highlighted with a brief
description of the issue.

**Why this priority**: This is the most fundamental "is everything working?"
check. Without it, engineers cannot tell whether a missing wiki update is a
system problem or expected latency.

**Independent Test**: Open the dashboard with a fully running stack and verify
all components show healthy. Stop one worker, let the dashboard auto-refresh,
and verify that worker shows as unavailable.

**Acceptance Scenarios**:

1. **Given** all system components are running, **When** a workspace member
   opens the dashboard, **Then** each component (API, ingest worker, lint
   worker, embedding worker, graph worker, database, cache) shows a "healthy"
   indicator.

2. **Given** one or more workers are stopped, **When** the dashboard
   auto-refreshes, **Then** the stopped workers are shown as unavailable with
   a timestamp of when they were last seen.

3. **Given** the message broker is unreachable, **When** the dashboard loads,
   **Then** the broker component is shown as degraded and pending jobs are
   flagged as stalled.

---

### User Story 2 — Ingest Job Monitoring (Priority: P2)

An editor who submitted a document for ingestion can open the dashboard and
track that specific job through its lifecycle: queued → processing → completed
(or failed). If the job fails, the dashboard shows the failure reason so the
editor knows whether to retry or fix the source document.

**Why this priority**: Ingest is the primary write operation. Engineers need
feedback on whether their documents were successfully incorporated into the wiki
without polling the API manually.

**Independent Test**: Trigger an ingest job, open the dashboard, and confirm the
job appears with real-time status updates. Trigger a job with an invalid source
to verify failure messages are visible.

**Acceptance Scenarios**:

1. **Given** an ingest job was submitted, **When** a workspace member views
   the dashboard, **Then** the job appears in a jobs list with its current
   status (queued / processing / completed / failed) and the source document
   name.

2. **Given** an ingest job fails after all retries, **When** the dashboard
   auto-refreshes, **Then** the job is shown as failed with the error message
   and the number of retry attempts made.

3. **Given** multiple jobs are active across queues (ingest, lint, embedding,
   graph), **When** a workspace member views the dashboard, **Then** jobs are
   shown filtered to their workspace with queue type, status, and elapsed time
   visible.

4. **Given** a workspace member has the reader role, **When** they view the
   dashboard, **Then** they can see job statuses for their workspace but cannot
   trigger or cancel jobs.

---

### User Story 3 — Knowledge Quality Monitoring (Priority: P3)

An admin reviews the dashboard's quality panel to see which wiki pages have
drifted semantically from their original content and which lint runs have
flagged issues. This gives a prioritized list of pages needing attention
without running lint manually or querying the database.

**Why this priority**: Quality monitoring is valuable but not blocking — the
system functions without it. It completes the dashboard with long-term
maintainability signals.

**Independent Test**: Introduce a page with drift above threshold and a lint
finding, then verify both appear on the quality panel with correct severity
labels.

**Acceptance Scenarios**:

1. **Given** one or more wiki pages have cosine drift above the alert threshold,
   **When** a workspace member views the quality panel, **Then** those pages are
   listed with their drift severity (warning / error) and the page title.

2. **Given** the most recent lint run produced findings (orphan pages,
   contradictions, stale content), **When** a workspace member views the quality
   panel, **Then** the findings are listed with type, affected page, and run
   timestamp.

3. **Given** no drift alerts or lint findings exist, **When** a workspace member
   views the quality panel, **Then** a clear "No issues found" state is displayed.

4. **Given** a platform admin views the dashboard, **When** they switch to a
   system-wide view, **Then** they can see health, job counts, and quality alert
   counts across all workspaces.

---

### Edge Cases

- What happens when a worker has crashed mid-job and the job is stuck "processing"
  with no heartbeat for an extended period?
- How does the dashboard behave when the workspace has no ingested pages yet
  (empty state for each panel)?
- If the message broker is temporarily unreachable, does the dashboard degrade
  gracefully or show a full error screen?
- How are long error messages from failed jobs displayed without breaking the layout?

## Clarifications

### Session 2026-04-21

- Q: Should "remove auth requirement" apply only to the HTML page, or also to the status API endpoints, and how should data access be controlled? → A: Server auto-generates a read-only JWT on page load via a public bootstrap endpoint; no manual token entry or login required. Dashboard silently fetches the token and available workspaces on load, then auto-selects the first workspace. API endpoints retain JWT validation internally but the token is transparent to the user.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The dashboard MUST display a health indicator for each system
  component: API server, message broker, database, and each named worker queue
  (ingest, lint, embedding, graph).

- **FR-002**: The dashboard MUST list active, queued, and recently completed/failed
  jobs scoped to the current workspace, showing queue name, status, source name,
  and elapsed or total time.

- **FR-003**: Failed jobs MUST display the failure reason and the number of retry
  attempts consumed, to allow editors to diagnose and re-submit if appropriate.

- **FR-004**: The dashboard MUST display semantic drift alerts for wiki pages in the
  workspace, segmented by severity (warning vs. error based on configured thresholds).

- **FR-005**: The dashboard MUST display findings from the most recent lint run for
  the workspace, including finding type and affected page.

- **FR-006**: The dashboard MUST load and display data with zero manual authentication
  steps. A public `GET /api/v1/status/bootstrap` endpoint MUST return a server-issued
  read-only JWT and the list of available workspaces; the dashboard fetches this
  silently on page load and auto-selects the first workspace. No login form or
  token input is shown to the user.

- **FR-007**: The dashboard MUST auto-refresh its data at a regular interval without
  requiring a manual page reload, and MUST display the time of the last successful
  data fetch.

- **FR-008**: Platform admins MUST be able to switch to a system-wide view that
  aggregates health, job counts, and quality alert counts across all workspaces.

- **FR-009**: The dashboard MUST be accessible via a stable URL path within the
  existing application, requiring no separate deployment or infrastructure.

### Key Entities

- **System Component**: A named infrastructure piece (API, worker type, database,
  broker) with a health status (healthy / degraded / unreachable) and a last-seen
  timestamp.

- **Job**: A unit of background work (ingest, lint, embedding, graph) with
  workspace, queue name, current status, source reference, start time, end time,
  error message (if failed), and retry count.

- **Drift Alert**: A wiki page that has exceeded the drift threshold, with its
  current cosine distance, severity level, and page title/slug.

- **Lint Finding**: A specific quality issue from a lint run, with finding type
  (orphan, contradiction, stale), the affected wiki page, and run timestamp.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A team member can determine whether the system is fully healthy or
  degraded within 10 seconds of opening the dashboard.

- **SC-002**: An editor can identify the status and failure reason for any ingest
  job they submitted within the last 24 hours, without using the API directly.

- **SC-003**: An admin can view all active drift alerts and the latest lint findings
  for their workspace on a single screen without scrolling more than one viewport.

- **SC-004**: Dashboard data is no more than 30 seconds stale under normal operating
  conditions (auto-refresh interval).

- **SC-005**: The dashboard is usable at a standard laptop viewport (1280×800)
  without horizontal scrolling.

- **SC-006**: The dashboard displays live data within 10 seconds of page open with
  no user action beyond navigating to `/status`.

## Assumptions

- The dashboard is a single-page view within the existing web application, not a
  standalone tool and not a replacement for the Flower worker dashboard (which
  remains available to operators for low-level queue inspection).

- Real-time updates are achieved via polling; a 15–30 second refresh interval is
  acceptable for a status dashboard.

- The dashboard is read-only — job cancellation, retry triggering, and wiki page
  editing are out of scope for this feature.

- Job history shown covers the last 24 hours by default; older history requires
  direct API access.

- The existing JWT infrastructure is reused internally, but the user never sees
  a login form. A server-managed service account issues read-only tokens
  transparently. This is a research/demo deployment; production hardening of
  this endpoint is out of scope.

- Mobile-specific layouts are out of scope for this iteration; laptop/desktop
  viewports are sufficient.
