# 🐳 ABRP EV Dashboard — Docker

> Run the ABRP dashboard in Docker on Raspberry Pi 4/5, NAS, or any Docker host.
> Low-resource footprint: **~80MB RAM, multi-arch (ARM64 + AMD64)**.

![Docker](https://img.shields.io/badge/Docker-✓-2496ED.svg)
![Arch: Multi](https://img.shields.io/badge/Architecture-ARM64%20%2B%20AMD64-green.svg)
![RAM: 256MB max](https://img.shields.io/badge/RAM-256MB%20max-orange.svg)

---

## 🚀 Quick Start

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/abrp-ev-dashboard.git
cd abrp-ev-dashboard/docker

# (Optional) Copy your ABRP Excel exports
cp ~/Downloads/*.xlsx data/

# Build and run
docker compose up -d --build
```

**Open** `http://<pi-ip>:8000` 🎉

---

## 📊 Resource Usage

| Resource | Limit | Typical |
|----------|-------|---------|
| **RAM** | 256 MB | ~80 MB idle |
| **CPU** | 0.5 cores | <1% idle |
| **Disk** (image) | ~120 MB | python:3.11-slim + flask |
| **Disk** (data) | your Excel files | ~10-50 KB per file |

> These limits are enforced by Docker — the container can never OOM your Pi.

---

## ⚙️ Configuration

### Change the port
```bash
# Option 1: Environment variable
ABRP_PORT=9000 docker compose up -d

# Option 2: Edit docker-compose.yml
# Change "${ABRP_PORT:-8000}:8000" to "9000:8000"
```

### Add Excel data
```bash
# Option 1: Copy to the mounted volume
cp your-export.xlsx data/
docker compose restart

# Option 2: Upload via the dashboard web UI
# Click 📂 Upload button
```

### Adjust resource limits
Edit `docker-compose.yml`:
```yaml
deploy:
  resources:
    limits:
      memory: 512M    # increase if needed
      cpus: "1.0"     # full core
```

---

## 🔧 Commands

```bash
# Start
docker compose up -d

# Stop
docker compose down

# Rebuild after code changes
docker compose up -d --build

# View logs
docker compose logs -f

# Check resource usage
docker stats abrp-dashboard

# Check health
docker inspect --format='{{.State.Health.Status}}' abrp-dashboard
```

---

## 🏗️ Dockerfile Details

| Choice | Why |
|--------|-----|
| `python:3.11-slim-bookworm` | ~45MB base, Debian-compatible with Pi OS |
| `gunicorn` (2 workers) | Production WSGI server, better than Flask dev server |
| `--max-requests 100` | Auto-restart workers to prevent memory leaks |
| No build tools | All deps are pure-Python wheels — no gcc needed |
| `.dockerignore` | Excludes venv, screenshots, .git — smaller build context |

---

## 🍓 Pi-Specific Notes

### Docker installation on Raspberry Pi
```bash
# Install Docker
curl -fsSL https://get.docker.com | sh

# Add user to docker group (avoid sudo)
sudo usermod -aG docker $USER

# Log out and back in, then:
docker compose version
```

### Performance on Pi 4 vs Pi 5
| Model | Boot time | Page load | Notes |
|-------|-----------|-----------|-------|
| Pi 5 (4GB) | ~3s | <100ms | Excellent |
| Pi 4 (2GB) | ~5s | <200ms | Good, stays within 256MB |
| Pi 4 (1GB) | ~5s | <300ms | Reduce to 1 worker if tight |

### Reducing memory further
Edit the CMD in `Dockerfile`:
```dockerfile
# Single worker, no threads — absolute minimum
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--timeout", "120", "server:app"]
```
And in `docker-compose.yml`:
```yaml
deploy:
  resources:
    limits:
      memory: 128M
```

---

## 📁 File Structure

```
docker/
├── Dockerfile              # Multi-arch image definition
├── docker-compose.yml      # Service config with resource limits
├── .dockerignore           # Excludes venv, .git, screenshots, etc.
├── requirements.txt        # Python dependencies (flask, gunicorn, openpyxl)
├── data/                   # Your Excel files (mounted volume)
│   └── .gitkeep
└── README.md               # This file
```
