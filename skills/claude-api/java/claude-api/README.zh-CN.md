# Claude API — Java

> [English](./README.md) | **中文**

> **说明：** Java SDK 支持 Claude API，以及通过注解类使用 beta 工具调用。Agent SDK 目前尚未提供 Java 版本。

## 包参考

类型按包组织。若下面示例中没有你需要的类，先用此表定位 —— 不要卡在从网络拉取 SDK 源码上。

| `import` 前缀 | 包含内容 |
|---|---|
| `com.anthropic.client` / `com.anthropic.client.okhttp` | `AnthropicClient`、`AnthropicOkHttpClient` |
| `com.anthropic.models.messages` | 非 beta 请求/响应类型 —— `MessageCreateParams`、`Model`、`Message`、`TextBlockParam`、`ContentBlockParam`、`ToolUseBlockParam`、`ToolResultBlockParam`、`CacheControlEphemeral`、`Tool*`（如 `ToolBash20250124`、`ToolTextEditor20250728`）、`StopReason`、`StructuredMessage*` |
| `com.anthropic.models.messages.batches` | Batch API —— `BatchResultsParams`、`MessageBatchIndividualResponse` |
| `com.anthropic.models.beta` | `AnthropicBeta`（beta 标志常量） |
| `com.anthropic.models.beta.messages` | beta 端点类型 —— `MessageCreateParams`、`BetaMessage`、`BetaStopReason`、`BetaContextManagementConfig`、`BetaMcpToolset`、`BetaRequestMcpServerUrlDefinition`、`BetaTool*` |
| `com.anthropic.core` | `JsonValue`、`JsonField`、`JsonSchemaLocalValidation`、`com.anthropic.core.http.StreamResponse` |
| `com.anthropic.errors` | 类型化异常 —— `AnthropicServiceException`、`RateLimitException`、`NotFoundException` 等（见 `shared/error-codes.md`） |

`client.messages()` 使用 `com.anthropic.models.messages.*`；`client.beta().messages()` 使用 `com.anthropic.models.beta.messages.*`。两个包都定义了 `MessageCreateParams` —— 导入与你调用的客户端路径匹配的那个。

### 各功能的关键类型

按此表编写，不要用 `javap`/jar 检查。Endpoint 列告诉你该用 `client.messages()` 还是 `client.beta().messages()`。

| 功能 | Endpoint | 关键 Java 类型 / builder 调用 |
|---|---|---|
| 用户画像 | beta | `client.beta().userProfiles().create(...)` / `.retrieve(id)` / `.list()`。把返回的 profile id 传给 beta 的 `MessageCreateParams`。需要 beta 头 —— 请查看 SDK 的 beta-headers 参考以获取当前标志。 |
| Agent Skills | beta | `BetaContainerParams`、`BetaSkillParams`、`BetaCodeExecutionTool20250825`。`.addBeta("code-execution-2025-08-25").addBeta("skills-2025-10-02")`。通过 `client.beta().files().download(fileId)` 下载输出。 |
| 缓存诊断 | beta | `BetaDiagnosticsParam`、`BetaCacheControlEphemeral` |
| 上下文编辑 | beta | `.contextManagement(BetaContextManagementConfig.builder()…)`。编辑策略是 `BetaClearToolUses20250919Edit`（或 `BetaClearThinking20251015Edit`）；其触发器是单独构建并传给 edit builder 的 `BetaInputTokensTrigger` —— edit builder 上没有直接的 `.inputTokensTrigger(N)` 快捷方法。对 edit 和 trigger 类做 `javap` 以确认确切 setter 名。 |
| Memory 工具 | non-beta | `.addTool(MemoryTool20250818.builder().build())`，来自 `com.anthropic.models.messages` |
| 可编程工具调用 | non-beta | `CodeExecutionTool20260120`、`Tool`、`ContentBlockParam` |
| 严格工具使用 | non-beta | `Tool`、`Tool.InputSchema` |
| 任务预算 | beta | `.outputConfig(BetaOutputConfig.builder().taskBudget(BetaTokenTaskBudget.builder()...))` |
| 工具搜索 | non-beta | `.addTool(ToolSearchToolRegex20251119.builder()...)`，来自 `com.anthropic.models.messages` |
| Web 搜索 | non-beta | `WebSearchTool20260209`，来自 `com.anthropic.models.messages` —— 带动态过滤的最新变体（Claude Fable 5 + Claude Opus 5 + Opus 4.8/4.7/4.6 + Claude Sonnet 5 + Sonnet 4.6）。较旧模型或 Vertex 请用 `WebSearchTool20250305` |

### 查找类型与成员名

若上表没有你需要的类或 builder 方法，`jar tf <anthropic-java-core jar> | grep -i <term>` 或 `javap -classpath <jar> com.anthropic.models.…` 足够快地定位名称。**不要另外编译并运行反射程序来枚举成员** —— 第一次构建在很多环境里慢到会被放到后台，把你困在轮询循环里。用找到的名字写脚本，让编译器错误（`cannot find symbol`）指出任何错误的成员。

## 安装

Maven：

```xml
<dependency>
    <groupId>com.anthropic</groupId>
    <artifactId>anthropic-java</artifactId>
    <version>2.34.0</version>
</dependency>
```

Gradle：

```groovy
implementation("com.anthropic:anthropic-java:2.34.0")
```

## 初始化客户端

```java
import com.anthropic.client.AnthropicClient;
import com.anthropic.client.okhttp.AnthropicOkHttpClient;

// Default (reads ANTHROPIC_API_KEY from environment)
AnthropicClient client = AnthropicOkHttpClient.fromEnv();

// Explicit API key
AnthropicClient client = AnthropicOkHttpClient.builder()
    .apiKey("your-api-key")
    .build();
```

---

## 基础消息请求

```java
import com.anthropic.models.messages.MessageCreateParams;
import com.anthropic.models.messages.Message;

MessageCreateParams params = MessageCreateParams.builder()
    .model("claude-opus-5")  // .model(String) overload — use it for ids with no typed Model constant yet
    .maxTokens(16000L)
    .addUserMessage("What is the capital of France?")
    .build();

Message response = client.messages().create(params);
response.content().stream()
    .flatMap(block -> block.text().stream())
    .forEach(textBlock -> System.out.println(textBlock.text()));
```

---

## 思考

**对 Claude 4.6+ 模型，推荐使用自适应思考。** Claude 会动态决定何时思考、思考多少。builder 有直接的 `.thinking(ThinkingConfigAdaptive)` 重载 —— 无需手动包 union。

> **Fable 5、Claude Opus 5、Opus 4.8、Opus 4.7、Opus 4.6 和 Sonnet 4.6：** 使用下述自适应思考。`ThinkingConfigEnabled.builder().budgetTokens(N)` 在 Fable 5、Claude Opus 5、Opus 4.8 和 4.7 上已移除（发送会返回 400）；在 Opus 4.6 和 Sonnet 4.6 上已弃用。
> **Claude Opus 5：** 默认开启思考 —— 省略 `.thinking(...)` 会走自适应（`ThinkingConfigAdaptive` 等价），这与 Opus 4.8/4.7 不同（后者省略即表示不思考）。`ThinkingConfigDisabled` 仅在 effort 为 `HIGH` 或更低时接受；与 `XHIGH`/`MAX` 搭配会返回 400。
> **较旧模型：** 使用 `.thinking(ThinkingConfigEnabled.builder().budgetTokens(N).build())`（budget 必须小于 `maxTokens`，最小 1024）。

```java
import com.anthropic.models.messages.ContentBlock;
import com.anthropic.models.messages.MessageCreateParams;
import com.anthropic.models.messages.Model;
import com.anthropic.models.messages.ThinkingConfigAdaptive;

MessageCreateParams params = MessageCreateParams.builder()
    .model(Model.CLAUDE_SONNET_4_6)
    .maxTokens(16000L)
    .thinking(ThinkingConfigAdaptive.builder().build())
    .addUserMessage("Solve this step by step: 27 * 453")
    .build();

for (ContentBlock block : client.messages().create(params).content()) {
    block.thinking().ifPresent(t -> System.out.println("[thinking] " + t.thinking()));
    block.text().ifPresent(t -> System.out.println(t.text()));
}
```

`ContentBlock` 收窄：`.thinking()` / `.text()` 返回 `Optional<T>` —— 使用 `.ifPresent(...)` 或 `.stream().flatMap(...)`。另一种方式：`isThinking()` / `asThinking()` 布尔值+解包对（变体不对会抛异常）。

---

## Effort 参数

Effort 嵌套在 `OutputConfig` 里 —— `MessageCreateParams.Builder` 上**没有**直接的 `.effort()`。

```java
import com.anthropic.models.messages.OutputConfig;

.outputConfig(OutputConfig.builder()
    .effort(OutputConfig.Effort.HIGH)  // or LOW, MEDIUM, XHIGH, MAX
    .build())
```

与 `Thinking = ThinkingConfigAdaptive` 结合，以控制成本与质量。

---

## 提示缓存

系统消息作为带 `CacheControlEphemeral` 的 `TextBlockParam` 列表。使用 `.systemOfTextBlockParams(...)` —— 普通的 `.system(String)` 重载无法携带缓存控制。关于放置模式与静默失效审计清单，见 `shared/prompt-caching.md`。

```java
import com.anthropic.models.messages.TextBlockParam;
import com.anthropic.models.messages.CacheControlEphemeral;

.systemOfTextBlockParams(List.of(
    TextBlockParam.builder()
        .text(longSystemPrompt)
        .cacheControl(CacheControlEphemeral.builder()
            .ttl(CacheControlEphemeral.Ttl.TTL_1H)  // optional; also TTL_5M
            .build())
        .build()))
```

`MessageCreateParams.Builder` 和 `Tool.builder()` 上也有顶层 `.cacheControl(CacheControlEphemeral)`。

通过 `response.usage().cacheCreationInputTokens()` / `response.usage().cacheReadInputTokens()` 验证命中。

---

## Token 计数

```java
import com.anthropic.models.messages.MessageCountTokensParams;

long tokens = client.messages().countTokens(
    MessageCountTokensParams.builder()
        .model(Model.CLAUDE_SONNET_4_6)
        .addUserMessage("Hello")
        .build()
).inputTokens();
```

---

## PDF / 文档输入

`DocumentBlockParam` builder 有源快捷方法。包在 `ContentBlockParam.ofDocument()` 中，并通过 `.addUserMessageOfBlockParams()` 传入。

```java
import com.anthropic.models.messages.DocumentBlockParam;
import com.anthropic.models.messages.ContentBlockParam;
import com.anthropic.models.messages.TextBlockParam;

DocumentBlockParam doc = DocumentBlockParam.builder()
    .source(Base64PdfSource.builder().data(base64String).build())
    // or .source(UrlPdfSource.builder().url("https://...").build())
    .title("My Document")        // optional
    .build();
```

**Files API** 文档引用请走 beta 路径和 beta 类型 —— 见 `files-api.md`：`BetaRequestDocumentBlock.builder().source(BetaFileDocumentSource.builder().fileId(id).build())`。

```java
.addUserMessageOfBlockParams(List.of(
    ContentBlockParam.ofDocument(doc),
    ContentBlockParam.ofText(TextBlockParam.builder().text("Summarize this").build())))
```

---

## 停止详情

当 `stopReason()` 为 `"refusal"` 时，响应会包含结构化的 `stopDetails()`：

```java
response.stopDetails().ifPresent(details -> {
    System.out.println("Category: " + details.category());
    System.out.println("Explanation: " + details.explanation());
});
```

**拒绝回退（Claude Fable 5）—— 默认建议选择加入。** 回退是选择加入的：没有它时，被拒绝的请求会直接停止。新的 `claude-fable-5` 代码默认应包含服务端 `fallbacks` 参数（beta 头 `server-side-fallback-2026-06-01`，回退模型 `claude-opus-4-8`，在 beta messages 调用上）。确切的 Java builder 方法（以及无服务端支持的提供商所用的客户端侧中间件）此处未文档化 —— 从 `shared/live-sources.md` WebFetch Java SDK 仓库的 `examples/`；完整语义见 `shared/model-migration.md` → Migrating to Claude Fable 5 → `refusal` stop reason。

---

## 错误类型

`AnthropicServiceException` 暴露 `.errorType()`，返回 `Optional<ErrorType>`，用于程序化错误分类：

```java
try {
    client.messages().create(params);
} catch (AnthropicServiceException e) {
    e.errorType().ifPresent(type ->
        System.out.println("Error type: " + type)  // RATE_LIMIT_ERROR, OVERLOADED_ERROR, etc.
    );
}
```

---
