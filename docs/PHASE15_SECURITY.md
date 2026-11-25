# Phase 15 - Testing & Security Audit

Status: audit complete; the six approved fixes are implemented. No database schema,
risk calculation, threshold, weight, authentication/authorization rule, snapshot
protection or export logic was changed.

## 1. Environment modes (new)

The mode is chosen with the `APP_ENV` environment variable.

| | development (default, `APP_ENV` unset) | production (`APP_ENV=production`, or any other value) |
|---|---|---|
| Start with the built-in `SECRET_KEY` | allowed, logs a warning | **refused** (also refused if empty or < 32 characters) |
| Debug mode | on when you run `python run.py` (as before). `FLASK_DEBUG=0` turns it off | always off; **refused to start** if `DEBUG` or `FLASK_DEBUG` is set |
| Session cookie `Secure` | off (so the local HTTP demo works) | on (override: `SESSION_COOKIE_SECURE=false`) |
| `Strict-Transport-Security` | not sent | sent on HTTPS requests |

Any unrecognised `APP_ENV` value (for example a typo such as `prodution`) is treated as
production, so a mistake makes the application stricter, never looser.
`SESSION_COOKIE_SECURE=true|false` is also honoured in development.

**Local demonstration: nothing changes.** `python run.py` behaves exactly as before.

### Running in production (future)

```
set APP_ENV=production
set SECRET_KEY=<64 random hex characters>      (python -c "import secrets; print(secrets.token_hex(32))")
set DATABASE_URL=sqlite:///academic_risk.db     (SQLite is kept for this project)
waitress-serve --listen=127.0.0.1:8000 run:app   (or gunicorn run:app) behind an HTTPS reverse proxy
```
Do not use `python run.py` as the production server. The `Secure` cookie needs HTTPS;
if the proxy terminates HTTPS, configure it to forward the original scheme
(`X-Forwarded-Proto`) or HSTS will not be sent.

## 2. Security headers (new, every response)

`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: strict-origin-when-cross-origin`,
`Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()`, and a
`Content-Security-Policy`:

```
default-src 'self'; script-src 'self' https://cdn.jsdelivr.net 'nonce-<per request>';
style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; img-src 'self' data:;
font-src 'self' https://cdn.jsdelivr.net data:; connect-src 'self'; object-src 'none';
base-uri 'self'; form-action 'self'; frame-ancestors 'none'
```

How it fits the application:
* Bootstrap and Chart.js still load from `cdn.jsdelivr.net` (the only external host).
* The three inline `<script>` blocks (risk report, student risk detail) carry a
  per-request nonce (`nonce="{{ csp_nonce }}"`).
* The four confirmation dialogs used inline `onsubmit="return confirm(...)"`, which a
  CSP blocks. They now use `data-confirm="..."` handled by `app/static/js/confirm.js`
  (capture phase, so a cancelled dialog stops every other submit handler). Behaviour
  and wording are unchanged.
* `style-src` keeps `'unsafe-inline'` because a few templates use `style="width: ..%"`.
  Scripts - the high-risk part - are strict (no `'unsafe-inline'`, no `'unsafe-eval'`).
* If a new inline script is added to a template it must use `nonce="{{ csp_nonce }}"`;
  a test fails otherwise.

## 3. Error handling (new)

* URL ids larger than SQLite can store (`> 2**63-1`) now give the normal **404** page
  instead of a server error (one `<int:...>` converter for every route).
* A friendly **500** page (same layout as 403/404) is shown for unexpected errors. It
  rolls back the database session first and never shows exception text or file paths;
  the real error is still written to the server log.

## 4. Files changed

| File | Change |
|---|---|
| `app/security.py` (new) | environment rules, SECRET_KEY/debug checks, cookie flag, CSP + headers, safe int converter |
| `app/__init__.py` | calls the above; registers the 500 handler |
| `config.py` | comments; `TestConfig` pins `APP_ENV = "testing"` so a developer's own variable cannot affect tests |
| `run.py` | `debug=True` replaced by `debug_allowed(app)` |
| `app/static/js/confirm.js` (new) | confirmation dialogs |
| `app/templates/base.html` | loads `confirm.js` |
| `admin/student_detail.html`, `admin/course_enrol.html`, `admin/courses.html`, `teacher/risk_report.html` | `onsubmit` -> `data-confirm` |
| `teacher/risk_report.html`, `teacher/student_risk_detail.html` | nonce on inline scripts |
| `tests/test_phase15_security.py` (new) | 73 regression tests |

## 5. Findings register

| ID | Severity | Status |
|---|---|---|
| F-01 oversized URL ids -> 500 | Low | **Fixed** |
| F-02 `max_marks` has no upper bound | Low | Open - deliberately unchanged until an academic requirement is agreed |
| F-03 no date range validation | Low | Open - to be discussed (valid academic date ranges) |
| F-04 free-text semester | Low | Open - unchanged by decision (output is escaped; not exploitable) |
| F-05 marks <= max enforced in the route only | Info | Accepted (cross-table rule; route enforces it) |
| F-06 `debug=True` in `run.py` | High if deployed | **Fixed** |
| F-07 default `SECRET_KEY` | High if deployed | **Fixed** |
| F-08 no login throttling | Medium | **Not implemented** (proposal only; see section 6) |
| F-09 session cookie `Secure` | Medium if deployed | **Fixed** (configurable; on in production) |
| F-10 no security headers | Medium if deployed | **Fixed** |
| F-11 logout does not invalidate a copied cookie | Medium | **Not implemented** (needs a schema change) |
| F-12 login timing reveals which emails exist | Low | Documented recommendation |
| F-13 weak password policy / demo seed passwords | Low | Documented recommendation |
| F-14 no custom 500 page | Low | **Fixed** |
| F-15 SQLite / single process | Info | Accepted (SQLite kept) |

## 6. Deferred items (documented, not implemented)

* **F-08 login limiter** (proposal): after N failed attempts per email+IP in a time
  window, return "too many attempts". In-memory only: resets on restart; each worker
  process keeps its own counters, so with several workers the real limit is N x workers;
  behind a proxy every user may share one IP unless proxy headers are configured;
  per-email lockout can be abused to lock a teacher out. A shared store (Redis) or
  Flask-Limiter is the production-grade option.
* **F-11 session versioning**: add a per-user session-version column changed on logout /
  password change. Needs a schema change, so requires separate approval.
* **F-12**: hash a dummy password when the email is unknown (removes the ~140 ms timing gap).
* **F-13**: password complexity / common-password checks; change or delete the demo
  accounts in `seed.py` before any deployment.
* Also recommended before deployment: a production WSGI server, HTTPS, log failed logins
  and admin actions, regular database backups, dependency vulnerability scan.

## 7. What was verified, and how

* **Automated** - audit probes (outside the project, isolated databases): authorization
  matrix for anonymous/admin/teacher/other teacher over every route; IDOR; invalid ids;
  CSRF on every POST route; GET cannot change state; XSS/SQLi payloads; PDF/Excel payloads
  (markup, Unicode, `=` formulas); input fuzzing; FK/unique/CHECK constraints; snapshot
  triggers; all-or-none course recording; calculation boundaries.
* **Automated** - project suite (see the final report for the exact numbers).
* **Manual browser (headless Chromium)** - 11 pages at 1280 px and 390 px; with the CSP on:
  charts render, filters/expand work, delete/record confirmations cancel and accept
  correctly, 500 and 404 pages, no CSP violations, in both development and production mode.
* **Static inspection** - `debug`, `SECRET_KEY`, absence of `|safe` / raw SQL.
* **Not tested** - real HTTPS and reverse proxy, multiple workers, load/performance,
  opening exports in Excel/PDF viewers, dependency vulnerability scan.
