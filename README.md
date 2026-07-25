```md
┌──────────────────────────────────────────────┐
│        ◢ S E S S I O N G U A R D            │
│        · auth gateway · session shield       │
└──────────────────────────────────────────────┘
Made by Aryan Giri | giriaryan694-a11y
```

# ◢ SessionGuard

**SessionGuard** is a secure HTTP gateway for local web tools.

It sits in front of your app, handles authentication, enforces per-user session limits, and forwards only approved traffic to your backend service. It is built for simple deployment, fast user management, and low-friction control through a web admin panel.

---

## What it does

SessionGuard protects any **HTTP web app** running locally, such as:

* internal dashboards
* admin tools
* browser-based utilities
* private web services
* local development apps exposed through a tunnel

Instead of exposing your tool directly, you expose **SessionGuard**.

```text
client ──► cloudflared ──► SessionGuard :8000 ──► local tool :8080
```

Your tool stays private on `127.0.0.1`, while SessionGuard acts as the public gatekeeper.

---

## Core features

* **Authentication gateway** for HTTP web apps
* **Per-user session limits** using `AS` (Allowed Sessions)
* **Web admin panel** for full configuration
* **User portal** for viewing and ending active sessions
* **Text-file user storage** instead of SQL
* **Live backend target switching** from the admin page
* **CSRF protection** and secure session handling
* **Audit logging** for auth and admin actions
* **Simple deployment** with Flask

---

## Why SessionGuard

SessionGuard is designed for the case where one tool needs controlled access by multiple users, but you do not want the overhead of a database or a full identity stack.

It gives you:

* a small attack surface
* easy file-based management
* session control per user
* admin visibility into active logins
* a clean front door for local apps exposed through tunnels

---

## How it works

1. A client opens the gateway URL.
2. SessionGuard shows a login page.
3. The user authenticates successfully.
4. SessionGuard checks how many sessions that user already has.
5. If the user is under their limit, access is granted.
6. If the limit is reached, the user is blocked or asked to end another session.
7. Approved traffic is forwarded to the target local tool.

---

## Quick start

```bash
# Install dependencies
pip install -r requirements.txt

# Start SessionGuard
python sessionguard.py --port 8000

# Expose SessionGuard, not the backend tool
cloudflared tunnel --url http://127.0.0.1:8000
```

Then open the tunnel URL and log in through the gateway.

After login, use the **admin panel** to configure users, sessions, and the backend target.

---

## Admin panel

SessionGuard includes an admin panel for full control over the gateway.

From the admin panel, you can:

* create users
* edit users
* delete users
* reset passwords
* increase or decrease Allowed Sessions
* view active sessions
* log out users remotely
* change the backend target
* review audit logs

There is **no separate CLI setup workflow** for normal administration.
Everything is managed from the web panel after logging in.

---

## User portal

Each user can manage their own active sessions from the portal.

Users can:

* see their active sessions
* log out from another device
* end all their sessions
* free up a slot when they hit their session limit

---

## User file format

SessionGuard uses a simple text file for user management.

Example:

```txt
admin:admin123 AS:2
admin2:admin223 AS:1
```

### Meaning

* `admin` / `admin2` → username
* `admin123` / `admin223` → password
* `AS:2` / `AS:1` → Allowed Sessions

If a user is allowed `AS:2`, they can stay logged in on two browsers or devices at the same time. A third login should be rejected or forced to replace an older session, depending on your policy.

---

## Admin credential file

The admin account is stored separately in:

```txt
admin_auth.txt
```

This file should hold the admin login securely and should never be exposed through the web UI.

---

## HTTPS proxy support

SessionGuard can sit behind an HTTPS proxy that converts secure client traffic into local HTTP traffic.

Example setup:

* **HTTP server:** `localhost:8000`
* **HTTPS proxy:** `localhost:8080`

Instead of opening:

```text
http://IP:8000
```

you open:

```text
https://IP:8080
```

The proxy accepts the secure connection, decrypts it locally, forwards the request to your HTTP server, and sends the response back to the client.

Related project:

* https://github.com/giriaryan694-a11y/http2https

This makes SessionGuard easier to place behind secure access layers without changing the backend tool itself.

---

## Security notes

SessionGuard is intended to be secure by default.

Recommended protections include:

* **Flask session cookies** with secure settings
* **CSRF protection** on forms and admin actions
* **Password hashing** instead of plaintext storage
* **HTTP-only cookies**
* **secure cookie flags** when using HTTPS
* **audit logging** for sensitive events
* **session revocation** on password reset or user disable
* **local-only backend binding** for the protected tool

### Important deployment rule

* Bind **SessionGuard** to the exposed port
* Bind the **backend tool** only to `127.0.0.1`
* Point the tunnel to **SessionGuard**, not directly to the tool

---

## Example deployment

```text
SessionGuard :8000      → exposed through tunnel
http2https :8080        → optional HTTPS proxy in front
Your tool :8080         → stays local only behind the shield
```

This setup keeps the tool hidden behind the gateway while allowing secure HTTPS access at the edge.

---

## Suggested file structure

```text
sessionguard/
├── sessionguard.py
├── requirements.txt
├── README.md
├── admin_auth.txt
├── users.txt
└── data/
    ├── sessions.json
    ├── events.json
    └── config.json
```

---

## Technology stack

* **Python**
* **Flask**
* **HTML / CSS / templates**
* **Text-file based storage**
* **Reverse proxy style forwarding for local web apps**

---

## Limitations

* Designed for **HTTP web apps only**
* Not intended for raw TCP services
* WebSocket support may require extra handling
* Text-file storage is best for small to medium private setups
* Best suited for one operator or a small trusted team

---

## Roadmap ideas

* optional MFA for admin login
* stronger password hashing
* per-user device labels
* session expiry controls
* activity export
* rate limiting
* theme toggle for the admin panel
* better logging filters
* IP-based access rules

---

## Made by

```text
Made by Aryan Giri | giriaryan694-a11y
```

## Credits

```text
◢ SESSIONGUARD
auth gateway · session shield · AS enforcement
```
