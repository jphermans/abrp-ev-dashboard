# ABRP EV Dashboard — Raspberry Pi Edition

> 🚗 Self-hosted EV dashboard for Raspberry Pi 4/5. Serves a beautiful analytics dashboard for ABRP (A Better Routeplanner) Excel exports, with optional live ABRP API integration.

![Platform: Raspberry Pi](https://img.shields.io/badge/Platform-Raspberry%20Pi%204%2F5-c51a4a.svg)
![Server: Flask](https://img.shields.io/badge/Server-Flask-000000.svg)
![Autostart: systemd](https://img.shields.io/badge/Autostart-systemd-blue.svg)
![Rate Limited](https://img.shields.io/badge/ABRP%20API-Rate%20Limited-orange.svg)

---

## 🚀 Quick Install (2 minutes)

```bash
# Clone or copy this folder to your Pi
git clone https://github.com/jphermans/abrp-ev-dashboard.git
cd abrp-ev-dashboard/pi

# Run the installer
chmod +x scripts/install.sh
./scripts/install.sh
```

That's it. The installer will:
1. ✅ Copy files to `~/abrp-dashboard/`
2. ✅ Create a Python virtual environment
3. ✅ Install Flask + openpyxl
4. ✅ Register a systemd service (autostart on boot)
5. ✅ Start the dashboard

**Open** `http://<pi-ip>:8000` in your browser.

---

## 📋 Requirements

| Item | Minimum | Recommended |
|------|---------|-------------|
| Raspberry Pi | Pi 4 (2GB) | Pi 5 (4GB+) |
| OS | Raspberry Pi OS 64-bit | Bookworm/Debian 12 |
| SD Card | 8GB Class 10 | 32GB A2-rated |
| Python | 3.9+ | 3.11+ |
| Network | WiFi | Ethernet |

---

## 🎛️ Features

### Dashboard
- 📊 **8 interactive charts** — distance, energy, SoC, odometer, weekday, distribution, provider breakdown
- 📋 **Full data tables** — all activities, charge locations with providers
- 🔀 **Time filters** — Day / Week / Month / Year / All
- 📂 **Excel upload** — drag your ABRP exports, auto-parsed and merged
- 📄 **PDF export** — full dashboard as multi-page PDF

### Settings Panel (⚙️ button)
- 🌙 **Light / Dark mode** — instant toggle, saved in browser
- 🌈 **6 color palettes** — default, warm, ocean, forest, sunset, mono
- 🔑 **ABRP API token** — securely stored in browser localStorage
- 🔗 **Test connection** — verify your API key works
- ℹ️ **System info** — Pi model, record count, server status

### Server
- 🐍 **Flask backend** — lightweight, perfect for Pi
- ⚡ **Rate limiting** — max 2 ABRP API calls/second (as required)
- 💾 **Auto-caching** — parsed data cached as JSON (5 min TTL)
- 🔄 **Auto-import** — Excel files in `data/` auto-imported on startup
- 🏠 **Autostart on boot** — systemd service, auto-restart on crash

---

## 🔧 Manual Operations

```bash
# Start / stop / restart
sudo systemctl start abrp-dashboard
sudo systemctl stop abrp-dashboard
sudo systemctl restart abrp-dashboard

# Check status
sudo systemctl status abrp-dashboard

# View live logs
sudo journalctl -u abrp-dashboard -f

# Change port
sudo systemctl edit abrp-dashboard
# Add: [Service]\nEnvironment=PORT=8080
sudo systemctl restart abrp-dashboard
```

---

## 📂 Adding Your Data

### Option 1: Upload button
Click 📂 Upload in the dashboard → select your ABRP `.xlsx` files.

### Option 2: Copy to data folder
```bash
cp your-abrp-export.xlsx ~/abrp-dashboard/data/
sudo systemctl restart abrp-dashboard
```

### Option 3: ABRP API (requires premium API key)
1. Get an API key at [iternio.com/api](https://www.iternio.com/api)
2. Open the dashboard → click ⚙️ Settings → paste your token
3. Click "Test verbinding"

> ⚠️ **Note:** Fetching activities (trips/charges) via the API requires a key with the `session` feature, which needs a premium plan. The free API key works for planning endpoints only. Excel upload works with any key tier.

---

## 📁 Project Structure

```
pi/
├── server.py                    # Flask server (ABRP proxy, rate limiter, data API)
├── templates/
│   └── dashboard.html           # Full dashboard (responsive, settings panel)
├── scripts/
│   ├── install.sh               # One-command installer
│   └── abrp-dashboard.service.template  # systemd template
├── data/                        # Excel files + cached JSON
└── README.md                    # This file
```

---

## 🔒 Privacy & Security

- **100% local** — all data stays on your Pi
- **No external calls** unless you use the ABRP API token feature
- **API token** stored in browser localStorage (never sent to third parties)
- **Rate limited** — the server enforces max 2 requests/second to ABRP
- **No HTTPS** by default — for local network use. Add a reverse proxy (nginx/caddy) for HTTPS

---

## 🛠️ Troubleshooting

| Problem | Solution |
|---------|----------|
| Port 8000 in use | `sudo systemctl edit abrp-dashboard` → set `PORT=8080` |
| Blank dashboard | Check: `sudo journalctl -u abrp-dashboard -f` |
| No data | Put `.xlsx` files in `~/abrp-dashboard/data/` and restart |
| ABRP API 403 | Your API key needs the `session` feature (premium plan) |
| SD card full | Check `~/abrp-dashboard/data/` for old Excel files |

---

## 📄 License

MIT
