# Error handling

An audit of how exceptions and errors actually propagate across the Esports Pakistan backend today — not a generic "how to handle errors in Django" guide. Every claim here was checked against the current code (file/function referenced throughout), not assumed from convention. Companion to [`OPERATIONS.md`](OPERATIONS.md) (how these failures actually look in production) and [`EDGE_CASES.md`](EDGE_CASES.md) (specific business-logic scenarios, some of which are also error-handling gaps).

## Purpose

This documents the real exception-handling architecture of this codebase: what happens when a view raises, what a client actually receives, which failures are logged and which are silent, where retries happen (almost nowhere) and where partial failures can leave inconsistent state. It exists so a future change to error handling starts from what's actually there, not from an assumption about what "should" be there.

## Status legend

- **Handled** — the current behavior is correct and deliberate, verified against the code.
- **Fixed** — a real gap was found and fixed (regression-tested where applicable); the entry describes what the bug *was*.
- **Needs improvement** — a real, currently-open gap.
- **Known limitation** — an intentional tradeoff, understood and accepted, not something to reactively patch.

## The exception-handling architecture

**One central hook**: `REST_FRAMEWORK['EXCEPTION_HANDLER'] = 'core.exceptions.security_aware_exception_handler'` (`config/settings.py`). Every view's exception ultimately passes through this one function.

```python
def security_aware_exception_handler(exc, context):
    response = drf_default_exception_handler(exc, context)
    if isinstance(exc, _SECURITY_RELEVANT_EXCEPTIONS):   # Throttled, NotAuthenticated, AuthenticationFailed, PermissionDenied
        log_security_event(f'http.{type(exc).__name__.lower()}', request=..., status_code=...)
    return response
```

It wraps DRF's *own* default handler (`rest_framework.views.exception_handler`) rather than replacing its logic — the actual response-building behavior is 100% standard DRF, this file only adds structured logging on top for four specific exception types.

**What DRF's own default handler actually does** (`rest_framework/views.py:exception_handler`, verified directly against the installed version):
1. `Http404` → converted to DRF's `NotFound` (404).
2. Django's `PermissionDenied` → converted to DRF's `PermissionDenied` (403).
3. Any `rest_framework.exceptions.APIException` subclass → `Response({'detail': exc.detail} or exc.detail, status=exc.status_code)`. A `Throttled` exception also gets a `Retry-After` header set from `exc.wait` — the **one place** in this codebase where a client is given explicit machine-readable retry guidance.
4. **Anything else returns `None`.**

**Handled, but worth being explicit about**: case 4 means a plain Python exception that isn't a DRF `APIException`/`Http404`/Django `PermissionDenied` (a bare `KeyError`, `AttributeError`, an unhandled `TypeError` from a bug) is **not converted into a JSON error response at all**. It propagates up to Django's own WSGI-level error handling, which — with `DEBUG=False` in production — renders Django's generic `500 Server Error` plain-text/HTML page, not a JSON body. A frontend expecting `{"detail": "..."}` gets a non-JSON response in this case. `frontend/src/lib/api.js`'s `handleResponse` degrades gracefully here (see "Frontend error handling" below), but the *specific reason* for the failure is never communicated to the client — only to whatever's watching the server logs.

**Where this actually gets caught before reaching that point**: most external-service integrations in this codebase (Cloudinary, Groq/Chroma, Google's cert verification) are wrapped in their *own* `try/except` that converts failures into a purpose-built `APIException` subclass (`StorageUnavailable`, `ChatServiceUnavailable`, `RuleBookProcessingError`, `GoogleAuthUnavailable` — see below) specifically so they get case 3's clean JSON response instead of falling through to case 4's bare 500. **Brevo is the deliberate exception** — see "Handled" below for why a plain `RuntimeError` is the right call there instead. A *new* integration that skips this conversion, without a comparable reason, will 500 silently (no JSON detail) the first time it fails, rather than failing loudly with a clear message.

## API error response shapes

Two different shapes exist side by side, and which one a given error takes isn't obvious without knowing how it was raised:

**Field-level serializer validation** (`serializer.is_valid(raise_exception=True)`) produces `{"field_name": ["error message", ...]}` — every value is a **list**, even for a single error, because DRF's validation machinery always wraps field errors in a list.

**A view directly raising `ValidationError({...})`** (not through serializer validation) produces whatever shape was passed — if the dict's values are plain strings, they **stay plain strings, not lists**. Verified directly:

```python
>>> from rest_framework.exceptions import ValidationError
>>> ValidationError({'otp': 'This code has expired.'}).detail['otp']
ErrorDetail(string='This code has expired.', code='invalid')   # a string, not ['This code has expired.']
>>> ValidationError({'otp': 'wrong', 'attempts_remaining': 4}).detail['attempts_remaining']
ErrorDetail(string='4', code='invalid')   # note: the int 4 became the string '4'
```

**Handled on the frontend, but a real shape inconsistency in the backend worth knowing about**: `frontend/src/lib/api.js`'s `handleResponse` does `Object.values(msg).flat().join(" ")` — `.flat()` is a no-op on a plain string value and doesn't error, so both shapes render *something* to the user either way. But a caller reading `err.data.some_field` directly (rather than the flattened `err.message`) needs to know whether to expect a list or a bare value — `core/views.py:VerifyEmailView` (email-OTP verification) is a concrete example that returns `attempts_remaining` as a bare (string-coerced) value this way, and the frontend code consuming it (`frontend/src/pages/auth.jsx`) has to know to read it as `data.attempts_remaining` directly, not `data.attempts_remaining[0]`. This is not "wrong," but it means the response shape for a given endpoint has to be checked per-endpoint (or in this file), not assumed uniform across the API.

**A raised `ValidationError` with no field association at all** — `raise ValidationError({'detail': '...'})` — is the most common pattern for "this whole request is invalid for a reason not tied to one field" (e.g. `lifecycle.py`'s state-machine guards: `"Only a draft tournament can be submitted for approval."`). This matches DRF's own convention (a bare `{"detail": "..."}` is what `Http404`/`PermissionDenied`/most built-in `APIException`s produce too), so `frontend/src/lib/api.js`'s `msg = data?.detail || data?.message || data?.error` check looks for `detail` *first*, before falling back to treating the whole body as a field-error dict.

## Authentication & permission failures

- **401 (`NotAuthenticated`)** — no/invalid/expired JWT. **403 (`PermissionDenied`)** — valid JWT, but the `IsAdminUser`/object-level permission check fails. Both are in `_SECURITY_RELEVANT_EXCEPTIONS` (`core/exceptions.py`), so both are automatically logged as `http.notauthenticated`/`http.permissiondenied` security events (`core/security_events.py`) with the requester's IP, user-agent, and path — **without any individual view needing to remember to log its own denial**. Handled, centrally, for the entire API.
- **A non-stakeholder probing a `Dispute` (or similar object-scoped resource) by ID gets 404, not 403** — deliberately, per `SECURITY.md`'s "User data isolation" section, so a wrong guess doesn't even confirm the object exists. This is an intentional *exception* to the usual 401/403 pattern, not an inconsistency.
- **Throttling (429, `Throttled`)** is the one case with real client-facing retry guidance: DRF's default handler sets `Retry-After: <seconds>` from `exc.wait`. Every other error type gives the client no signal about whether/when retrying might succeed.
- **The single most consequential admin action (granting/revoking `is_staff`/`is_active`) requires re-entering the acting admin's own current password** (`core.views.AdminUserDetailView.update`) — a failed re-auth here logs `admin.staff_status_change.reauth_failed` as its own explicit security event (not just a generic 400), distinct from the blanket 401/403 logging above, because this specific failure is worth alerting on individually.

## External-service failure handling

Each of these follows the same shape: wrap the SDK/HTTP call, log the real cause server-side via `logger.exception`/`logger.error`, and raise (or re-raise as) a purpose-built `APIException` with a generic, safe message for the client.

| Service | Wrapper | Client sees | Server log has |
|---|---|---|---|
| Cloudinary (signed documents: CNIC, payment proofs, dispute evidence) | `core/storage.py:CloudinarySignedStorage` — every method (`_save`/`delete`/`exists`/`size`/`get_created_time`) | `503 StorageUnavailable`, generic message | `logger.exception` with the real Cloudinary SDK error |
| Cloudinary (rulebook PDFs) | `rag_chat/services/cloudinary_service.py` — **not wrapped** at the storage layer; caught one level up | `503 RuleBookProcessingError` | `logger.exception` in `rag_chat/views.py:RuleBookUploadView.create` |
| Brevo (all transactional email) | `core/email_backend.py:BrevoAPIBackend._send_one`, caught by `send_messages` | Depends on caller — see below | A single `logger.exception('Failed to send email via Brevo (subject=%r)', ...)` in `send_messages` — this does **not** currently distinguish a network-unreachable failure from Brevo actively rejecting the request (a bad API key, an unverified sender) in the log *message* itself; the attached traceback is the only way to tell them apart today (see "Needs improvement" below and `OPERATIONS.md`) |
| Groq (RAG answer generation) | `rag_chat/views.py:ChatView.post`'s broad `try/except Exception` around the whole retrieve→rerank→build→generate pipeline | `503 ChatServiceUnavailable`, generic message | `logger.exception` with the real pipeline failure (whichever stage actually broke) |
| Chroma (vector/keyword retrieval) | Same `try/except` as Groq above — not handled separately, since a Chroma failure and a Groq failure look identical to the caller | Same `503 ChatServiceUnavailable` | Same `logger.exception` — **the log message doesn't distinguish which stage failed**, only that the pipeline did (see "Needs improvement" below) |
| Google (`id_token` verification) | `core/views.py:GoogleLoginView.post` — explicit `except ValueError` / `except GoogleAuthError`, not a broad catch | `400` (bad token) or `503 GoogleAuthUnavailable` (Google unreachable) — the *only* external-service integration that distinguishes two different failure causes into two different status codes | `logger.warning` (bad token, since `ValueError`'s message is the only way to tell failure modes apart) or `logger.exception` (Google unreachable) |

**Handled**: Brevo's `_send_one` raising a plain `RuntimeError` (not a DRF `APIException`) is deliberate, not an oversight — Brevo sends are never triggered directly from a request/response cycle the same way a Cloudinary upload is. The caller decides what to do with the failure:
- `core/views.py`'s `RegisterView`/`ForgotPasswordView`/`ResendVerificationView` catch it broadly (`except Exception: logger.exception(...)`) and still return a normal success response — an email failure must never turn a real signup/reset request into a client-visible error, since the underlying action (creating the `PendingRegistration`, etc.) already succeeded.
- `tourny_regist/emails.py`'s `send_announcement_emails`/`send_reschedule_email`/`send_tournament_win_email` catch it **per-recipient, inside a loop** — one bad address or one Brevo rejection doesn't stop the rest of the batch, and doesn't turn a successful announcement/reschedule/win-declaration into an error response for the organizer/admin who triggered it.

**Fixed**: `_send_one` used to funnel every failure through one identically-worded `except Exception` in `send_messages`, so a network-level failure reaching `api.brevo.com` and Brevo actively rejecting the request (wrong API key, unverified sender) were indistinguishable without reading the full traceback. It now logs two differently-worded messages *before* re-raising — `logger.error('Brevo API unreachable sending to %s (subject=%r): %s', ...)` for a `requests.exceptions.RequestException` (network/DNS/timeout), and `logger.error('Brevo API rejected an email to %s (subject=%r): HTTP %s — %s', ...)` for a non-2xx response — so the two causes can now be told apart by scanning the log message text, not by opening every traceback. `send_messages`'s outer `logger.exception('Failed to send email via Brevo...')` still fires too (it wraps the call per-message), so both the specific and the generic line appear together; the specific one is what to scan for.

**Needs improvement**: the Groq/Chroma pipeline's single broad `try/except Exception` in `ChatView.post` means a Groq authentication failure, a Chroma quota error, an embedding-model crash, and a genuine bug in `prompt_service.build_context` all produce the **identical** `503 ChatServiceUnavailable` to the client and the **identical**-*looking* `logger.exception('rag_chat pipeline failed for question=%r', question)` server-side (the traceback itself differs, but there's no structured field distinguishing "this was a Groq problem" from "this was a Chroma problem" for a log-search/alerting rule to filter on). Diagnosing which external dependency actually failed currently requires reading the full traceback by hand every time (as was necessary for both real incidents in `OPERATIONS.md`'s RAG section) rather than being able to search/alert on "Groq failures spiked" vs. "Chroma failures spiked" as distinct signals.

## Swallowed / partial-failure exceptions

**Handled, deliberately**: per-recipient email loops (above) and `rag_chat/views.py:RuleBookUploadView.create`'s cleanup-on-failure (deletes the just-uploaded Cloudinary asset if chunking/embedding fails after the upload succeeded, itself wrapped in its own nested `try/except` so a *second* failure — the cleanup delete itself failing — is logged rather than masking the original error) are the two best examples of correctly-scoped exception swallowing: each bounds a failure to exactly the thing that actually failed, without silently discarding information a caller needs.

**Known limitation**: `tourny_regist/lifecycle.py:disqualify_registration` commits the registration's own `DISQUALIFIED` status inside one `transaction.atomic()` block, then — **after that transaction has already committed** — calls `brackets.services.disqualify_player_from_bracket` as a second, separately-locked operation, deliberately *not* wrapped in a shared transaction with the first step (the module's own comment explains why: keeping the two decoupled avoids ever having to reason about interleaving a `Registration` lock with `brackets/services.py`'s Tournament→Bracket→Match lock order). If the second call raises for any reason — `forfeit_match`'s own defensive guards (`brackets/services.py`) can raise `ValidationError` if, by the time it runs, a targeted match's state has already changed — the registration is **already, irreversibly** `DISQUALIFIED` in the database, but the corresponding bracket match was never auto-forfeited. `RegistrationDisqualifyView.post` (`tourny_regist/views.py`) has no `try/except` of its own around this call, so the `ValidationError` propagates as an ordinary 400 — which reads to the caller like "the disqualification didn't happen," when in fact half of it did. This is a real, currently-unhandled partial-failure window, not just a hypothetical: retrying the same request would then get a *different* error ("This registration is already disqualified") without ever completing the missed forfeit. No test currently exercises this specific interleaving.

**Fixed**: abandoned, never-verified `PendingRegistration` rows (and any CNIC/company document already pushed to Cloudinary for an abandoned organizer signup) used to accumulate indefinitely with no cleanup path at all. `core/management/commands/cleanup_pending_registrations.py` now deletes rows past `--older-than-days` (default 7), deleting each row's Cloudinary document first and tolerating an individual Cloudinary delete failure without blocking the rest of the run (`--dry-run` supported). It's a plain management command, not wired to run automatically — same as `flushexpiredtokens` (see `OPERATIONS.md`'s "Known operational limitations" and `SECURITY_CHECKLIST.md`'s "Scheduled cleanup"), so it still needs an external scheduler (a Render Cron Job) to actually run on a cadence. Regression tests: `core/tests.py:CleanupPendingRegistrationsCommandTests`.

## Logging behavior

**Handled**: `LOGGING` in `config/settings.py` explicitly configures four loggers — `django`, `core`, `rag_chat`, `security` — each with a `console` handler at `INFO` level and `propagate: False`. The `django` entry specifically exists because Django's own default logging config only sends `django.request` (unhandled 500 tracebacks) to console when `DEBUG=True` (via a `require_debug_true` filter) — with `DEBUG` correctly `False` in production, that would otherwise leave every unhandled server error completely unlogged anywhere. Restoring it here means 500s are visible in Render's console logs regardless of `DEBUG`.

**Needs improvement, verified directly**: `organizer`, `tourny_regist`, `brackets`, `games`, `partners`, and `dashboard` are **not** in that `loggers` dict. `tourny_regist/emails.py` is the one file among them that actually calls `logging.getLogger(__name__)` and logs (`logger.exception(...)`, in `send_announcement_emails`/`send_reschedule_email`/`send_tournament_win_email`). Since Python's logging config here defines no `root` logger either, an unconfigured logger like `tourny_regist.emails` falls back to Python's built-in defaults — verified directly against the running settings:

```python
>>> logging.getLogger('tourny_regist.emails').getEffectiveLevel()
30   # WARNING — the interpreter default, not this project's chosen INFO level
>>> logging.getLogger('tourny_regist.emails').handlers, logging.getLogger('tourny_regist.emails').parent.handlers
([], [])   # no handler anywhere in the chain
```

Concretely:
- `logger.exception(...)`/`logger.error(...)` calls in `tourny_regist/emails.py` **do** currently show up in console output, purely because `ERROR` (40) exceeds the interpreter's built-in `WARNING` (30) threshold and Python's "handler of last resort" (a plain `StreamHandler` to stderr, used when *no* handler exists anywhere up the chain) catches it. This works today, but by accident of log level, not by this project's own logging configuration actually including that module.
- If any of those files ever added a `logger.info(...)` call expecting it to behave like `core`'s or `rag_chat`'s (both explicitly `INFO`-level), it would be **silently dropped** — below the default `WARNING` threshold, with no error or indication anywhere that it didn't get logged. This has not happened yet (no `logger.info`/`.debug`/`.warning` call exists in any of these six apps today, confirmed directly), but the moment one is added, it silently does nothing.

## Retry behavior

**Known limitation**: there is no automatic retry logic anywhere in application code — no `tenacity`, no manual backoff loop, no re-attempt after a timeout — for any external call (Brevo, Cloudinary, Groq, Chroma, Google). Every one of them is a single attempt with a fixed timeout (e.g. `core/email_backend.py:REQUEST_TIMEOUT = 10`). A transient failure (a momentary network blip to any of these services) is indistinguishable, from the client's perspective, from a real, persistent failure — both surface as the exact same error the first time. The only retry behavior anywhere in this system is:
- **Client-initiated** — a user/frontend simply trying the same action again, which is safe *because* of idempotency design elsewhere (duplicate `AdminReviewRequest` suppression, OTP resend, `PendingRegistration.objects.update_or_create` on repeat signups — see `EDGE_CASES.md`), not because the backend retries anything on their behalf.
- **Infrastructure-level** — `.github/workflows/health-check.yml`'s `curl --retry 5 --retry-delay 10 --retry-max-time 300` is the one place an automatic retry exists at all in this project, and it's a CI/CD workflow, not application code. Widened over time specifically to survive a Render free-tier cold start — see `OPERATIONS.md`'s "Health checks" section for why.

## Frontend error handling

Out of scope for "the backend," but worth noting the seam where backend error shapes meet the UI, since it's part of the same end-to-end error path:

- **`frontend/src/lib/api.js:handleResponse`** normalizes every non-2xx response into a single `Error` object: prefers `data.detail`, falls back to flattening a field-error dict (`Object.values(msg).flat().join(" ")`, which — see above — tolerates both the list and bare-string shapes DRF can produce), and falls back to `Request failed (${status})` if the body isn't parseable as JSON at all (e.g. Django's bare HTML 500 page for an unconverted exception, per "The exception-handling architecture" above). The original response body is preserved on `err.data` for any caller that needs the structured shape rather than the flattened message.
- **`frontend/src/lib/api.js`'s `safeFetch`** catches the case `fetch()` itself throws (network genuinely unreachable, CORS misconfiguration, DNS failure) — distinct from a real HTTP error response — and normalizes it to the same friendly-error shape, so a wifi drop doesn't surface a raw browser-native error string to the UI.
- **`frontend/src/components/errorboundary.jsx`** is a class-based React error boundary (required — there's no hook equivalent for `componentDidCatch`) wrapping the whole app (`main.jsx`) — catches unexpected *render-time* JavaScript errors (not API errors, which never throw inside React's render cycle) and shows a "Something went wrong" screen with reload/home actions instead of an unhandled error unmounting the app to a blank white screen. Logs to `console.error` only — no Sentry/error-reporting integration on the frontend, unlike the backend's optional `SENTRY_DSN`.
