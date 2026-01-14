import{c as r,A as s,e as n}from"./index-koyNnZzO.js";const a=(o,t)=>{const u=o.__vccOpts||o;for(const[e,q]of t)u[e]=q;return u},p={},l={class:"space-y-6"};function c(o,t){return n(),r("div",l,[...t[0]||(t[0]=[s(`<section class="rounded-3xl border border-border bg-card p-6"><div class="flex flex-wrap items-center justify-between gap-3"><div><p class="text-base font-semibold text-foreground">文档中心</p><p class="mt-1 text-xs text-muted-foreground"> 常用格式说明与示例，复制即可使用 </p></div></div><div class="mt-6 space-y-6 text-sm text-foreground"><div class="space-y-2"><p class="text-sm font-semibold">账户配置格式</p><p class="mt-1 text-xs text-muted-foreground"> accounts.json 或环境变量 ACCOUNTS_CONFIG 使用的 JSON 数组 </p><pre class="mt-3 overflow-x-auto whitespace-pre-wrap rounded-2xl border border-border bg-card px-4 py-3 text-xs font-mono scrollbar-slim">[
  {
    &quot;id&quot;: &quot;account_1&quot;,
    &quot;secure_c_ses&quot;: &quot;CSE.Ad...&quot;,
    &quot;csesidx&quot;: &quot;498...&quot;,
    &quot;config_id&quot;: &quot;0cd...&quot;,
    &quot;host_c_oses&quot;: &quot;&quot;,
    &quot;expires_at&quot;: &quot;2026-12-31 23:59:59&quot;
  }
]</pre><p class="mt-2 text-xs text-muted-foreground"> 必填：secure_c_ses / csesidx / config_id。id、host_c_oses、expires_at 可选。 </p></div><div class="space-y-2"><p class="text-sm font-semibold">API 对话 curl 格式</p><p class="mt-1 text-xs text-muted-foreground"> 标准的 OpenAI 兼容格式，支持流式和非流式输出。 </p><div class="mt-3 grid gap-3 md:grid-cols-2"><pre class="overflow-x-auto whitespace-pre-wrap rounded-2xl border border-border bg-card px-4 py-3 text-xs font-mono scrollbar-slim">curl -X POST &quot;http://localhost:7860/v1/chat/completions&quot; \\
  -H &quot;Content-Type: application/json&quot; \\
  -H &quot;Authorization: Bearer YOUR_API_KEY&quot; \\
  -d &#39;{
    &quot;model&quot;: &quot;gemini-2.5-flash&quot;,
    &quot;stream&quot;: false,
    &quot;temperature&quot;: 0.7,
    &quot;top_p&quot;: 1,
    &quot;messages&quot;: [
      { &quot;role&quot;: &quot;system&quot;, &quot;content&quot;: &quot;你是一个简洁的助手&quot; },
      { &quot;role&quot;: &quot;user&quot;, &quot;content&quot;: &quot;你好，介绍一下这个项目&quot; }
    ]
  }&#39;</pre></div><p class="mt-2 text-xs text-muted-foreground"> 如果未设置 API Key，可省略 Authorization。 </p></div><div class="space-y-2"><p class="text-sm font-semibold">文生图格式（Base64 / URL 输出）</p><p class="mt-1 text-xs text-muted-foreground"> 使用支持文生图的模型，直接给文本提示即可；输出格式由系统设置决定（base64 或 url）。 </p><pre class="mt-3 overflow-x-auto whitespace-pre-wrap rounded-2xl border border-border bg-card px-4 py-3 text-xs font-mono scrollbar-slim">curl -X POST &quot;http://localhost:7860/v1/chat/completions&quot; \\
  -H &quot;Content-Type: application/json&quot; \\
  -H &quot;Authorization: Bearer YOUR_API_KEY&quot; \\
  -d &#39;{
    &quot;model&quot;: &quot;gemini-3-pro-preview&quot;,
    &quot;stream&quot;: true,
    &quot;temperature&quot;: 0.7,
    &quot;top_p&quot;: 1,
    &quot;messages&quot;: [
      { &quot;role&quot;: &quot;user&quot;, &quot;content&quot;: &quot;生成一只戴着头盔的猫，赛博风格&quot; }
    ]
  }&#39;</pre></div><div class="space-y-2"><p class="text-sm font-semibold">图生图格式（Base64 / URL 输入）</p><p class="mt-1 text-xs text-muted-foreground"> content 使用多模态数组，image_url 可填 URL 或 data:base64。 </p><div class="mt-3 grid gap-3 md:grid-cols-2"><pre class="overflow-x-auto whitespace-pre-wrap rounded-2xl border border-border bg-card px-4 py-3 text-xs font-mono scrollbar-slim">curl -X POST &quot;http://localhost:7860/v1/chat/completions&quot; \\
  -H &quot;Content-Type: application/json&quot; \\
  -H &quot;Authorization: Bearer YOUR_API_KEY&quot; \\
  -d &#39;{
    &quot;model&quot;: &quot;gemini-3-flash-preview&quot;,
    &quot;stream&quot;: false,
    &quot;temperature&quot;: 0.7,
    &quot;top_p&quot;: 1,
    &quot;messages&quot;: [
      {
        &quot;role&quot;: &quot;user&quot;,
        &quot;content&quot;: [
          { &quot;type&quot;: &quot;text&quot;, &quot;text&quot;: &quot;把图片改成插画风格&quot; },
          { &quot;type&quot;: &quot;image_url&quot;, &quot;image_url&quot;: { &quot;url&quot;: &quot;https://example.com/cat.png&quot; } }
        ]
      }
    ]
  }&#39;</pre><pre class="overflow-x-auto whitespace-pre-wrap rounded-2xl border border-border bg-card px-4 py-3 text-xs font-mono scrollbar-slim">curl -X POST &quot;http://localhost:7860/v1/chat/completions&quot; \\
  -H &quot;Content-Type: application/json&quot; \\
  -H &quot;Authorization: Bearer YOUR_API_KEY&quot; \\
  -d &#39;{
    &quot;model&quot;: &quot;gemini-3-flash-preview&quot;,
    &quot;stream&quot;: false,
    &quot;temperature&quot;: 0.7,
    &quot;top_p&quot;: 1,
    &quot;messages&quot;: [
      {
        &quot;role&quot;: &quot;user&quot;,
        &quot;content&quot;: [
          { &quot;type&quot;: &quot;text&quot;, &quot;text&quot;: &quot;增强画面细节&quot; },
          { &quot;type&quot;: &quot;image_url&quot;, &quot;image_url&quot;: { &quot;url&quot;: &quot;data:image/png;base64,AAA...&quot; } }
        ]
      }
    ]
  }&#39;</pre></div></div><div class="space-y-2"><p class="text-sm font-semibold">读文件格式（URL / Base64）</p><p class="mt-1 text-xs text-muted-foreground"> 适用于 PDF/图片/文本等可读文件，Word/PPT 等可能不支持会被提示转换。大部分文件都可能支持，建议自行测试。 </p><div class="mt-3 grid gap-3 md:grid-cols-2"><pre class="overflow-x-auto whitespace-pre-wrap rounded-2xl border border-border bg-card px-4 py-3 text-xs font-mono scrollbar-slim">curl -X POST &quot;http://localhost:7860/v1/chat/completions&quot; \\
  -H &quot;Content-Type: application/json&quot; \\
  -H &quot;Authorization: Bearer YOUR_API_KEY&quot; \\
  -d &#39;{
    &quot;model&quot;: &quot;gemini-2.5-pro&quot;,
    &quot;stream&quot;: false,
    &quot;temperature&quot;: 0.7,
    &quot;top_p&quot;: 1,
    &quot;messages&quot;: [
      {
        &quot;role&quot;: &quot;user&quot;,
        &quot;content&quot;: [
          { &quot;type&quot;: &quot;text&quot;, &quot;text&quot;: &quot;读取并总结这个文件&quot; },
          { &quot;type&quot;: &quot;image_url&quot;, &quot;image_url&quot;: { &quot;url&quot;: &quot;https://example.com/doc.pdf&quot; } }
        ]
      }
    ]
  }&#39;</pre><pre class="overflow-x-auto whitespace-pre-wrap rounded-2xl border border-border bg-card px-4 py-3 text-xs font-mono scrollbar-slim">curl -X POST &quot;http://localhost:7860/v1/chat/completions&quot; \\
  -H &quot;Content-Type: application/json&quot; \\
  -H &quot;Authorization: Bearer YOUR_API_KEY&quot; \\
  -d &#39;{
    &quot;model&quot;: &quot;gemini-2.5-pro&quot;,
    &quot;stream&quot;: false,
    &quot;temperature&quot;: 0.7,
    &quot;top_p&quot;: 1,
    &quot;messages&quot;: [
      {
        &quot;role&quot;: &quot;user&quot;,
        &quot;content&quot;: [
          { &quot;type&quot;: &quot;text&quot;, &quot;text&quot;: &quot;读取并摘要&quot; },
          { &quot;type&quot;: &quot;image_url&quot;, &quot;image_url&quot;: { &quot;url&quot;: &quot;data:application/pdf;base64,AAA...&quot; } }
        ]
      }
    ]
  }&#39;</pre></div></div></div></section>`,1)])])}const i=a(p,[["render",c]]);export{i as default};
