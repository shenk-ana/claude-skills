# Claude API — Ruby

> [English](./README.md) | **中文**

> **说明：** Ruby SDK 支持 Claude API。可通过 `client.beta.messages.tool_runner()` 使用 beta 工具运行器。Agent SDK 目前尚未提供 Ruby 版本。

## 安装

```bash
gem install anthropic
```

## 初始化客户端

```ruby
require "anthropic"

# Default (uses ANTHROPIC_API_KEY env var)
client = Anthropic::Client.new

# Explicit API key
client = Anthropic::Client.new(api_key: "your-api-key")
```

---

## 基础消息请求

```ruby
message = client.messages.create(
  model: :"claude-opus-5",
  max_tokens: 16000,
  messages: [
    { role: "user", content: "What is the capital of France?" }
  ]
)
# content is an array of polymorphic block objects (TextBlock, ThinkingBlock,
# ToolUseBlock, ...). .type is a Symbol — compare with :text, not "text".
# .text raises NoMethodError on non-TextBlock entries.
message.content.each do |block|
  puts block.text if block.type == :text
end
```

---

## 扩展思考

> **Fable 5、Claude Opus 5、Opus 4.8、Opus 4.7、Opus 4.6 和 Sonnet 4.6：** 使用自适应思考。`budget_tokens` 在 Fable 5、Claude Opus 5、Opus 4.8 和 4.7 上已移除（发送会返回 400）；在 Opus 4.6 和 Sonnet 4.6 上已弃用。
> **Claude Opus 5：** 默认开启思考 —— 省略 `thinking:` 会走自适应（等价于 `{ type: "adaptive" }`），这与 Opus 4.8/4.7 不同（后者省略即表示不思考）。`{ type: "disabled" }` 仅在 effort 为 `high` 或更低时接受；与 `xhigh`/`max` 搭配会返回 400。
> **较旧模型：** 使用 `thinking: { type: "enabled", budget_tokens: N }`（必须小于 `max_tokens`，最小 1024）。

```ruby
message = client.messages.create(
  model: :"claude-opus-5",
  max_tokens: 16000,
  thinking: { type: "adaptive" },
  messages: [{ role: "user", content: "Solve: 27 * 453" }]
)

message.content.each do |block|
  case block.type
  when :thinking then puts "Thinking: #{block.thinking}"
  when :text then puts "Response: #{block.text}"
  end
end
```

---

## 提示缓存

`system_:`（末尾下划线 —— 避免遮蔽 `Kernel#system`）接受文本块数组；在最后一个块上设置 `cache_control`。普通 hash 可通过 `OrHash` 类型别名使用。关于放置模式与静默失效审计清单，见 `shared/prompt-caching.md`。

```ruby
message = client.messages.create(
  model: :"claude-opus-5",
  max_tokens: 16000,
  system_: [
    { type: "text", text: long_system_prompt, cache_control: { type: "ephemeral" } }
  ],
  messages: [{ role: "user", content: "Summarize the key points" }]
)
```

1 小时 TTL：`cache_control: { type: "ephemeral", ttl: "1h" }`。`messages.create` 上也有顶层 `cache_control:`，会自动放到最后一个可缓存块上。

通过 `message.usage.cache_creation_input_tokens` / `message.usage.cache_read_input_tokens` 验证命中。

---

## 停止详情

当 `stop_reason` 为 `:refusal` 时，响应会包含结构化的 `stop_details`：

```ruby
if message.stop_reason == :refusal && message.stop_details
  puts "Category: #{message.stop_details.category}"     # e.g. :cyber, :bio, :reasoning_extraction, :frontier_llm, or nil — see docs for the full set
  puts "Explanation: #{message.stop_details.explanation}"
end
```

**拒绝回退（Claude Fable 5）—— 默认建议选择加入。** 回退是选择加入的：没有它时，被拒绝的请求会直接停止。新的 `claude-fable-5` 代码默认应包含服务端 `fallbacks` 参数（beta 头 `server-side-fallback-2026-06-01`，在 beta messages 调用上 `fallbacks: [{model: "claude-opus-4-8"}]`）。确切的 Ruby 绑定（以及无服务端支持的提供商所用的客户端侧中间件）此处未文档化 —— 从 `shared/live-sources.md` WebFetch Ruby SDK 仓库的 `examples/`；完整语义见 `shared/model-migration.md` → Migrating to Claude Fable 5 → `refusal` stop reason。

---

## Beta 功能

`betas:` 仅在 `client.beta.messages.create` 上有效，不能用在非 beta 路径。

### 任务预算

```ruby
response = client.beta.messages.create(
  model: :"claude-opus-5",
  max_tokens: 16000,
  output_config: { task_budget: { type: :tokens, total: 64_000 } },
  tools: [...],
  messages: [...],
  betas: ["task-budgets-2026-03-13"]
)
```

---

## 错误类型

`APIStatusError` 暴露 `.type` 字段，用于程序化错误分类：

```ruby
begin
  client.messages.create(...)
rescue Anthropic::Errors::APIStatusError => e
  puts e.type  # :rate_limit_error, :overloaded_error, etc.
end
```
