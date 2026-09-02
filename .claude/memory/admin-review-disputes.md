---
feature: admin-review-disputes
status: stable
last_updated: 2026-08-28
backend_paths:
  - backend/core/models.py (AuditLog, Dispute, DisputeEvidence, AdminReviewRequest)
  - backend/core/audit.py
  - backend/core/security_events.py
  - backend/core/views.py (Admin*View, Dispute*View, AdminReviewRequestDecideView)
  - backend/tourny_regist/lifecycle.py (NeedsAdminReview)
  - backend/brackets/services.py (NeedsAdminReview)
frontend_paths:
  - frontend/src/pages/admindisputes.jsx
  - frontend/src/pages/adminreviewrequests.jsx
related_docs:
  - docs/ARCHITECTURE.md#authorization-architecture
  - docs/SECURITY.md#authorization
  - docs/SECURITY.md#user-data-isolation
  - docs/EDGE_CASES.md (Admin review & disputes section)
---

# Admin review escalation, disputes, and audit log (cross-cutting)

## What it does

This is not one Django app — it's the load-bearing authorization *pattern* that shows up identically in three unrelated places (`tourny_regist` cancel/reschedule, `brackets` reset), plus the `core` models that back it: `AuditLog` (accountability), `Dispute`/`DisputeEvidence` (player/organizer complaints), `AdminReviewRequest` (the escalation queue itself).

## How it works

**The escalation pattern**:
```
Organizer attempts a dangerous action (cancel tournament / cancel registration / reset bracket)
  → Is it safe? (no registrations yet / no bracket yet / no real results yet)
      yes → execute immediately, self-service
      no  → raise NeedsAdminReview
              → view catches it, creates an AdminReviewRequest, returns 202
              → admin later approves/rejects via AdminReviewRequestDecideView
              → on approval: re-calls the *same* service function with bypass_safety_check=True
```
`NeedsAdminReview` exists as two separate classes (`tourny_regist.lifecycle.NeedsAdminReview`, `brackets.services.NeedsAdminReview`) matched structurally by the catching view, not a shared base — deliberate, so `tourny_regist` doesn't import `brackets` just to catch its exception. Each `request_type` (`TOURNAMENT_CANCELLATION`, `REGISTRATION_CANCELLATION`, `BRACKET_RESET`) is handled by its own explicit branch in `AdminReviewRequestDecideView`, calling the exact same function the safe path would — one code path per dangerous action, never a parallel "admin version."

**`AdminReviewRequestDecideView` locks the `AdminReviewRequest` row** for the check-then-decide sequence — a second concurrent decide on an already-committed request correctly rejects instead of double-processing. `AdminReviewRequest.Meta` has a partial `UniqueConstraint` (one `pending` per target+type) so a retried/double-clicked dangerous action doesn't queue duplicates.

**`Dispute`/`DisputeEvidence`** — `target` is a `GenericForeignKey` onto either a `Tournament` (general complaint) or a `Match` (result-specific), which is why `core` doesn't import `tourny_regist`/`brackets`. `escalated_to_admin` moves resolution authority from "the tournament's own organizer" to "staff only" for the case a dispute is *about* that organizer's own ruling. A non-stakeholder probing a dispute ID gets `404`, not `403` — deliberately, so a wrong guess doesn't confirm the dispute exists. Both `DisputeStatusView` and (after a found-and-fixed gap) `DisputeEvidenceUploadView`/`DisputeEscalateView` refuse further action once `RESOLVED`/`DISMISSED`.

**`AuditLog`** — generic (`GenericForeignKey` `target`), written only through `core.audit.log_action(actor, action, target, reason, **metadata)`. **Append-only at the model layer**: `save()` raises `ValueError` on an update (row already has a `pk`), `delete()` raises unconditionally (`core/tests.py:AuditLogImmutabilityTests`). Deliberately not globally browsable — the only read paths (`TeamHistoryView`, `RegistrationHistoryView`) are scoped to one object the requester already manages, so it can't be used to enumerate objects outside the requester's authority. **Never pass a raw request body, password, or token into `log_action`'s metadata kwarg** — it's permanent, free-form JSON storage.

**Security events** (distinct from `AuditLog`): `core/security_events.py:log_security_event(event, request=None, **fields)` writes structured lines to a dedicated `security` logger, for aggregate/alerting concerns (failed-login spikes, admin actions) rather than per-object accountability. Centralized: `core.exceptions.security_aware_exception_handler` (DRF's `EXCEPTION_HANDLER`) auto-logs every `401`/`403`/`429` across the whole API. **The secret-free rule is enforced, not just documented** — `log_security_event` raises `ValueError` if any field name contains `password`/`token`/`refresh`/`secret`/`authorization`/`cookie` (case-insensitive substring).

## Invariants & gotchas

- **Staff means `is_staff`, not `is_superuser`**, everywhere in the DRF API — every `Admin*View` checks `is_staff`. `is_superuser` only matters for Django's own `/admin/` site. There is currently no permission tier between "no admin access" and "every admin endpoint" — `core/admin_capabilities.py:HasAdminCapability` is a prepared (but not yet enforced) extension point for that future rollout; don't assume it does more than pass any `is_staff` user today.
- A future third call site for a `NeedsAdminReview`-guarded action (bulk-admin action, management command, background task) gets the safety check automatically *only if* the check lives inside the service function (`lifecycle.py`/`brackets/services.py`), never in the view. `tourny_regist/tests.py:ServiceLayerInvariantTests` is what proves this holds today — extend it, don't bypass it, when adding a new escalation-guarded action.
- Reinstating a rejected `Organizer` application is intentionally allowed directly (no `PENDING`-only restriction) — don't "fix" this to match the tournament-approval pattern; see organizer.md.

## Change log

- 2026-08-28 — Initial memory file seeded from `CLAUDE.md` + `docs/ARCHITECTURE.md`/`SECURITY.md`/`EDGE_CASES.md`. No code changes made.
