<p align="center">
  <img src="docs/logo.svg" width="120" alt="Gemini Business2API logo" />
</p>
<h1 align="center">Gemini Business2API</h1>
<p align="center">赋予硅基生物以灵魂</p>
<p align="center">当时明月在 · 曾照彩云归</p>
<p align="center">
  <strong>简体中文</strong> | <a href="docs/README_EN.md">English</a>
</p>
<p align="center"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" /> <img src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white" /> <img src="https://img.shields.io/badge/FastAPI-0.110-009688?logo=fastapi&logoColor=white" /> <img src="https://img.shields.io/badge/Vue-3-4FC08D?logo=vue.js&logoColor=white" /> <img src="https://img.shields.io/badge/Vite-7-646CFF?logo=vite&logoColor=white" /> <img src="https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white" /></p>

<p align="center">将 Gemini Business 转换为 OpenAI 兼容接口，支持多账号负载均衡、图像生成、视频生成、多模态能力与内置管理面板。</p>

---

## 📜 开源协议与声明

**开源协议**: MIT License - 查看 [LICENSE](LICENSE) 文件了解详情

### ⚠️ 严禁滥用：禁止将本工具用于商业用途或任何形式的滥用（无论规模大小）

**本工具严禁用于以下行为：**
- 商业用途或盈利性使用
- 任何形式的批量操作或自动化滥用（无论规模大小）
- 破坏市场秩序或恶意竞争
- 违反 Google 服务条款的任何行为
- 违反 Microsoft 服务条款的任何行为

**违规后果**：滥用行为可能导致账号永久封禁、法律追责，一切后果由使用者自行承担。

**合法用途**：本项目仅限个人学习、技术研究与非商业性技术交流。

📖 **完整声明与免责条款**：[DISCLAIMER.md](docs/DISCLAIMER.md)

---

## ✨ 功能特性

- ✅ OpenAI API 完全兼容 - 无缝对接现有工具
- ✅ 多账号负载均衡 - 轮询与故障自动切换
- ✅ 自动化账号管理 - 支持自动注册与登录，集成多种临时邮箱，支持无头浏览器模式
- ✅ 流式输出 - 实时响应
- ✅ 多模态输入 - 100+ 文件类型（图片、PDF、Office 文档、音频、视频、代码等）
- ✅ 图片生成 & 图生图 - 模型可配置，Base64 或 URL 返回
- ✅ 视频生成 - 专用模型，支持 HTML/URL/Markdown 输出格式
- ✅ 智能文件处理 - 自动识别文件类型，支持 URL 与 Base64
- ✅ 日志与监控 - 实时状态与统计信息
- ✅ 代理支持 - 通过设置面板配置
- ✅ 内置管理面板 - 在线配置与账号管理
- ✅ PostgreSQL / SQLite 存储 - 账户/设置/统计持久化

## 🤖 模型功能

| 模型ID                   | 识图 | 原生联网 | 文件多模态 | 图片生成 | 视频生成 |
| ------------------------ | ---- | -------- | ---------- | -------- | -------- |
| `gemini-auto`            | ✅    | ✅        | ✅          | 可选     | -        |
| `gemini-2.5-flash`       | ✅    | ✅        | ✅          | 可选     | -        |
| `gemini-2.5-pro`         | ✅    | ✅        | ✅          | 可选     | -        |
| `gemini-3-flash-preview` | ✅    | ✅        | ✅          | 可选     | -        |
| `gemini-3-pro-preview`   | ✅    | ✅        | ✅          | 可选     | -        |
| `gemini-3.1-pro-preview` | ✅    | ✅        | ✅          | 可选     | -        |
| `gemini-imagen`          | ✅    | ✅        | ✅          | ✅        | -        |
| `gemini-veo`             | ✅    | ✅        | ✅          | -        | ✅        |

> `gemini-imagen`：专用图片生成模型 · `gemini-veo`：专用视频生成模型

---

## 🚀 快速开始

### 方式一：Docker Compose（推荐）

**支持 ARM64 和 AMD64 架构**

```bash
git clone https://github.com/Dreamy-rain/gemini-business2api.git
cd gemini-business2api
cp .env.example .env
# 编辑 .env 设置 ADMIN_KEY

docker compose up -d

# 查看日志
docker compose logs -f

# 更新到最新版本
docker compose pull && docker compose up -d
```

---

### 方式二：安装脚本

> **前置要求**：Git、Node.js & npm（构建前端用）。脚本会自动安装 Python 3.11 和 uv。

**Linux / macOS / WSL：**
```bash
git clone https://github.com/Dreamy-rain/gemini-business2api.git
cd gemini-business2api
bash setup.sh
# 编辑 .env 设置 ADMIN_KEY
source .venv/bin/activate
python main.py
# pm2 后台运行
pm2 start main.py --name gemini-api --interpreter ./.venv/bin/python3
```

**Windows：**
```cmd
git clone https://github.com/Dreamy-rain/gemini-business2api.git
cd gemini-business2api
setup.bat
# 编辑 .env 设置 ADMIN_KEY
.venv\Scripts\activate.bat
python main.py
# pm2 后台运行
pm2 start main.py --name gemini-api --interpreter ./.venv/Scripts/python.exe
```

安装脚本会自动完成：uv 安装、Python 3.11 下载、依赖安装、前端构建、`.env` 创建。
更新项目时重新运行同一脚本即可。

---

### 方式三：手动部署

```bash
git clone https://github.com/Dreamy-rain/gemini-business2api.git
cd gemini-business2api

curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.11

cd frontend && npm install && npm run build && cd ..

uv venv --python 3.11 .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate.bat
uv pip install -r requirements.txt

cp .env.example .env
# 编辑 .env 设置 ADMIN_KEY
python main.py
```

---

### 访问方式

- **管理面板**：`http://localhost:7860/`（使用 `ADMIN_KEY` 登录）
- **API 接口**：`http://localhost:7860/v1/chat/completions`

---

## 🗄️ 数据库持久化

默认不配置 `DATABASE_URL`，直接使用 SQLite（本地 `data.db`，推荐）。
仅在必要场景（如多实例共享同一份数据、云平台无法挂载持久化目录）再使用在线数据库。

**配置方式：**
- 本地部署 → 写入 `.env`
- 云平台 → 在平台环境变量中设置

```
DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require
```

### 本地刷新服务建议（refresh-worker）

- 推荐拓扑：`main` 部署在云端，`refresh-worker` 在本地机器执行浏览器刷新。
- 推荐本地优先使用 SQLite（`data.db`）做刷新侧缓存，网络不稳定时更稳。
- 如需由本地刷新器直接连远端面板，可使用远端接口 + `ADMIN_KEY`：

```env
REMOTE_PROJECT_BASE_URL=https://your-beta-domain.example
REMOTE_PROJECT_PASSWORD=your_admin_key
```

**如需在线 PostgreSQL（可选）：**

| 服务 | 免费额度 | 获取方式 |
|------|---------|---------|
| [Neon](https://neon.tech) | 512MB 存储 / 100 CPUH 月 | 注册 → Create Project → 复制 Connection string |
| [Aiven](https://aiven.io) | 额度更充裕 | 注册 → 创建 PostgreSQL 服务 → 复制连接串 |

> `postgres://` 和 `postgresql://` 两种格式均可直接使用，无需手动转换。

<details>
<summary>⚠️ 常见问题：定期保存失败 / ConnectionDoesNotExistError</summary>

如果日志出现类似以下错误：

```
ERROR [COOLDOWN] 冷却期保存失败: connection was closed in the middle of operation
asyncpg.exceptions.ConnectionDoesNotExistError: connection was closed in the middle of operation
```

这是因为部分免费 PostgreSQL 服务（如 Aiven 免费版）会主动关闭长时间空闲的连接。**不影响正常使用**，下次操作会自动重新连接。如频繁出现，建议换用 [Neon](https://neon.tech) 或升级数据库套餐。

</details>

<details>
<summary>📦 数据库迁移（从旧版升级）</summary>

如果有旧的本地文件（`accounts.json` / `settings.yaml` / `stats.json`），运行迁移脚本：

```bash
python scripts/migrate_to_database.py
```

迁移脚本会自动检测环境（PostgreSQL / SQLite），迁移完成后自动重命名旧文件。


</details>

---

## 📡 API 接口

完全兼容 OpenAI API 格式，可直接对接 ChatGPT-Next-Web、LobeChat、OpenCat 等客户端。

| 接口 | 方法 | 说明 |
|------|------|------|
| `/v1/chat/completions` | POST | 对话补全（支持流式） |
| `/v1/models` | GET | 获取可用模型列表 |
| `/v1/images/generations` | POST | 图片生成（文生图） |
| `/v1/images/edits` | POST | 图片编辑（图生图） |
| `/health` | GET | 健康检查 |

**调用示例：**

```bash
curl http://localhost:7860/v1/chat/completions \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-2.5-flash",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": true
  }'
```

> `API_KEY` 在管理面板 → 系统设置中配置，留空则公开访问，支持多个 Key 逗号分隔。

---

## 📧 邮箱提供商配置

项目支持 6 种临时邮箱，用于自动注册账号。在 **管理面板 → 系统设置 → 临时邮箱提供商** 中切换。

### Moemail（默认推荐）

开源临时邮箱服务，开箱即用。

- **项目地址**：[github.com/beilunyang/moemail](https://github.com/beilunyang/moemail)
- **官网**：[moemail.app](https://moemail.app)
- **配置项**：API 地址 + API Key + 域名（可选）

### DuckMail

临时邮箱 API 服务，推荐配置自定义域名。

- **域名管理**：[domain.duckmail.sbs](https://domain.duckmail.sbs/)
- **配置项**：API 地址 + API Key + 注册域名

### GPTMail

临时邮箱 API 服务，无需密码即可使用。

- **默认地址**：`https://mail.chatgpt.org.uk`
- **默认 API Key**：`gpt-test`
- **配置项**：API 地址 + API Key + 域名（可选）

### Freemail

需要自行搭建的临时邮箱服务，适合有服务器的用户。

- **项目地址**：[github.com/idinging/freemail](https://github.com/idinging/freemail)
- **配置项**：自部署服务地址 + JWT Token + 域名（可选）

### Cloudflare Mail（CFMail）

基于 Cloudflare 的临时邮箱服务，适合希望自建或轻量部署的用户。

- **项目地址**：[github.com/dreamhunter2333/cloudflare_temp_email](https://github.com/dreamhunter2333/cloudflare_temp_email)
- **管理面板配置路径**：系统设置 → 临时邮箱提供商选择 `cfmail`
- **配置项**：
  - Cloudflare Mail API 地址（`cfmail_base_url`）
  - 访问密码（`cfmail_api_key`，实例未启用可留空）
  - 邮箱域名（`cfmail_domain`，可选，不带 `@`）
- **导入格式（可选）**：`cfmail----you@example.com----jwtToken`
  - 第三个字段是该邮箱的 JWT Token（用于拉取邮件验证码）

### Sample Mail

基于 Cloudflare Workers + D1 的轻量自建临时邮箱，无需 API Key，域名由 Worker 环境变量决定。

- **项目地址**：[github.com/bestK/sample-mail](https://github.com/bestK/sample-mail)
- **管理面板配置路径**：系统设置 → 临时邮箱提供商选择 `samplemail`
- **配置项**：
  - Sample Mail Worker 地址（`samplemail_base_url`，必填）
  - SSL 校验（`samplemail_verify_ssl`，默认开启）
- **说明**：不支持指定域名或 API Key，邮箱域名由 Worker 的 `EMAIL_DOMAIN` 环境变量决定。

> **提示**：所有邮箱配置均在管理面板中完成，无需手动编辑配置文件。Microsoft 邮箱登录也在管理面板中操作。

---

## 🌐 推荐部署平台

除本地 Docker Compose 外，以下平台均支持 Docker 镜像部署：

| 平台 | 免费额度 | 特点 |
|------|---------|------|
| [Render](https://render.com) | ✅ 有 | 支持 Docker、自动 SSL、免费 PostgreSQL |
| [Railway](https://railway.app) | $5/月额度 | 一键 Docker 部署、自带数据库 |
| [Fly.io](https://fly.io) | ✅ 有 | 全球边缘部署、支持持久化卷 |
| [Claw Cloud](https://claw.cloud) | ✅ 有 | 容器云平台，简单易用 |
| 自建 VPS（推荐） | — | 完全可控，配合 Docker Compose |

> Docker 镜像：`cooooookk/gemini-business2api:latest`
>
> 部署时先设置 `ADMIN_KEY`；`DATABASE_URL` 仅在必要时再配置（默认本地 `data.db` 更推荐）。

### Zeabur 部署教程

1. Fork 本仓库到你的 GitHub
2. 登录 [Zeabur](https://zeabur.com) → **创建项目** → **共享集群** → **部署新服务** → **连接 GitHub** → 选择 Fork 的仓库
3. 添加环境变量：

   | 变量名 | 必填 | 说明 |
   |--------|------|------|
   | `ADMIN_KEY` | ✅ | 管理面板登录密钥 |
   | `DATABASE_URL` | 可选 | PostgreSQL 连接串（仅在需要在线数据库时配置） |

4. **持久化挂载目录**（重要）：

   在服务设置中添加持久化存储：

   | 硬盘 ID | 挂载目录 |
   |---------|---------|
   | `data` | `/app/data` |

5. 点击 **重新部署** 使配置生效

**更新方式**：GitHub 仓库 → **Sync fork** → **Update branch**，Zeabur 会自动重新部署。

---

## 🔄 独立刷新服务

如果需要将账号刷新服务单独部署（与主 API 分离），可使用 [`refresh-worker` 分支](https://github.com/Dreamy-rain/gemini-business2api/tree/refresh-worker)：

```bash
git clone -b refresh-worker https://github.com/Dreamy-rain/gemini-business2api.git gemini-refresh-worker
cd gemini-refresh-worker
cp .env.example .env
# 编辑 .env（默认本地 data.db；仅在必要时设置 DATABASE_URL）
docker compose up -d
```

该服务从数据库读取账号，独立执行定时刷新，支持 cron 调度、分批执行、冷却防重复。适合需要刷新服务与 API 服务分离部署的场景。

---

## 🌿 分支使用指南

为避免部署混乱，建议按场景选择分支：

- `main`：稳定主线（推荐生产部署 API 与前端面板）
- `beta`：新功能预发布线（会先于 main 更新）
- `refresh-worker`：独立刷新服务分支（适合本地运行刷新、远端部署 API）
- `clash-proxy`：Clash 代理场景分支（用于代理网络环境下的注册/刷新）

推荐组合：

- 云端部署 `main`/`beta` 提供 API 与管理面板
- 本地部署 `refresh-worker` 负责账号注册与刷新
- 需要 Clash 代理网络策略时使用 `clash-proxy`

### Clash 代理场景示例

```bash
git clone -b clash-proxy https://github.com/Dreamy-rain/gemini-business2api.git gemini-business2api-clash
cd gemini-business2api-clash
cp .env.example .env
# 编辑 .env 与面板代理配置后启动
docker compose up -d
```

---

## 🌐 Socks5 免费代理池

自动注册/刷新账号时可配置代理以提高成功率。推荐使用免费 Socks5 代理池：

- **项目地址**：[github.com/Dreamy-rain/socks5-proxy](https://github.com/Dreamy-rain/socks5-proxy)
- **说明**：免费代理不太稳定，但能一定程度提高注册成功率
- **使用方式**：在管理面板 → 系统设置 → 代理设置中配置

---

## 📸 功能展示

### 管理系统

<table>
  <tr>
    <td><img src="docs/img/1.png" alt="管理系统 1" /></td>
    <td><img src="docs/img/2.png" alt="管理系统 2" /></td>
  </tr>
  <tr>
    <td><img src="docs/img/3.png" alt="管理系统 3" /></td>
    <td><img src="docs/img/4.png" alt="管理系统 4" /></td>
  </tr>
  <tr>
    <td><img src="docs/img/5.png" alt="管理系统 5" /></td>
    <td><img src="docs/img/6.png" alt="管理系统 6" /></td>
  </tr>
</table>

### 图片效果

<table>
  <tr>
    <td><img src="docs/img/img_1.png" alt="图片效果 1" /></td>
    <td><img src="docs/img/img_2.png" alt="图片效果 2" /></td>
  </tr>
  <tr>
    <td><img src="docs/img/img_3.png" alt="图片效果 3" /></td>
    <td><img src="docs/img/img_4.png" alt="图片效果 4" /></td>
  </tr>
</table>

### 更多文档

- 支持的文件类型：[SUPPORTED_FILE_TYPES.md](docs/SUPPORTED_FILE_TYPES.md)

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Dreamy-rain/gemini-business2api&type=date&legend=top-left)](https://www.star-history.com/#Dreamy-rain/gemini-business2api&type=date&legend=top-left)

**如果这个项目对你有帮助，请给个 ⭐ Star!**
