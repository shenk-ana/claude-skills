# Managed Agents — Python

> [English](./README.md) | **中文**

> **此处未列出的绑定：** 本 README 覆盖 Python 上最常见的 managed-agents 流程。若需要未展示的类、方法、命名空间、字段或行为，请 WebFetch Python SDK 仓库 **或** `shared/live-sources.md` 中的相关文档页，不要猜测。不要从 cURL 形态或其他语言的 SDK 外推。

> **Agent 是持久的 —— 创建一次，之后用 ID 引用。** 保存 `agents.create` 返回的 agent ID，并在后续每次 `sessions.create` 中传入；不要在请求路径里调用 `agents.create`。**推荐：** 将 agent 和环境定义为纳入版本控制的 YAML，并用 `ant` CLI 应用 —— 见 `shared/anthropic-cli.md`（其在线文档 URL 在 `shared/live-sources.md`）。CLI 负责控制面（创建/更新）；你的代码负责数据面（用已保存的 ID 开 session）。下面的示例展示必须用代码预配时的创建方式；生产环境中，创建调用应放在初始化阶段，而不是请求路径里。

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
```

---

## 创建环境

```python
environment = client.beta.environments.create(
    name="my-dev-env",
    config={
        "type": "cloud",
        "networking": {"type": "unrestricted"},
    },
)
print(environment.id)  # env_...
```

---

## 创建 Agent（必做的第一步）

> ⚠️ **没有内联 agent 配置。** `model`/`system`/`tools` 在 agent 对象上，不在 session 上。始终先调用 `agents.create()` —— session 只接收 `agent={"type": "agent", "id": agent.id}`。

### 最小示例

```python
# 1. Create the agent (reusable, versioned)
agent = client.beta.agents.create(
    name="Coding Assistant",
    model="claude-opus-5",
    tools=[{"type": "agent_toolset_20260401", "default_config": {"enabled": True}}],
)

# 2. Start a session
session = client.beta.sessions.create(
    agent={"type": "agent", "id": agent.id, "version": agent.version},
    environment_id=environment.id,
)
print(session.id, session.status)
print(f"Trace: https://platform.claude.com/workspaces/default/sessions/{session.id}")  # swap 'default' for your workspace ID if the API key is not in the Default workspace
```

### 带系统提示和自定义工具

```python
import os

agent = client.beta.agents.create(
    name="Code Reviewer",
    model="claude-opus-5",
    system="You are a senior code reviewer.",
    tools=[
        {"type": "agent_toolset_20260401"},
        {
            "type": "custom",
            "name": "run_tests",
            "description": "Run the test suite",
            "input_schema": {
                "type": "object",
                "properties": {
                    "test_path": {"type": "string", "description": "Path to test file"}
                },
                "required": ["test_path"],
            },
        },
    ],
)

session = client.beta.sessions.create(
    agent={"type": "agent", "id": agent.id, "version": agent.version},
    environment_id=environment.id,
    title="Code review session",
    resources=[
        {
            "type": "github_repository",
            "url": "https://github.com/owner/repo",
            "mount_path": "/workspace/repo",
            "authorization_token": os.environ["GITHUB_TOKEN"],
            "branch": "main",
        }
    ],
)
```

---

## 发送用户消息

```python
client.beta.sessions.events.send(
    session_id=session.id,
    events=[
        {
            "type": "user.message",
            "content": [{"type": "text", "text": "Review the auth module"}],
        }
    ],
)
```

> 💡 **先开流：** 在发送消息*之前*（或同时）打开流。流只会投递打开之后发生的事件 —— 先发送再开流，早期事件会缓冲成一批到达。见 [Steering Patterns](../../shared/managed-agents-events.md#steering-patterns)。

---

## 流式事件（SSE）

```python
import json

# Stream-first: open stream, then send while stream is live
with client.beta.sessions.events.stream(
    session_id=session.id,
) as stream:
    client.beta.sessions.events.send(
        session_id=session.id,
        events=[{"type": "user.message", "content": [{"type": "text", "text": "..."}]}],
    )
    for event in stream:
        ...  # process events

# Standalone stream iteration:
with client.beta.sessions.events.stream(
    session_id=session.id,
) as stream:
    for event in stream:
        if event.type == "agent.message":
            for block in event.content:
                if block.type == "text":
                    print(block.text, end="", flush=True)
        elif event.type == "agent.custom_tool_use":
            # Custom tool invocation — session is now idle
            print(f"\nCustom tool call: {event.name}")
            print(f"Input: {json.dumps(event.input)}")
            # Send result back (see below)
        elif event.type == "session.status_idle":
            print("\n--- Agent idle ---")
        elif event.type == "session.status_terminated":
            print("\n--- Session terminated ---")
            break
```

---

## 提供自定义工具结果

```python
client.beta.sessions.events.send(
    session_id=session.id,
    events=[
        {
            "type": "user.custom_tool_result",
            "custom_tool_use_id": "sevt_abc123",
            "content": [{"type": "text", "text": "All 42 tests passed."}],
        }
    ],
)
```

---

## 轮询事件

```python
events = client.beta.sessions.events.list(
    session_id=session.id,
)
for event in events.data:
    print(f"{event.type}: {event.id}")
```

> ⚠️ **优先用 SDK，而不是裸的 `requests`/`httpx`。** 若手写轮询循环，不要假设 `timeout=(5, 60)` 或 `httpx.Timeout(120)` 会限制整次调用时长 —— 两者都是**按块**的读超时（每收到一个字节就重置），因此滴流式响应可能永远阻塞。需要硬性墙钟截止时，在循环层用 `time.monotonic()` 跟踪并显式退出，或用 `asyncio.wait_for()` 包裹。见 [Receiving Events](../../shared/managed-agents-events.md#receiving-events)。

---

## 带自定义工具的完整流式循环

```python
import json


def run_custom_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a custom tool and return the result."""
    if tool_name == "run_tests":
        # Your tool implementation here
        return "All tests passed."
    return f"Unknown tool: {tool_name}"


def run_session(client, session_id: str):
    """Stream events and handle custom tool calls."""
    while True:
        with client.beta.sessions.events.stream(
            session_id=session_id,
        ) as stream:
            tool_calls = []
            for event in stream:
                if event.type == "agent.message":
                    for block in event.content:
                        if block.type == "text":
                            print(block.text, end="", flush=True)
                elif event.type == "agent.custom_tool_use":
                    tool_calls.append(event)
                elif event.type == "session.status_idle":
                    break
                elif event.type == "session.status_terminated":
                    return

        if not tool_calls:
            break

        # Process custom tool calls
        results = []
        for call in tool_calls:
            result = run_custom_tool(call.name, call.input)
            results.append({
                "type": "user.custom_tool_result",
                "custom_tool_use_id": call.id,
                "content": [{"type": "text", "text": result}],
            })

        client.beta.sessions.events.send(
            session_id=session_id,
            events=results,
        )
```

---

## 上传文件

```python
with open("data.csv", "rb") as f:
    file = client.beta.files.upload(
        file=f,
    )

# Use in a session
session = client.beta.sessions.create(
    agent={"type": "agent", "id": agent.id, "version": agent.version},
    environment_id=environment.id,
    resources=[{"type": "file", "file_id": file.id, "mount_path": "/workspace/data.csv"}],
)
```

---

## 列出并下载 Session 文件

列出 agent 在 session 期间写入 `/mnt/session/outputs/` 的文件，然后下载。

```python
# List files associated with a session
files = client.beta.files.list(
    scope_id=session.id,
    betas=["managed-agents-2026-04-01"],
)
for f in files.data:
    print(f.filename, f.size_bytes)
    # Download each file and save to disk
    file_content = client.beta.files.download(f.id)
    file_content.write_to_file(f.filename)
```

> 💡 在 `session.status_idle` 与输出文件出现在 `files.list` 之间，会有短暂索引延迟（约 1–3 秒）。若列表为空，重试一两次。

---

## Session 管理

```python
# Get session details
session = client.beta.sessions.retrieve(session_id="sesn_011CZxAbc123Def456")
print(session.status, session.usage)

# List sessions
sessions = client.beta.sessions.list()

# Delete a session
client.beta.sessions.delete(session_id="sesn_011CZxAbc123Def456")

# Archive a session
client.beta.sessions.archive(session_id="sesn_011CZxAbc123Def456")
```

---

## MCP 服务器集成

```python
# Agent declares MCP server (no auth here — auth goes in a vault)
agent = client.beta.agents.create(
    name="MCP Agent",
    model="claude-opus-5",
    mcp_servers=[
        {"type": "url", "name": "my-tools", "url": "https://my-mcp-server.example.com/sse"},
    ],
    tools=[
        {"type": "agent_toolset_20260401", "default_config": {"enabled": True}},
        {"type": "mcp_toolset", "mcp_server_name": "my-tools"},
    ],
)

# Session attaches vault(s) containing credentials for those MCP server URLs
session = client.beta.sessions.create(
    agent=agent.id,
    environment_id=environment.id,
    vault_ids=[vault.id],
)
```

创建 vault 与添加凭据见 `shared/managed-agents-tools.md` 的 Vaults 一节。
