# Managed Agents — Java

> [English](./README.md) | **中文**

> **此处未列出的绑定：** 本 README 覆盖 Java 上最常见的 managed-agents 流程。若需要未展示的类、方法、命名空间、字段或行为，请 WebFetch Java SDK 仓库 **或** `shared/live-sources.md` 中的相关文档页，不要猜测。不要从 cURL 形态或其他语言的 SDK 外推。

> **Agent 是持久的 —— 创建一次，之后用 ID 引用。** 保存 `client.beta().agents().create` 返回的 agent ID，并在后续每次 `client.beta().sessions().create` 中传入；不要在请求路径里调用 `agents().create`。**推荐：** 将 agent 和环境定义为纳入版本控制的 YAML，并用 `ant` CLI 应用 —— 见 `shared/anthropic-cli.md`（其在线文档 URL 在 `shared/live-sources.md`）。CLI 负责控制面（创建/更新）；你的代码负责数据面（用已保存的 ID 开 session）。下面的示例展示必须用代码预配时的创建方式；生产环境中，创建调用应放在初始化阶段，而不是请求路径里。

## 安装

```xml
<dependency>
    <groupId>com.anthropic</groupId>
    <artifactId>anthropic-java</artifactId>
</dependency>
```

## 初始化客户端

```java
import com.anthropic.client.okhttp.AnthropicOkHttpClient;

// Default (uses ANTHROPIC_API_KEY env var)
var client = AnthropicOkHttpClient.fromEnv();
```

---

## 创建环境

```java
import com.anthropic.models.beta.environments.BetaCloudConfigParams;
import com.anthropic.models.beta.environments.BetaUnrestrictedNetwork;
import com.anthropic.models.beta.environments.EnvironmentCreateParams;

var environment = client.beta().environments().create(EnvironmentCreateParams.builder()
    .name("my-dev-env")
    .config(BetaCloudConfigParams.builder()
        .networking(BetaUnrestrictedNetwork.builder().build())
        .build())
    .build());
System.out.println("Environment ID: " + environment.id()); // env_...
```

---

## 创建 Agent（必做的第一步）

> ⚠️ **没有内联 agent 配置。** model、system 和 tools 在 agent 对象上，不在 session 上。始终先调用 `client.beta().agents().create()` —— session 接收 `.agent(agent.id())` 或类型化的 `BetaManagedAgentsAgentParams.builder()...build()`。

### 最小示例

```java
import com.anthropic.models.beta.agents.AgentCreateParams;
import com.anthropic.models.beta.agents.BetaManagedAgentsAgentToolset20260401Params;
import com.anthropic.models.beta.sessions.BetaManagedAgentsAgentParams;
import com.anthropic.models.beta.sessions.SessionCreateParams;

// 1. Create the agent (reusable, versioned)
var agent = client.beta().agents().create(AgentCreateParams.builder()
    .name("Coding Assistant")
    .model("claude-opus-5")
    .system("You are a helpful coding assistant.")
    .addTool(BetaManagedAgentsAgentToolset20260401Params.builder()
        .type(BetaManagedAgentsAgentToolset20260401Params.Type.AGENT_TOOLSET_20260401)
        .build())
    .build());

// 2. Start a session
var session = client.beta().sessions().create(SessionCreateParams.builder()
    .agent(BetaManagedAgentsAgentParams.builder()
        .type(BetaManagedAgentsAgentParams.Type.AGENT)
        .id(agent.id())
        .version(agent.version())
        .build())
    .environmentId(environment.id())
    .title("Quickstart session")
    .build());
System.out.println("Session ID: " + session.id());
System.out.println("Trace: https://platform.claude.com/workspaces/default/sessions/" + session.id()); // swap 'default' for your workspace ID if the API key is not in the Default workspace
```

### 更新 Agent

更新会创建新版本；每个版本的 agent 对象不可变。

```java
import com.anthropic.models.beta.agents.AgentUpdateParams;

var updatedAgent = client.beta().agents().update(agent.id(), AgentUpdateParams.builder()
    .version(agent.version())
    .system("You are a helpful coding agent. Always write tests.")
    .build());
System.out.println("New version: " + updatedAgent.version());

// List all versions
for (var version : client.beta().agents().versions().list(agent.id()).autoPager()) {
    System.out.println("Version " + version.version() + ": " + version.updatedAt());
}

// Archive the agent
var archived = client.beta().agents().archive(agent.id());
System.out.println("Archived at: " + archived.archivedAt().orElseThrow());
```

---

## 发送用户消息

```java
import com.anthropic.models.beta.sessions.events.BetaManagedAgentsUserMessageEventParams;
import com.anthropic.models.beta.sessions.events.EventSendParams;

client.beta().sessions().events().send(session.id(), EventSendParams.builder()
    .addEvent(BetaManagedAgentsUserMessageEventParams.builder()
        .type(BetaManagedAgentsUserMessageEventParams.Type.USER_MESSAGE)
        .addTextContent("Review the auth module")
        .build())
    .build());
```

> 💡 **先开流：** 在发送消息*之前*（或同时）打开流。流只会投递打开之后发生的事件 —— 先发送再开流，早期事件会缓冲成一批到达。见 [Steering Patterns](../../shared/managed-agents-events.md#steering-patterns)。

---

## 流式事件（SSE）

```java
import com.anthropic.models.beta.sessions.events.StreamEvents;

// Open the stream first, then send the user message
try (var stream = client.beta().sessions().events().streamStreaming(session.id())) {
    client.beta().sessions().events().send(session.id(), EventSendParams.builder()
        .addEvent(BetaManagedAgentsUserMessageEventParams.builder()
            .type(BetaManagedAgentsUserMessageEventParams.Type.USER_MESSAGE)
            .addTextContent("Summarize the repo README")
            .build())
        .build());

    for (var event : (Iterable<StreamEvents>) stream.stream()::iterator) {
        if (event.isAgentMessage()) {
            event.asAgentMessage().content().forEach(block -> System.out.print(block.text()));
        } else if (event.isAgentToolUse()) {
            System.out.println("\n[Using tool: " + event.asAgentToolUse().name() + "]");
        } else if (event.isSessionStatusIdle()) {
            break;
        } else if (event.isSessionError()) {
            System.out.println("\n[Error]");
            break;
        }
    }
}
```

### 重连与跟踪

中途重连 session 时，先列出历史事件去重，再跟踪实时事件。跨变体的 `id` 字段从原始 `_json()` 值读取：

```java
import com.anthropic.core.JsonValue;
import java.util.HashSet;
import java.util.Map;
import java.util.Optional;

try (var stream = client.beta().sessions().events().streamStreaming(session.id())) {
    // Stream is open and buffering. List history before tailing live.
    var seenEventIds = new HashSet<String>();
    for (var past : client.beta().sessions().events().list(session.id()).autoPager()) {
        Optional<Map<String, JsonValue>> obj = past._json().orElseThrow().asObject();
        seenEventIds.add(obj.orElseThrow().get("id").asStringOrThrow());
    }

    // Tail live events, skipping anything already seen
    for (var event : (Iterable<StreamEvents>) stream.stream()::iterator) {
        Optional<Map<String, JsonValue>> obj = event._json().orElseThrow().asObject();
        if (!seenEventIds.add(obj.orElseThrow().get("id").asStringOrThrow())) continue;
        if (event.isAgentMessage()) {
            event.asAgentMessage().content().forEach(block -> System.out.print(block.text()));
        } else if (event.isSessionStatusIdle()) {
            break;
        }
    }
}
```

---

## 提供自定义工具结果

> ℹ️ Java 的 managed-agents 对 `user.custom_tool_result` 的绑定尚未在本 skill 或 apps 源码示例中文档化。线格式见 `shared/managed-agents-events.md`，对应的 params 类型见 `anthropic-java` 仓库。

---

## 轮询事件

```java
for (var event : client.beta().sessions().events().list(session.id()).autoPager()) {
    System.out.println(event.type() + ": " + event);
}
```

---

## 上传文件

```java
import com.anthropic.models.beta.files.FileUploadParams;
import com.anthropic.models.beta.sessions.BetaManagedAgentsFileResourceParams;
import java.nio.file.Path;

var dataCsv = Path.of("data.csv");

var file = client.beta().files().upload(FileUploadParams.builder()
    .file(dataCsv)
    .build());
System.out.println("File ID: " + file.id());

// Mount in a session
var session = client.beta().sessions().create(SessionCreateParams.builder()
    .agent(agent.id())
    .environmentId(environment.id())
    .addResource(BetaManagedAgentsFileResourceParams.builder()
        .type(BetaManagedAgentsFileResourceParams.Type.FILE)
        .fileId(file.id())
        .mountPath("/workspace/data.csv")
        .build())
    .build());
```

### 在已有 Session 上添加与管理资源

```java
import com.anthropic.models.beta.sessions.resources.ResourceAddParams;
import com.anthropic.models.beta.sessions.resources.ResourceDeleteParams;

// Attach an additional file to an open session
var resource = client.beta().sessions().resources().add(session.id(), ResourceAddParams.builder()
    .betaManagedAgentsFileResourceParams(BetaManagedAgentsFileResourceParams.builder()
        .type(BetaManagedAgentsFileResourceParams.Type.FILE)
        .fileId(file.id())
        .build())
    .build());
System.out.println(resource.id()); // "sesrsc_01ABC..."

// List resources on the session — entries are a discriminated union
var listed = client.beta().sessions().resources().list(session.id());
for (var entry : listed.data()) {
    if (entry.isFile()) {
        var fileResource = entry.asFile();
        System.out.println(fileResource.id() + " " + fileResource.type());
    } else if (entry.isGitHubRepository()) {
        var repoResource = entry.asGitHubRepository();
        System.out.println(repoResource.id() + " " + repoResource.type());
    }
}

// Detach a resource
client.beta().sessions().resources().delete(resource.id(), ResourceDeleteParams.builder()
    .sessionId(session.id())
    .build());
```

---

## 列出并下载 Session 文件

> ℹ️ 列出并下载 agent 在 session 期间写入的文件，目前尚未在本 skill 或 apps 源码示例中为 Java 文档化。见 `shared/managed-agents-events.md` 以及 `anthropic-java` 仓库中的文件列表/下载绑定。

---

## Session 管理

```java
// List environments
var environments = client.beta().environments().list();

// Retrieve a specific environment
var env = client.beta().environments().retrieve(environment.id());

// Archive an environment (read-only, existing sessions continue)
client.beta().environments().archive(environment.id());

// Delete an environment (only if no sessions reference it)
client.beta().environments().delete(environment.id());

// Delete a session
client.beta().sessions().delete(session.id());
```

---

## MCP 服务器集成

```java
import com.anthropic.models.beta.agents.BetaManagedAgentsMcpToolsetParams;
import com.anthropic.models.beta.agents.BetaManagedAgentsUrlMcpServerParams;

// Agent declares MCP server (no auth here — auth goes in a vault)
var agent = client.beta().agents().create(AgentCreateParams.builder()
    .name("GitHub Assistant")
    .model("claude-opus-5")
    .addMcpServer(BetaManagedAgentsUrlMcpServerParams.builder()
        .type(BetaManagedAgentsUrlMcpServerParams.Type.URL)
        .name("github")
        .url("https://api.githubcopilot.com/mcp/")
        .build())
    .addTool(BetaManagedAgentsAgentToolset20260401Params.builder()
        .type(BetaManagedAgentsAgentToolset20260401Params.Type.AGENT_TOOLSET_20260401)
        .build())
    .addTool(BetaManagedAgentsMcpToolsetParams.builder()
        .type(BetaManagedAgentsMcpToolsetParams.Type.MCP_TOOLSET)
        .mcpServerName("github")
        .build())
    .build());

// Session attaches vault(s) containing credentials for those MCP server URLs
var session = client.beta().sessions().create(SessionCreateParams.builder()
    .agent(BetaManagedAgentsAgentParams.builder()
        .type(BetaManagedAgentsAgentParams.Type.AGENT)
        .id(agent.id())
        .version(agent.version())
        .build())
    .environmentId(environment.id())
    .addVaultId(vault.id())
    .build());
```

创建 vault 与添加凭据见 `shared/managed-agents-tools.md` 的 Vaults 一节。

---

## Vaults

```java
import com.anthropic.core.JsonValue;
import com.anthropic.models.beta.vaults.VaultCreateParams;
import com.anthropic.models.beta.vaults.credentials.BetaManagedAgentsMcpOAuthCreateParams;
import com.anthropic.models.beta.vaults.credentials.BetaManagedAgentsMcpOAuthRefreshParams;
import com.anthropic.models.beta.vaults.credentials.BetaManagedAgentsMcpOAuthRefreshUpdateParams;
import com.anthropic.models.beta.vaults.credentials.BetaManagedAgentsMcpOAuthUpdateParams;
import com.anthropic.models.beta.vaults.credentials.CredentialCreateParams;
import com.anthropic.models.beta.vaults.credentials.CredentialUpdateParams;
import java.time.OffsetDateTime;

// Create a vault
var vault = client.beta().vaults().create(VaultCreateParams.builder()
    .displayName("Alice")
    .metadata(VaultCreateParams.Metadata.builder()
        .putAdditionalProperty("external_user_id", JsonValue.from("usr_abc123"))
        .build())
    .build());
System.out.println(vault.id()); // "vlt_01ABC..."

// Add an OAuth credential
var credential = client.beta().vaults().credentials().create(vault.id(),
    CredentialCreateParams.builder()
        .displayName("Alice's Slack")
        .auth(BetaManagedAgentsMcpOAuthCreateParams.builder()
            .type(BetaManagedAgentsMcpOAuthCreateParams.Type.MCP_OAUTH)
            .mcpServerUrl("https://mcp.slack.com/mcp")
            .accessToken("xoxp-...")
            .expiresAt(OffsetDateTime.parse("2026-04-15T00:00:00Z"))
            .refresh(BetaManagedAgentsMcpOAuthRefreshParams.builder()
                .tokenEndpoint("https://slack.com/api/oauth.v2.access")
                .clientId("1234567890.0987654321")
                .scope("channels:read chat:write")
                .refreshToken("xoxe-1-...")
                .clientSecretPostTokenEndpointAuth("abc123...")
                .build())
            .build())
        .build());

// Rotate the credential (e.g., after a token refresh)
client.beta().vaults().credentials().update(credential.id(),
    CredentialUpdateParams.builder()
        .vaultId(vault.id())
        .auth(BetaManagedAgentsMcpOAuthUpdateParams.builder()
            .type(BetaManagedAgentsMcpOAuthUpdateParams.Type.MCP_OAUTH)
            .accessToken("xoxp-new-...")
            .expiresAt(OffsetDateTime.parse("2026-05-15T00:00:00Z"))
            .refresh(BetaManagedAgentsMcpOAuthRefreshUpdateParams.builder()
                .refreshToken("xoxe-1-new-...")
                .build())
            .build())
        .build());

// Archive a vault
client.beta().vaults().archive(vault.id());
```

---

## GitHub 仓库集成

将 GitHub 仓库挂载为 session 资源（vault 保存 GitHub MCP 凭据）：

```java
import com.anthropic.models.beta.sessions.BetaManagedAgentsGitHubRepositoryResourceParams;

var session = client.beta().sessions().create(SessionCreateParams.builder()
    .agent(agent.id())
    .environmentId(environment.id())
    .addVaultId(vault.id())
    .addResource(BetaManagedAgentsGitHubRepositoryResourceParams.builder()
        .type(BetaManagedAgentsGitHubRepositoryResourceParams.Type.GITHUB_REPOSITORY)
        .url("https://github.com/org/repo")
        .mountPath("/workspace/repo")
        .authorizationToken("ghp_your_github_token")
        .build())
    .build());
```

同一 session 上挂载多个仓库：

```java
import java.util.List;

var resources = List.of(
    BetaManagedAgentsGitHubRepositoryResourceParams.builder()
        .type(BetaManagedAgentsGitHubRepositoryResourceParams.Type.GITHUB_REPOSITORY)
        .url("https://github.com/org/frontend")
        .mountPath("/workspace/frontend")
        .authorizationToken("ghp_your_github_token")
        .build(),
    BetaManagedAgentsGitHubRepositoryResourceParams.builder()
        .type(BetaManagedAgentsGitHubRepositoryResourceParams.Type.GITHUB_REPOSITORY)
        .url("https://github.com/org/backend")
        .mountPath("/workspace/backend")
        .authorizationToken("ghp_your_github_token")
        .build());
```

轮换仓库的授权令牌：

```java
import com.anthropic.models.beta.sessions.resources.ResourceUpdateParams;

var listed = client.beta().sessions().resources().list(session.id());
var repoResourceId = listed.data().get(0).asGitHubRepository().id();

client.beta().sessions().resources().update(repoResourceId, ResourceUpdateParams.builder()
    .sessionId(session.id())
    .authorizationToken("ghp_your_new_github_token")
    .build());
```
