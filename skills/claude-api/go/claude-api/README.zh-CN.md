# Claude API — Go

> [English](./README.md) | **中文**

> **说明：** Go SDK 支持 Claude API，以及通过 `BetaToolRunner` 使用 beta 工具调用。Agent SDK 目前尚未提供 Go 版本。

## 安装

```bash
go get github.com/anthropics/anthropic-sdk-go
```

## 初始化客户端

```go
import (
    "github.com/anthropics/anthropic-sdk-go"
    "github.com/anthropics/anthropic-sdk-go/option"
)

// Default (uses ANTHROPIC_API_KEY env var)
client := anthropic.NewClient()

// Explicit API key
client := anthropic.NewClient(
    option.WithAPIKey("your-api-key"),
)
```

---

## 模型常量

Go SDK 提供类型化的模型常量：`anthropic.ModelClaudeFable5`、`anthropic.ModelClaudeOpus4_8`、`anthropic.ModelClaudeOpus4_7`、`anthropic.ModelClaudeSonnet4_6`、`anthropic.ModelClaudeHaiku4_5_20251001`。除非用户另有指定，默认使用 Claude Opus 5；若对方要求 Fable 或最强模型，使用 `anthropic.ModelClaudeFable5`（完整解析表见 `shared/models.md`）。

`anthropic.Model` 是 `string` 的别名，因此尚无类型化常量的模型 —— 包括 Claude Opus 5 —— 以普通 id 传入：`Model: "claude-opus-5"`。在假设存在类型化 `Claude Opus 5` 常量之前，请先查看 SDK 发行说明。

---

## 基础消息请求

```go
response, err := client.Messages.New(context.Background(), anthropic.MessageNewParams{
    Model:     "claude-opus-5",
    MaxTokens: 16000,
    Messages: []anthropic.MessageParam{
        anthropic.NewUserMessage(anthropic.NewTextBlock("What is the capital of France?")),
    },
})
if err != nil {
    log.Fatal(err)
}
for _, block := range response.Content {
    switch variant := block.AsAny().(type) {
    case anthropic.TextBlock:
        fmt.Println(variant.Text)
    }
}
```

---

## 思考

通过在 `MessageNewParams` 中设置 `Thinking` 启用 Claude 的内部推理。响应会在最终 `TextBlock` 之前包含 `ThinkingBlock` 内容。

**对 Claude 4.6+ 模型，推荐使用自适应思考。** Claude 会动态决定何时思考、思考多少。可与 `effort` 参数结合，以控制成本与质量。

派生自 `anthropic-sdk-go/message.go`（`ThinkingConfigParamUnion`、`ThinkingConfigAdaptiveParam`）。

```go
// There is no ThinkingConfigParamOfAdaptive helper — construct the union
// struct-literal directly and take the address of the variant.
adaptive := anthropic.ThinkingConfigAdaptiveParam{}
params := anthropic.MessageNewParams{
    Model:     anthropic.ModelClaudeSonnet4_6,
    MaxTokens: 16000,
    Thinking:  anthropic.ThinkingConfigParamUnion{OfAdaptive: &adaptive},
    Messages: []anthropic.MessageParam{
        anthropic.NewUserMessage(anthropic.NewTextBlock("How many r's in strawberry?")),
    },
}

resp, err := client.Messages.New(context.Background(), params)
if err != nil {
    log.Fatal(err)
}

// ThinkingBlock(s) precede TextBlock in content
for _, block := range resp.Content {
    switch b := block.AsAny().(type) {
    case anthropic.ThinkingBlock:
        fmt.Println("[thinking]", b.Thinking)
    case anthropic.TextBlock:
        fmt.Println(b.Text)
    }
}
```

> **Fable 5、Claude Opus 5、Opus 4.8、Opus 4.7、Opus 4.6 和 Sonnet 4.6：** 使用上述自适应思考。`ThinkingConfigParamOfEnabled(budgetTokens)` 在 Fable 5、Claude Opus 5、Opus 4.8 和 4.7 上已移除（发送会返回 400）；在 Opus 4.6 和 Sonnet 4.6 上已弃用。
> **Claude Opus 5：** 默认开启思考 —— 不设置 `Thinking` 会走自适应（自适应 union 等价），这与 Opus 4.8/4.7 不同（后者不设置即表示不思考）。
> **较旧模型：** 使用 `anthropic.ThinkingConfigParamOfEnabled(N)`（budget 必须小于 `MaxTokens`，最小 1024）。

禁用：`anthropic.ThinkingConfigParamUnion{OfDisabled: &anthropic.ThinkingConfigDisabledParam{}}`。在 Claude Opus 5 上仅在 effort 为 `high` 或更低时接受 —— 与 `xhigh`/`max` 搭配会返回 400。

---

## 提示缓存

`System` 的类型是 `[]TextBlockParam`；在最后一个块上设置 `CacheControl`，即可同时缓存 tools + system。关于放置模式与静默失效审计清单，见 `shared/prompt-caching.md`。

```go
System: []anthropic.TextBlockParam{{
    Text:         longSystemPrompt,
    CacheControl: anthropic.NewCacheControlEphemeralParam(), // default 5m TTL
}},
```

1 小时 TTL：`anthropic.CacheControlEphemeralParam{TTL: anthropic.CacheControlEphemeralTTLTTL1h}`。`MessageNewParams` 上也有顶层 `CacheControl`，会自动放到最后一个可缓存块上。

通过 `resp.Usage.CacheCreationInputTokens` / `resp.Usage.CacheReadInputTokens` 验证命中。

---

## 停止详情

当 `StopReason` 为 `anthropic.StopReasonRefusal` 时，响应会包含结构化的 `StopDetails`：

```go
if resp.StopReason == anthropic.StopReasonRefusal {
    fmt.Println("Category:", resp.StopDetails.Category)     // e.g. "cyber", "bio", "reasoning_extraction", "frontier_llm", or "" — see docs for the full set
    fmt.Println("Explanation:", resp.StopDetails.Explanation)
}
```

**拒绝回退（Claude Fable 5）—— 默认建议选择加入。** 回退是选择加入的：没有它时，被拒绝的请求会直接停止。在 `claude-fable-5` 代码中，默认在 `client.Beta.Messages.New` 上加入 `Fallbacks: []anthropic.BetaFallbackParam{{Model: "claude-opus-4-8"}}` 以及 `anthropic.AnthropicBetaServerSideFallback2026_06_01` beta —— 策略拒绝会在同一次调用内由回退模型重新服务。在 Amazon Bedrock、Vertex AI 或 Microsoft Foundry 上不可用 —— 在这些平台上注册客户端侧中间件：来自 `lib/betafallback` 的 `option.WithMiddleware(betafallback.BetaRefusalFallbackMiddleware(...))`，并通过 `betafallback.WithBetaFallbackState(&betafallback.BetaFallbackState{})` 做按对话的状态。完整语义（计费、粘性路由、流式）与可运行示例：`shared/model-migration.md` → Migrating to Claude Fable 5 → `refusal` stop reason，以及 Go SDK 仓库的 `examples/`（通过 `shared/live-sources.md` WebFetch）。

---

## PDF / 文档输入

`NewDocumentBlock` 泛型辅助函数接受任意源类型。`MediaType`/`Type` 会自动设置。

```go
b64 := base64.StdEncoding.EncodeToString(pdfBytes)

msg := anthropic.NewUserMessage(
    anthropic.NewDocumentBlock(anthropic.Base64PDFSourceParam{Data: b64}),
    anthropic.NewTextBlock("Summarize this document"),
)
```

其他源：`URLPDFSourceParam{URL: "https://..."}`、`PlainTextSourceParam{Data: "..."}`。

---

## 上下文编辑 / 压缩（Beta）

对 `BetaMessageNewParams` 使用 `Beta.Messages.New` 并设置 `ContextManagement`。没有 `NewBetaAssistantMessage` —— 往返时使用 `.ToParam()`。

```go
params := anthropic.BetaMessageNewParams{
    Model:     "claude-opus-5",  // also supported: ModelClaudeOpus4_8, ModelClaudeSonnet4_6
    MaxTokens: 16000,
    Betas:     []anthropic.AnthropicBeta{"compact-2026-01-12"},
    ContextManagement: anthropic.BetaContextManagementConfigParam{
        Edits: []anthropic.BetaContextManagementConfigEditUnionParam{
            {OfCompact20260112: &anthropic.BetaCompact20260112EditParam{}},
        },
    },
    Messages: []anthropic.BetaMessageParam{ /* ... */ },
}

resp, err := client.Beta.Messages.New(ctx, params)
if err != nil {
    log.Fatal(err)
}

// Round-trip: append response to history via .ToParam()
params.Messages = append(params.Messages, resp.ToParam())

// Read compaction blocks from the response
for _, block := range resp.Content {
    if c, ok := block.AsAny().(anthropic.BetaCompactionBlock); ok {
        fmt.Println("compaction summary:", c.Content)
    }
}
```

其他编辑类型：`BetaClearToolUses20250919EditParam`、`BetaClearThinking20251015EditParam` —— 这些需要 `Betas: []anthropic.AnthropicBeta{"context-management-2025-06-27"}`，而不是 `compact-2026-01-12`。
