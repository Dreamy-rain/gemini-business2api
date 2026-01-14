<template>
  <div class="space-y-6">
    <section class="rounded-3xl border border-border bg-card p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p class="text-base font-semibold text-foreground">文档中心</p>
          <p class="mt-1 text-xs text-muted-foreground">
            常用格式说明与示例，复制即可使用
          </p>
        </div>
      </div>

      <div class="mt-6 space-y-6 text-sm text-foreground">
        <div class="space-y-2">
          <p class="text-sm font-semibold">账户配置格式</p>
          <p class="mt-1 text-xs text-muted-foreground">
            accounts.json 或环境变量 ACCOUNTS_CONFIG 使用的 JSON 数组
          </p>
          <pre class="mt-3 overflow-x-auto whitespace-pre-wrap rounded-2xl border border-border bg-card px-4 py-3 text-xs font-mono scrollbar-slim">[
  {
    "id": "account_1",
    "secure_c_ses": "CSE.Ad...",
    "csesidx": "498...",
    "config_id": "0cd...",
    "host_c_oses": "",
    "expires_at": "2026-12-31 23:59:59"
  }
]</pre>
          <p class="mt-2 text-xs text-muted-foreground">
            必填：secure_c_ses / csesidx / config_id。id、host_c_oses、expires_at 可选。
          </p>
        </div>

        <div class="space-y-2">
          <p class="text-sm font-semibold">API 对话 curl 格式</p>
          <p class="mt-1 text-xs text-muted-foreground">
            标准的 OpenAI 兼容格式，支持流式和非流式输出。
          </p>
          <div class="mt-3 grid gap-3 md:grid-cols-2">
            <pre class="overflow-x-auto whitespace-pre-wrap rounded-2xl border border-border bg-card px-4 py-3 text-xs font-mono scrollbar-slim">curl -X POST "http://localhost:7860/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "model": "gemini-2.5-flash",
    "stream": false,
    "temperature": 0.7,
    "top_p": 1,
    "messages": [
      { "role": "system", "content": "你是一个简洁的助手" },
      { "role": "user", "content": "你好，介绍一下这个项目" }
    ]
  }'</pre>
          </div>
          <p class="mt-2 text-xs text-muted-foreground">
            如果未设置 API Key，可省略 Authorization。
          </p>
        </div>

        <div class="space-y-2">
          <p class="text-sm font-semibold">文生图格式（Base64 / URL 输出）</p>
          <p class="mt-1 text-xs text-muted-foreground">
            使用支持文生图的模型，直接给文本提示即可；输出格式由系统设置决定（base64 或 url）。
          </p>
          <pre class="mt-3 overflow-x-auto whitespace-pre-wrap rounded-2xl border border-border bg-card px-4 py-3 text-xs font-mono scrollbar-slim">curl -X POST "http://localhost:7860/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "model": "gemini-3-pro-preview",
    "stream": true,
    "temperature": 0.7,
    "top_p": 1,
    "messages": [
      { "role": "user", "content": "生成一只戴着头盔的猫，赛博风格" }
    ]
  }'</pre>
        </div>

        <div class="space-y-2">
          <p class="text-sm font-semibold">图生图格式（Base64 / URL 输入）</p>
          <p class="mt-1 text-xs text-muted-foreground">
            content 使用多模态数组，image_url 可填 URL 或 data:base64。
          </p>
          <div class="mt-3 grid gap-3 md:grid-cols-2">
            <pre class="overflow-x-auto whitespace-pre-wrap rounded-2xl border border-border bg-card px-4 py-3 text-xs font-mono scrollbar-slim">curl -X POST "http://localhost:7860/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "model": "gemini-3-flash-preview",
    "stream": false,
    "temperature": 0.7,
    "top_p": 1,
    "messages": [
      {
        "role": "user",
        "content": [
          { "type": "text", "text": "把图片改成插画风格" },
          { "type": "image_url", "image_url": { "url": "https://example.com/cat.png" } }
        ]
      }
    ]
  }'</pre>
            <pre class="overflow-x-auto whitespace-pre-wrap rounded-2xl border border-border bg-card px-4 py-3 text-xs font-mono scrollbar-slim">curl -X POST "http://localhost:7860/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "model": "gemini-3-flash-preview",
    "stream": false,
    "temperature": 0.7,
    "top_p": 1,
    "messages": [
      {
        "role": "user",
        "content": [
          { "type": "text", "text": "增强画面细节" },
          { "type": "image_url", "image_url": { "url": "data:image/png;base64,AAA..." } }
        ]
      }
    ]
  }'</pre>
          </div>
        </div>

        <div class="space-y-2">
          <p class="text-sm font-semibold">读文件格式（URL / Base64）</p>
          <p class="mt-1 text-xs text-muted-foreground">
            适用于 PDF/图片/文本等可读文件，Word/PPT 等可能不支持会被提示转换。大部分文件都可能支持，建议自行测试。
          </p>
          <div class="mt-3 grid gap-3 md:grid-cols-2">
            <pre class="overflow-x-auto whitespace-pre-wrap rounded-2xl border border-border bg-card px-4 py-3 text-xs font-mono scrollbar-slim">curl -X POST "http://localhost:7860/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "model": "gemini-2.5-pro",
    "stream": false,
    "temperature": 0.7,
    "top_p": 1,
    "messages": [
      {
        "role": "user",
        "content": [
          { "type": "text", "text": "读取并总结这个文件" },
          { "type": "image_url", "image_url": { "url": "https://example.com/doc.pdf" } }
        ]
      }
    ]
  }'</pre>
            <pre class="overflow-x-auto whitespace-pre-wrap rounded-2xl border border-border bg-card px-4 py-3 text-xs font-mono scrollbar-slim">curl -X POST "http://localhost:7860/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "model": "gemini-2.5-pro",
    "stream": false,
    "temperature": 0.7,
    "top_p": 1,
    "messages": [
      {
        "role": "user",
        "content": [
          { "type": "text", "text": "读取并摘要" },
          { "type": "image_url", "image_url": { "url": "data:application/pdf;base64,AAA..." } }
        ]
      }
    ]
  }'</pre>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>