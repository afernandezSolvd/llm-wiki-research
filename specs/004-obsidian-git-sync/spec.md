# Feature Specification: Obsidian Read-Only Vault via Git Remote Sync

**Feature Branch**: `004-obsidian-git-sync`  
**Created**: 2026-04-24  
**Status**: Draft  

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Wiki Changes Reach Obsidian After Ingest (Priority: P1)

A developer ingests a document into the wiki. Within a short time, the new or updated wiki pages appear in their local Obsidian vault without any manual action beyond an automatic periodic pull. They can browse the wiki graph, follow wikilinks, and read the full content exactly as the LLM wrote it.

**Why this priority**: This is the core value of the feature. Everything else (workspace setup, clone URL retrieval) only matters if the sync actually delivers content to Obsidian reliably.

**Independent Test**: Trigger an ingest, wait for the async push to complete, run `git pull` in the local vault clone, open Obsidian — new page is visible and wikilinks resolve correctly.

**Acceptance Scenarios**:

1. **Given** a workspace has a remote repository configured, **When** an ingest job completes and writes a wiki page, **Then** that commit is pushed to the remote within 60 seconds of the commit being made.
2. **Given** a user's local Obsidian vault is a clone of the workspace remote, **When** the user's vault pulls (manually or via auto-pull plugin), **Then** new and updated pages appear with correct Markdown content and working wikilinks.
3. **Given** the remote push fails (network error, authentication issue), **When** the ingest job runs, **Then** the ingest still completes successfully — the push failure is logged as a warning but does not block or roll back the ingest.
4. **Given** a wiki page is deleted, **When** the deletion is committed locally, **Then** the deletion is pushed to the remote so users' vaults remove the file on next pull.

---

### User Story 2 — Developer Gets a Clone URL and Sets Up Obsidian in Minutes (Priority: P2)

A developer wants Obsidian access to a workspace they are a member of. They call a single API endpoint, receive a clone URL and setup instructions, clone the repo, open the folder in Obsidian, and immediately see the existing wiki. They do not need to contact an administrator or manually configure credentials.

**Why this priority**: The clone-URL endpoint is the self-service entry point. Without it, remote sync works internally but users have no way to discover or bootstrap their local vault.

**Independent Test**: Call the clone-URL endpoint with valid workspace membership, clone the returned URL, verify `index.md` and `schema.md` exist with valid content, open the folder in Obsidian and confirm the graph view shows linked pages.

**Acceptance Scenarios**:

1. **Given** an authenticated workspace member calls the clone-URL endpoint, **When** the request is valid, **Then** the response includes the remote clone URL and a brief set of setup steps (clone command, recommended auto-pull plugin).
2. **Given** a non-member or unauthenticated user calls the clone-URL endpoint, **When** the request is made, **Then** the system returns a 403 error with a clear message.
3. **Given** the workspace does not have a remote configured, **When** the clone-URL endpoint is called, **Then** the system returns an informative error explaining that remote sync is not enabled for this workspace.

---

### User Story 3 — New Workspace Automatically Gets a Remote Repository (Priority: P3)

When an administrator creates a new workspace, the system automatically provisions a remote git repository for it. No separate manual step is required. From the first ingest onward, the workspace is push-enabled and Obsidian-ready.

**Why this priority**: Eliminates operational overhead as the number of workspaces grows. P3 because P1 and P2 can be validated with a manually pre-configured remote in the interim.

**Independent Test**: Create a new workspace via the API; verify a corresponding remote repository is created in the configured provider; verify the first ingest pushes to that remote successfully.

**Acceptance Scenarios**:

1. **Given** remote provisioning is enabled in configuration, **When** a new workspace is created, **Then** a remote repository is created in the configured provider and the workspace's local repo has the remote URL registered.
2. **Given** remote provisioning is not configured, **When** a new workspace is created, **Then** workspace creation succeeds normally with no error — remote setup is simply skipped.
3. **Given** the remote provisioning call fails (provider API error, quota), **When** a new workspace is created, **Then** the workspace is still created successfully, the error is logged, and remote sync can be configured later.

---

### Edge Cases

- What if two ingests for the same workspace complete almost simultaneously and both schedule a push? Only one push should run at a time per workspace; the second must wait for the first to finish, not run concurrently (concurrent pushes cause conflicts).
- What if the remote repository is deleted externally by an admin? The next push attempt fails; the error is logged and the workspace is flagged as needing remote reconfiguration — the failure is not silently swallowed.
- What if a workspace accumulates a large git history before its remote is first connected? The initial push must include the full commit history, not just the most recent state.
- What if the EKS node cannot reach the git provider due to network policy? All push attempts fail gracefully; local wiki operations continue unaffected and users simply don't receive new commits until connectivity is restored.
- What if an Obsidian user edits a file in their local clone? Their change is overwritten on the next pull — the vault is strictly read-only from the system's perspective; the spec does not handle write-back from Obsidian.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: After every wiki page write or delete, the system MUST schedule an asynchronous push of that workspace's local git repo to its configured remote.
- **FR-002**: A push failure MUST NOT prevent, delay, or roll back the ingest, lint, or manual wiki edit that triggered it.
- **FR-003**: Push tasks for the same workspace MUST be serialized — only one concurrent push per workspace; additional pushes for the same workspace queue behind the running one.
- **FR-004**: The system MUST expose an authenticated API endpoint that returns the remote clone URL for a given workspace, along with minimal setup instructions.
- **FR-005**: The clone-URL endpoint MUST be accessible only to authenticated members of that workspace (any role) and platform admins; all other callers receive 403.
- **FR-006**: On new workspace creation, the system MUST attempt to provision a remote repository when a git provider is configured; provisioning failures MUST be non-fatal to workspace creation.
- **FR-007**: The first push to a newly connected remote MUST include the workspace's full git commit history.
- **FR-008**: Wiki page content and directory structure MUST remain standard Markdown with wikilink syntax — no transformation is needed for Obsidian compatibility.
- **FR-009**: Remote sync MUST be globally toggleable via configuration; when disabled, all push scheduling is skipped without error.

### Key Entities

- **WorkspaceRemote**: Represents the link between a workspace and its remote git repository. Attributes: workspace ID, remote URL, provider, creation timestamp, last successful push timestamp, last push error.
- **PushTask**: An async job that pushes a workspace repo to its remote. Attributes: workspace ID, trigger source (ingest job ID or user action), queued-at, status, error detail.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Wiki page changes are available in a user's Obsidian vault within 90 seconds of ingest completion, assuming auto-pull is configured at a 60-second interval.
- **SC-002**: Push failures have zero measurable impact on ingest success rate — ingest completion rate is identical whether remote sync is enabled or disabled.
- **SC-003**: A developer can go from "I want Obsidian access" to actively browsing the wiki in Obsidian in under 5 minutes, following only the instructions returned by the clone-URL endpoint.
- **SC-004**: Concurrent ingests on the same workspace produce a consistent remote history with no merge conflicts or missing commits.
- **SC-005**: When the git provider is unreachable, zero user-facing error messages appear in API responses for ingest, lint, or wiki CRUD operations.

---

## Assumptions

- Users have git installed locally and are comfortable running a `git clone` command.
- The Obsidian Git community plugin is used for automatic periodic pulls; the system provides the clone URL, not a managed sync client.
- Remote repositories are private; public repository support is out of scope.
- A single git provider is configured per deployment (one GitHub org, one GitLab group, etc.); multi-provider is out of scope.
- The EKS deployment has outbound network access to the git provider; if it does not, the feature degrades gracefully (local wiki still works).
- Read-only access for users is enforced by not distributing write credentials — users receive a read-only clone URL or token.
- Existing workspace git repos already contain a valid, complete commit history on the EKS server; no migration or history rewrite is required.
- Obsidian vault configuration (installed plugins, theme, workspace settings) is each user's responsibility; the system only guarantees the content format is compatible.
