<p align="center">
  <img src="../docs/logo.svg" width="120" alt="Gemini Business2API logo" />
</p>
<h1 align="center">Gemini Business2API</h1>
<p align="center">Endow silicon-based beings with souls</p>
<p align="center">When the bright moon was there · It once shone on the colorful clouds returning</p>
<p align="center">
  <a href="../README.md">简体中文</a> | <strong>English</strong>
</p>
<p align="center"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" /> <img src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white" /> <img src="https://img.shields.io/badge/FastAPI-0.110-009688?logo=fastapi&logoColor=white" /> <img src="https://img.shields.io/badge/Vue-3-4FC08D?logo=vue.js&logoColor=white" /> <img src="https://img.shields.io/badge/Vite-7-646CFF?logo=vite&logoColor=white" /> <img src="https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white" /></p>

<p align="center">
  <a href="https://huggingface.co/spaces/xiaoyukkkk/gemini-business2api?duplicate=true">
    <img src="https://huggingface.co/datasets/huggingface/badges/resolve/main/deploy-to-spaces-md.svg" />
  </a>
</p>

<p align="center">Convert Gemini Business to OpenAI-compatible API with multi-account load balancing, image generation, multimodal capabilities, and built-in admin panel.</p>

---

## 📜 License & Disclaimer

**License**: MIT License - See [LICENSE](../LICENSE) for details

**Usage Disclaimer**:
- ⚠️ **This project is for educational and research purposes only. Commercial use is prohibited.**
- 📝 **Please retain this disclaimer, original author information, and open source attribution when using.**
- 🔗 **Project Repository**: [github.com/Dreamy-rain/gemini-business2api](https://github.com/Dreamy-rain/gemini-business2api)

---

## ✨ Features

- ✅ Full OpenAI API compatibility - Seamless integration with existing tools
- ✅ Multi-account load balancing - Round-robin with automatic failover
- ✅ Streaming output - Real-time responses
- ✅ Multimodal input - 100+ file types (images, PDF, Office docs, audio, video, code, etc.)
- ✅ Image generation & image-to-image - Configurable models, Base64 or URL output
- ✅ Smart file handling - Auto file type detection, supports URL and Base64
- ✅ Logging & monitoring - Real-time status and statistics
- ✅ Proxy support - Via PROXY configuration
- ✅ Built-in admin panel - Online configuration and account management
- ✅ Optional PostgreSQL backend — persists accounts/settings/stats [thanks PR](https://github.com/Dreamy-rain/gemini-business2api/pull/4)

## 🤖 Model Capabilities

| Model ID                 | Vision | Native Web | File Multimodal | Image Gen |
| ------------------------ | ------ | ---------- | --------------- | --------- |
| `gemini-auto`            | ✅      | ✅          | ✅               | Optional  |
| `gemini-2.5-flash`       | ✅      | ✅          | ✅               | Optional  |
| `gemini-2.5-pro`         | ✅      | ✅          | ✅               | Optional  |
| `gemini-3-flash-preview` | ✅      | ✅          | ✅               | Optional  |
| `gemini-3-pro-preview`   | ✅      | ✅          | ✅               | Optional  |

## 🚀 Quick Start

### Method 1: Local Run (Recommended)

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env to set ADMIN_KEY
python main.py
```

### Method 2: Docker

```bash
docker build -t gemini-business2api .
docker run -d -p 7860:7860 \
  -e ADMIN_KEY=your_admin_key \
  gemini-business2api
```

### Optional: Database Persistence (Local / HF Spaces)

- Recommended on HF Spaces (free tier) to avoid data loss after restart
- Uncomment `asyncpg` in `requirements.txt` and install dependencies
- Set `DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require`
  - Local: put it in `.env`
  - HF Spaces: Settings -> Variables/Secrets
- Accounts/settings/stats are stored in the database
- Keep the connection string secret (it includes credentials)

```
#  Get DATABASE_URL from Neon (recommended)
1. Open https://neon.tech and sign in
2. Create project -> choose a region
3. Open the project page, copy the Connection string
4. Example:
   postgresql://user:password@ep-xxx.neon.tech/dbname?sslmode=require
```

### Access

- Admin Panel: `http://localhost:7860/` (Login with `ADMIN_KEY`)
- OpenAI-compatible API: `http://localhost:7860/v1/chat/completions`

### Configuration Tips

- Account config prioritizes `ACCOUNTS_CONFIG` env var, or can be entered in admin panel and saved to `data/accounts.json`.
- For authentication, set `API_KEY` to protect `/v1/chat/completions`.

### Documentation

- Supported file types: `SUPPORTED_FILE_TYPES.md`

## 📸 Screenshots

### Admin System

<table>
  <tr>
    <td><img src="1.png" alt="Admin System 1" /></td>
    <td><img src="2.png" alt="Admin System 2" /></td>
  </tr>
  <tr>
    <td><img src="3.png" alt="Admin System 3" /></td>
    <td><img src="4.png" alt="Admin System 4" /></td>
  </tr>
  <tr>
    <td><img src="5.png" alt="Admin System 5" /></td>
    <td><img src="6.png" alt="Admin System 6" /></td>
  </tr>
</table>

### Image Generation

<table>
  <tr>
    <td><img src="img_1.png" alt="Image Generation 1" /></td>
    <td><img src="img_2.png" alt="Image Generation 2" /></td>
  </tr>
  <tr>
    <td><img src="img_3.png" alt="Image Generation 3" /></td>
    <td><img src="img_4.png" alt="Image Generation 4" /></td>
  </tr>
</table>

## 🙏 Acknowledgments

* Original project: [F's Linux.do Discussion](https://linux.do/t/topic/1225645)
* Original project: [heixxin/gemini](https://huggingface.co/spaces/heixxin/gemini/tree/main) | [Linux.do Discussion](https://linux.do/t/topic/1226413)
* Image generation reference: [Gemini-Link-System](https://github.com/qxd-ljy/Gemini-Link-System) | [Linux.do Discussion](https://linux.do/t/topic/1234363)

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Dreamy-rain/gemini-business2api&type=date&legend=top-left)](https://www.star-history.com/#Dreamy-rain/gemini-business2api&type=date&legend=top-left)

**If this project helps you, please give it a ⭐ Star!**



