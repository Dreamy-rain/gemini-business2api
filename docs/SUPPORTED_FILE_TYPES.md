# 支持的文件类型清单

本文档列出了 Gemini 可能支持的所有文件类型（可能支持）。

**支持的文件类型**（12 个分类，100+ 种格式）：

- 🖼️ **图片文件** - 11 种格式（PNG, JPEG, WebP, GIF, BMP, TIFF, SVG, ICO, HEIC, HEIF, AVIF）
- 📄 **文档文件** - 9 种格式（PDF, TXT, Markdown, HTML, XML, CSV, TSV, RTF, LaTeX）
- 📊 **Microsoft Office** - 6 种格式（.docx, .doc, .xlsx, .xls, .pptx, .ppt）
- 📝 **Google Workspace** - 3 种格式（Docs, Sheets, Slides）
- 💻 **代码文件** - 19 种语言（Python, JavaScript, TypeScript, Java, C/C++, Go, Rust, PHP, Ruby, Swift, Kotlin, Scala, Shell, PowerShell, SQL, R, MATLAB 等）
- 🎨 **Web 开发** - 8 种格式（CSS, SCSS, LESS, JSON, YAML, TOML, Vue, Svelte）
- 🎵 **音频文件** - 10 种格式（MP3, WAV, AAC, M4A, OGG, FLAC, AIFF, WMA, OPUS, AMR）
- 🎬 **视频文件** - 10 种格式（MP4, MOV, AVI, MPEG, WebM, FLV, WMV, MKV, 3GPP, M4V）
- 📦 **数据文件** - 6 种格式（JSON, JSONL, CSV, TSV, Parquet, Avro）
- 🗜️ **压缩文件** - 5 种格式（ZIP, RAR, 7Z, TAR, GZ）
- 🔧 **配置文件** - 5 种格式（YAML, TOML, INI, ENV, Properties）
- 📚 **电子书** - 2 种格式（EPUB, MOBI）

## 🖼️ 图片文件（Image Files）

| 格式 | 扩展名          | MIME 类型       | 支持状态   | 说明               |
| ---- | --------------- | --------------- | ---------- | ------------------ |
| PNG  | `.png`          | `image/png`     | ✅ 完全支持 | 无损压缩，支持透明 |
| JPEG | `.jpg`, `.jpeg` | `image/jpeg`    | ✅ 完全支持 | 有损压缩，照片常用 |
| WebP | `.webp`         | `image/webp`    | ✅ 完全支持 | 现代格式，体积小   |
| GIF  | `.gif`          | `image/gif`     | ✅ 完全支持 | 支持动画           |
| BMP  | `.bmp`          | `image/bmp`     | ✅ 支持     | Windows 位图       |
| TIFF | `.tiff`, `.tif` | `image/tiff`    | ✅ 支持     | 高质量图像         |
| SVG  | `.svg`          | `image/svg+xml` | ✅ 支持     | 矢量图形           |
| ICO  | `.ico`          | `image/x-icon`  | ✅ 支持     | 图标文件           |
| HEIC | `.heic`         | `image/heic`    | ✅ 支持     | Apple 高效图像格式 |
| HEIF | `.heif`         | `image/heif`    | ✅ 支持     | 高效图像格式       |
| AVIF | `.avif`         | `image/avif`    | ✅ 支持     | 新一代图像格式     |

## 📄 文档文件（Document Files）

| 格式     | 扩展名          | MIME 类型                       | 支持状态   | 说明                   |
| -------- | --------------- | ------------------------------- | ---------- | ---------------------- |
| PDF      | `.pdf`          | `application/pdf`               | ✅ 完全支持 | 可提取文本、图片、表格 |
| 纯文本   | `.txt`          | `text/plain`                    | ✅ 完全支持 | 纯文本文件             |
| Markdown | `.md`           | `text/markdown`                 | ✅ 完全支持 | 标记语言               |
| HTML     | `.html`, `.htm` | `text/html`                     | ✅ 完全支持 | 网页文件               |
| XML      | `.xml`          | `text/xml` 或 `application/xml` | ✅ 完全支持 | 结构化数据             |
| CSV      | `.csv`          | `text/csv`                      | ✅ 完全支持 | 表格数据               |
| TSV      | `.tsv`          | `text/tab-separated-values`     | ✅ 支持     | 制表符分隔             |
| RTF      | `.rtf`          | `application/rtf`               | ✅ 支持     | 富文本格式             |
| LaTeX    | `.tex`          | `text/x-tex`                    | ✅ 支持     | 科学文档               |

## 📊 Microsoft Office 文档

| 格式            | 扩展名  | MIME 类型                                                                   | 支持状态 | 说明             |
| --------------- | ------- | --------------------------------------------------------------------------- | -------- | ---------------- |
| Word (新)       | `.docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document`   | ✅ 支持   | 可提取文本和格式 |
| Word (旧)       | `.doc`  | `application/msword`                                                        | ✅ 支持   | 旧版 Word 文档   |
| Excel (新)      | `.xlsx` | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`         | ✅ 支持   | 可读取表格数据   |
| Excel (旧)      | `.xls`  | `application/vnd.ms-excel`                                                  | ✅ 支持   | 旧版 Excel 文档  |
| PowerPoint (新) | `.pptx` | `application/vnd.openxmlformats-officedocument.presentationml.presentation` | ✅ 支持   | 可提取文本和图片 |
| PowerPoint (旧) | `.ppt`  | `application/vnd.ms-powerpoint`                                             | ✅ 支持   | 旧版 PPT 文档    |

## 📝 Google Workspace 文档

| 格式          | 扩展名     | MIME 类型                                  | 支持状态 | 说明         |
| ------------- | ---------- | ------------------------------------------ | -------- | ------------ |
| Google Docs   | `.gdoc`    | `application/vnd.google-apps.document`     | ✅ 支持   | 需要导出链接 |
| Google Sheets | `.gsheet`  | `application/vnd.google-apps.spreadsheet`  | ✅ 支持   | 需要导出链接 |
| Google Slides | `.gslides` | `application/vnd.google-apps.presentation` | ✅ 支持   | 需要导出链接 |

## 💻 代码文件（Code Files）

| 格式       | 扩展名                | MIME 类型                                     | 支持状态   | 说明            |
| ---------- | --------------------- | --------------------------------------------- | ---------- | --------------- |
| Python     | `.py`                 | `text/x-python` 或 `application/x-python`     | ✅ 完全支持 | Python 代码     |
| JavaScript | `.js`                 | `text/javascript` 或 `application/javascript` | ✅ 完全支持 | JS 代码         |
| TypeScript | `.ts`                 | `text/typescript` 或 `application/typescript` | ✅ 完全支持 | TS 代码         |
| JSX/TSX    | `.jsx`, `.tsx`        | `text/jsx`, `text/tsx`                        | ✅ 支持     | React 组件      |
| Java       | `.java`               | `text/x-java-source`                          | ✅ 完全支持 | Java 代码       |
| C          | `.c`                  | `text/x-c`                                    | ✅ 支持     | C 语言          |
| C++        | `.cpp`, `.cc`, `.cxx` | `text/x-c++`                                  | ✅ 支持     | C++ 代码        |
| C#         | `.cs`                 | `text/x-csharp`                               | ✅ 支持     | C# 代码         |
| Go         | `.go`                 | `text/x-go`                                   | ✅ 支持     | Go 语言         |
| Rust       | `.rs`                 | `text/x-rust`                                 | ✅ 支持     | Rust 代码       |
| PHP        | `.php`                | `text/x-php` 或 `application/x-php`           | ✅ 支持     | PHP 代码        |
| Ruby       | `.rb`                 | `text/x-ruby`                                 | ✅ 支持     | Ruby 代码       |
| Swift      | `.swift`              | `text/x-swift`                                | ✅ 支持     | Swift 代码      |
| Kotlin     | `.kt`                 | `text/x-kotlin`                               | ✅ 支持     | Kotlin 代码     |
| Scala      | `.scala`              | `text/x-scala`                                | ✅ 支持     | Scala 代码      |
| Shell      | `.sh`, `.bash`        | `text/x-shellscript`                          | ✅ 支持     | Shell 脚本      |
| PowerShell | `.ps1`                | `text/x-powershell`                           | ✅ 支持     | PowerShell 脚本 |
| SQL        | `.sql`                | `text/x-sql` 或 `application/sql`             | ✅ 支持     | SQL 脚本        |
| R          | `.r`, `.R`            | `text/x-r`                                    | ✅ 支持     | R 语言          |
| MATLAB     | `.m`                  | `text/x-matlab`                               | ✅ 支持     | MATLAB 代码     |

## 🎨 Web 开发文件

| 格式      | 扩展名           | MIME 类型                           | 支持状态   | 说明         |
| --------- | ---------------- | ----------------------------------- | ---------- | ------------ |
| CSS       | `.css`           | `text/css`                          | ✅ 完全支持 | 样式表       |
| SCSS/Sass | `.scss`, `.sass` | `text/x-scss`, `text/x-sass`        | ✅ 支持     | CSS 预处理器 |
| LESS      | `.less`          | `text/x-less`                       | ✅ 支持     | CSS 预处理器 |
| JSON      | `.json`          | `application/json`                  | ✅ 完全支持 | 数据交换格式 |
| YAML      | `.yaml`, `.yml`  | `text/yaml` 或 `application/x-yaml` | ✅ 支持     | 配置文件     |
| TOML      | `.toml`          | `application/toml`                  | ✅ 支持     | 配置文件     |
| Vue       | `.vue`           | `text/x-vue`                        | ✅ 支持     | Vue 组件     |
| Svelte    | `.svelte`        | `text/x-svelte`                     | ✅ 支持     | Svelte 组件  |

## 🎵 音频文件（Audio Files）

| 格式 | 扩展名          | MIME 类型                    | 支持状态   | 说明         |
| ---- | --------------- | ---------------------------- | ---------- | ------------ |
| MP3  | `.mp3`          | `audio/mpeg` 或 `audio/mp3`  | ✅ 完全支持 | 最常用格式   |
| WAV  | `.wav`          | `audio/wav` 或 `audio/x-wav` | ✅ 完全支持 | 无损格式     |
| AAC  | `.aac`          | `audio/aac`                  | ✅ 支持     | 高质量压缩   |
| M4A  | `.m4a`          | `audio/m4a` 或 `audio/mp4`   | ✅ 支持     | Apple 格式   |
| OGG  | `.ogg`          | `audio/ogg`                  | ✅ 支持     | 开源格式     |
| FLAC | `.flac`         | `audio/flac`                 | ✅ 支持     | 无损压缩     |
| AIFF | `.aiff`, `.aif` | `audio/aiff`                 | ✅ 支持     | Apple 格式   |
| WMA  | `.wma`          | `audio/x-ms-wma`             | ✅ 支持     | Windows 格式 |
| OPUS | `.opus`         | `audio/opus`                 | ✅ 支持     | 高效编码     |
| AMR  | `.amr`          | `audio/amr`                  | ✅ 支持     | 语音编码     |

**音频功能**：
- 🎤 语音转文字（转录）
- 🗣️ 说话人识别
- 🌍 语言识别
- 😊 情感分析
- 🎵 音乐分析

## 🎬 视频文件（Video Files）

| 格式 | 扩展名          | MIME 类型          | 支持状态   | 说明         |
| ---- | --------------- | ------------------ | ---------- | ------------ |
| MP4  | `.mp4`          | `video/mp4`        | ✅ 完全支持 | 最常用格式   |
| MOV  | `.mov`          | `video/quicktime`  | ✅ 完全支持 | Apple 格式   |
| AVI  | `.avi`          | `video/x-msvideo`  | ✅ 支持     | Windows 格式 |
| MPEG | `.mpeg`, `.mpg` | `video/mpeg`       | ✅ 支持     | 标准格式     |
| WebM | `.webm`         | `video/webm`       | ✅ 支持     | 网页格式     |
| FLV  | `.flv`          | `video/x-flv`      | ✅ 支持     | Flash 格式   |
| WMV  | `.wmv`          | `video/x-ms-wmv`   | ✅ 支持     | Windows 格式 |
| MKV  | `.mkv`          | `video/x-matroska` | ✅ 支持     | 开源容器     |
| 3GPP | `.3gp`, `.3gpp` | `video/3gpp`       | ✅ 支持     | 移动格式     |
| M4V  | `.m4v`          | `video/x-m4v`      | ✅ 支持     | Apple 格式   |

**视频功能**：
- 🎬 场景识别
- 👤 人物检测
- 🏷️ 对象识别
- 📝 字幕生成
- 🎯 动作识别
- 📊 内容分析

## 📦 数据文件（Data Files）

| 格式    | 扩展名     | MIME 类型                   | 支持状态   | 说明        |
| ------- | ---------- | --------------------------- | ---------- | ----------- |
| JSON    | `.json`    | `application/json`          | ✅ 完全支持 | 数据交换    |
| JSONL   | `.jsonl`   | `application/jsonlines`     | ✅ 支持     | 行分隔 JSON |
| CSV     | `.csv`     | `text/csv`                  | ✅ 完全支持 | 表格数据    |
| TSV     | `.tsv`     | `text/tab-separated-values` | ✅ 支持     | 制表符分隔  |
| Parquet | `.parquet` | `application/x-parquet`     | ⚠️ 可能支持 | 列式存储    |
| Avro    | `.avro`    | `application/avro`          | ⚠️ 可能支持 | 数据序列化  |

## 🗜️ 压缩文件（Archive Files）

| 格式 | 扩展名 | MIME 类型                      | 支持状态   | 说明     |
| ---- | ------ | ------------------------------ | ---------- | -------- |
| ZIP  | `.zip` | `application/zip`              | ⚠️ 部分支持 | 需要解压 |
| RAR  | `.rar` | `application/x-rar-compressed` | ❌ 不支持   | 需要解压 |
| 7Z   | `.7z`  | `application/x-7z-compressed`  | ❌ 不支持   | 需要解压 |
| TAR  | `.tar` | `application/x-tar`            | ⚠️ 部分支持 | 需要解压 |
| GZ   | `.gz`  | `application/gzip`             | ⚠️ 部分支持 | 需要解压 |

## 🔧 配置文件（Configuration Files）

| 格式       | 扩展名          | MIME 类型          | 支持状态   | 说明      |
| ---------- | --------------- | ------------------ | ---------- | --------- |
| YAML       | `.yaml`, `.yml` | `text/yaml`        | ✅ 完全支持 | 配置文件  |
| TOML       | `.toml`         | `application/toml` | ✅ 支持     | 配置文件  |
| INI        | `.ini`          | `text/plain`       | ✅ 支持     | 配置文件  |
| ENV        | `.env`          | `text/plain`       | ✅ 支持     | 环境变量  |
| Properties | `.properties`   | `text/plain`       | ✅ 支持     | Java 配置 |

## 📚 电子书格式（E-book Formats）

| 格式 | 扩展名  | MIME 类型                        | 支持状态   | 说明        |
| ---- | ------- | -------------------------------- | ---------- | ----------- |
| EPUB | `.epub` | `application/epub+zip`           | ⚠️ 可能支持 | 电子书格式  |
| MOBI | `.mobi` | `application/x-mobipocket-ebook` | ⚠️ 可能支持 | Kindle 格式 |

## 📊 文件大小限制

| 文件类型    | 推荐大小 | 最大大小 | 处理时间   |
| ----------- | -------- | -------- | ---------- |
| 图片        | < 5 MB   | ~20 MB   | 秒级       |
| PDF         | < 10 MB  | ~100 MB  | 秒到分钟   |
| Office 文档 | < 10 MB  | ~50 MB   | 秒到分钟   |
| 文本/代码   | < 1 MB   | ~10 MB   | 秒级       |
| 音频        | < 20 MB  | ~100 MB  | 分钟级     |
| 视频        | < 100 MB | ~2 GB    | 分钟到小时 |

## 🎯 使用示例

### 1. 图片文件

```bash
curl -X POST http://localhost:7860/v1/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key" \
  -d '{
    "model": "gemini-2.5-pro",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "text", "text": "描述这张图片"},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/4AAQSkZJRg..."}}
      ]
    }]
  }'
```

### 2. PDF 文档

```bash
curl -X POST http://localhost:7860/v1/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key" \
  -d '{
    "model": "gemini-2.5-pro",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "text", "text": "总结这个PDF的主要内容"},
        {"type": "image_url", "image_url": {"url": "https://example.com/report.pdf"}}
      ]
    }]
  }'
```

### 3. Office 文档

```bash
# Word 文档
curl -X POST http://localhost:7860/v1/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key" \
  -d '{
    "model": "gemini-2.5-pro",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "text", "text": "总结这个Word文档的内容"},
        {"type": "image_url", "image_url": {"url": "https://example.com/document.docx"}}
      ]
    }]
  }'

# Excel 表格
curl -X POST http://localhost:7860/v1/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key" \
  -d '{
    "model": "gemini-2.5-pro",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "text", "text": "分析这个Excel表格的数据"},
        {"type": "image_url", "image_url": {"url": "https://example.com/data.xlsx"}}
      ]
    }]
  }'

# PowerPoint 演示文稿
curl -X POST http://localhost:7860/v1/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key" \
  -d '{
    "model": "gemini-2.5-pro",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "text", "text": "总结这个PPT的主要内容"},
        {"type": "image_url", "image_url": {"url": "https://example.com/presentation.pptx"}}
      ]
    }]
  }'
```

### 4. 音频文件

```bash
curl -X POST http://localhost:7860/v1/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key" \
  -d '{
    "model": "gemini-2.5-pro",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "text", "text": "转录这段音频并总结内容"},
        {"type": "image_url", "image_url": {"url": "https://example.com/audio.mp3"}}
      ]
    }]
  }'
```

### 5. 视频文件

```bash
curl -X POST http://localhost:7860/v1/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key" \
  -d '{
    "model": "gemini-2.5-pro",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "text", "text": "描述这个视频的主要场景"},
        {"type": "image_url", "image_url": {"url": "https://example.com/video.mp4"}}
      ]
    }]
  }'
```

### 6. 代码文件

```bash
curl -X POST http://localhost:7860/v1/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key" \
  -d '{
    "model": "gemini-2.5-pro",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "text", "text": "审查这段代码并提出改进建议"},
        {"type": "image_url", "image_url": {"url": "data:text/x-python;base64,ZGVmIGhlbGxvKCk6..."}}
      ]
    }]
  }'
```

### 7. 混合多种文件

```bash
curl -X POST http://localhost:7860/v1/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key" \
  -d '{
    "model": "gemini-2.5-pro",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "text", "text": "比较这些文件的内容"},
        {"type": "image_url", "image_url": {"url": "https://example.com/image.jpg"}},
        {"type": "image_url", "image_url": {"url": "https://example.com/document.pdf"}},
        {"type": "image_url", "image_url": {"url": "https://example.com/audio.mp3"}}
      ]
    }]
  }'
```

## ⚠️ 重要说明

1. **实际支持范围**：Google Gemini API 的实际支持范围可能比官方文档更广，建议实际测试
2. **MIME 类型**：必须正确指定 MIME 类型，否则可能处理失败
3. **文件大小**：超大文件可能导致超时或处理失败
4. **处理质量**：不同文件类型的处理质量可能不同
5. **API 版本**：支持的文件类型可能随 API 版本变化
6. **字段名称**：虽然支持所有文件类型，但仍使用 `image_url` 字段（OpenAI API 标准）

## 📝 支持状态说明

- ✅ **完全支持**：经过充分测试，稳定可用
- ✅ **支持**：可以使用，但可能有限制
- ⚠️ **可能支持**：理论上支持，需要实际测试
- ⚠️ **部分支持**：有条件支持，可能需要特殊处理
- ❌ **不支持**：当前不支持或需要转换

## 🔗 相关链接

- [项目主页](https://github.com/Dreamy-rain/gemini-business2api)
- [API 文档](README.md)
- [问题反馈](https://github.com/Dreamy-rain/gemini-business2api/issues)
