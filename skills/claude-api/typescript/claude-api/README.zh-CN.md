# Claude API — TypeScript

> [English](./README.md) | **中文**

| 功能 | 命名空间 | 关键类型 / 调用 |
|---|---|---|
| 用户画像 | beta | `client.beta.userProfiles.create(...)` / `.retrieve(id)` / `.list()`。把返回的 profile id 传给 `client.beta.messages.create`。需要 beta 头 —— 请查看 SDK 的 beta-headers 参考以获取当前标志。 |

## 安装

```bash
npm install @anthropic-ai/sdk
```

> **读取本地文件（ESM）：** 在 ES 模块中 `__dirname` 和 `__filename` **未定义** —— 使用任一者都会在运行时抛出 `ReferenceError: __dirname is not defined`。相对当前工作目录读取时，直接传相对路径（`fs.readFileSync("./sample.png")`）。相对脚本路径时，从 `import.meta.url` 推导目录：`const here = path.dirname(fileURLToPath(import.meta.url))`。永远不要在 ESM `.ts` 文件里写 `path.join(__dirname, …)`。

## 初始化客户端

```typescript
import Anthropic from "@anthropic-ai/sdk";

// Default — resolves credentials from the environment:
// ANTHROPIC_API_KEY, or ANTHROPIC_AUTH_TOKEN, or an `ant auth login` profile.
// Prefer this for local dev; don't hardcode a key.
const client = new Anthropic();

// Explicit API key (only when you must inject a specific key)
const client = new Anthropic({ apiKey: "your-api-key" });
```

---

## 基础消息请求

```typescript
const response = await client.messages.create({
  model: "claude-opus-5",
  max_tokens: 16000,
  messages: [{ role: "user", content: "What is the capital of France?" }],
});
// response.content is ContentBlock[] — a discriminated union. Narrow by .type
// before accessing .text (TypeScript will error on content[0].text without this).
for (const block of response.content) {
  if (block.type === "text") {
    console.log(block.text);
  }
}
```

---

## 系统提示

```typescript
const response = await client.messages.create({
  model: "claude-opus-5",
  max_tokens: 16000,
  system:
    "You are a helpful coding assistant. Always provide examples in Python.",
  messages: [{ role: "user", content: "How do I read a JSON file?" }],
});
```

### 对话中途的系统消息（受模型支持限制）

对于对话中途到达的操作员指令（模式切换、注入状态），请向 `messages` 追加 `{role: "system", ...}`，而不是修改顶层 `system` —— 这样能保留已缓存的前缀，并带有操作员权限。必须跟在用户消息（或以服务端工具调用结束的 `assistant` 消息）之后，且必须是 `messages` 的最后一项，或后面再跟一轮 `assistant`；不能是 `messages[0]`。不支持的模型会返回 400（`role 'system' is not supported on this model`）。何时用这种方式、何时用顶层 `system`，见 `shared/prompt-caching.md`。

```typescript
// No beta header needed — use regular client.messages.create.
const response = await client.messages.create({
  model: MODEL_ID, // must support mid-conversation system messages
  max_tokens: 16000,
  system: [
    { type: "text", text: STABLE_SYSTEM, cache_control: { type: "ephemeral" } },
  ],
  messages: [
    ...history,
    { role: "user", content: userMessage },
    { role: "system", content: "Terse mode enabled — keep responses under 40 words." },
  ],
});
```

---

## 视觉（图片）

### URL

```typescript
const response = await client.messages.create({
  model: "claude-opus-5",
  max_tokens: 16000,
  messages: [
    {
      role: "user",
      content: [
        {
          type: "image",
          source: { type: "url", url: "https://example.com/image.png" },
        },
        { type: "text", text: "Describe this image" },
      ],
    },
  ],
});
```

### Base64

```typescript
import fs from "fs";

const imageData = fs.readFileSync("image.png").toString("base64");

const response = await client.messages.create({
  model: "claude-opus-5",
  max_tokens: 16000,
  messages: [
    {
      role: "user",
      content: [
        {
          type: "image",
          source: { type: "base64", media_type: "image/png", data: imageData },
        },
        { type: "text", text: "What's in this image?" },
      ],
    },
  ],
});
```

---

## 提示缓存

**缓存按前缀匹配** —— 前缀中任意字节变化都会使之后的全部缓存失效。关于放置模式、架构建议（冻结系统提示、确定性工具顺序、易变内容放哪里）以及静默失效审计清单，请阅读 `shared/prompt-caching.md`。

### 自动缓存（推荐）

使用顶层 `cache_control` 即可自动缓存请求中最后一个可缓存块：

```typescript
const response = await client.messages.create({
  model: "claude-opus-5",
  max_tokens: 16000,
  cache_control: { type: "ephemeral" }, // auto-caches the last cacheable block
  system: "You are an expert on this large document...",
  messages: [{ role: "user", content: "Summarize the key points" }],
});
```

### 手动缓存控制

需要细粒度控制时，给特定内容块添加 `cache_control`：

```typescript
const response = await client.messages.create({
  model: "claude-opus-5",
  max_tokens: 16000,
  system: [
    {
      type: "text",
      text: "You are an expert on this large document...",
      cache_control: { type: "ephemeral" }, // default TTL is 5 minutes
    },
  ],
  messages: [{ role: "user", content: "Summarize the key points" }],
});

// With explicit TTL (time-to-live)
const response2 = await client.messages.create({
  model: "claude-opus-5",
  max_tokens: 16000,
  system: [
    {
      type: "text",
      text: "You are an expert on this large document...",
      cache_control: { type: "ephemeral", ttl: "1h" }, // 1 hour TTL
    },
  ],
  messages: [{ role: "user", content: "Summarize the key points" }],
});
```

### 验证缓存命中

```typescript
console.log(response.usage.cache_creation_input_tokens); // tokens written to cache (~1.25x cost)
console.log(response.usage.cache_read_input_tokens);     // tokens served from cache (~0.1x cost)
console.log(response.usage.input_tokens);                // uncached tokens (full cost)
```

若在前缀相同的重复请求中 `cache_read_input_tokens` 始终为零，说明存在静默失效因素 —— 例如系统提示里的 `Date.now()` 或 UUID、非确定性的键顺序，或变化的工具集。完整审计表见 `shared/prompt-caching.md`。

---

## 扩展思考

> **Fable 5、Claude Opus 5、Opus 4.8、Opus 4.7、Opus 4.6 和 Sonnet 4.6：** 使用自适应思考。`budget_tokens` 在 Fable 5、Claude Opus 5、Opus 4.8 和 4.7 上已移除（发送会返回 400）；在 Opus 4.6 和 Sonnet 4.6 上已弃用。
> **Claude Opus 5：** 默认开启思考 —— 省略 `thinking` 会走自适应（等价于 `{ type: "adaptive" }`），这与 Opus 4.8/4.7 不同（后者省略即表示不思考）。`{ type: "disabled" }` 仅在 effort 为 `high` 或更低时接受；与 `xhigh`/`max` 搭配会返回 400。
> **较旧模型：** 使用 `thinking: {type: "enabled", budget_tokens: N}`（必须小于 `max_tokens`，最小 1024）。

```typescript
// Fable 5 / Claude Opus 5 / Opus 4.8 / 4.7 / 4.6: adaptive thinking (recommended)
const response = await client.messages.create({
  model: "claude-opus-5",
  max_tokens: 16000,
  thinking: { type: "adaptive", display: "summarized" }, // display opt-in: default is omitted (empty thinking text) on Fable 5 / Mythos 5 / Claude Opus 5 / Opus 4.8 / 4.7
  output_config: { effort: "high" }, // low | medium | high | xhigh | max
  messages: [
    { role: "user", content: "Solve this math problem step by step..." },
  ],
});

for (const block of response.content) {
  if (block.type === "thinking") {
    console.log("Thinking:", block.thinking);
  } else if (block.type === "text") {
    console.log("Response:", block.text);
  }
}
```

---

## 错误处理

使用 SDK 的类型化异常类 —— 不要用字符串匹配检查错误消息：

```typescript
import Anthropic from "@anthropic-ai/sdk";

try {
  const response = await client.messages.create({...});
} catch (error) {
  if (error instanceof Anthropic.BadRequestError) {
    console.error("Bad request:", error.message);
  } else if (error instanceof Anthropic.AuthenticationError) {
    console.error("Invalid API key");
  } else if (error instanceof Anthropic.RateLimitError) {
    console.error("Rate limited - retry later");
  } else if (error instanceof Anthropic.APIError) {
    console.error(`API error ${error.status}:`, error.message);
  }
}
```

所有类都继承带有类型化 `status` 字段的 `Anthropic.APIError`。从最具体到最宽泛依次检查。完整错误码参考见 [shared/error-codes.md](../../shared/error-codes.md)。

---

## 多轮对话

API 是无状态的 —— 每次都要发送完整对话历史。用 `Anthropic.MessageParam[]` 为消息数组标注类型：

```typescript
const messages: Anthropic.MessageParam[] = [
  { role: "user", content: "My name is Alice." },
  { role: "assistant", content: "Hello Alice! Nice to meet you." },
  { role: "user", content: "What's my name?" },
];

const response = await client.messages.create({
  model: "claude-opus-5",
  max_tokens: 16000,
  messages: messages,
});
```

**规则：**

- 允许连续相同角色的消息 —— API 会把它们合并为同一轮
- 第一条消息必须是 `user`
- 所有 API 数据结构都使用 SDK 类型（`Anthropic.MessageParam`、`Anthropic.Message`、`Anthropic.Tool` 等）—— 不要重新定义等价接口

---

### 压缩（长对话）

> **Beta，Fable 5、Claude Opus 5、Opus 4.8、Opus 4.7、Opus 4.6 和 Sonnet 4.6。** 当对话接近 200K 上下文窗口时，压缩会在服务端自动总结更早的上下文。API 会返回 `compaction` 块；后续请求必须把它传回去 —— 追加 `response.content`，而不是只追加文本。

```typescript
import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic();
const messages: Anthropic.Beta.BetaMessageParam[] = [];

async function chat(userMessage: string): Promise<string> {
  messages.push({ role: "user", content: userMessage });

  const response = await client.beta.messages.create({
    betas: ["compact-2026-01-12"],
    model: "claude-opus-5",
    max_tokens: 16000,
    messages,
    context_management: {
      edits: [{ type: "compact_20260112" }],
    },
  });

  // Append full content — compaction blocks must be preserved
  messages.push({ role: "assistant", content: response.content });

  const textBlock = response.content.find(
    (b): b is Anthropic.Beta.BetaTextBlock => b.type === "text",
  );
  return textBlock?.text ?? "";
}

// Compaction triggers automatically when context grows large
console.log(await chat("Help me build a Python web scraper"));
console.log(await chat("Add support for JavaScript-rendered pages"));
console.log(await chat("Now add rate limiting and error handling"));
```

---

## 停止原因

响应中的 `stop_reason` 字段说明模型为何停止生成：

| 值           | 含义                                                         |
| --------------- | --------------------------------------------------------------- |
| `end_turn`      | Claude 自然结束了回复                          |
| `max_tokens`    | 达到 `max_tokens` 上限 —— 请增大该值或使用流式输出       |
| `stop_sequence` | 命中自定义停止序列                                      |
| `tool_use`      | Claude 想调用工具 —— 执行后继续           |
| `pause_turn`    | 模型暂停，可恢复（智能体流程）                 |
| `refusal`       | Claude 因安全原因拒绝 —— 查看 `stop_details`        |

### 结构化停止详情

当 `stop_reason` 为 `"refusal"` 时，响应会包含带有结构化拒绝信息的 `stop_details` 对象：

```typescript
if (response.stop_reason === "refusal" && response.stop_details) {
  console.log(`Category: ${response.stop_details.category}`); // e.g. "cyber", "bio", "reasoning_extraction", "frontier_llm", or null — see docs for the full set
  console.log(`Explanation: ${response.stop_details.explanation}`);
}
```

### 拒绝回退（Claude Fable 5）—— 默认建议选择加入

回退是**选择加入**的：没有它时，被拒绝的请求会直接停止。在 `claude-fable-5` 代码中默认加入服务端 `fallbacks` 参数 —— 策略拒绝时，API 会在同一次调用内用回退模型重新执行同一请求。若在产生任何输出前被拒绝则不计费（流式中途拒绝会按已流出的部分计费）；救援请求按回退模型自身费率计费，缓存重计价会自动应用。

```typescript
const response = await client.beta.messages.create({
  model: "claude-fable-5",
  max_tokens: 16000,
  betas: ["server-side-fallback-2026-06-01"],
  fallbacks: [{ model: "claude-opus-4-8" }],
  messages: [{ role: "user", content: "..." }],
});

// Switch points: one fallback block per model that ran and declined this turn
for (const block of response.content) {
  if (block.type === "fallback") {
    console.log(`${block.from.model} declined; ${block.to.model} continued`);
  }
}

// Served-by signal — covers sticky turns, which carry no fallback block.
// Pair with stop_reason: the fallback model can itself refuse.
const fallbackRan = (response.usage.iterations ?? []).some(
  (entry) => entry.type === "fallback_message",
);
if (fallbackRan && response.stop_reason !== "refusal") {
  console.log(`Served by ${response.model}`);
}
```

最终响应上的 `stop_reason: "refusal"` 表示整条链路都拒绝了。该数组形式的请求头必须恰好是 `server-side-fallback-2026-06-01`；较新的标量形式 `fallbacks: "default"` 则使用 `server-side-fallback-2026-07-01`（见 `shared/model-migration.md` → Migrating to Claude Opus 5 → New API features），把头与另一种形式混用会返回 400。该参数在 Batches API 上会被拒绝，且在 Amazon Bedrock、Vertex AI 和 Microsoft Foundry 上不可用 —— 在这些平台上请改为在客户端注册客户端侧的 `betaRefusalFallbackMiddleware`。完整语义（粘性路由、计费、流式、回传回退轮次）：`shared/model-migration.md` → Migrating to Claude Fable 5 → `refusal` stop reason。

---

## 成本优化策略

### 1. 对重复上下文使用提示缓存

```typescript
// Automatic caching (simplest — caches the last cacheable block)
const response = await client.messages.create({
  model: "claude-opus-5",
  max_tokens: 16000,
  cache_control: { type: "ephemeral" },
  system: largeDocumentText, // e.g., 50KB of context
  messages: [{ role: "user", content: "Summarize the key points" }],
});

// First request: full cost
// Subsequent requests: ~90% cheaper for cached portion
```

### 2. 请求前先做 Token 计数

```typescript
const countResponse = await client.messages.countTokens({
  model: "claude-opus-5",
  messages: messages,
  system: system,
});

const estimatedInputCost = countResponse.input_tokens * 0.000005; // $5/1M tokens
console.log(`Estimated input cost: $${estimatedInputCost.toFixed(4)}`);
```
