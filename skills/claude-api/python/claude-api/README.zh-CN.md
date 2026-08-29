# Claude API — Python

> [English](./README.md) | **中文**

## 安装

```bash
pip install anthropic
```

## 初始化客户端

```python
import anthropic

# Default — resolves credentials from the environment:
# ANTHROPIC_API_KEY, or ANTHROPIC_AUTH_TOKEN, or an `ant auth login` profile.
# Prefer this for local dev; don't hardcode a key.
client = anthropic.Anthropic()

# Explicit API key (only when you must inject a specific key)
client = anthropic.Anthropic(api_key="your-api-key")

# Async client
async_client = anthropic.AsyncAnthropic()
```

---

## 客户端配置

### 单次请求覆盖

使用 `with_options()` 可在不修改客户端本身的情况下，覆盖单次调用的设置：

```python
client.with_options(timeout=5.0, max_retries=5).messages.create(
    model="claude-opus-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}],
)
```

### 超时

默认请求超时为 10 分钟。可传入浮点数（秒）或 `anthropic.Timeout` 做更细粒度控制。超时后 SDK 会抛出 `anthropic.APITimeoutError`（并按 `max_retries` 重试）。

```python
client = anthropic.Anthropic(timeout=20.0)
client = anthropic.Anthropic(
    timeout=anthropic.Timeout(60.0, read=5.0, write=10.0, connect=2.0),
)
```

`anthropic` 1.x 基于 [`httpx2`](https://pypi.org/project/httpx2/)，而不是 `httpx`。`anthropic.Timeout` 即 `httpx2.Timeout`；若自行导入 HTTP 库，请写 `import httpx2 as httpx` —— 来自 `httpx` 包的对象（`httpx.Timeout`、`httpx.Client`、transport、limits）会被拒绝，或在请求时失败。既有 `httpx` 时代代码见 [v1 迁移指南](https://github.com/anthropics/anthropic-sdk-python/blob/main/MIGRATION.md) 以及 `/claude-api upgrade python`。

### 重试

SDK 会以指数退避自动重试连接错误、408、409、429 以及 ≥500（默认重试 2 次）。可在客户端上或通过 `with_options()` 设置 `max_retries`；`max_retries=0` 表示禁用。

### 异步性能（aiohttp 后端）

高并发异步负载下，可安装 `anthropic[aiohttp]` 并传入 `DefaultAioHttpClient`，替代默认的 httpx2 后端：

```python
from anthropic import AsyncAnthropic, DefaultAioHttpClient

async with AsyncAnthropic(http_client=DefaultAioHttpClient()) as client:
    ...
```

### 自定义 HTTP 客户端（代理、基础 URL）

请使用 `DefaultHttpxClient` / `DefaultAsyncHttpxClient` —— 不要直接用裸的 `httpx2.Client`（更不要用 `httpx` 包里的客户端）—— 这样才能保留 SDK 默认的超时和连接限制：

```python
from anthropic import Anthropic, DefaultHttpxClient

client = Anthropic(
    base_url="http://my.test.server.example.com:8083",  # or ANTHROPIC_BASE_URL env var
    http_client=DefaultHttpxClient(proxy="http://my.test.proxy.example.com"),
)
```

### 日志

设置 `ANTHROPIC_LOG=debug`（或 `info`）可通过标准 `logging` 模块启用 SDK 日志。

---

## 基础消息请求

```python
response = client.messages.create(
    model="claude-opus-5",
    max_tokens=16000,
    messages=[
        {"role": "user", "content": "What is the capital of France?"}
    ]
)
# response.content is a list of content block objects (TextBlock, ThinkingBlock,
# ToolUseBlock, ...). Check .type before accessing .text.
for block in response.content:
    if block.type == "text":
        print(block.text)
```

---

## 系统提示

```python
response = client.messages.create(
    model="claude-opus-5",
    max_tokens=16000,
    system="You are a helpful coding assistant. Always provide examples in Python.",
    messages=[{"role": "user", "content": "How do I read a JSON file?"}]
)
```

### 对话中途的系统消息（受模型支持限制）

对于对话中途到达的操作员指令（模式切换、注入状态），请向 `messages` 追加 `{"role": "system", ...}`，而不是修改顶层 `system` —— 这样能保留已缓存的前缀，并带有操作员权限。必须跟在用户消息（或以服务端工具调用结束的 `assistant` 消息）之后，且必须是 `messages` 的最后一项，或后面再跟一轮 `assistant`；不能是 `messages[0]`。不支持的模型会返回 400（`role 'system' is not supported on this model`）。何时用这种方式、何时用顶层 `system`，见 `shared/prompt-caching.md`。

```python
response = client.messages.create(
    model=MODEL_ID,  # must support mid-conversation system messages
    max_tokens=16000,
    system=[{"type": "text", "text": STABLE_SYSTEM, "cache_control": {"type": "ephemeral"}}],
    messages=history + [
        {"role": "user", "content": user_message},
        {"role": "system", "content": "Terse mode enabled — keep responses under 40 words."},
    ],
)  # No beta header needed — use regular client.messages.create
```

---

## 视觉（图片）

### Base64

```python
import base64

with open("image.png", "rb") as f:
    image_data = base64.standard_b64encode(f.read()).decode("utf-8")

response = client.messages.create(
    model="claude-opus-5",
    max_tokens=16000,
    messages=[{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": image_data
                }
            },
            {"type": "text", "text": "What's in this image?"}
        ]
    }]
)
```

### URL

```python
response = client.messages.create(
    model="claude-opus-5",
    max_tokens=16000,
    messages=[{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "url",
                    "url": "https://example.com/image.png"
                }
            },
            {"type": "text", "text": "Describe this image"}
        ]
    }]
)
```

---

## 提示缓存

缓存大段上下文以降低成本（最高可节省约 90%）。**缓存按前缀匹配** —— 前缀中任意字节变化都会使之后的全部缓存失效。关于放置模式、架构建议（冻结系统提示、确定性工具顺序、易变内容放哪里）以及静默失效审计清单，请阅读 `shared/prompt-caching.md`。

### 自动缓存（推荐）

使用顶层 `cache_control` 即可自动缓存请求中最后一个可缓存块，无需给各个内容块单独标注：

```python
response = client.messages.create(
    model="claude-opus-5",
    max_tokens=16000,
    cache_control={"type": "ephemeral"},  # auto-caches the last cacheable block
    system="You are an expert on this large document...",
    messages=[{"role": "user", "content": "Summarize the key points"}]
)
```

### 手动缓存控制

需要细粒度控制时，给特定内容块添加 `cache_control`：

```python
response = client.messages.create(
    model="claude-opus-5",
    max_tokens=16000,
    system=[{
        "type": "text",
        "text": "You are an expert on this large document...",
        "cache_control": {"type": "ephemeral"}  # default TTL is 5 minutes
    }],
    messages=[{"role": "user", "content": "Summarize the key points"}]
)

# With explicit TTL (time-to-live)
response = client.messages.create(
    model="claude-opus-5",
    max_tokens=16000,
    system=[{
        "type": "text",
        "text": "You are an expert on this large document...",
        "cache_control": {"type": "ephemeral", "ttl": "1h"}  # 1 hour TTL
    }],
    messages=[{"role": "user", "content": "Summarize the key points"}]
)
```

### 验证缓存命中

```python
print(response.usage.cache_creation_input_tokens)  # tokens written to cache (~1.25x cost)
print(response.usage.cache_read_input_tokens)      # tokens served from cache (~0.1x cost)
print(response.usage.input_tokens)                 # uncached tokens (full cost)
```

若在前缀相同的重复请求中 `cache_read_input_tokens` 始终为零，说明存在静默失效因素 —— 例如系统提示里的 `datetime.now()` 或 UUID、未排序的 `json.dumps()`，或变化的工具集。完整审计表见 `shared/prompt-caching.md`。

---

## 扩展思考

> **Fable 5、Claude Opus 5、Opus 4.8、Opus 4.7、Opus 4.6 和 Sonnet 4.6：** 使用自适应思考。`budget_tokens` 在 Fable 5、Claude Opus 5、Opus 4.8 和 4.7 上已移除（发送会返回 400）；在 Opus 4.6 和 Sonnet 4.6 上已弃用。
> **Claude Opus 5：** 默认开启思考 —— 省略 `thinking` 会走自适应（等价于 `{"type": "adaptive"}`），这与 Opus 4.8/4.7 不同（后者省略即表示不思考）。`{"type": "disabled"}` 仅在 effort 为 `high` 或更低时接受；与 `xhigh`/`max` 搭配会返回 400。
> **较旧模型：** 使用 `thinking: {type: "enabled", budget_tokens: N}`（必须小于 `max_tokens`，最小 1024）。

```python
# Fable 5 / Claude Opus 5 / Opus 4.8 / 4.7 / 4.6: adaptive thinking (recommended)
response = client.messages.create(
    model="claude-opus-5",
    max_tokens=16000,
    thinking={"type": "adaptive", "display": "summarized"},  # display opt-in: default is omitted (empty thinking text) on Fable 5 / Mythos 5 / Claude Opus 5 / Opus 4.8 / 4.7
    output_config={"effort": "high"},  # low | medium | high | xhigh | max
    messages=[{"role": "user", "content": "Solve this step by step..."}]
)

# Access thinking and response
for block in response.content:
    if block.type == "thinking":
        print(f"Thinking: {block.thinking}")
    elif block.type == "text":
        print(f"Response: {block.text}")
```

---

## 错误处理

```python
import anthropic

try:
    response = client.messages.create(...)
except anthropic.BadRequestError as e:
    print(f"Bad request: {e.message}")
except anthropic.AuthenticationError:
    print("Invalid API key")
except anthropic.PermissionDeniedError:
    print("API key lacks required permissions")
except anthropic.NotFoundError:
    print("Invalid model or endpoint")
except anthropic.RateLimitError as e:
    retry_after = int(e.response.headers.get("retry-after", "60"))
    print(f"Rate limited. Retry after {retry_after}s.")
except anthropic.APIStatusError as e:
    if e.status_code >= 500:
        print(f"Server error ({e.status_code}). Retry later.")
    else:
        print(f"API error: {e.message}")
except anthropic.APIConnectionError:
    print("Network error. Check internet connection.")
```

---

## 响应辅助方法

每个响应对象都暴露 `_request_id`（来自 `request-id` 响应头）—— 向 Anthropic 报告故障时请记录它。尽管有下划线前缀，该属性是公开的。

```python
message = client.messages.create(...)
print(message._request_id)       # req_018EeWyXxfu5pfWkrYcMdjWG
print(message.to_json())          # serialize the Pydantic model
print(message.to_dict())          # plain dict
```

要访问原始响应头或其他元数据，使用 `.with_raw_response`：

```python
raw = client.messages.with_raw_response.create(
    model="claude-opus-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}],
)
print(raw.headers.get("request-id"))
message = raw.parse()  # the Message object messages.create() would have returned
```

---

## 多轮对话

API 是无状态的 —— 每次都要发送完整对话历史。

```python
class ConversationManager:
    """Manage multi-turn conversations with the Claude API."""

    def __init__(self, client: anthropic.Anthropic, model: str, system: str = None):
        self.client = client
        self.model = model
        self.system = system
        self.messages = []

    def send(self, user_message: str, **kwargs) -> str:
        """Send a message and get a response."""
        self.messages.append({"role": "user", "content": user_message})

        response = self.client.messages.create(
            model=self.model,
            max_tokens=kwargs.get("max_tokens", 16000),
            system=self.system,
            messages=self.messages,
            **kwargs
        )

        assistant_message = next(
            (b.text for b in response.content if b.type == "text"), ""
        )
        self.messages.append({"role": "assistant", "content": assistant_message})

        return assistant_message

# Usage
conversation = ConversationManager(
    client=anthropic.Anthropic(),
    model="claude-opus-5",
    system="You are a helpful assistant."
)

response1 = conversation.send("My name is Alice.")
response2 = conversation.send("What's my name?")  # Claude remembers "Alice"
```

**规则：**

- 允许连续相同角色的消息 —— API 会把它们合并为同一轮
- 第一条消息必须是 `user`
- 在支持的模型上，对话中途允许 `role: "system"` 消息（无需 beta 头）—— 见上文「对话中途的系统消息」

---

### 压缩（长对话）

> **Beta，Fable 5、Claude Opus 5、Opus 4.8、Opus 4.7、Opus 4.6 和 Sonnet 4.6。** 当对话接近 200K 上下文窗口时，压缩会在服务端自动总结更早的上下文。API 会返回 `compaction` 块；后续请求必须把它传回去 —— 追加 `response.content`，而不是只追加文本。

```python
import anthropic

client = anthropic.Anthropic()
messages = []

def chat(user_message: str) -> str:
    messages.append({"role": "user", "content": user_message})

    response = client.beta.messages.create(
        betas=["compact-2026-01-12"],
        model="claude-opus-5",
        max_tokens=16000,
        messages=messages,
        context_management={
            "edits": [{"type": "compact_20260112"}]
        }
    )

    # Append full content — compaction blocks must be preserved
    messages.append({"role": "assistant", "content": response.content})

    return next(block.text for block in response.content if block.type == "text")

# Compaction triggers automatically when context grows large
print(chat("Help me build a Python web scraper"))
print(chat("Add support for JavaScript-rendered pages"))
print(chat("Now add rate limiting and error handling"))
```

---

## 停止原因

响应中的 `stop_reason` 字段说明模型为何停止生成：

| 值 | 含义 |
|-------|---------|
| `end_turn` | Claude 自然结束了回复 |
| `max_tokens` | 达到 `max_tokens` 上限 —— 请增大该值或使用流式输出 |
| `stop_sequence` | 命中自定义停止序列 |
| `tool_use` | Claude 想调用工具 —— 执行后继续 |
| `pause_turn` | 模型暂停，可恢复（智能体流程） |
| `refusal` | Claude 因安全原因拒绝 —— 查看 `stop_details` |

### 结构化停止详情

当 `stop_reason` 为 `"refusal"` 时，响应会包含带有结构化拒绝信息的 `stop_details` 对象：

```python
if response.stop_reason == "refusal" and response.stop_details:
    print(f"Category: {response.stop_details.category}")   # e.g. "cyber", "bio", "reasoning_extraction", "frontier_llm", or None — see docs for the full set
    print(f"Explanation: {response.stop_details.explanation}")
```

### 拒绝回退（Claude Fable 5）—— 默认建议选择加入

回退是**选择加入**的：没有它时，被拒绝的请求会直接停止。在 `claude-fable-5` 代码中默认加入服务端 `fallbacks` 参数 —— 策略拒绝时，API 会在同一次调用内用回退模型重新执行同一请求。若在产生任何输出前被拒绝则不计费（流式中途拒绝会按已流出的部分计费）；救援请求按回退模型自身费率计费，缓存重计价会自动应用。

```python
response = client.beta.messages.create(
    model="claude-fable-5",
    max_tokens=16000,
    betas=["server-side-fallback-2026-06-01"],
    fallbacks=[{"model": "claude-opus-4-8"}],
    messages=[{"role": "user", "content": "..."}],
)

# Switch points: one fallback block per model that ran and declined this turn
for block in response.content:
    if block.type == "fallback":
        print(f"{block.from_.model} declined; {block.to.model} continued")

# Served-by signal — covers sticky turns, which carry no fallback block.
# Pair with stop_reason: the fallback model can itself refuse.
fallback_ran = any(
    entry.type == "fallback_message" for entry in response.usage.iterations or []
)
if fallback_ran and response.stop_reason != "refusal":
    print(f"Served by {response.model}")
```

最终响应上的 `stop_reason: "refusal"` 表示整条链路都拒绝了。该数组形式的请求头必须恰好是 `server-side-fallback-2026-06-01`；较新的标量形式 `fallbacks: "default"` 则使用 `server-side-fallback-2026-07-01`（见 `shared/model-migration.md` → Migrating to Claude Opus 5 → New API features），把头与另一种形式混用会返回 400。该参数在 Batches API 上会被拒绝，且在 Amazon Bedrock、Vertex AI 和 Microsoft Foundry 上不可用 —— 在这些平台上请改为在客户端注册客户端侧的 `BetaRefusalFallbackMiddleware`。完整语义（粘性路由、计费、流式、回传回退轮次）：`shared/model-migration.md` → Migrating to Claude Fable 5 → `refusal` stop reason。

---

## 成本优化策略

### 1. 对重复上下文使用提示缓存

```python
# Automatic caching (simplest — caches the last cacheable block)
response = client.messages.create(
    model="claude-opus-5",
    max_tokens=16000,
    cache_control={"type": "ephemeral"},
    system=large_document_text,  # e.g., 50KB of context
    messages=[{"role": "user", "content": "Summarize the key points"}]
)

# First request: full cost
# Subsequent requests: ~90% cheaper for cached portion
```

### 2. 选择合适的模型

```python
# Default to Opus for most tasks
response = client.messages.create(
    model="claude-opus-5",  # $5.00/$25.00 per 1M tokens
    max_tokens=16000,
    messages=[{"role": "user", "content": "Explain quantum computing"}]
)

# Use Sonnet for high-volume production workloads
standard_response = client.messages.create(
    model="claude-sonnet-5",  # $3.00/$15.00 per 1M tokens
    max_tokens=16000,
    messages=[{"role": "user", "content": "Summarize this document"}]
)

# Use Haiku only for simple, speed-critical tasks
simple_response = client.messages.create(
    model="claude-haiku-4-5",  # $1.00/$5.00 per 1M tokens
    max_tokens=256,
    messages=[{"role": "user", "content": "Classify this as positive or negative"}]
)
```

### 3. 请求前先做 Token 计数

```python
count_response = client.messages.count_tokens(
    model="claude-opus-5",
    messages=messages,
    system=system
)

estimated_input_cost = count_response.input_tokens * 0.000005  # $5/1M tokens
print(f"Estimated input cost: ${estimated_input_cost:.4f}")
```

---

## 指数退避重试

> **说明：** Anthropic SDK 会以指数退避自动重试限流（429）和服务器错误（5xx）。可用 `max_retries` 配置（默认：2）。仅在需要超出 SDK 能力的行为时，才自行实现重试逻辑。

```python
import time
import random
import anthropic

def call_with_retry(
    client: anthropic.Anthropic,
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    **kwargs
):
    """Call the API with exponential backoff retry."""
    last_exception = None

    for attempt in range(max_retries):
        try:
            return client.messages.create(**kwargs)
        except anthropic.RateLimitError as e:
            last_exception = e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                last_exception = e
            else:
                raise  # Client errors (4xx except 429) should not be retried

        delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
        print(f"Retry {attempt + 1}/{max_retries} after {delay:.1f}s")
        time.sleep(delay)

    raise last_exception
```
