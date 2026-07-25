
┌──────────────────────────────────────────────┐
│        ◢ S E S S I O N G U A R D            │
│        · auth gateway · session shield       │
└──────────────────────────────────────────────┘

Made by Aryan Giri | giriaryan694-a11y

# ◢ SessionGuard

**SessionGuard** is a secure HTTP authentication gateway and session enforcement shield for local web tools.

It sits in front of your app, handles authentication, enforces per-user concurrent session limits, and forwards only approved traffic to your backend service. It is built for simple deployment, fast user management, and low-friction control through a web admin panel.

---

## What it does

SessionGuard protects any **HTTP web app** running locally, such as:

- internal dashboards
- admin tools
- browser-based utilities
- private web services
- local development apps exposed through a tunnel

Instead of exposing your tool directly, you expose **SessionGuard**.

```text
client ──► cloudflared ──► SessionGuard :8000 ──► local tool (127.0.0.1:PORT)
````

Your tool stays private on `127.0.0.1`, while SessionGuard acts as the public gatekeeper.

---

## Core features

* **Authentication gateway** — every request hits a login gate first
* **Per-user session limits** — `AS` (Allowed Sessions) controls how many concurrent browsers or devices a user can use
* **Server-side CSRF protection** — single-use tokens stored in memory, no cookie dependency, works across browsers and privacy extensions
* **Bruteforce lockout** — 5 failed attempts triggers a 5-minute lock per IP and per username
* **Web admin panel** — full user management, session control, live backend routing, and audit log
* **User self-service portal** — users can view and end their own sessions at `/auth/portal`
* **Text-file user storage** — no database, no SQL, just `users.txt`
* **Auto credential hashing** — plaintext passwords in `users.txt` are upgraded to PBKDF2-SHA256 (200k rounds) on first login
* **Live backend target switching** — change where traffic is forwarded from the admin panel, no restart needed
* **Audit logging** — all auth events, admin actions, and session changes are recorded
* **No backend address leakage** — the login page never reveals the target backend address
* **Simple deployment** — single Python file, Flask, no build step

---

## Why SessionGuard

SessionGuard is designed for the case where one tool needs controlled access by multiple users, but you do not want the overhead of a database or a full identity stack.

It gives you:

* a small attack surface
* easy file-based management
* strict session control per user
* admin visibility into all active logins
* a clean front door for local apps exposed through tunnels
* no information leakage about internal infrastructure

---

## How it works

1. A client opens the gateway URL.
2. SessionGuard shows a login page. No backend address, no admin links, and no internal details are exposed.
3. The user authenticates with their credentials.
4. SessionGuard checks how many active sessions that user already has.
5. If the user is under their `AS` limit, a session is created and access is granted.
6. If the limit is reached, the user is told their session limit has been reached and directed to free a slot.
7. Approved traffic is forwarded to the configured backend target.
8. Admin users are routed to the admin panel after login. Regular users are forwarded to the tool.

---

## Quick start

```bash
# Install dependencies
pip install flask requests

# 1. Set up the admin account
python sessionguard.py --set-admin

# 2. (Optional) Add users from CLI
python sessionguard.py --add-user operator1 --as 2
python sessionguard.py --add-user operator2 --as 1

# 3. Start the gateway
python sessionguard.py --port 8000

# 4. Expose SessionGuard through a tunnel (NOT the backend tool)
cloudflared tunnel --url http://127.0.0.1:8000
```

Open the tunnel URL. Every visitor hits the login page. Log in as admin to configure the backend target and manage users.

---

## CLI reference

```text
python sessionguard.py --set-admin              Create or overwrite the admin account
python sessionguard.py --add-user NAME --as N   Add a user with N allowed sessions
python sessionguard.py --list-users             List all users and their status
python sessionguard.py --target HOST:PORT       Set initial backend target
python sessionguard.py --host 0.0.0.0           Bind address (default: 0.0.0.0)
python sessionguard.py --port 8000              Listen port (default: 8000)
```

---

## Admin panel

After logging in as the admin user, you are routed to the admin panel automatically.

From the admin panel you can:

* set the gateway target — where authenticated traffic is forwarded
* create, edit, and delete users
* reset user passwords, which revokes all their sessions
* increase or decrease Allowed Sessions per user
* view all active sessions across all users
* terminate any session remotely
* disable or enable user accounts
* review the full audit log

The admin panel is never advertised at startup. There is no public link to it. Only authenticated admin sessions can reach it.

---

## User portal

Each authenticated user can manage their own sessions at `/auth/portal`.

Users can:

* see all their active sessions (IP, device, time)
* end a specific session on another device
* end all their sessions at once
* free up a slot when they hit their session limit

---

## User file format

SessionGuard uses a plain text file (`users.txt`) for user storage.

```txt
# SessionGuard users — user:credential AS:<allowed sessions> [OFF]
# plaintext credentials are auto-hashed on first login
operator1:$a1b2c3...hash... AS:2
operator2:$d4e5f6...hash... AS:1
tempuser:SomePass123 AS:1 OFF
```

### Fields

| Field               | Meaning                                                               |
| ------------------- | --------------------------------------------------------------------- |
| `operator1`         | Username (2–32 chars, `a-z 0-9 _ . -`)                                |
| `$a1b2c3...hash...` | PBKDF2-SHA256 credential, auto-upgraded from plaintext on first login |
| `AS:2`              | Allowed Sessions — max concurrent logins                              |
| `OFF`               | Account disabled flag                                                 |

If a user has `AS:1`, they can only be logged in on one browser or device at a time. A second login attempt is blocked until they free the slot.

---

## Admin credential file

The admin account is stored separately in `admin_auth.txt`:

```txt
admin|$salt$hash
```

* PBKDF2-SHA256, 200,000 rounds
* file permissions set to `600`
* never exposed through the web UI
* never transmitted to the backend

---

## Security model

| Protection                 | Implementation                                                                               |
| -------------------------- | -------------------------------------------------------------------------------------------- |
| Password storage           | PBKDF2-SHA256, 200k rounds, random 16-byte salt                                              |
| CSRF (login form)          | Server-side single-use tokens, 10-minute TTL, no cookie dependency                           |
| CSRF (authenticated forms) | Session-bound token, validated on every state-changing request                               |
| Bruteforce                 | 5 failures → 5-minute lockout per IP and per username                                        |
| Session tokens             | `secrets.token_urlsafe(32)`, HttpOnly, SameSite=Lax, Secure when behind HTTPS                |
| Session TTL                | 12 hours, auto-purged                                                                        |
| Cookie stripping           | Gateway strips its own auth cookies by exact name before forwarding to backend               |
| Backend isolation          | Target never shown on login page, never leaked in error pages                                |
| File permissions           | `users.txt`, `admin_auth.txt`, `data/` all chmod `600/700`                                   |
| Headers                    | CSP, X-Content-Type-Options, X-Frame-Options: DENY, Referrer-Policy, Cache-Control: no-store |
| Session revocation         | All sessions killed on password reset, account disable, or user deletion                     |
| Audit trail                | Last 100 events stored with timestamp, kind, and detail                                      |

---

## HTTPS proxy support

SessionGuard can sit behind an HTTPS proxy that terminates TLS and forwards plain HTTP locally.

```text
client ──HTTPS──► proxy :443 ──HTTP──► SessionGuard :8000 ──► tool :PORT
```

When `X-Forwarded-Proto: https` is present, session cookies are set with the `Secure` flag automatically.

Related project: [http2https](https://github.com/giriaryan694-a11y/http2https)

---

## Deployment rules

```text
✓ Bind SessionGuard to 0.0.0.0:8000 (faces outward)
✓ Bind your backend tool to 127.0.0.1:PORT (stays local)
✓ Point cloudflared / tunnel at SessionGuard :8000
✗ Never expose the backend tool directly
✗ Never point the tunnel at the tool's port
```

---

## File structure

```text
sessionguard/
├── sessionguard.py        ← the entire gateway (single file)
├── requirements.txt       ← flask, requests
├── README.md
├── admin_auth.txt         ← admin credential (chmod 600, auto-created)
├── users.txt              ← user registry (chmod 600, auto-created)
└── data/                  ← runtime state (chmod 700, auto-created)
    ├── sessions.json      ← active session tokens
    ├── events.json        ← audit log (last 100)
    └── config.json        ← gateway target
```

---

## Technology stack

* **Python 3**
* **Flask** — web framework and reverse proxy
* **requests** — upstream forwarding
* **Embedded HTML/CSS/JS** — no build step, no external assets except Google Fonts
* **Text-file + JSON storage** — no database

---

## Limitations

* Designed for **HTTP web apps only**
* Not intended for raw TCP or UDP services
* WebSocket proxying may require extra handling
* Text-file storage is best for small to medium private setups
* Single-process Flask dev server is sufficient for the intended use case
* In-memory CSRF token store resets on restart, so users just reload the login page

---

## Roadmap ideas

* optional TOTP / MFA for admin login
* per-user device labels and naming
* configurable session expiry
* activity log export (JSON / CSV)
* IP-based allow/deny rules
* rate limiting on the gateway itself
* theme toggle for the admin panel
* structured logging with log levels
* health-check endpoint for monitoring

---

## Made by

```text
Made by Aryan Giri | giriaryan694-a11y
GitHub: https://github.com/giriaryan694-a11y
```

---

## Credits

```text
◢ SESSIONGUARD
auth gateway · session shield · AS enforcement
```

```
```
