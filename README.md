```
┌──────────────────────────────────────────────┐
│        ◢ S E S S I O N G U A R D            │
│        · auth gateway · session shield       │
└──────────────────────────────────────────────┘
```

# ◢ SessionGuard

**Made by Aryan Giri | giriaryan694-a11y**

SessionGuard is a small authentication gateway and reverse proxy for private HTTP web tools. It authenticates users, limits concurrent sessions, applies optional IP/User-Agent restrictions, and forwards approved requests to a configured backend.

```text
browser ──► trusted HTTPS proxy/tunnel ──► SessionGuard ──► private web app
                                             │
                                      login + sessions
                                      admin + audit log
```

> **Security note:** SessionGuard is a personal/small-team access gate, not a substitute for a mature identity provider or a formal security review. Keep the backend private, use HTTPS for remote access, keep dependencies updated, and test the configuration before putting sensitive data behind it.

## Features

- Login gateway with server-side sessions and CSRF validation for state-changing forms/API calls.
- Per-user concurrent session limit (`AS`), session expiry, device labels, and a self-service session portal.
- Admin panel for users, password resets, account disabling, backend routing, sessions, and audit events.
- Scrypt password hashes; legacy PBKDF2 hashes and plaintext `users.txt` credentials are upgraded on successful login.
- Five failed-login attempts trigger a five-minute lock for the source IP and username.
- Request rate limiting, optional global/per-user IP allowlists, IP denylist, and per-user User-Agent matching.
- Configurable global or per-user backend; accepted targets are HTTP(S) URLs without embedded credentials, query strings, or fragments.
- Atomic state-file writes, restricted POSIX file permissions, response security headers and no-store behavior for authenticated proxied responses, bounded body sizes, and proxy hop-by-hop header filtering.
- Dark/light admin UI, audit filtering, and JSON/CSV event export.

## Quick start

Python 3.9+ is required.

```bash
# Install dependencies
python -m pip install -r requirements.txt

# Create or replace the administrator credential
python sessionguard.py --set-admin

# Optional: create users from the CLI
python sessionguard.py --add-user operator1 --as 2
python sessionguard.py --add-user operator2 --as 1

# Start on loopback (the default)
python sessionguard.py --port 8000

# In another terminal, expose SessionGuard, never the backend directly
cloudflared tunnel --url http://127.0.0.1:8000
```

When Cloudflare Tunnel is the only path to the loopback listener, enable trusted proxy headers so HTTPS cookies and source-IP restrictions work as expected. Set `SESSIONGUARD_TRUST_PROXY=1` **before starting SessionGuard**; exact commands for PowerShell and POSIX shells are shown below. Do not enable it when untrusted clients can connect directly to the app port.

Open the tunnel URL and sign in as the admin. Set the backend target in **GATEWAY TARGET**. The backend should listen on loopback, for example `127.0.0.1:8080`.

The default bind address is `127.0.0.1` so the gateway is not automatically exposed on every network interface. Use `--host 0.0.0.0` only when you deliberately need network access and have applied suitable firewall rules.

SessionGuard uses Waitress by default. `--dev-server` selects Flask's development server for local development only; do not use that mode for remote/public deployments. Flask explicitly cautions against using its development server in production deployments: <https://flask.palletsprojects.com/en/stable/deploying/>.

## CLI reference

```text
python sessionguard.py --set-admin
python sessionguard.py --add-user NAME --as N
python sessionguard.py --add-user NAME --as N --user-target http://127.0.0.1:8080
python sessionguard.py --list-users
python sessionguard.py --target http://127.0.0.1:8080
python sessionguard.py --host 127.0.0.1 --port 8000
python sessionguard.py --dev-server       # local development only
```

Additional per-user options for `--add-user` are `--user-ttl SECONDS`, `--user-ip IP/CIDR,...`, and `--user-ua SUBSTRING,...`.

## Admin panel and user portal

After admin login, SessionGuard routes to `/admin`. The panel can create/edit/delete user accounts, reset passwords, enable/disable accounts, set allowed concurrent sessions, route users to different backends, terminate sessions, and inspect/export the audit log.

Authenticated users can open `/auth/portal` to view their own sessions, label a device, or revoke one/all of their own sessions. Password resets, account disabling, and account deletion revoke the affected user's sessions.

## User file format

`users.txt` is created automatically. A record can contain the following whitespace-separated tokens:

```text
operator1:scrypt$16384$8$1$<32 hex salt chars>$<128 hex digest chars> AS:2
operator2:plaintext-temporary-pass AS:1 OFF
limiteduser:<credential> AS:1 TARGET:http://127.0.0.1:8081 TTL:3600 IP:127.0.0.1/32 UA:Firefox
```

- `AS:n`: maximum number of concurrent user sessions; default `1`.
- `TARGET:url`: optional per-user target; blank or absent uses the global target.
- `TTL:seconds`: optional per-user inactivity timeout.
- `IP:address/CIDR,...`: optional per-user source-IP allowlist.
- `UA:substring,...`: optional case-insensitive User-Agent substring allowlist.
- `OFF`: disable the account.

The sample strings above are format examples, not usable credentials. Use long, unique passphrases. Plaintext entries exist only for backward compatibility and should be replaced by the automatic hash upgrade on a successful login. `sg_sid` is reserved for SessionGuard; the gateway drops an upstream `Set-Cookie` using that exact name so it cannot overwrite the auth session.

The admin credential is stored separately in `admin_auth.txt` using this format:

```text
admin|scrypt$16384$8$1$<32 hex salt chars>$<128 hex digest chars>
```

Files are set to restrictive mode bits on POSIX systems. Windows ACLs are separate from POSIX mode bits, so protect the project directory with appropriate Windows permissions as well.

## Proxy and HTTPS configuration

SessionGuard should sit behind the trusted HTTPS proxy/tunnel when accessed remotely. Cookies are marked `Secure` when Flask sees the request as HTTPS. If the trusted proxy terminates TLS and forwards HTTP to SessionGuard, enable proxy-header support only when direct untrusted clients cannot reach the app port.

PowerShell:

```powershell
$env:SESSIONGUARD_TRUST_PROXY = "1"
python sessionguard.py --host 127.0.0.1 --port 8000
```

Linux/macOS:

```bash
SESSIONGUARD_TRUST_PROXY=1 python sessionguard.py --host 127.0.0.1 --port 8000
```

This setting trusts one proxy's `X-Forwarded-For` and `X-Forwarded-Proto` values. **Do not enable it when untrusted clients can connect directly to SessionGuard.** Werkzeug documents that trusting spoofable proxy headers incorrectly is a security issue: <https://werkzeug.palletsprojects.com/en/stable/deployment/proxy_fix/>.

## Security behavior and defaults

| Control | Behavior |
|---|---|
| Password hashing | Scrypt (`N=16384, r=8, p=1`); PBKDF2-SHA256 legacy hashes are upgraded on login |
| Session token | Random URL-safe token; `HttpOnly`, `SameSite=Lax`, `Secure` for HTTPS requests |
| Session expiry | 12-hour default inactivity TTL; global and per-user settings |
| CSRF | Single-use server-side login tokens plus session-bound tokens for state changes |
| Login lockout | Five failures; five-minute lock for IP and username |
| Rate limit | Default 240 requests per source IP per 60 seconds; configurable from admin |
| Proxy auth | All gateway methods, including `OPTIONS`, require a session |
| Proxy headers | Strips standard and `Connection`-nominated hop-by-hop headers; client-supplied forwarding and `X-SG-User` headers are replaced/removed |
| Malformed restrictions | Invalid non-empty IP or User-Agent restriction values fail closed rather than becoming unrestricted |
| Private response caching | Authenticated proxied responses receive `Cache-Control: no-store` and security headers |
| Backend target | Validated HTTP(S) URL; no target supplied by request data |
| Cookie namespace | `sg_sid` is reserved for SessionGuard; an upstream cookie with that exact name is dropped |
| Request size | 64 MiB default limit; override with `SESSIONGUARD_MAX_BODY` |
| State persistence | Atomic JSON/text-file writes; designed for one process and small deployments |

## File structure

```text
SessionGuard-main/
├── sessionguard.py
├── requirements.txt
├── README.md
├── tests/
│   └── test_sessionguard.py
├── admin_auth.txt       # created at setup
├── users.txt            # created at startup
└── data/                # created at startup
    ├── sessions.json
    ├── events.json
    └── config.json
```

## Tests

After installing dependencies, run:

```bash
python -m unittest discover -s tests -v
```

The regression tests cover target validation, fail-closed IP allowlist parsing, credential hash checks, unauthenticated `OPTIONS`, upstream header filtering, duplicate `Set-Cookie` forwarding, and file permissions where supported.

## Limitations

- HTTP web apps only; WebSockets and raw TCP/UDP are not supported.
- JSON/text files are not a multi-process database. Run a single SessionGuard process and keep the state directory private.
- This version has been syntax-checked and its pure helper functions smoke-tested in the authoring sandbox, but its Flask integration suite still needs to be run after installing dependencies.
- IP detection behind a proxy depends on correct, explicitly enabled trusted-proxy configuration.
- There is no MFA/TOTP, distributed session store, database transaction layer, or independent security audit.
- Do not expose the backend directly, and do not assume this gateway fixes vulnerabilities in the protected application.

## Made by

**Aryan Giri | giriaryan694-a11y**  
GitHub: https://github.com/giriaryan694-a11y
