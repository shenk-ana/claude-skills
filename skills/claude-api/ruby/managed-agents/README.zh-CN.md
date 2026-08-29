# Managed Agents — Ruby

> [English](./README.md) | **中文**

> **此处未列出的绑定：** 本 README 覆盖 Ruby 上最常见的 managed-agents 流程。若需要未展示的类、方法、命名空间、字段或行为，请 WebFetch Ruby SDK 仓库 **或** `shared/live-sources.md` 中的相关文档页，不要猜测。不要从 cURL 形态或其他语言的 SDK 外推。

> **Agent 是持久的 —— 创建一次，之后用 ID 引用。** 保存 `client.beta.agents.create` 返回的 agent ID，并在后续每次 `client.beta.sessions.create` 中传入；不要在请求路径里调用 `agents.create`。**推荐：** 将 agent 和环境定义为纳入版本控制的 YAML，并用 `ant` CLI 应用 —— 见 `shared/anthropic-cli.md`（其在线文档 URL 在 `shared/live-sources.md`）。CLI 负责控制面（创建/更新）；你的代码负责数据面（用已保存的 ID 开 session）。下面的示例展示必须用代码预配时的创建方式；生产环境中，创建调用应放在初始化阶段，而不是请求路径里。

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

> ⚠️ **末尾下划线：** Ruby SDK 使用 `system_:` 和 `send_(`（末尾下划线）以避免遮蔽 `Kernel#system` 和 `Kernel#send`。在 managed-agents 代码中请始终使用这些形式。

---

## 创建环境

```ruby
environment = client.beta.environments.create(
  name: "my-dev-env",
  config: {
    type: "cloud",
    networking: {type: "unrestricted"}
  }
)
puts "Environment ID: #{environment.id}" # env_...
```

---

## 创建 Agent（必做的第一步）

> ⚠️ **没有内联 agent 配置。** `model`/`system_`/`tools` 在 agent 对象上，不在 session 上。始终先调用 `client.beta.agents.create()` —— session 接收 `agent: agent.id` 或类型化 hash 形式 `agent: {type: "agent", id: agent.id, version: agent.version}`。

### 最小示例

```ruby
# 1. Create the agent (reusable, versioned)
agent = client.beta.agents.create(
  name: "Coding Assistant",
  model: :"claude-opus-5",
  system_: "You are a helpful coding assistant.",
  tools: [{type: "agent_toolset_20260401"}]
)

# 2. Start a session
session = client.beta.sessions.create(
  agent: {type: "agent", id: agent.id, version: agent.version},
  environment_id: environment.id,
  title: "Quickstart session"
)
puts "Session ID: #{session.id}"
puts "Trace: https://platform.claude.com/workspaces/default/sessions/#{session.id}"  # swap 'default' for your workspace ID if the API key is not in the Default workspace
```

### 更新 Agent

更新会创建新版本；每个版本的 agent 对象不可变。

```ruby
updated_agent = client.beta.agents.update(
  agent.id,
  version: agent.version,
  system_: "You are a helpful coding agent. Always write tests."
)
puts "New version: #{updated_agent.version}"

# List all versions
client.beta.agents.versions.list(agent.id).auto_paging_each do |version|
  puts "Version #{version.version}: #{version.updated_at.iso8601}"
end

# Archive the agent
archived = client.beta.agents.archive(agent.id)
puts "Archived at: #{archived.archived_at.iso8601}"
```

---

## 发送用户消息

```ruby
client.beta.sessions.events.send_(
  session.id,
  events: [{
    type: "user.message",
    content: [{type: "text", text: "Review the auth module"}]
  }]
)
```

> 💡 **先开流：** 在发送消息*之前*（或同时）打开流。流只会投递打开之后发生的事件 —— 先发送再开流，早期事件会缓冲成一批到达。见 [Steering Patterns](../../shared/managed-agents-events.md#steering-patterns)。

---

## 流式事件（SSE）

```ruby
# Open the stream first, then send the user message
stream = client.beta.sessions.events.stream_events(session.id)

client.beta.sessions.events.send_(
  session.id,
  events: [{
    type: "user.message",
    content: [{type: "text", text: "Summarize the repo README"}]
  }]
)

stream.each do |event|
  case event.type
  in :"agent.message"
    event.content.each { |block| print block.text }
  in :"agent.tool_use"
    puts "\n[Using tool: #{event.name}]"
  in :"session.status_idle"
    break
  in :"session.error"
    puts "\n[Error: #{event.error&.message || "unknown"}]"
    break
  else
    # ignore other event types
  end
end
```

> ℹ️ 事件的 `.type` 是 Symbol（与 `:"agent.message"` 比较，而不是 `"agent.message"`）。

### 重连与跟踪

中途重连 session 时，先列出历史事件去重，再跟踪实时事件：

```ruby
require "set"

stream = client.beta.sessions.events.stream_events(session.id)

# Stream is open and buffering. List history before tailing live.
seen_event_ids = Set.new
client.beta.sessions.events.list(session.id).auto_paging_each { |past| seen_event_ids << past.id }

# Tail live events, skipping anything already seen
stream.each do |event|
  next if seen_event_ids.include?(event.id)
  seen_event_ids << event.id
  case event.type
  in :"agent.message"
    event.content.each { |block| print block.text }
  in :"session.status_idle"
    break
  else
    # ignore other event types
  end
end
```

---

## 提供自定义工具结果

> ℹ️ Ruby 的 managed-agents 对 `user.custom_tool_result` 的绑定尚未在本 skill 或 apps 源码示例中文档化。线格式见 `shared/managed-agents-events.md`，对应的 params 见 `anthropic` Ruby gem 仓库。

---

## 轮询事件

```ruby
client.beta.sessions.events.list(session.id).auto_paging_each do |event|
  puts "#{event.type}: #{event.id}"
end
```

---

## 上传文件

```ruby
require "pathname"

file = client.beta.files.upload(file: Pathname("data.csv"))
puts "File ID: #{file.id}"

# Mount in a session
session = client.beta.sessions.create(
  agent: agent.id,
  environment_id: environment.id,
  resources: [
    {
      type: "file",
      file_id: file.id,
      mount_path: "/workspace/data.csv"
    }
  ]
)
```

### 在已有 Session 上添加与管理资源

```ruby
# Attach an additional file to an open session
resource = client.beta.sessions.resources.add(
  session.id,
  type: "file",
  file_id: file.id
)
puts resource.id # "sesrsc_01ABC..."

# List resources on the session
listed = client.beta.sessions.resources.list(session.id)
listed.data.each { |entry| puts "#{entry.id} #{entry.type}" }

# Detach a resource
client.beta.sessions.resources.delete(resource.id, session_id: session.id)
```

---

## 列出并下载 Session 文件

```ruby
files = client.beta.files.list(scope_id: "sesn_abc123", betas: ["managed-agents-2026-04-01"])
content = client.beta.files.download(files.data[0].id)
File.binwrite("output.txt", content.read)
```

---

## Session 管理

```ruby
# List environments
environments = client.beta.environments.list

# Retrieve a specific environment
env = client.beta.environments.retrieve(environment.id)

# Archive an environment (read-only, existing sessions continue)
client.beta.environments.archive(environment.id)

# Delete an environment (only if no sessions reference it)
client.beta.environments.delete(environment.id)

# Delete a session
client.beta.sessions.delete(session.id)
```

---

## MCP 服务器集成

```ruby
# Agent declares MCP server (no auth here — auth goes in a vault)
agent = client.beta.agents.create(
  name: "GitHub Assistant",
  model: :"claude-opus-5",
  mcp_servers: [
    {
      type: "url",
      name: "github",
      url: "https://api.githubcopilot.com/mcp/"
    }
  ],
  tools: [
    {type: "agent_toolset_20260401"},
    {type: "mcp_toolset", mcp_server_name: "github"}
  ]
)

# Session attaches vault(s) containing credentials for those MCP server URLs
session = client.beta.sessions.create(
  agent: {type: "agent", id: agent.id, version: agent.version},
  environment_id: environment.id,
  vault_ids: [vault.id]
)
```

创建 vault 与添加凭据见 `shared/managed-agents-tools.md` 的 Vaults 一节。

---

## Vaults

```ruby
# Create a vault
vault = client.beta.vaults.create(
  display_name: "Alice",
  metadata: {external_user_id: "usr_abc123"}
)
puts vault.id # "vlt_01ABC..."

# Add an OAuth credential
credential = client.beta.vaults.credentials.create(
  vault.id,
  display_name: "Alice's Slack",
  auth: {
    type: "mcp_oauth",
    mcp_server_url: "https://mcp.slack.com/mcp",
    access_token: "xoxp-...",
    expires_at: "2026-04-15T00:00:00Z",
    refresh: {
      token_endpoint: "https://slack.com/api/oauth.v2.access",
      client_id: "1234567890.0987654321",
      scope: "channels:read chat:write",
      refresh_token: "xoxe-1-...",
      token_endpoint_auth: {
        type: "client_secret_post",
        client_secret: "abc123..."
      }
    }
  }
)

# Rotate the credential (e.g., after a token refresh)
client.beta.vaults.credentials.update(
  credential.id,
  vault_id: vault.id,
  auth: {
    type: "mcp_oauth",
    access_token: "xoxp-new-...",
    expires_at: "2026-05-15T00:00:00Z",
    refresh: {refresh_token: "xoxe-1-new-..."}
  }
)

# Archive a vault
client.beta.vaults.archive(vault.id)
```

---

## GitHub 仓库集成

将 GitHub 仓库挂载为 session 资源（vault 保存 GitHub MCP 凭据）：

```ruby
session = client.beta.sessions.create(
  agent: agent.id,
  environment_id: environment.id,
  vault_ids: [vault.id],
  resources: [
    {
      type: "github_repository",
      url: "https://github.com/org/repo",
      mount_path: "/workspace/repo",
      authorization_token: "ghp_your_github_token"
    }
  ]
)
```

同一 session 上挂载多个仓库：

```ruby
resources = [
  {
    type: "github_repository",
    url: "https://github.com/org/frontend",
    mount_path: "/workspace/frontend",
    authorization_token: "ghp_your_github_token"
  },
  {
    type: "github_repository",
    url: "https://github.com/org/backend",
    mount_path: "/workspace/backend",
    authorization_token: "ghp_your_github_token"
  }
]
```

轮换仓库的授权令牌：

```ruby
listed = client.beta.sessions.resources.list(session.id)
repo_resource_id = listed.data.first.id

client.beta.sessions.resources.update(
  repo_resource_id,
  session_id: session.id,
  authorization_token: "ghp_your_new_github_token"
)
```
