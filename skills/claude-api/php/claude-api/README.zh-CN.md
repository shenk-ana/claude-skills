# Claude API — PHP

> [English](./README.md) | **中文**

> **说明：** PHP SDK 是 Anthropic 官方 PHP SDK。可通过 `$client->beta->messages->toolRunner()` 使用 beta 工具运行器。结构化输出辅助通过 `StructuredOutputModel` 类支持。Agent SDK 不可用。支持 Bedrock、Vertex AI 和 Foundry 客户端。

## 安装

```bash
composer require "anthropic-ai/sdk"
```

## 初始化客户端

```php
use Anthropic\Client;

// Using API key from environment variable
$client = new Client(apiKey: getenv("ANTHROPIC_API_KEY"));
```

### Amazon Bedrock

```php
use Anthropic\Bedrock\MantleClient;

// Messages-API Bedrock endpoint. Reads AWS credentials from env.
$client = new MantleClient(awsRegion: 'us-east-1');
```

Bedrock 上的模型 ID 带有 `anthropic.` 前缀 —— 例如 `model: 'anthropic.claude-opus-5'`。

### Google Vertex AI

```php
use Anthropic\Vertex;

// Constructor is private. Parameter is `location`, not `region`.
$client = Vertex\Client::fromEnvironment(
    location: 'us-east5',
    projectId: 'my-project-id',
);
```

### Anthropic Foundry

```php
use Anthropic\Foundry;

// Constructor is private. baseUrl or resource is required.
$client = Foundry\Client::withCredentials(
    apiKey: getenv('ANTHROPIC_FOUNDRY_API_KEY'),
    baseUrl: 'https://<resource>.services.ai.azure.com/anthropic/v1',
);
```

---

## 基础消息请求

```php
$message = $client->messages->create(
    model: 'claude-opus-5',
    maxTokens: 16000,
    messages: [
        ['role' => 'user', 'content' => 'What is the capital of France?'],
    ],
);

// content is an array of polymorphic blocks (TextBlock, ToolUseBlock,
// ThinkingBlock). Accessing ->text on content[0] without checking the block
// type will throw if the first block is not a TextBlock (e.g., when extended
// thinking is enabled and a ThinkingBlock comes first). Always guard:
foreach ($message->content as $block) {
    if ($block->type === 'text') {
        echo $block->text;
    }
}
```

若只要第一个文本块：

```php
foreach ($message->content as $block) {
    if ($block->type === 'text') {
        echo $block->text;
        break;
    }
}
```

---

## 扩展思考

**对 Claude 4.6+ 模型，推荐使用自适应思考。** Claude 会动态决定何时思考、思考多少。

```php
use Anthropic\Messages\ThinkingBlock;

$message = $client->messages->create(
    model: 'claude-opus-5',
    maxTokens: 16000,
    thinking: ['type' => 'adaptive', 'display' => 'summarized'], // display opt-in: default is omitted (empty thinking text) on Fable 5 / Mythos 5 / Claude Opus 5 / Opus 4.8 / 4.7
    messages: [
        ['role' => 'user', 'content' => 'Solve: 27 * 453'],
    ],
);

// ThinkingBlock(s) precede TextBlock in content
foreach ($message->content as $block) {
    if ($block instanceof ThinkingBlock) {
        echo "Thinking:\n{$block->thinking}\n\n";
        // $block->signature is an opaque string — preserve verbatim if
        // passing thinking blocks back in multi-turn conversations
    } elseif ($block->type === 'text') {
        echo "Answer: {$block->text}\n";
    }
}
```

> **Fable 5、Claude Opus 5、Opus 4.8、Opus 4.7、Opus 4.6 和 Sonnet 4.6：** 使用上述自适应思考。`['type' => 'enabled', 'budgetTokens' => N]` 在 Fable 5、Claude Opus 5、Opus 4.8 和 4.7 上已移除（发送会返回 400）；在 Opus 4.6 和 Sonnet 4.6 上已弃用。
> **Claude Opus 5：** 默认开启思考 —— 省略 `thinking:` 会走自适应（等价于 `['type' => 'adaptive']`），这与 Opus 4.8/4.7 不同（后者省略即表示不思考）。`['type' => 'disabled']` 仅在 effort 为 `high` 或更低时接受；与 `xhigh`/`max` 搭配会返回 400。
> **较旧模型：** 使用 `thinking: ['type' => 'enabled', 'budgetTokens' => N]`（budget 必须小于 `maxTokens`，最小 1024）。

`$block->type === 'thinking'` 同样可用于检查；`instanceof` 可收窄类型供 PHPStan 使用。

---

## 提示缓存

`system:` 接受文本块数组；在最后一个块上设置 `cacheControl`。数组形态语法（camelCase 键）是惯用写法。关于放置模式与静默失效审计清单，见 `shared/prompt-caching.md`。

```php
$message = $client->messages->create(
    model: 'claude-opus-5',
    maxTokens: 16000,
    system: [
        ['type' => 'text', 'text' => $longSystemPrompt, 'cacheControl' => ['type' => 'ephemeral']],
    ],
    messages: [['role' => 'user', 'content' => 'Summarize the key points']],
);
```

1 小时 TTL：`'cacheControl' => ['type' => 'ephemeral', 'ttl' => '1h']`。`messages->create(...)` 上也有顶层 `cacheControl:`，会自动放到最后一个可缓存块上。

通过 `$message->usage->cacheCreationInputTokens` / `$message->usage->cacheReadInputTokens` 验证命中。

---

## 停止详情

当 `stopReason` 为 `'refusal'` 时，响应会包含结构化的 `stopDetails`：

```php
if ($message->stopReason === 'refusal' && $message->stopDetails !== null) {
    echo "Category: " . $message->stopDetails->category . "\n";     // e.g. "cyber", "bio", "reasoning_extraction", "frontier_llm", or null — see docs for the full set
    echo "Explanation: " . $message->stopDetails->explanation . "\n";
}
```

**拒绝回退（Claude Fable 5）—— 默认建议选择加入。** 回退是选择加入的：没有它时，被拒绝的请求会直接停止。新的 `claude-fable-5` 代码默认应包含服务端 `fallbacks` 参数（beta 头 `server-side-fallback-2026-06-01`，回退模型 `claude-opus-4-8`，在 beta messages 调用上）。确切的 PHP 绑定（以及无服务端支持的提供商所用的客户端侧中间件）此处未文档化 —— 从 `shared/live-sources.md` WebFetch PHP SDK 仓库的 `examples/`；完整语义见 `shared/model-migration.md` → Migrating to Claude Fable 5 → `refusal` stop reason。

---

## 错误类型

`APIStatusException` 暴露 `->type` 属性，用于程序化错误分类：

```php
try {
    $client->messages->create(...);
} catch (\Anthropic\Core\Exceptions\APIStatusException $e) {
    echo $e->type?->value;  // "rate_limit_error", "overloaded_error", etc.
}
```
