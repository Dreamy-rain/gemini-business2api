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

<p align="center">将 Gemini Business 转换为 OpenAI 兼容接口，支持多账号负载均衡、图像生成、多模态能力与内置管理面板。</p>

---

## 📜 开源协议与声明

**开源协议**: MIT License - 查看 [LICENSE](LICENSE) 文件了解详情

**使用声明**:
- ⚠️ **本项目仅限学习与研究用途，禁止用于商业用途**
- 📝 **使用时请保留本声明、原作者信息与开源来源**
- 🔗 **项目地址**: [github.com/Dreamy-rain/gemini-business2api](https://github.com/Dreamy-rain/gemini-business2api)

---

## ✨ 功能特性

- ✅ OpenAI API 完全兼容 - 无缝对接现有工具
- ✅ 多账号负载均衡 - 轮询与故障自动切换
- ✅ 流式输出 - 实时响应
- ✅ 多模态输入 - 100+ 文件类型（图片、PDF、Office 文档、音频、视频、代码等）
- ✅ 图片生成 & 图生图 - 模型可配置，Base64 或 URL 返回
- ✅ 智能文件处理 - 自动识别文件类型，支持 URL 与 Base64
- ✅ 日志与监控 - 实时状态与统计信息
- ✅ 代理支持 - 通过 PROXY 配置
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

### 方式一：使用部署脚本（推荐）

**Linux/macOS:**
```bash
git clone https://github.com/Dreamy-rain/gemini-business2api.git
cd gemini-business2api
bash deploy.sh
```

**Windows:**
```cmd
git clone https://github.com/Dreamy-rain/gemini-business2api.git
cd gemini-business2api
deploy.bat
```

部署脚本会自动完成：
- 构建前端
- 创建 Python 虚拟环境
- 安装依赖
- 创建配置文件

完成后编辑 `.env` 设置 `ADMIN_KEY`，然后运行 `python main.py`

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
# 编辑 .env 设置 ADMIN_KEY
python main.py
```

### 方式三：Docker

```bash
docker build -t gemini-business2api .
docker run -d -p 7860:7860 \
  -e ADMIN_KEY=your_admin_key \
  gemini-business2api
```

### 更新

**Linux/macOS:**
```bash
bash update.sh
```

**Windows:**
```cmd
update.bat
```

**HuggingFace:**
```
暂时只能重新部署更新，记得保存数据，建议用 PostgreSQL
```

更新脚本会自动备份配置、拉取最新代码、更新依赖并构建前端。

### 数据库持久化（可选）

- HF Spaces 环境建议开启，否则重启会丢数据
- 取消 `requirements.txt` 中 `asyncpg` 的注释并安装依赖
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
- 如需鉴权，可设置 `API_KEY` 保护 `/v1/chat/completions`。

### 更多文档

- 支持的文件类型：[docs/SUPPORTED_FILE_TYPES.md](docs/SUPPORTED_FILE_TYPES.md)

## 📸 功能展示

### 管理系统

<table>
  <tr>
    <td><img src="docs/1.png" alt="管理系统 1" /></td>
    <td><img src="docs/2.png" alt="管理系统 2" /></td>
  </tr>
  <tr>
    <td><img src="docs/3.png" alt="管理系统 3" /></td>
    <td><img src="docs/4.png" alt="管理系统 4" /></td>
  </tr>
  <tr>
    <td><img src="docs/5.png" alt="管理系统 5" /></td>
    <td><img src="docs/6.png" alt="管理系统 6" /></td>
  </tr>
</table>

### 图片效果

<table>
  <tr>
    <td><img src="docs/img_1.png" alt="图片效果 1" /></td>
    <td><img src="docs/img_2.png" alt="图片效果 2" /></td>
  </tr>
  <tr>
    <td><img src="docs/img_3.png" alt="图片效果 3" /></td>
    <td><img src="docs/img_4.png" alt="图片效果 4" /></td>
  </tr>
</table>

## 🙏 致谢

* 源项目：[F佬 Linux.do 讨论](https://linux.do/t/topic/1225645)
* 源项目：[heixxin/gemini](https://huggingface.co/spaces/heixxin/gemini/tree/main) | [Linux.do 讨论](https://linux.do/t/topic/1226413)
* 绘图参考：[Gemini-Link-System](https://github.com/qxd-ljy/Gemini-Link-System) | [Linux.do 讨论](https://linux.do/t/topic/1234363)

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Dreamy-rain/gemini-business2api&type=date&legend=top-left)](https://www.star-history.com/#Dreamy-rain/gemini-business2api&type=date&legend=top-left)

**如果这个项目对你有帮助，请给个 ⭐ Star!**



