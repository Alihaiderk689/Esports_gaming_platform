---
feature: organizer
status: stable
last_updated: 2026-08-30
backend_paths:
  - backend/organizer/
frontend_paths:
  - frontend/src/pages/organizer.jsx
  - frontend/src/pages/adminorganizers.jsx
  - frontend/src/components/admin/docpreview.jsx
related_docs:
  - docs/ARCHITECTURE.md (Database design — organizer.Organizer row)
  - docs/EDGE_CASES.md (Admin review & disputes section — organizer document re-upload/reinstatement entries)
---

# Organizer (application, compliance docs, admin approval)

## What it does

Lets a `User` apply to become a tournament organizer: company info, CNIC scan, company registration document, payout method. Gated behind admin approval before `IsApprovedOrganizer` (`tourny_regist/permissions.py`) will let them create tournaments.

## How it works

`Organizer` (`backend/organizer/models.py`) is a `OneToOneField` on `User` (`user.organizer_profile`), with `Status`: `pending` → `approved`/`rejected`. No `services.py` here — logic lives directly in `views.py`/`serializers.py` (CRUD-shaped, no multi-step invariant needing to be shared across call sites, per `docs/ARCHITECTURE.md`'s service-layer table).

CNIC/company documents go through `core/storage.py:CloudinarySignedStorage` — same signed-URL, never-a-raw-link pattern as every other sensitive document in the platform (see auth.md's storage notes and `docs/SECURITY.md#file-uploads`). `frontend/src/components/admin/docpreview.jsx` renders them in an `<iframe>` for admin review, which is why SVG is excluded from accepted formats platform-wide.

**Re-upload after approval reopens review**: `OrganizerUploadCnicView`/`OrganizerUploadCompanyView` call `_reopen_review_after_document_change()` whenever a document is (re-)uploaded while `status == APPROVED` — sends the application back to `PENDING`, logged via `core.audit.log_action('organizer.compliance_document_replaced', ...)`. Deliberately a no-op for `PENDING` (already awaiting review) and `REJECTED` (must go through the separate `OrganizerResubmitView` flow instead). The existing `last_seen_status`/`OrganizerAcknowledgeStatusView` mechanism surfaces the status change to the organizer automatically.

**Reinstating a rejected application** — `AdminOrganizerUpdateSerializer` intentionally allows re-deciding an already-rejected application directly (no `PENDING`-only restriction, unlike `tourny_regist`'s tournament-approval serializer). This is confirmed deliberate by an existing test (`organizer/tests.py:test_approve_clears_previous_rejection_reason`) — don't "fix" this asymmetry for consistency with the tournament pattern; that was already attempted once and broke intended behavior.

## Invariants & gotchas

- `_get_organizer(user)` always derives the organizer from `request.user`, never a URL parameter — structurally impossible to address another user's organizer profile through this app's endpoints.
- No `permissions.py` in this app — ownership checks are inline in view bodies rather than a dedicated permission class.
- Admin approval/rejection here doesn't go through the `NeedsAdminReview`/`AdminReviewRequest` escalation pattern (that pattern is for *dangerous self-service actions*, not first-time applications) — see admin-review-disputes.md for where that pattern actually applies.
- `AdminOrganizerListView` now paginates (`core.pagination.StandardResultsPagination`, 20/page, `{count, next, previous, results}` instead of a bare array) — `adminorganizers.jsx` reads `data.results` and drives simple prev/next controls off `data.next`/`data.previous`.

## Change log

- 2026-08-30 — Production-hardening pass: added pagination to `AdminOrganizerListView`/`adminorganizers.jsx`.
- 2026-08-28 — Initial memory file seeded from `CLAUDE.md` + `docs/ARCHITECTURE.md`/`EDGE_CASES.md`. No code changes made.
