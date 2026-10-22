# Changes in this improved build

- Required an authenticated session for gateway `OPTIONS` requests.
- Validated backend target URLs before storing or proxying them.
- Stripped headers nominated by `Connection`, untrusted forwarding headers, and client-supplied `X-SG-User` values.
- Preserved duplicate upstream response headers such as `Set-Cookie` and closed upstream responses when streaming ends.
- Added a configurable maximum request-body size.
- Bound and pruned in-memory rate-limit and login-failure tables; reset admin username lockout after successful admin authentication.
- Capped scrypt verification parameters to limit resource-exhaustion attacks from malformed credential records.
- Switched runtime persistence writes to unique, restrictive, atomic temporary files.
- Failed closed on malformed global/per-user IP restrictions and malformed non-empty User-Agent allowlists.
- Throttled repeated rate-limit audit writes and rejected non-object JSON in the admin session-label endpoint.
- Added no-store/security headers for authenticated proxied responses; bounded and validated the request-body size environment setting.
- Added opt-in trusted-proxy handling and changed the default listener to loopback.
- Made Waitress the default WSGI server; kept Flask's server as an explicit local-development option.
- Corrected stale password-hash/deployment documentation and added regression tests.
