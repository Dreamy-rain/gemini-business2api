# 浏览器自动化测试指南

## 测试结果总结（2026-01-29）

### ✅ 成功获取的元素

#### 1. 验证码输入框
```python
# 选择器（按优先级）
selectors = [
    "css:input[jsname='ovqh0b']",  # ✅ 最可靠
    "css:input[name='pinInput']",   # ✅ 可靠
    "css:input.J6L5wc",             # ✅ 可靠
]

# 元素属性
type: text
name: pinInput
jsname: ovqh0b
class: J6L5wc
style: opacity: 1; left: 0px; width: 54px;
```

#### 2. 提交按钮（"验证"）
```python
# 选择器
selector = "css:button[jsname='XooR8e']"

# 元素属性
text: '验证'
aria-label: '验证'
jsname: 'XooR8e'

# 查找逻辑
buttons = page.eles("tag:button")
for btn in buttons:
    text = btn.text or ''
    aria_label = btn.attr('aria-label') or ''
    if '验证' in text and '重新' not in text:
        # 这是提交按钮
        btn.click()
```

#### 3. 重新发送按钮
```python
# 选择器
selector = "css:button[jsname='WGPTvf']"

# 元素属性
text: '重新发送验证码'
aria-label: '重新发送验证码'
jsname: 'WGPTvf'

# 查找逻辑
for btn in buttons:
    text = btn.text or ''
    if '重新发送' in text or 'resend' in text.lower():
        # 这是重新发送按钮
        btn.click()
```

---

## 🎯 LLM 自动化浏览器测试的最佳实践

### 方法对比

| 方法 | 优点 | 缺点 | 成本 | 推荐度 |
|------|------|------|------|--------|
| **Playwright MCP** | • LLM 可看截图<br>• 自动分析 DOM<br>• 自动生成选择器<br>• 容错性强 | • 需要 MCP 服务器<br>• 可能有权限问题 | 免费 | ⭐⭐⭐⭐⭐ |
| **Computer Use API** | • 直接看屏幕<br>• 像人类一样操作<br>• 无需选择器 | • 需要 Anthropic API<br>• 成本较高<br>• 速度较慢 | $$ | ⭐⭐⭐⭐ |
| **Browser Use** | • 专为 LLM 设计<br>• 开源免费<br>• 易于集成 | • 需要额外安装<br>• 社区较小 | 免费 | ⭐⭐⭐⭐ |
| **手动脚本** | • 完全控制<br>• 无依赖<br>• 性能最好 | • 需要人工分析<br>• 维护成本高<br>• 页面变化需更新 | 免费 | ⭐⭐⭐ |

---

## 🚀 推荐方案

### 方案 1：Playwright MCP（最佳）

**为什么最好？**
1. **视觉理解**：LLM 可以看到页面截图，像人类一样理解界面
2. **自动推理**：LLM 可以自动推断元素位置和选择器
3. **容错性强**：即使页面结构变化，LLM 也能适应
4. **无需维护**：不需要手动更新选择器

**使用示例**：
```python
# 用户只需要说：
"测试 https://business.gemini.google/ 的登录功能，使用邮箱 test@example.com"

# LLM 自动执行：
1. playwright_navigate("https://business.gemini.google/")
2. playwright_screenshot() → 分析截图
3. playwright_fill("input[type='email']", "test@example.com")
4. playwright_click("button:has-text('Continue')")
5. playwright_screenshot() → 验证结果
6. 生成测试报告
```

**安装**：
```bash
# 安装 Playwright MCP Server
npm install -g @executeautomation/mcp-playwright

# 配置 MCP
# 在 claude_desktop_config.json 中添加：
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["-y", "@executeautomation/mcp-playwright"]
    }
  }
}
```

**资源**：
- GitHub: https://github.com/executeautomation/mcp-playwright
- 文档: https://modelcontextprotocol.io/

---

### 方案 2：Browser Use（开源首选）

**特点**：
- 专门为 LLM 设计的浏览器自动化框架
- 支持多种 LLM（Claude, GPT-4, Gemini）
- 自动处理页面交互

**使用示例**：
```python
from browser_use import Agent
from langchain_anthropic import ChatAnthropic

llm = ChatAnthropic(model="claude-3-5-sonnet-20241022")
agent = Agent(
    task="测试 Gemini Business 登录功能",
    llm=llm,
)

result = agent.run()
```

**安装**：
```bash
pip install browser-use
```

**资源**：
- GitHub: https://github.com/browser-use/browser-use
- 文档: https://docs.browser-use.com/

---

### 方案 3：Computer Use API（Anthropic）

**特点**：
- Claude 直接控制计算机
- 可以看屏幕截图并操作
- 适合复杂交互场景

**使用示例**：
```python
import anthropic

client = anthropic.Anthropic()
response = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=1024,
    tools=[
        {
            "type": "computer_20241022",
            "name": "computer",
            "display_width_px": 1280,
            "display_height_px": 800,
        }
    ],
    messages=[
        {
            "role": "user",
            "content": "测试 https://business.gemini.google/ 的登录功能"
        }
    ],
)
```

**资源**：
- 文档: https://docs.anthropic.com/en/docs/build-with-claude/computer-use

---

### 方案 4：手动脚本（当前使用）

**当前项目使用的方法**：
```python
from DrissionPage import ChromiumPage

page = ChromiumPage()
page.get("https://business.gemini.google/")

# 手动编写选择器
email_input = page.ele("css:input[name='loginHint']")
email_input.input("test@example.com")

continue_btn = page.ele("tag:button")
continue_btn.click()
```

**优点**：
- 完全控制
- 性能最好
- 无需额外依赖

**缺点**：
- 需要人工分析页面
- 页面变化需要更新代码
- 维护成本高

---

## 📝 测试脚本模板

### 完整测试流程
```python
# -*- coding: utf-8 -*-
"""Gemini Business 登录测试"""
import time
from DrissionPage import ChromiumPage, ChromiumOptions

def test_gemini_login(email: str):
    """测试 Gemini Business 登录流程"""
    
    # 配置浏览器
    options = ChromiumOptions()
    options.set_argument("--incognito")
    options.set_argument("--no-sandbox")
    options.set_argument("--lang=zh-CN")
    options.auto_port()
    
    page = ChromiumPage(options)
    
    try:
        # Step 1: 访问首页
        print("Step 1: 访问首页")
        page.get("https://business.gemini.google/", timeout=60)
        time.sleep(8)
        print(f"当前 URL: {page.url}")
        
        # Step 2: 输入邮箱
        print("\nStep 2: 输入邮箱")
        email_input = page.ele("css:input[name='loginHint']", timeout=5)
        if not email_input:
            raise Exception("未找到邮箱输入框")
        
        email_input.input(email, clear=True)
        print(f"已输入邮箱: {email}")
        time.sleep(2)
        
        # Step 3: 点击继续按钮
        print("\nStep 3: 点击继续按钮")
        buttons = page.eles("tag:button")
        for btn in buttons:
            if btn.text and '继续' in btn.text:
                btn.click()
                print(f"已点击按钮: {btn.text}")
                break
        time.sleep(8)
        
        # Step 4: 等待验证码输入框
        print("\nStep 4: 等待验证码输入框")
        code_input = page.ele("css:input[jsname='ovqh0b']", timeout=10)
        if not code_input:
            raise Exception("未找到验证码输入框")
        
        print("✅ 找到验证码输入框")
        print(f"  type: {code_input.attr('type')}")
        print(f"  name: {code_input.attr('name')}")
        print(f"  jsname: {code_input.attr('jsname')}")
        
        # Step 5: 输入测试验证码
        print("\nStep 5: 输入测试验证码")
        code_input.input("123456", clear=True)
        print("已输入验证码: 123456")
        time.sleep(2)
        
        # Step 6: 查找提交按钮
        print("\nStep 6: 查找提交按钮")
        buttons = page.eles("tag:button")
        submit_btn = None
        for btn in buttons:
            text = btn.text or ''
            if '验证' in text and '重新' not in text:
                submit_btn = btn
                print(f"找到提交按钮: {text}")
                break
        
        if submit_btn:
            submit_btn.click()
            print("已点击提交按钮")
            time.sleep(5)
        
        # Step 7: 查找重新发送按钮
        print("\nStep 7: 查找重新发送按钮")
        buttons = page.eles("tag:button")
        for btn in buttons:
            text = btn.text or ''
            if '重新发送' in text:
                print(f"找到重新发送按钮: {text}")
                print(f"  aria-label: {btn.attr('aria-label')}")
                print(f"  jsname: {btn.attr('jsname')}")
                break
        
        print("\n✅ 测试完成")
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        input("按 Enter 键关闭浏览器...")
        page.quit()

if __name__ == "__main__":
    test_gemini_login("test@example.com")
```

---

## 🔧 代码优化建议

### 当前代码中需要更新的部分

#### 1. `_find_verify_button()` 方法
```python
# 当前代码（第 505 行）
def _find_verify_button(self, page):
    """查找验证按钮（排除重新发送按钮）"""
    try:
        buttons = page.eles("tag:button")
        for btn in buttons:
            text = (btn.text or "").strip().lower()
            if (
                text
                and "重新" not in text
                and "发送" not in text
                and "resend" not in text
                and "send" not in text
            ):
                return btn
    except Exception:
        pass
    return None

# 建议优化为：
def _find_verify_button(self, page):
    """查找验证按钮（排除重新发送按钮）"""
    try:
        # 方法1: 通过 jsname 直接查找
        verify_btn = page.ele("css:button[jsname='XooR8e']", timeout=2)
        if verify_btn:
            return verify_btn
        
        # 方法2: 通过文本查找
        buttons = page.eles("tag:button")
        for btn in buttons:
            text = (btn.text or "").strip()
            aria_label = (btn.attr('aria-label') or "").strip()
            
            # 匹配"验证"但排除"重新发送"
            if ('验证' in text or 'Verify' in text or 'Submit' in text) and \
               '重新' not in text and 'resend' not in text.lower():
                return btn
    except Exception:
        pass
    return None
```

#### 2. `_click_resend_code_button()` 方法
```python
# 当前代码（第 523 行）
def _click_resend_code_button(self, page) -> bool:
    """点击重新发送验证码按钮"""
    time.sleep(2)
    
    try:
        buttons = page.eles("tag:button")
        for btn in buttons:
            text = (btn.text or "").strip().lower()
            if text and ("重新" in text or "resend" in text):
                try:
                    self._log("info", f"found resend button: {text}")
                    btn.click()
                    time.sleep(2)
                    return True
                except Exception:
                    pass
    except Exception:
        pass
    
    return False

# 建议优化为：
def _click_resend_code_button(self, page) -> bool:
    """点击重新发送验证码按钮"""
    time.sleep(2)
    
    try:
        # 方法1: 通过 jsname 直接查找
        resend_btn = page.ele("css:button[jsname='WGPTvf']", timeout=2)
        if resend_btn:
            self._log("info", f"✅ 找到重新发送按钮: {resend_btn.text}")
            resend_btn.click()
            time.sleep(2)
            return True
        
        # 方法2: 通过文本查找
        buttons = page.eles("tag:button")
        for btn in buttons:
            text = (btn.text or "").strip()
            aria_label = (btn.attr('aria-label') or "").strip()
            
            if '重新发送' in text or 'resend' in text.lower() or \
               '重新发送' in aria_label or 'resend' in aria_label.lower():
                self._log("info", f"✅ 找到重新发送按钮: {text}")
                btn.click()
                time.sleep(2)
                return True
    except Exception as e:
        self._log("warning", f"⚠️ 点击重新发送按钮失败: {e}")
    
    return False
```

---

## 📚 相关资源

### 官方文档
- **Playwright**: https://playwright.dev/
- **Puppeteer**: https://pptr.dev/
- **Selenium**: https://www.selenium.dev/
- **DrissionPage**: https://drissionpage.cn/

### MCP 相关
- **Model Context Protocol**: https://modelcontextprotocol.io/
- **Playwright MCP**: https://github.com/executeautomation/mcp-playwright
- **MCP Servers List**: https://github.com/modelcontextprotocol/servers

### LLM 浏览器自动化
- **Browser Use**: https://github.com/browser-use/browser-use
- **Anthropic Computer Use**: https://docs.anthropic.com/en/docs/build-with-claude/computer-use
- **LangChain Agents**: https://python.langchain.com/docs/modules/agents/

### 测试框架
- **Pytest**: https://docs.pytest.org/
- **Robot Framework**: https://robotframework.org/
- **Cypress**: https://www.cypress.io/

---

## 💡 总结

### 当前项目状态
- ✅ 验证码输入框可以被找到
- ✅ 提交按钮可以被找到
- ✅ 重新发送按钮可以被找到
- ⚠️ 代码中的选择器可以优化（使用 jsname）

### 下一步建议
1. **短期**：优化现有代码，使用更精确的选择器（jsname）
2. **中期**：考虑集成 Browser Use 框架
3. **长期**：迁移到 Playwright MCP，实现完全自动化

### 最佳实践
- 优先使用 **jsname** 或 **aria-label** 作为选择器（更稳定）
- 添加详细的日志输出（便于调试）
- 使用多种选择器作为备选（提高容错性）
- 定期更新选择器（应对页面变化）
