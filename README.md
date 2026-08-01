# 🚗 ABRP EV Dashboard

> A self-hosted analytics dashboard for electric vehicle data. Runs anywhere — Raspberry Pi, Intel/AMD, NAS, cloud. Import ABRP (A Better Routeplanner) Excel exports, sync directly from your car manufacturer's servers, and get rich insights into driving habits, charging sessions, and energy consumption.

![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%20%7C%20Intel%2FAMD%20%7C%20ARM64%20%7C%20x86--c51a4a.svg)
![Server: Flask](https://img.shields.io/badge/Server-Flask-000000.svg)
![Docker](https://img.shields.io/badge/Docker-Multi--arch-2496ED.svg)
![Multi-user](https://img.shields.io/badge/Multi--user-✓-green.svg)
![i18n](https://img.shields.io/badge/i18n-4%2B%20languages-purple.svg)
![Responsive](https://img.shields.io/badge/Responsive-Mobile%20First-brightgreen.svg)

---

## 🚀 Quick Start

### Option A: Docker (recommended)

```bash
git clone https://github.com/YOUR_USERNAME/abrp-ev-dashboard.git
cd abrp-ev-dashboard/docker

# (Optional) Copy your ABRP Excel exports
cp ~/Downloads/*.xlsx data/

# Build and run
docker compose up -d --build
```

Open `http://<host-ip>:8765` — login with `admin` / `admin123` (you'll be asked to change it immediately).

### Option B: Bare metal (any Linux)

```bash
git clone https://github.com/YOUR_USERNAME/abrp-ev-dashboard.git
cd abrp-ev-dashboard
chmod +x scripts/install.sh
./scripts/install.sh
```

The installer creates a venv, installs dependencies, registers a systemd service (autostart on boot), and starts the dashboard.

Works on Raspberry Pi (ARM64), Intel NUC, AMD server, NAS, or any Debian/Ubuntu-based system.

### Option C: Standalone HTML (no server)

For quick local use without authentication or multi-user:

```bash
# Just open index.html in a browser — works offline
open index.html       # macOS
xdg-open index.html   # Linux
start index.html      # Windows
```

---

## 📋 Requirements

The dashboard runs on **any Linux system** — Raspberry Pi, Intel/AMD servers, NUCs, NAS devices, VMs, or cloud instances. Docker image supports both **ARM64** (Pi, Mac M-series) and **AMD64** (Intel/AMD) architectures.

| Item | Minimum | Recommended |
|------|---------|-------------|
| Hardware | Raspberry Pi 4, Intel NUC, or any x86/ARM box | Pi 5, NUC, or dedicated mini-PC |
| Architecture | ARM64 or x86_64 (AMD64) | Same |
| RAM | 512 MB free | 1 GB free |
| OS | Any Linux (Debian, Ubuntu, Alpine, etc.) | Debian 12 / Ubuntu 24.04 |
| Python | 3.9+ | 3.11+ |
| Docker | 20.10+ (Docker mode only) | Latest |
| Storage | 1 GB | 8 GB (Excel files accumulate over time) |

---

## ✨ Features

### 📊 Dashboard

- **8 interactive charts** — distance, energy, battery SoC, odometer, weekday distribution, distance buckets, provider breakdown
- **6 KPI cards** — total km, total kWh, consumption (kWh/100km), active days, top provider, longest trip
- **Vehicle info bar** — shows vehicle name, odometer, battery SoC, total km, trip/charge counts. Uses live connector data or falls back to Excel data automatically
- **Time filters** — Day / Week / Month / Year / All — all charts update instantly
- **Date range picker** — select a custom from/to date range to filter all data. Works in combination with time filters
- **Full data tables** — every trip and charging session with provider detection
- **Charge location analytics** — per-provider session counts, total kWh, last visit
- **PDF export** — save the entire dashboard as a multi-page report
- **Fully responsive** — works on phones, tablets, and desktops (all data accessible at every screen size)
- **Centered button text** — all buttons have centered labels on every screen size

### 🚗 Multi-Brand Vehicle Connectors (Plugin System)

Connect your car directly — no manual Excel exports needed. Each user can connect their own vehicle(s).

| Brand | Status | Auth | Data |
|-------|--------|------|------|
| 🚗 **Volkswagen WeConnect** | ✅ Implemented | VW email + password (free) | Trips, charging, odometer, SoC |
| 🚀 **Tesla** | 🔧 Stub | Tesla email + password | (requires `teslajsonpy`) |
| 🔵 **BMW Connected Drive** | 🔧 Stub | BMW email + password + region | (requires `bimmer_connected`) |
| 🟦 **Hyundai / Kia Connect** | 🔧 Stub | Email + password + brand + region | (requires `hyundai_kia_connect_api`) |
| ⭐ **Mercedes me** | 🔧 Stub | Mercedes email + password | (requires `mercedes_jsonio`) |

**Adding a new brand is 1 file + 1 line:**

```python
# connectors/polestar_connector.py — subclass BaseConnector
class PolestarConnector(BaseConnector):
    @property
    def brand(self): return "polestar"
    @property
    def display_name(self): return "Polestar"
    @property
    def credential_fields(self): return [...]
    def test_connection(self): ...
    def sync(self): ...

# connectors/__init__.py — register it
CONNECTORS["polestar"] = PolestarConnector
# Done! The settings panel auto-renders the new brand card.
```

### 🔑 Data Sources

| Source | Cost | How |
|--------|------|-----|
| 📂 **Excel upload** | Free | Upload ABRP exports via the dashboard |
| 🚗 **Manufacturer API** | Free | VW WeConnect (email + password). More brands via plugin system |
| 🔑 **ABRP API** | Premium key | Fetch activities directly from ABRP servers |

### 👥 Multi-User & Fleet Support

- **User accounts** — register, login, logout (SQLite-backed)
- **Multiple vehicles per user** — each user can track multiple cars with separate data
- **Vehicle management** — add, edit, delete vehicles with name, model, license plate
- **Fleet manager role** — designated users can see a fleet overview of all vehicles across all users
- **Fleet overview page** — total vehicles, total km, per-user breakdown with vehicle stats
- **Strict data isolation** — every vehicle's data in separate directories
- **Default admin** — auto-created on first run (`admin` / `admin123`, forced to change on first login)
- **Per-vehicle connectors** — each vehicle can have its own manufacturer connection
- **Per-user language uploads** — custom language files stored per user
- **Per-user caching** — cache keys include user + vehicle ID to prevent cross-user data leaks
- **Account deletion** — users can delete their own account from Settings

### 🌐 Internationalization (i18n)

- **4 built-in languages**: 🇳🇱 Dutch, 🇬🇧 English, 🇫🇷 French, 🇩🇪 German
- **Custom languages**: Download a JSON template → translate → upload
- Uploaded languages appear in the language dropdown with a ⭐ marker
- Built-in languages cannot be overwritten or deleted

### ⚙️ Settings Panel

| Section | Features |
|---------|----------|
| 🌐 **Language** | Dropdown selector, template download, custom upload |
| 🎨 **Theme** | Dark / Light mode toggle |
| 🌈 **Color palette** | 6 palettes: Default, Warm, Ocean, Forest, Sunset, Mono |
| 🔑 **ABRP API token** | Save, test, delete |
| 🚗 **Vehicle connections** | Dynamic — auto-renders all registered connector brands |
| ℹ️ **System** | Server status, Pi model, record count, active connections |

### ❓ Built-in Help

A comprehensive help modal (❓ button) explains every chart, KPI card, filter, and feature in plain language.

---

## 🏗️ Architecture

### Modular Server

```
server.py              Entry point + startup (64 lines)
config.py              Paths, rate limiter, cache
excel_parser.py        ABRP Excel parsing + provider detection
data_utils.py          Shared merge/dedup helper (atomic writes)
auth.py                SQLite users DB, PBKDF2 auth, sessions, login/register/logout
routes/
  core.py              Dashboard page, data API, upload, status
  abrp.py              ABRP API proxy (requires premium key)
  connectors.py        Generic /api/connector/<brand>/* endpoints
  locales.py           Language list, download template, upload, delete
connectors/
  base.py              BaseConnector ABC — subclass to add brands
  vw_connector.py      Volkswagen WeConnect (implemented)
  tesla_connector.py   Tesla (stub)
  bmw_connector.py     BMW (stub)
  hyundai_kia.py       Hyundai/Kia (stub)
  mercedes.py          Mercedes (stub)
  __init__.py          Registry — add new brands here
locales/
  nl.json, en.json, fr.json, de.json
templates/
  dashboard.html       Full dashboard (responsive, i18n, settings, help)
  login.html           Login/register page
```

### API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Dashboard (or login page if not authenticated) |
| `POST /api/auth/register` | Create account |
| `POST /api/auth/login` | Login |
| `POST /api/auth/logout` | Logout |
| `GET /api/auth/me` | Current user info |
| `POST /api/auth/delete-account` | Permanently delete account + all data (password required) |
| `GET /api/vehicles` | List all vehicles for current user |
| `POST /api/vehicles` | Create a new vehicle |
| `DELETE /api/vehicles/<id>` | Delete a vehicle and all its data |
| `GET /api/vehicles/<id>/data` | Get activity data for a specific vehicle |
| `POST /api/vehicles/<id>/upload` | Upload Excel files for a specific vehicle |
| `GET /api/fleet` | Fleet overview (fleet managers + admins only) |
| `GET /api/data` | Get all activity records (per-user) |
| `POST /api/upload` | Upload ABRP Excel files (per-user) |
| `GET /api/status` | Server health + user info |
| `GET /api/connectors` | List all vehicle connectors |
| `POST /api/connector/<brand>/config` | Save/delete connector credentials |
| `GET /api/connector/<brand>/status` | Check if connector is configured |
| `POST /api/connector/<brand>/test` | Test connector connection |
| `POST /api/connector/<brand>/sync` | Fetch trips + charging from manufacturer |
| `GET /api/connector/<brand>/vehicle-info` | Fetch vehicle details (model, odometer, battery) |
| `GET /api/locales` | List available languages |
| `GET /api/locales/<code>` | Get a language file |
| `GET /api/locales/template` | Download translation template |
| `POST /api/locales/upload` | Upload custom language |
| `DELETE /api/locales/<code>` | Delete custom language |

### Docker

| Metric | Value |
|--------|-------|
| Base image | `python:3.11-slim-bookworm` |
| Memory (idle) | ~24 MB RSS |
| CPU (idle) | 0.03% |
| Image size | ~120 MB |
| Max memory | 256 MB (enforced) |
| Max CPU | 0.5 cores |
| Health check | Built-in |
| Log rotation | 2 MB × 3 files |

---

## 🔧 Operations

### systemd (bare metal)

```bash
sudo systemctl {start|stop|restart|status} abrp-dashboard
sudo journalctl -u abrp-dashboard -f          # live logs

# Change port
sudo systemctl edit abrp-dashboard
# Add: [Service]\nEnvironment=PORT=8080
sudo systemctl restart abrp-dashboard
```

### Docker

```bash
docker compose up -d                          # start
docker compose down                           # stop
docker compose up -d --build                  # rebuild after code changes
docker compose logs -f                        # live logs
docker stats abrp-dashboard                   # resource usage
```

---

## 📂 Adding Data

### Excel upload (easiest)
Login → click 📂 Upload → select `.xlsx` files. Auto-parsed, miles→km converted, providers detected.

### Manufacturer sync (VW)
Login → ⚙️ Settings → 🚗 Volkswagen WeConnect → enter VW email + password → click 🔄 Sync.

> **VW Note:** The VW connector uses the [CarConnectivity](https://github.com/tillsteinbach/CarConnectivity) library (successor to WeConnect-python). As of July 2026, VW's BFF auth endpoints are still being adapted. The connector handles errors gracefully and suggests Excel upload as fallback. CarConnectivity also supports Skoda, Audi, Seat/Cupra and Tronity through the same plugin architecture.

### ABRP API
Login → ⚙️ Settings → 🔑 ABRP API Token → paste key → Test. Requires a premium API key with the `session` feature.

---

## 🛠️ Troubleshooting

| Problem | Solution |
|---------|----------|
| Can't access dashboard | Check firewall / port forwarding |
| Port 8000 in use | Set `PORT=8080` in systemd or docker-compose |
| VW login fails | VW changed auth flow (May 2026). Use Excel upload until library is updated |
| ABRP API 403 | Free-tier keys lack the `session` feature — use Excel upload |
| Blank dashboard | Upload data or run a manufacturer sync |
| No data after sync | Vehicle may not expose trip history via WeConnect |
| SD card full | Clean `data/users/*/` for old files |
| Docker: cgroup warnings | Normal on some Pi kernels — memory limits may be ignored |

---

## 🔒 Privacy & Security

- **100% local** — all data stays on your Pi/server
- **Multi-user isolation** — each user's data in separate directories
- **PBKDF2 password hashing** (100,000 iterations SHA-256 + salt) — GPU-resistant
- **Default admin**: `admin` / `admin123` — forced to change on first login
- **Forced password change** on first login — admin must set a new password before accessing the dashboard
- **Password change** available in Settings for all users (current + new + confirm)
- **Auto-logout on browser close** — session cookies are non-persistent; closing the browser logs you out
- **Session cookie**: `SameSite=Strict`, `HttpOnly`, persisted secret key (survives server restarts)
- **Path traversal protection**: `secure_filename` on uploads, regex-validated locale codes
- **All API endpoints require authentication** (including locale management and ABRP proxy)
- **Upload size limit**: 50 MB max
- **Atomic JSON writes**: temp file + `os.replace()` prevents corruption on crash
- **XSS prevention**: all user-facing data escaped via `escapeHtml()` before rendering
- **Credentials** stored in `data/users/<id>/connector_<brand>.json` (local only)
- **Rate limited** — max 2 external API requests/second
- **No HTTPS by default** — for LAN use. Add nginx/caddy reverse proxy for HTTPS

---

## 📄 License

MIT — free to use, modify, and distribute.
