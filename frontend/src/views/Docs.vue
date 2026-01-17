<template>
  <div class="space-y-6">
    <section class="rounded-3xl border border-border bg-card p-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p class="text-base font-semibold text-foreground">帮助中心</p>
          <p class="mt-1 text-xs text-muted-foreground">
            快速上手与常见问题
          </p>
        </div>
      </div>

      <!-- 标签切换 -->
      <div class="mt-6 flex rounded-full border border-border bg-muted/30 p-1 text-xs">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          class="flex-1 rounded-full px-4 py-2 font-medium transition-colors"
          :class="activeTab === tab.id
            ? 'bg-foreground text-background'
            : 'text-muted-foreground hover:text-foreground'"
          @click="activeTab = tab.id"
        >
          {{ tab.label }}
        </button>
      </div>

      <!-- 内容区域 -->
      <div class="mt-6 space-y-6 text-sm text-foreground">
        <!-- 使用教程 -->
        <div v-if="activeTab === 'api'" class="space-y-6">
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
            <div class="mt-3">
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

        <!-- 使用教程 -->
        <div v-if="activeTab === 'tutorials'" class="space-y-6">
          <div class="space-y-2">
            <p class="text-sm font-semibold">DuckMail 自动注册教程</p>
            <p class="mt-1 text-xs text-muted-foreground">
              DuckMail 是一个临时邮箱服务，可用于自动注册 Google 账号。
            </p>
            <div class="mt-3 space-y-3 text-xs text-muted-foreground">
              <div class="rounded-2xl border border-border bg-muted/30 p-4">
                <p class="font-medium text-foreground">步骤 1：配置 DuckMail</p>
                <p class="mt-2">访问 <a href="https://domain.duckmail.sbs/" target="_blank" class="text-primary hover:underline">https://domain.duckmail.sbs/</a>，登录注册后：</p>
                <ul class="mt-2 space-y-1 pl-4">
                  <li>• 添加域名，按照提示进行 DNS 解析</li>
                  <li>• 创建自己的密钥（API Key）</li>
                  <li>• 前往本系统"配置面板"，找到"DuckMail 配置"部分</li>
                  <li>• 填写 DuckMail API Key</li>
                  <li>• <strong>推荐：</strong>在"默认注册域名"中填入自己的域名（DuckMail 可能会出现密码错误情况，建议使用自己的域名）</li>
                </ul>
              </div>

              <div class="rounded-2xl border border-border bg-muted/30 p-4">
                <p class="font-medium text-foreground">步骤 2：开始注册</p>
                <p class="mt-2">前往"账户管理"页面：</p>
                <ul class="mt-2 space-y-1 pl-4">
                  <li>• 点击"添加账户"按钮</li>
                  <li>• 选择"自动注册"标签</li>
                  <li>• 设置注册数量</li>
                  <li>• 勾选同意声明</li>
                  <li>• 点击"开始注册"</li>
                </ul>
              </div>

              <div class="rounded-2xl border border-border bg-muted/30 p-4">
                <p class="font-medium text-foreground">步骤 3：查看进度</p>
                <p class="mt-2">注册过程会自动进行：</p>
                <ul class="mt-2 space-y-1 pl-4">
                  <li>• 系统会自动打开"任务状态"弹窗</li>
                  <li>• 可以查看实时日志和进度</li>
                  <li>• 注册完成后会显示成功/失败数量</li>
                  <li>• 成功的账号会自动添加到账户列表</li>
                </ul>
              </div>
            </div>
          </div>

          <div class="space-y-2">
            <p class="text-sm font-semibold">常见问题</p>
            <div class="mt-3 space-y-3 text-xs text-muted-foreground">
              <div class="rounded-2xl border border-border bg-muted/30 p-4">
                <p class="font-medium text-foreground">❓ 自动注册/刷新失败怎么办？</p>
                <p class="mt-2">关闭无头浏览器可以直接看到问题所在：</p>
                <ul class="mt-2 space-y-1 pl-4">
                  <li>• 前往"配置面板"，找到"自动化配置"部分</li>
                  <li>• 取消勾选"无头模式"</li>
                  <li>• 重新执行注册/刷新操作，观察浏览器窗口</li>
                </ul>
                <p class="mt-3 font-medium text-foreground">可能的原因：</p>
                <ul class="mt-2 space-y-1 pl-4">
                  <li>• <strong>IP 被检测拦截：</strong>同一 IP 多次注册有风控，建议更换合适的 IP</li>
                  <li>• <strong>验证码问题：</strong>Google 可能要求人机验证</li>
                  <li>• <strong>网络问题：</strong>检查网络连接是否稳定</li>
                </ul>
              </div>

              <div class="rounded-2xl border border-border bg-muted/30 p-4">
                <p class="font-medium text-foreground">❓ 503 Service Unavailable 错误</p>
                <p class="mt-2">如果后台日志出现以下错误：</p>
                <pre class="mt-2 overflow-x-auto whitespace-pre-wrap rounded-xl border border-border bg-card px-3 py-2 text-[11px] font-mono">INFO:     127.0.0.1:7860 - "GET /admin/register/current HTTP/1.1" 503 Service Unavailable
INFO:     127.0.0.1:7860 - "GET /admin/login/current HTTP/1.1" 503 Service Unavailable
INFO:     127.0.0.1:7860 - "POST /admin/register/start HTTP/1.1" 503 Service Unavailable</pre>
                <p class="mt-3 font-medium text-foreground">解决方法：</p>
                <ul class="mt-2 space-y-1 pl-4">
                  <li>• 这是 undetected-chromedriver 没有正常启动导致的</li>
                  <li>• 在虚拟环境内重新安装依赖：<code class="rounded bg-card px-1.5 py-0.5 font-mono text-[11px]">pip install -r requirements.txt</code></li>
                  <li>• 删除之前的进程（检查是否有残留的 Chrome 进程）</li>
                  <li>• 重新启动服务</li>
                </ul>
              </div>
            </div>
          </div>
        </div>

        <!-- 使用声明 -->
        <div v-if="activeTab === 'disclaimer'" class="space-y-6">
          <div class="space-y-2">
            <p class="text-sm font-semibold">使用声明与免责条款</p>
            <div class="mt-3 space-y-3 text-xs text-muted-foreground leading-relaxed">
              <div class="rounded-2xl border border-rose-200 bg-rose-50 p-4">
                <p class="font-medium text-rose-600">⚠️ 严禁滥用：禁止将本工具用于商业用途或任何形式的滥用（无论规模大小）</p>
              </div>

              <div class="rounded-2xl border border-border bg-muted/30 p-4">
                <p class="font-medium text-foreground">本工具严禁用于以下行为：</p>
                <ul class="mt-2 space-y-1 pl-4">
                  <li>• 商业用途或盈利性使用</li>
                  <li>• 任何形式的批量操作或自动化滥用（无论规模大小）</li>
                  <li>• 破坏市场秩序或恶意竞争</li>
                  <li>• 违反 Google 服务条款的任何行为</li>
                  <li>• 违反 Microsoft 服务条款的任何行为</li>
                </ul>
              </div>

              <div class="rounded-2xl border border-border bg-muted/30 p-4">
                <p class="font-medium text-foreground">违规后果</p>
                <p class="mt-2">滥用行为可能导致账号永久封禁、法律追责，一切后果由使用者自行承担。</p>
              </div>

              <div class="rounded-2xl border border-border bg-muted/30 p-4">
                <p class="font-medium text-foreground">📖 合法用途</p>
                <p class="mt-2">本项目仅限于以下场景：</p>
                <ul class="mt-2 space-y-1 pl-4">
                  <li>• 个人学习与技术研究</li>
                  <li>• 浏览器自动化技术探索</li>
                  <li>• 非商业性技术交流</li>
                </ul>
              </div>

              <div class="rounded-2xl border border-border bg-muted/30 p-4">
                <p class="font-medium text-foreground">⚖️ 法律责任</p>
                <ul class="mt-2 space-y-2 pl-4">
                  <li><strong>使用者责任：</strong>使用本工具产生的一切后果（包括但不限于账号封禁、数据损失、法律纠纷）由使用者完全承担</li>
                  <li><strong>合规义务：</strong>使用者必须遵守所在地法律法规及第三方服务条款（包括但不限于 Google Workspace、Microsoft 365 等服务条款）</li>
                  <li><strong>作者免责：</strong>作者不对任何违规使用、滥用行为或由此产生的后果承担责任</li>
                </ul>
              </div>

              <div class="rounded-2xl border border-border bg-muted/30 p-4">
                <p class="font-medium text-foreground">📋 技术声明</p>
                <ul class="mt-2 space-y-1 pl-4">
                  <li>• <strong>无担保：</strong>本项目按"现状"提供，不提供任何形式的担保</li>
                  <li>• <strong>第三方依赖：</strong>依赖的第三方服务（如 DuckMail API、Microsoft Graph API 等）可用性不受作者控制</li>
                  <li>• <strong>维护权利：</strong>作者保留随时停止维护、变更功能或关闭项目的权利</li>
                </ul>
              </div>

              <div class="rounded-2xl border border-border bg-muted/30 p-4">
                <p class="font-medium text-foreground">🔗 相关服务条款</p>
                <p class="mt-2">使用本工具时，您必须同时遵守以下第三方服务的条款：</p>
                <ul class="mt-2 space-y-1 pl-4">
                  <li>• <a href="https://policies.google.com/terms" target="_blank" class="text-primary hover:underline">Google 服务条款</a></li>
                  <li>• <a href="https://workspace.google.com/terms/service-terms.html" target="_blank" class="text-primary hover:underline">Google Workspace 附加条款</a></li>
                  <li>• <a href="https://www.microsoft.com/servicesagreement" target="_blank" class="text-primary hover:underline">Microsoft 服务协议</a></li>
                  <li>• <a href="https://www.microsoft.com/licensing/terms" target="_blank" class="text-primary hover:underline">Microsoft 365 使用条款</a></li>
                </ul>
              </div>

              <div class="rounded-2xl border border-amber-200 bg-amber-50 p-4">
                <p class="font-medium text-amber-700">使用本工具即表示您已阅读、理解并同意遵守以上所有条款。</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const activeTab = ref('tutorials')

const tabs = [
  { id: 'tutorials', label: '使用教程' },
  { id: 'api', label: 'API 文档' },
  { id: 'disclaimer', label: '使用声明' },
]
</script>
