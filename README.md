<p align="center">
  <img src="docs/logo.svg" width="120" alt="Gemini Business2API logo" />
</p>
<h1 align="center">Gemini Business2API</h1>
<p align="center">赋予硅基生物以灵魂</p>
<p align="center">当时明月在 · 曾照彩云归</p>
<p align="center">
  <strong>简体中文</strong> | <a href="docs/README_EN.md">English</a>
</p>
<p align="center"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" /> <img src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white" /> <img src="https://img.shields.io/badge/FastAPI-0.110-009688?logo=fastapi&logoColor=white" /> <img src="https://img.shields.io/badge/Vue-3-4FC08D?logo=vue.js&logoColor=white" /> <img src="https://img.shields.io/badge/Vite-7-646CFF?logo=vite&logoColor=white" /> <img src="https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white" /></p>

<p align="center">
  <a href="https://huggingface.co/spaces/xiaoyukkkk/gemini-business2api?duplicate=true">
    <img src="https://huggingface.co/datasets/huggingface/badges/resolve/main/deploy-to-spaces-md.svg" />
  </a>
</p>

<p align="center"><em>注意：HF Spaces 部署不支持自动注册/刷新功能（需 Chrome 浏览器），请手动添加账号</em></p>

<p align="center"><em>💡 提示：远程环境(Hugging Face/Linux)和本地环境可共用同一数据库，账户数据将自动保持同步</em></p>

<p align="center">将 Gemini Business 转换为 OpenAI 兼容接口，支持多账号负载均衡、图像生成、多模态能力与内置管理面板。</p>

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
- ✅ 自动化账号管理 - 支持自动注册与登录，集成 DuckMail 和 Microsoft 邮箱，支持无头浏览器模式
- ✅ 流式输出 - 实时响应
- ✅ 多模态输入 - 100+ 文件类型（图片、PDF、Office 文档、音频、视频、代码等）
- ✅ 图片生成 & 图生图 - 模型可配置，Base64 或 URL 返回
- ✅ 智能文件处理 - 自动识别文件类型，支持 URL 与 Base64
- ✅ 日志与监控 - 实时状态与统计信息
- ✅ 代理支持 - 通过设置面板配置
- ✅ 内置管理面板 - 在线配置与账号管理
- ✅ 可选 PostgreSQL 后端 - 支持账户/设置/统计持久化 [感谢PR](https://github.com/Dreamy-rain/gemini-business2api/pull/4)

## 🤖 模型功能

| 模型ID                   | 识图 | 原生联网 | 文件多模态 | 香蕉绘图 |
| ------------------------ | ---- | -------- | ---------- | -------- |
| `gemini-auto`            | ✅    | ✅        | ✅          | 可选     |
| `gemini-2.5-flash`       | ✅    | ✅        | ✅          | 可选     |
| `gemini-2.5-pro`         | ✅    | ✅        | ✅          | 可选     |
| `gemini-3-flash-preview` | ✅    | ✅        | ✅          | 可选     |
| `gemini-3-pro-preview`   | ✅    | ✅        | ✅          | 可选     |

## 🚀 快速开始

### 方式一：使用安装脚本（推荐）

**Linux/macOS:**
```bash
git clone https://github.com/Dreamy-rain/gemini-business2api.git
cd gemini-business2api
bash setup.sh

cp .env.example .env
# 编辑 .env 设置 ADMIN_KEY

source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate.bat  # Windows

python main.py

# pm2后台运行
# 确保你在项目目录下
pm2 start main.py --name gemini-api --interpreter ./.venv/bin/python3
```

**Windows:**
```cmd
git clone https://github.com/Dreamy-rain/gemini-business2api.git
cd gemini-business2api
setup.bat

copy .env.example .env
# 编辑 .env 设置 ADMIN_KEY

source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate.bat  # Windows

python main.py

# pm2后台运行
# 确保你在项目目录下
pm2 start main.py --name gemini-api --interpreter ./.venv/bin/python3
```

**脚本功能：**
- ✅ 自动同步最新代码
- ✅ 更新前端到最新版本
- ✅ 创建/更新 Python 虚拟环境
- ✅ 安装/更新依赖
- ✅ 自动创建 `.env` 配置文件（如不存在）

**首次安装：** 完成后编辑 `.env` 设置 `ADMIN_KEY`，然后运行 `python main.py`

**更新项目：** 直接运行相同命令即可，脚本会自动更新所有组件（代码、依赖、前端）

### 方式二：手动部署

```bash
git clone https://github.com/Dreamy-rain/gemini-business2api.git
cd gemini-business2api

# 构建前端
cd frontend
npm install
npm run build
cd ..

# 创建虚拟环境（推荐）
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate.bat  # Windows

# 安装 Python 依赖
pip install -r requirements.txt
cp .env.example .env
# win copy .env.example .env
# 编辑 .env 设置 ADMIN_KEY
python main.py

# pm2后台运行
# 确保你在项目目录下
pm2 start main.py --name gemini-api --interpreter ./.venv/bin/python3
```

### 方式三：Docker Compose（推荐用于生产环境）

**支持 ARM64 和 AMD64 架构**

```bash
# 1. 克隆仓库
git clone https://github.com/Dreamy-rain/gemini-business2api.git
cd gemini-business2api

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 设置 ADMIN_KEY

# 3. 启动服务
docker-compose up -d

# 4. 查看日志
docker-compose logs -f

# 5. 更新到最新版本
docker-compose pull && docker-compose up -d
```

感谢 [PR #9](https://github.com/Dreamy-rain/gemini-business2api/pull/9) 优化 Dockerfile 构建


### 数据库持久化（可选）（强烈推荐）

💡 提示：远程环境(Hugging Face/Linux)和本地环境可共用同一数据库，账户数据将自动保持同步

- HF Spaces 环境建议开启，否则重启会丢数据
- 设置 `DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require`
  - 本地：写入 `.env`
  - HF Spaces：Settings -> Variables/Secrets
- 启用后账户/设置/统计写入数据库（HF Spaces 重启不丢）
- 注意：连接串包含密码，请勿公开

```
#  Neon 获取 DATABASE_URL（推荐）
1. 打开 https://neon.tech 并登录
2. Create project -> 选择区域
3. 进入项目页，找到 Connection string 并复制
4. 形如：
   postgresql://user:password@ep-xxx.neon.tech/dbname?sslmode=require
```

### 访问方式

- 管理面板：`http://localhost:7860/`（使用 `ADMIN_KEY` 登录）
- OpenAI 兼容接口：`http://localhost:7860/v1/chat/completions`

### 配置提示

- 账号配置优先读取 `ACCOUNTS_CONFIG`，也可在管理面板中录入并保存至 `data/accounts.json`。
- 如需鉴权，可在管理面板设置中配置 `API_KEY` 保护 `/v1/chat/completions`。

### 更多文档

- 支持的文件类型：[docs/SUPPORTED_FILE_TYPES.md](docs/SUPPORTED_FILE_TYPES.md)

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

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Dreamy-rain/gemini-business2api&type=date&legend=top-left)](https://www.star-history.com/#Dreamy-rain/gemini-business2api&type=date&legend=top-left)

**如果这个项目对你有帮助，请给个 ⭐ Star!**



