<p align="center">
  <img src="../docs/logo.svg" width="120" alt="Gemini Business2API logo" />
</p>
<h1 align="center">Gemini Business2API</h1>
<p align="center">Empowering AI with seamless integration</p>
<p align="center">
  <a href="../README.md">简体中文</a> | <strong>English</strong>
</p>
<p align="center"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" /> <img src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white" /> <img src="https://img.shields.io/badge/FastAPI-0.110-009688?logo=fastapi&logoColor=white" /> <img src="https://img.shields.io/badge/Vue-3-4FC08D?logo=vue.js&logoColor=white" /> <img src="https://img.shields.io/badge/Vite-7-646CFF?logo=vite&logoColor=white" /> <img src="https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white" /></p>

<p align="center">Convert Gemini Business to OpenAI-compatible API with multi-account load balancing, image generation, video generation, multimodal capabilities, and built-in admin panel.</p>

---

## 📜 License & Disclaimer

**License**: MIT License - See [LICENSE](../LICENSE) for details

### ⚠️ Prohibited Use & Anti-Abuse Policy

**This tool is strictly prohibited for:**
- Commercial use or profit-making activities
- Batch operations or automated abuse of any scale
- Market disruption or malicious competition
- Violations of Google's Terms of Service
- Violations of Microsoft's Terms of Service

**Consequences of Abuse**: Violations may result in permanent account suspension, legal liability, and all consequences are the sole responsibility of the user.

**Legitimate Use Only**: This project is intended solely for personal learning, technical research, and non-commercial educational purposes.

📖 **Full Disclaimer**: [DISCLAIMER_EN.md](DISCLAIMER_EN.md)

---

## ✨ Features

- ✅ Full OpenAI API compatibility - Seamless integration with existing tools
- ✅ Multi-account load balancing - Round-robin with automatic failover
- ✅ Automated account management - Auto registration and login with DuckMail and Microsoft email integration, supports headless browser mode
- ✅ Streaming output - Real-time responses
- ✅ Multimodal input - 100+ file types (images, PDF, Office docs, audio, video, code, etc.)
- ✅ Image generation & image-to-image - Configurable models, Base64 or URL output
- ✅ Video generation - Dedicated model with HTML/URL/Markdown output formats
- ✅ Smart file handling - Auto file type detection, supports URL and Base64
- ✅ Logging & monitoring - Real-time status and statistics
- ✅ Proxy support - Configure in the admin settings
- ✅ Built-in admin panel - Online configuration and account management
- ✅ Optional PostgreSQL backend — persists accounts/settings/stats [thanks PR](https://github.com/Dreamy-rain/gemini-business2api/pull/4)

## 🤖 Model Capabilities

| Model ID                 | Vision | Native Web | File Multimodal | Image Gen | Video Gen |
| ------------------------ | ------ | ---------- | --------------- | --------- | --------- |
| `gemini-auto`            | ✅      | ✅          | ✅               | Optional  | -         |
| `gemini-2.5-flash`       | ✅      | ✅          | ✅               | Optional  | -         |
| `gemini-2.5-pro`         | ✅      | ✅          | ✅               | Optional  | -         |
| `gemini-3-flash-preview` | ✅      | ✅          | ✅               | Optional  | -         |
| `gemini-3-pro-preview`   | ✅      | ✅          | ✅               | Optional  | -         |
| `gemini-3.1-pro-preview` | ✅      | ✅          | ✅               | Optional  | -         |
| `gemini-imagen`          | ✅      | ✅          | ✅               | ✅         | -         |
| `gemini-veo`             | ✅      | ✅          | ✅               | -         | ✅         |

**Virtual Models**:
- `gemini-imagen`: Dedicated image generation model with forced image generation capability
- `gemini-veo`: Dedicated video generation model with forced video generation capability

## 🚀 Quick Start

### Method 1: Zeabur Deployment (Recommended, Auto-Update Supported)

Thanks to [PR #37](https://github.com/Dreamy-rain/gemini-business2api/pull/37) for Linux and Docker deployment optimizations.

#### Step 1: Fork the Repository

Click the **Fork** button in the top-right corner to copy this project to your GitHub account.

#### Step 2: Deploy to Zeabur

1. Log in to [Zeabur](https://zeabur.com) and create a new project
2. Click **Create Project** → **Shared Cluster / Silicon Valley, United States** → **Create Project** → **Deploy New Service** → **Connect GitHub** (authorize if prompted) → **Select your forked repository** → **Deploy**
3. Click on the service card → **Variables** tab, and add the following environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `ADMIN_KEY` | ✅ | Admin panel login key (set your own) |
| `DATABASE_URL` | Recommended | PostgreSQL connection string (see "Database Persistence" below) |

> 💡 **Strongly recommended to configure DATABASE_URL**, otherwise data will be lost when Zeabur restarts. Get a free database at [neon.tech](https://neon.tech)

4. Click **Redeploy** to apply the environment variables
5. Wait for the build to complete (~1-2 minutes)

#### How to Update?

When this project is updated:

1. Go to your forked GitHub repository
2. Click **Sync fork** → **Update branch**
3. Zeabur will automatically detect changes and redeploy

---

### Method 2: Setup Script (Local Deployment)

**Linux/macOS:**
```bash
git clone https://github.com/Dreamy-rain/gemini-business2api.git
cd gemini-business2api
bash setup.sh

cp .env.example .env
# Edit .env to set ADMIN_KEY

source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate.bat  # Windows

python main.py

# Run with pm2 in background
# Make sure you're in the project directory
pm2 start main.py --name gemini-api --interpreter ./.venv/bin/python3
```

**Windows:**
```cmd
git clone https://github.com/Dreamy-rain/gemini-business2api.git
cd gemini-business2api
setup.bat

copy .env.example .env
# Edit .env to set ADMIN_KEY

source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate.bat  # Windows

python main.py

# Run with pm2 in background
# Make sure you're in the project directory
pm2 start main.py --name gemini-api --interpreter ./.venv/bin/python3
```

**Script Features:**
- ✅ Automatically syncs latest code
- ✅ Updates frontend to latest versions
- ✅ Creates/updates Python virtual environment
- ✅ Installs/updates dependencies
- ✅ Automatically creates `.env` config file (if not exists)

**First Installation:** After completion, edit `.env` to set `ADMIN_KEY`, then run `python main.py`

**Update Project:** Simply run the same command, the script will automatically update all components (code, dependencies, frontend)

### Method 3: Manual Deployment

```bash
git clone https://github.com/Dreamy-rain/gemini-business2api.git
cd gemini-business2api

# Build frontend
cd frontend
npm install
npm run build
cd ..

# Create virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate.bat  # Windows

# Install Python dependencies
pip install -r requirements.txt
cp .env.example .env
# win copy .env.example .env
# Edit .env to set ADMIN_KEY
python main.py

# Run with pm2 in background
# Make sure you're in the project directory
pm2 start main.py --name gemini-api --interpreter ./.venv/bin/python3
```

### Method 4: Docker Compose (Recommended for Production)

**Supports ARM64 and AMD64 architectures**

```bash
# 1. Clone the repository
git clone https://github.com/Dreamy-rain/gemini-business2api.git
cd gemini-business2api

# 2. Configure environment variables
cp .env.example .env
# Edit .env to set ADMIN_KEY

# 3. Start the service
docker-compose up -d

# 4. View logs
docker-compose logs -f

# 5. Update to the latest version
docker-compose pull && docker-compose up -d
```

Thanks to [PR #9](https://github.com/Dreamy-rain/gemini-business2api/pull/9) for optimizing the Dockerfile build


### Database Persistence (Recommended)

Configure a PostgreSQL database to persist accounts, settings, and statistics across restarts.

- Set `DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require`
  - Local deployment: Add to `.env` file
  - Zeabur deployment: Add in the Variables tab
- Keep the connection string secret (contains credentials)

```
# Get DATABASE_URL from Neon (Free)
1. Go to https://neon.tech and sign in
2. Create project -> Select a region
3. Open the project page, copy the Connection string
4. Example:
   postgresql://user:password@ep-xxx.neon.tech/dbname?sslmode=require
```

#### Database Migration (First-time Setup or Upgrade)

If you have old local files (accounts.json/settings.yaml/stats.json), run the migration script:

```bash
# Run migration script directly
python scripts/migrate_to_database.py

# Zeabur environment: Click service → Command → Enter the following
python scripts/migrate_to_database.py
```

**Migration script auto-detects**:
- ✅ `DATABASE_URL` configured → Migrate to PostgreSQL (remote database)
- ✅ `DATABASE_URL` not configured → Migrate to SQLite (local data.db)

**Migration content**:
- ✅ Migrate from kv_store (old table structure) to new tables (PostgreSQL only)
- ✅ Migrate from local files (accounts.json/settings.yaml/stats.json) to database
- ✅ Auto-rename local files after migration (prevent duplicates)
- ✅ Preserve kv_store as backup (PostgreSQL only)

> **Note**: SQLite and PostgreSQL table structures are fully compatible, future migration from SQLite → PostgreSQL is possible

### Access

- Admin Panel: `http://localhost:7860/` (Login with `ADMIN_KEY`)
- OpenAI-compatible API: `http://localhost:7860/v1/chat/completions`

### Configuration Tips

- Account config prioritizes `ACCOUNTS_CONFIG` env var, or can be entered in admin panel and saved to `data/accounts.json`.
- For authentication, configure `API_KEY` in the admin settings to protect `/v1/chat/completions`.

### Documentation

- Supported file types: [SUPPORTED_FILE_TYPES.md](SUPPORTED_FILE_TYPES.md)

## 📸 Screenshots

### Admin System

<table>
  <tr>
    <td><img src="img/1.png" alt="Admin System 1" /></td>
    <td><img src="img/2.png" alt="Admin System 2" /></td>
  </tr>
  <tr>
    <td><img src="img/3.png" alt="Admin System 3" /></td>
    <td><img src="img/4.png" alt="Admin System 4" /></td>
  </tr>
  <tr>
    <td><img src="img/5.png" alt="Admin System 5" /></td>
    <td><img src="img/6.png" alt="Admin System 6" /></td>
  </tr>
</table>

### Image Effects

<table>
  <tr>
    <td><img src="img/img_1.png" alt="Image Effects 1" /></td>
    <td><img src="img/img_2.png" alt="Image Effects 2" /></td>
  </tr>
  <tr>
    <td><img src="img/img_3.png" alt="Image Effects 3" /></td>
    <td><img src="img/img_4.png" alt="Image Effects 4" /></td>
  </tr>
</table>

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Dreamy-rain/gemini-business2api&type=date&legend=top-left)](https://www.star-history.com/#Dreamy-rain/gemini-business2api&type=date&legend=top-left)

**If this project helps you, please give it a ⭐ Star!**



