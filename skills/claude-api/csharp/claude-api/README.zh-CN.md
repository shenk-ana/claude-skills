# Claude API — C#

> [English](./README.md) | **中文**

> **说明：** C# SDK 是 Anthropic 官方 C# SDK。工具调用通过 Messages API 支持，并提供用于自动工具执行循环的 beta `BetaToolRunner`。SDK 还支持带函数调用的 Microsoft.Extensions.AI IChatClient 集成，以及 Managed Agents（beta）。

## 命名空间参考

类型按命名空间组织。若下面示例中没有你需要的类型，先用此表定位 —— 不要卡在从网络拉取 SDK 源码上。

| `using` | 包含内容 |
|---|---|
| `Anthropic` | `AnthropicClient`、顶层选项 |
| `Anthropic.Models.Messages` | 非 beta 请求/响应类型 —— `MessageCreateParams`、`Model`、`Role`、`ContentBlock`、`TextBlock`、`ToolUseBlock`、`ToolResultBlockParam`、`Tool*`（工具定义类） |
| `Anthropic.Models.Beta.Messages` | beta 端点等价物 —— `MessageCreateParams`、`BetaMessage`、`BetaTool*`、`Speed`、`BetaRequestMcpServerUrlDefinition`、上下文编辑/压缩配置 |
| `Anthropic.Models.Beta` | 共享 beta 常量 |
| `Anthropic.Models.Beta.Files` | Files API 类型 |
| `Anthropic.Models.Messages.Batches` | Batch API 类型 |
| `Anthropic.Helpers.Beta` | `BetaToolRunner`、beta 辅助工具 |
| `Anthropic.Exceptions` | `AnthropicApiException`、`AnthropicRateLimitException`、`Anthropic5xxException` 等 —— 见 `shared/error-codes.md` |
| `Anthropic.Bedrock` / `Anthropic.Vertex` / `Anthropic.Foundry` / `Anthropic.Aws` | 平台客户端（独立 NuGet 包）：`AnthropicBedrockMantleClient`、`AnthropicFoundryClient`、`AnthropicAwsClient` |

`client.Messages.*` 使用非 beta 类型；`client.Beta.Messages.*` 使用 `Anthropic.Models.Beta.Messages` 类型。两个命名空间都定义了 `MessageCreateParams` —— 选择与你调用的客户端路径匹配的那个。

### 各功能的关键类型

按此表编写，不要反射 SDK 程序集。Endpoint 列告诉你该用 `client.Messages.*` 还是 `client.Beta.Messages.*`。

| 功能 | Endpoint | 关键 C# 类型（命名空间见上表） |
|---|---|---|
| 用户画像 | beta | `client.Beta.UserProfiles.Create(...)` / `.Retrieve(id)` / `.List()`。把返回的 profile id 传给 beta messages 调用。需要 beta 头 —— 请查看 SDK 的 beta-headers 参考以获取当前标志。 |
| Agent Skills | beta | `BetaContainerParams`（`Skills = [new BetaSkillParams { ... }]`）、`BetaCodeExecutionTool20250825`。`Betas = ["code-execution-2025-08-25", "skills-2025-10-02"]`。通过 `client.Beta.Files.Download(fileId)` 下载输出。 |
| Advisor 工具 | beta | `BetaAdvisorTool20260301` —— 可能尚未包含在所有 SDK 发行版中 |
| 缓存诊断 | beta | `Diagnostics = new() { PreviousMessageID = … }`、`BetaCacheControlEphemeral`、`BetaContentBlockParam` |
| 上下文编辑 | beta | `ContextManagement = new BetaContextManagementConfig { Edits = [new BetaClearToolUses20250919Edit()] }`。`Betas = ["context-management-2025-06-27"]`（不是 `compact-2026-01-12` —— 那是给 `BetaCompact20260112Edit` 的）。 |
| Memory 工具 | non-beta | `Tools = [new ToolUnion(new MemoryTool20250818())]` |
| 可编程工具调用 | non-beta | `CodeExecutionTool20260120`、`ToolResultBlockParam`、`ContentBlockParam` |
| 任务预算 | beta | 带 `TaskBudget = new BetaTokenTaskBudget { ... }` 的 `BetaOutputConfig` |
| 工具搜索 | non-beta | `new ToolUnion(new ToolSearchToolRegex20251119 { Type = ToolSearchToolRegex20251119Type.ToolSearchToolRegex20251119 })` —— 必须显式设置 `Type`。 |
| Web 搜索 | non-beta | `new ToolUnion(new WebSearchTool20260209())` —— 带动态过滤的最新变体（Claude Fable 5 + Claude Opus 5 + Opus 4.8/4.7/4.6 + Claude Sonnet 5 + Sonnet 4.6）。较旧模型或 Vertex 请用 `WebSearchTool20250305()` |

### 查找类型与成员名

若上表没有你需要的类型或成员，`strings ~/.nuget/packages/anthropic/*/lib/*/Anthropic.dll | grep -i <term>` 足够快地定位类和属性名。**不要升级到 `dotnet run` 反射探测来精确转储成员** —— 第一次编译在很多环境里慢到会被放到后台，把你困在轮询循环里。用 `strings | grep` 找到的名字写 `Program.cs`；若成员名不对，编译器错误（`error CS1061: 'X' does not contain a definition for 'Y'`）会在几秒内指出，比任何反射探测都快。

注意 `strings` 不会露出线格式的 snake_case 字段名（`output_tokens`、`stop_reason`）—— 它们在 DLL 中以不同方式存储。**C# 属性是线字段的 PascalCase 等价物**（`response.Usage.OutputTokens`、`response.StopReason`）。若你从文档知道线字段名，写成 PascalCase 属性再编译即可；不要探测 snake_case 字符串。

### 最小可运行骨架

**写一个普通的 `Program.cs` 主体** —— 如下所示，`using` 语句后跟顶层语句。**不要**加 `#!/usr/bin/env dotnet` shebang 或 `#:package Anthropic@*` 指令：那些是 .NET 基于文件的应用语法，通过已有 `.csproj` 编译时会失败，报 `CS1024: Preprocessor directive expected`。标准项目设置（见 [C# 快速入门](https://platform.claude.com/docs/en/get-started)：`dotnet new console` → `dotnet add package Anthropic` → 编辑 `Program.cs` → `dotnet run`）会提供 `.csproj` 和包引用。

从这里开始 —— 原样即可编译。填入功能相关字段；不要先花轮次运行反射或 XML 文档检查来发现类型名。

```csharp
using System;
using Anthropic;
using Anthropic.Models.Messages;       // or Anthropic.Models.Beta.Messages for beta endpoints

AnthropicClient client = new();

var message = await client.Messages.Create(new MessageCreateParams
{
    Model = "claude-opus-5",
    MaxTokens = 1024,
    Messages = [ new() { Role = Role.User, Content = "Hello, Claude" } ],
});

Console.WriteLine(message);
```

对于 beta 功能（任何需要 `anthropic-beta` 头的内容），使用 beta 客户端路径和命名空间 —— 整体形态相同：

```csharp
using System;
using Anthropic;
using Anthropic.Models.Beta.Messages;

AnthropicClient client = new();

var response = await client.Beta.Messages.Create(new MessageCreateParams
{
    Model = "claude-opus-5",
    MaxTokens = 4096,
    Betas = ["<beta-flag>"],
    Messages = [ new() { Role = Role.User, Content = "…" } ],
    // Tools = new BetaToolUnion[] { new BetaSomeTool { … } },   // for tool features
});

Console.WriteLine(response);
```

若本文件没有功能所需的类型名，按上面命名空间参考中的命名模式写，再根据编译器输出修正 —— 产出 `Program.cs` 并迭代，比先做调研更快。

### 常见 C# 编译错误

- **CS8803（顶层语句必须在类型声明之前）：** 把任何 `record`/`class`/`struct` 定义放在**最后一个顶层语句之后**，即文件末尾。在 `var client = new AnthropicClient()` 之上定义 record 将无法编译。
- **对 `Task<…Page>` 使用 `await foreach`：** `client.Models.List()` 返回 `Task<ModelListPage>`，它本身不是异步可枚举的。先 await，再迭代：`var page = await client.Models.List(); foreach (var m in page.Items) {…}`。自动分页时，先确认页面类型是否暴露 `AutoPagingEachAsync()` 或类似方法，再使用 `await foreach`。

## 安装

```bash
dotnet add package Anthropic
```

## 初始化客户端

```csharp
using Anthropic;

// Default (uses ANTHROPIC_API_KEY env var)
AnthropicClient client = new();

// Explicit API key (use environment variables — never hardcode keys)
AnthropicClient client = new() {
    ApiKey = Environment.GetEnvironmentVariable("ANTHROPIC_API_KEY")
};
```

---

## 基础消息请求

```csharp
using Anthropic.Models.Messages;

var parameters = new MessageCreateParams
{
    Model = "claude-opus-5",
    MaxTokens = 16000,
    Messages = [new() { Role = Role.User, Content = "What is the capital of France?" }]
};
var response = await client.Messages.Create(parameters);

// ContentBlock is a union wrapper. .Value unwraps to the variant object,
// then OfType<T> filters to the type you want. Or use the TryPick* idiom
// shown in the Thinking section below.
foreach (var text in response.Content.Select(b => b.Value).OfType<TextBlock>())
{
    Console.WriteLine(text.Text);
}
```

---

## 思考

**对 Claude 4.6+ 模型，推荐使用自适应思考。** Claude 会动态决定何时思考、思考多少。

> **Fable 5、Claude Opus 5、Opus 4.8、Opus 4.7、Opus 4.6 和 Sonnet 4.6：** 使用下述自适应思考。`new ThinkingConfigEnabled { BudgetTokens = N }` 在 Fable 5、Claude Opus 5、Opus 4.8 和 4.7 上已移除（发送会返回 400）；在 Opus 4.6 和 Sonnet 4.6 上已弃用。
> **Claude Opus 5：** 默认开启思考 —— 省略 `Thinking` 会走自适应（`ThinkingConfigAdaptive` 等价），这与 Opus 4.8/4.7 不同（后者省略即表示不思考）。`ThinkingConfigDisabled` 仅在 effort 为 `high` 或更低时接受；与 `xhigh`/`max` 搭配会返回 400。
> **较旧模型：** 使用 `new ThinkingConfigEnabled { BudgetTokens = N }`（budget 必须小于 `MaxTokens`，最小 1024）。

```csharp
using Anthropic.Models.Messages;

var response = await client.Messages.Create(new MessageCreateParams
{
    Model = "claude-opus-5",
    MaxTokens = 16000,
    // ThinkingConfigParam? implicitly converts from the concrete variant classes —
    // no wrapper needed.
    // display opt-in: default is omitted (empty thinking text) on Fable 5 / Mythos 5 / Claude Opus 5 / Opus 4.8 / 4.7
    Thinking = new ThinkingConfigAdaptive { Display = Display.Summarized },
    Messages =
    [
        new() { Role = Role.User, Content = "Solve: 27 * 453" },
    ],
});

// ThinkingBlock(s) precede TextBlock in Content. TryPick* narrows the union.
foreach (var block in response.Content)
{
    if (block.TryPickThinking(out ThinkingBlock? t))
    {
        Console.WriteLine($"[thinking] {t.Thinking}");
    }
    else if (block.TryPickText(out TextBlock? text))
    {
        Console.WriteLine(text.Text);
    }
}
```

`TryPick*` 的替代：`.Select(b => b.Value).OfType<ThinkingBlock>()`（与基础消息示例相同的 LINQ 模式）。

---

## 上下文编辑 / 压缩（Beta）

**Beta 命名空间前缀不一致**（已对照 `src/Anthropic/Models/Beta/Messages/*.cs` @ 12.9.0 源码验证）。无前缀：`MessageCreateParams`、`MessageCountTokensParams`、`Role`、`Speed`。**其他所有类型都有 `Beta` 前缀**：`BetaMessageParam`、`BetaMessage`、`BetaContentBlock`、`BetaToolUseBlock`、所有块参数类型。若同时导入两个命名空间，无前缀的 `Role` **会**与 `Anthropic.Models.Messages.Role` 冲突（CS0104）。最安全：只导入 Beta；若混用，给 beta 的 `Role` 起别名：

```csharp
using Anthropic.Models.Beta.Messages;
using NonBeta = Anthropic.Models.Messages;  // only if you also need non-beta types
// Now: MessageCreateParams, BetaMessageParam, Role (beta's), NonBeta.Role (if needed)
```


`BetaMessage.Content` 是 `IReadOnlyList<BetaContentBlock>` —— 15 变体的可判别联合。用 `TryPick*` 收窄。**响应的 `BetaContentBlock` 不能赋给参数的 `BetaContentBlockParam`** —— C# 没有 `.ToParam()`。通过转换每个块来往返：

```csharp
using Anthropic.Models.Beta.Messages;

var betaParams = new MessageCreateParams   // no Beta prefix — see unprefixed list above
{
    Model = "claude-opus-5",
    MaxTokens = 16000,
    Betas = ["compact-2026-01-12"],
    ContextManagement = new BetaContextManagementConfig
    {
        Edits = [new BetaCompact20260112Edit()],
    },
    Messages = messages,
};
BetaMessage resp = await client.Beta.Messages.Create(betaParams);

foreach (BetaContentBlock block in resp.Content)
{
    if (block.TryPickCompaction(out BetaCompactionBlock? compaction))
    {
        // Content is nullable — compaction can fail server-side
        Console.WriteLine($"compaction summary: {compaction.Content}");
    }
}

// Context-edit metadata lives on a separate nullable field
if (resp.ContextManagement is { } ctx)
{
    foreach (var edit in ctx.AppliedEdits)
        Console.WriteLine($"cleared {edit.ClearedInputTokens} tokens");
}

// ROUND-TRIP: BetaMessageParam.Content is BetaMessageParamContent (a string|list
// union). It implicit-converts from List<BetaContentBlockParam>, NOT from the
// response's IReadOnlyList<BetaContentBlock>. Convert each block:
List<BetaContentBlockParam> paramBlocks = [];
foreach (var b in resp.Content)
{
    if (b.TryPickText(out var t)) paramBlocks.Add(new BetaTextBlockParam { Text = t.Text });
    else if (b.TryPickCompaction(out var c)) paramBlocks.Add(new BetaCompactionBlockParam { Content = c.Content });
    // ... other variants as needed
}
messages.Add(new BetaMessageParam { Role = Role.Assistant, Content = paramBlocks });
```

全部 15 个 `BetaContentBlock.TryPick*` 变体：`Text`、`Thinking`、`RedactedThinking`、`ToolUse`、`ServerToolUse`、`WebSearchToolResult`、`WebFetchToolResult`、`CodeExecutionToolResult`、`BashCodeExecutionToolResult`、`TextEditorCodeExecutionToolResult`、`ToolSearchToolResult`、`McpToolUse`、`McpToolResult`、`ContainerUpload`、`Compaction`。

**`BetaToolUseBlock.Input` 是 `IReadOnlyDictionary<string, JsonElement>`** —— 按键索引，再调用 `JsonElement` 提取器：

```csharp
if (block.TryPickToolUse(out BetaToolUseBlock? tu))
{
    int a = tu.Input["a"].GetInt32();
    string s = tu.Input["name"].GetString()!;
}
```

---

## Effort 参数

Effort 嵌套在 `OutputConfig` 下，**不是**顶层属性。`ApiEnum<string, Effort>` 有从枚举的隐式转换，因此可直接赋 `Effort.High`。

```csharp
OutputConfig = new OutputConfig { Effort = Effort.High },
```

取值：`Effort.Low`、`Effort.Medium`、`Effort.High`、`Effort.Max`。与 `Thinking = new ThinkingConfigAdaptive()` 结合，以控制成本与质量。

---

## 提示缓存

`System` 接受 `MessageCreateParamsSystem?` —— `string` 或 `List<TextBlockParam>` 的联合。没有 `SystemTextBlockParam`；使用普通 `TextBlockParam`。隐式转换需要具体的 `List<TextBlockParam>` 类型（数组字面量无法转换）。关于放置模式与静默失效审计清单，见 `shared/prompt-caching.md`。

```csharp
System = new List<TextBlockParam> {
    new() {
        Text = longSystemPrompt,
        CacheControl = new CacheControlEphemeral(),  // auto-sets Type = "ephemeral"
    },
},
```

`CacheControlEphemeral` 上可选的 `Ttl`：`new() { Ttl = Ttl.Ttl1h }` 或 `Ttl.Ttl5m`。`CacheControl` 也存在于 `Tool.CacheControl` 和顶层 `MessageCreateParams.CacheControl`。

通过 `response.Usage.CacheCreationInputTokens` / `response.Usage.CacheReadInputTokens` 验证命中。

---

## Token 计数

```csharp
MessageTokensCount result = await client.Messages.CountTokens(new MessageCountTokensParams {
    Model = "claude-opus-5",
    Messages = [new() { Role = Role.User, Content = "Hello" }],
});
long tokens = result.InputTokens;
```

`MessageCountTokensParams.Tools` 使用的联合类型（`MessageCountTokensTool`）与 `MessageCreateParams.Tools`（`ToolUnion`）不同 —— 若传入 tools，编译器会在需要时告诉你。

---

## PDF / 文档输入

`DocumentBlockParam` 接受 `DocumentBlockParamSource` 联合：`Base64PdfSource` / `UrlPdfSource` / `PlainTextSource` / `ContentBlockSource`。`Base64PdfSource` 会自动设置 `MediaType = "application/pdf"` 和 `Type = "base64"`。

```csharp
new MessageParam {
    Role = Role.User,
    Content = new List<ContentBlockParam> {
        new DocumentBlockParam { Source = new Base64PdfSource { Data = base64String } },
        new TextBlockParam { Text = "Summarize this PDF" },
    },
}
```

---

## 快速模式（Beta）

```csharp
var response = await client.Beta.Messages.Create(new MessageCreateParams {
    Model = "claude-opus-5", MaxTokens = 4096,
    Speed = Speed.Fast,
    Betas = ["fast-mode-2026-02-01"],
    Messages = [...],
});
```

## Models API

```csharp
var page = await client.Models.List();
foreach (var m in page.Items) { Console.WriteLine(m.ID); }
var one = await client.Models.Retrieve("claude-opus-5");
```

## 长输出（128k）+ Prefill

在 `client.Messages` 上设置 `MaxTokens = 128000` 并使用流式路径（见 `streaming.md`）。在 Claude 4+ 模型上，128k 输出是原生的 —— 不需要 `output-128k-*` beta 头或 beta 命名空间。

**预填 assistant 消息**（在输入中放一条尾部 `Role.Assistant` 消息）在 Claude Fable 5、Claude Opus 5、Opus 4.8、Opus 4.7、Opus 4.6 和 Sonnet 4.6 上**不受支持** —— 请求会返回 400。请改用 `OutputConfig.Format`（结构化输出）。

## 停止详情

当 `StopReason` 为 `"refusal"` 时，响应会包含结构化的 `StopDetails`：

```csharp
if (response.StopReason == "refusal" && response.StopDetails is { } details)
{
    Console.WriteLine($"Category: {details.Category}");
    Console.WriteLine($"Explanation: {details.Explanation}");
}
```

**拒绝回退（Claude Fable 5）—— 默认建议选择加入。** 回退是选择加入的：没有它时，被拒绝的请求会直接停止。在 `claude-fable-5` 代码中，默认在 beta messages 调用上加入 `Fallbacks = [new(Model.ClaudeOpus4_8)]` 以及 `AnthropicBeta.ServerSideFallback2026_06_01` beta —— 策略拒绝会在同一次调用内由回退模型重新服务。在 Amazon Bedrock、Vertex AI 或 Microsoft Foundry 上不可用 —— 在这些平台上使用客户端侧处理器：`new AnthropicClient { Handlers = [new BetaRefusalFallbackHandler { Fallbacks = [new(Model.ClaudeOpus4_8)] }] }`（命名空间 `Anthropic.Helpers`），并通过 `using (fallbackState.Use()) { ... }` 作用域内的 `BetaFallbackState.Create()` 做按对话的状态。完整语义（计费、粘性路由、流式）与可运行示例：`shared/model-migration.md` → Migrating to Claude Fable 5 → `refusal` stop reason，以及 C# SDK 仓库的 `examples/`（通过 `shared/live-sources.md` WebFetch）。

---

## Managed Agents（Beta）

C# SDK 通过 `client.Beta.Agents`、`client.Beta.Sessions`、`client.Beta.Environments` 及相关命名空间支持 Managed Agents。架构见 `shared/managed-agents-overview.md`，线级参考见 `curl/managed-agents.md`。
