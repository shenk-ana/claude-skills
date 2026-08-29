# Managed Agents — PHP

> [English](./README.md) | **中文**

> **此处未列出的绑定：** 本 README 覆盖 PHP 上最常见的 managed-agents 流程。若需要未展示的类、方法、命名空间、字段或行为，请 WebFetch PHP SDK 仓库 **或** `shared/live-sources.md` 中的相关文档页，不要猜测。不要从 cURL 形态或其他语言的 SDK 外推。

> **Agent 是持久的 —— 创建一次，之后用 ID 引用。** 保存 `$client->beta->agents->create` 返回的 agent ID，并在后续每次 `->sessions->create` 中传入；不要在请求路径里调用 `agents->create`。**推荐：** 将 agent 和环境定义为纳入版本控制的 YAML，并用 `ant` CLI 应用 —— 见 `shared/anthropic-cli.md`（其在线文档 URL 在 `shared/live-sources.md`）。CLI 负责控制面（创建/更新）；你的代码负责数据面（用已保存的 ID 开 session）。下面的示例展示必须用代码预配时的创建方式；生产环境中，创建调用应放在初始化阶段，而不是请求路径里。

## 安装

```bash
composer require "anthropic-ai/sdk" "guzzlehttp/guzzle:^7"
```

## 初始化客户端

```php
use Anthropic\Client;

// Default (uses ANTHROPIC_API_KEY env var)
$client = new Client();

// Explicit API key
$client = new Client(apiKey: 'your-api-key');
```

---

## 创建环境

```php
$environment = $client->beta->environments->create(
    name: 'my-dev-env',
    config: ['type' => 'cloud', 'networking' => ['type' => 'unrestricted']],
);
echo "Environment ID: {$environment->id}\n"; // env_...
```

---

## 创建 Agent（必做的第一步）

> ⚠️ **没有内联 agent 配置。** `model`/`system`/`tools` 在 agent 对象上，不在 session 上。始终先调用 `$client->beta->agents->create()` —— session 接收 `agent: $agent->id` 或类型化的 `BetaManagedAgentsAgentParams::with(type: 'agent', id: $agent->id, version: $agent->version)`。

### 最小示例

```php
use Anthropic\Beta\Agents\BetaManagedAgentsAgentToolset20260401Params;

// 1. Create the agent (reusable, versioned)
$agent = $client->beta->agents->create(
    name: 'Coding Assistant',
    model: 'claude-opus-5',
    system: 'You are a helpful coding assistant.',
    tools: [
        BetaManagedAgentsAgentToolset20260401Params::with(
            type: 'agent_toolset_20260401',
        ),
    ],
);

// 2. Start a session
$session = $client->beta->sessions->create(
    agent: ['type' => 'agent', 'id' => $agent->id, 'version' => $agent->version],
    environmentID: $environment->id,
    title: 'Quickstart session',
);
echo "Session ID: {$session->id}\n";
echo "Trace: https://platform.claude.com/workspaces/default/sessions/{$session->id}\n"; // swap 'default' for your workspace ID if the API key is not in the Default workspace
```

### 更新 Agent

更新会创建新版本；每个版本的 agent 对象不可变。

```php
$updatedAgent = $client->beta->agents->update(
    $agent->id,
    version: $agent->version,
    system: 'You are a helpful coding agent. Always write tests.',
);
echo "New version: {$updatedAgent->version}\n";

// List all versions
foreach ($client->beta->agents->versions->list($agent->id)->pagingEachItem() as $version) {
    echo "Version {$version->version}: {$version->updatedAt->format(DateTimeInterface::ATOM)}\n";
}

// Archive the agent
$archived = $client->beta->agents->archive($agent->id);
echo "Archived at: {$archived->archivedAt->format(DateTimeInterface::ATOM)}\n";
```

---

## 发送用户消息

```php
$client->beta->sessions->events->send(
    $session->id,
    events: [
        [
            'type' => 'user.message',
            'content' => [['type' => 'text', 'text' => 'Review the auth module']],
        ],
    ],
);
```

> 💡 **先开流：** 在发送消息*之前*（或同时）打开流。流只会投递打开之后发生的事件 —— 先发送再开流，早期事件会缓冲成一批到达。见 [Steering Patterns](../../shared/managed-agents-events.md#steering-patterns)。

---

## 流式事件（SSE）

> ℹ️ **流式传输器：** PHP 默认的缓冲 PSR-18 客户端永远不会从开放式 session 事件流返回。对 `streamStream()` 调用使用流式 Guzzle 传输器 —— 其他调用继续用默认客户端。

```php
$streamingClient = new GuzzleHttp\Client(['stream' => true]);

// Open the stream first, then send the user message
$stream = $client->beta->sessions->events->streamStream(
    $session->id,
    requestOptions: ['transporter' => $streamingClient],
);
$client->beta->sessions->events->send(
    $session->id,
    events: [
        [
            'type' => 'user.message',
            'content' => [['type' => 'text', 'text' => 'Summarize the repo README']],
        ],
    ],
);

foreach ($stream as $event) {
    match ($event->type) {
        'agent.message' => array_walk(
            $event->content,
            static fn($block) => $block->type === 'text' ? print($block->text) : null,
        ),
        'agent.tool_use' => print("\n[Using tool: {$event->name}]\n"),
        'session.error' => printf("\n[Error: %s]", $event->error?->message ?? 'unknown'),
        default => null,
    };
    if ($event->type === 'session.status_idle' || $event->type === 'session.error') {
        break;
    }
}
$stream->close();
```

### 重连与跟踪

中途重连 session 时，先列出历史事件去重，再跟踪实时事件：

```php
$stream = $client->beta->sessions->events->streamStream(
    $session->id,
    requestOptions: ['transporter' => $streamingClient],
);

// Stream is open and buffering. List history before tailing live.
$seenEventIds = [];
foreach ($client->beta->sessions->events->list($session->id)->pagingEachItem() as $event) {
    $seenEventIds[$event->id] = true;
}

// Tail live events, skipping anything already seen
foreach ($stream as $event) {
    if (isset($seenEventIds[$event->id])) {
        continue;
    }
    $seenEventIds[$event->id] = true;
    match ($event->type) {
        'agent.message' => array_walk(
            $event->content,
            static fn($block) => $block->type === 'text' ? print($block->text) : null,
        ),
        default => null,
    };
    if ($event->type === 'session.status_idle') {
        break;
    }
}
$stream->close();
```

---

## 提供自定义工具结果

> ℹ️ PHP 的 managed-agents 对 `user.custom_tool_result` 的绑定尚未在本 skill 或 apps 源码示例中文档化。线格式见 `shared/managed-agents-events.md`，对应的 params 见 `anthropic-ai/sdk` PHP 仓库。

---

## 轮询事件

```php
foreach ($client->beta->sessions->events->list($session->id)->pagingEachItem() as $event) {
    echo "{$event->type}: {$event->id}\n";
}
```

---

## 上传文件

> ℹ️ **PHP 文件上传：** PHP SDK 的 beta managed-agents 文件上传绑定未出现在 apps 源码示例中；规范 PHP 示例使用原始 cURL 调用 `POST /v1/files`。若你的代码库更倾向 SDK，请在写代码前 WebFetch `anthropic-ai/sdk` PHP 仓库以获取最新绑定。

```php
use Anthropic\Beta\Sessions\BetaManagedAgentsFileResourceParams;

// Raw cURL upload (canonical example from the apps source)
$csvPath = 'data.csv';
$ch = curl_init('https://api.anthropic.com/v1/files');
curl_setopt_array($ch, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_POST => true,
    CURLOPT_HTTPHEADER => [
        'x-api-key: ' . getenv('ANTHROPIC_API_KEY'),
        'anthropic-version: 2023-06-01',
        'anthropic-beta: files-api-2025-04-14',
    ],
    CURLOPT_POSTFIELDS => ['file' => new CURLFile($csvPath, 'text/csv', 'data.csv')],
]);
$file = json_decode(curl_exec($ch));
echo "File ID: {$file->id}\n";

// Mount in a session
$session = $client->beta->sessions->create(
    agent: $agent->id,
    environmentID: $environment->id,
    resources: [
        BetaManagedAgentsFileResourceParams::with(
            type: 'file',
            fileID: $file->id,
            mountPath: '/workspace/data.csv',
        ),
    ],
);
```

### 在已有 Session 上添加与管理资源

```php
// Attach an additional file to an open session
$resource = $client->beta->sessions->resources->add(
    $session->id,
    type: 'file',
    fileID: $file->id,
);
echo "{$resource->id}\n"; // "sesrsc_01ABC..."

// List resources on the session
$listed = $client->beta->sessions->resources->list($session->id);
foreach ($listed->data as $entry) {
    echo "{$entry->id} {$entry->type}\n";
}

// Detach a resource
$client->beta->sessions->resources->delete($resource->id, sessionID: $session->id);
```

---

## 列出并下载 Session 文件

```php
$files = $client->beta->files->list(
    scopeID: 'sesn_abc123',
    betas: ['managed-agents-2026-04-01'],
);
$content = $client->beta->files->download($files->data[0]->id);
file_put_contents('output.txt', $content);
```

---

## Session 管理

```php
// List environments
$environments = $client->beta->environments->list();

// Retrieve a specific environment
$env = $client->beta->environments->retrieve($environment->id);

// Archive an environment (read-only, existing sessions continue)
$client->beta->environments->archive($environment->id);

// Delete an environment (only if no sessions reference it)
$client->beta->environments->delete($environment->id);

// Delete a session
$client->beta->sessions->delete($session->id);
```

---

## MCP 服务器集成

```php
use Anthropic\Beta\Agents\BetaManagedAgentsAgentToolset20260401Params;
use Anthropic\Beta\Agents\BetaManagedAgentsMCPToolsetParams;
use Anthropic\Beta\Agents\BetaManagedAgentsURLMCPServerParams;
use Anthropic\Beta\Sessions\BetaManagedAgentsAgentParams;

// Agent declares MCP server (no auth here — auth goes in a vault)
$agent = $client->beta->agents->create(
    name: 'GitHub Assistant',
    model: 'claude-opus-5',
    mcpServers: [
        BetaManagedAgentsURLMCPServerParams::with(
            type: 'url',
            name: 'github',
            url: 'https://api.githubcopilot.com/mcp/',
        ),
    ],
    tools: [
        BetaManagedAgentsAgentToolset20260401Params::with(type: 'agent_toolset_20260401'),
        BetaManagedAgentsMCPToolsetParams::with(
            type: 'mcp_toolset',
            mcpServerName: 'github',
        ),
    ],
);

// Session attaches vault(s) containing credentials for those MCP server URLs
$session = $client->beta->sessions->create(
    agent: BetaManagedAgentsAgentParams::with(
        type: 'agent',
        id: $agent->id,
        version: $agent->version,
    ),
    environmentID: $environment->id,
    vaultIDs: [$vault->id],
);
```

创建 vault 与添加凭据见 `shared/managed-agents-tools.md` 的 Vaults 一节。

---

## Vaults

```php
// Create a vault
$vault = $client->beta->vaults->create(
    displayName: 'Alice',
    metadata: ['external_user_id' => 'usr_abc123'],
);
echo $vault->id . "\n"; // "vlt_01ABC..."

// Add an OAuth credential
$credential = $client->beta->vaults->credentials->create(
    vaultID: $vault->id,
    displayName: "Alice's Slack",
    auth: [
        'type' => 'mcp_oauth',
        'mcp_server_url' => 'https://mcp.slack.com/mcp',
        'access_token' => 'xoxp-...',
        'expires_at' => '2026-04-15T00:00:00Z',
        'refresh' => [
            'token_endpoint' => 'https://slack.com/api/oauth.v2.access',
            'client_id' => '1234567890.0987654321',
            'scope' => 'channels:read chat:write',
            'refresh_token' => 'xoxe-1-...',
            'token_endpoint_auth' => [
                'type' => 'client_secret_post',
                'client_secret' => 'abc123...',
            ],
        ],
    ],
);

// Rotate the credential (e.g., after a token refresh)
$client->beta->vaults->credentials->update(
    $credential->id,
    vaultID: $vault->id,
    auth: [
        'type' => 'mcp_oauth',
        'access_token' => 'xoxp-new-...',
        'expires_at' => '2026-05-15T00:00:00Z',
        'refresh' => ['refresh_token' => 'xoxe-1-new-...'],
    ],
);

// Archive a vault
$client->beta->vaults->archive($vault->id);
```

---

## GitHub 仓库集成

将 GitHub 仓库挂载为 session 资源（vault 保存 GitHub MCP 凭据）：

```php
$session = $client->beta->sessions->create(
    agent: $agent->id,
    environmentID: $environment->id,
    vaultIDs: [$vault->id],
    resources: [
        [
            'type' => 'github_repository',
            'url' => 'https://github.com/org/repo',
            'mount_path' => '/workspace/repo',
            'authorization_token' => 'ghp_your_github_token',
        ],
    ],
);
```

同一 session 上挂载多个仓库：

```php
$resources = [
    [
        'type' => 'github_repository',
        'url' => 'https://github.com/org/frontend',
        'mount_path' => '/workspace/frontend',
        'authorization_token' => 'ghp_your_github_token',
    ],
    [
        'type' => 'github_repository',
        'url' => 'https://github.com/org/backend',
        'mount_path' => '/workspace/backend',
        'authorization_token' => 'ghp_your_github_token',
    ],
];
```

轮换仓库的授权令牌：

```php
$listed = $client->beta->sessions->resources->list($session->id);
$repoResourceId = $listed->data[0]->id;

$client->beta->sessions->resources->update(
    $repoResourceId,
    sessionID: $session->id,
    authorizationToken: 'ghp_your_new_github_token',
);
```
