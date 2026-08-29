> **说明：** 本仓库收录 Anthropic 为 Claude 实现的 Skills。关于 Agent Skills 标准，请参阅 [agentskills.io](http://agentskills.io)。
>
> [English](./README.md) | **中文**

[![skills.sh](https://skills.sh/b/anthropics/skills)](https://skills.sh/anthropics/skills)

# Skills

Skills 是一组指令、脚本和资源组成的文件夹。Claude 会按需动态加载它们，以提升在专项任务上的表现。Skills 能让 Claude 以可重复的方式完成特定任务：例如按公司品牌规范创建文档、按组织内部流程分析数据，或自动化个人事务。

更多信息请参阅：
- [什么是 Skills？](https://support.claude.com/en/articles/12512176-what-are-skills)
- [在 Claude 中使用 Skills](https://support.claude.com/en/articles/12512180-using-skills-in-claude)
- [如何创建自定义 Skills](https://support.claude.com/en/articles/12512198-creating-custom-skills)
- [用 Agent Skills 让智能体真正落地](https://anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)

# 关于本仓库

本仓库收录的 Skills 用于展示 Claude Skills 体系能做到什么。范围从创意应用（艺术、音乐、设计），到技术任务（Web 应用测试、MCP 服务器生成），再到企业工作流（沟通、品牌等）。

每个 Skill 都独立放在各自的文件夹中，其中的 `SKILL.md` 包含 Claude 使用的指令和元数据。浏览这些 Skills，可以为你自己的 Skill 获取灵感，或了解不同的模式与做法。

仓库中的许多 Skills 以开源协议发布（Apache 2.0）。我们也收录了支撑 [Claude 文档能力](https://www.anthropic.com/news/create-files) 的文档创建与编辑 Skills，位于 [`skills/docx`](./skills/docx)、[`skills/pdf`](./skills/pdf)、[`skills/pptx`](./skills/pptx) 和 [`skills/xlsx`](./skills/xlsx)。这些是源码可见（source-available），并非开源，但我们希望把它们分享给开发者，作为生产级 AI 应用中更复杂 Skills 的参考。

## 免责声明

**这些 Skills 仅用于演示与教学。** 即便 Claude 中提供了部分能力，你从 Claude 获得的实现与行为也可能与这些 Skills 中展示的不同。它们意在说明模式与可能性。在将 Skills 用于关键任务之前，请务必在自己的环境中充分测试。

# Skill 集合
- [./skills](./skills)：创意与设计、开发与技术、企业与沟通，以及文档类 Skill 示例
- [./spec](./spec)：Agent Skills 规范
- [./template](./template)：Skill 模板

# 在 Claude Code、Claude.ai 和 API 中试用

## Claude Code
可在 Claude Code 中运行以下命令，将本仓库注册为 Claude Code 插件市场：
```
/plugin marketplace add anthropics/skills
```

然后安装某一组 Skills：
1. 选择 `Browse and install plugins`
2. 选择 `anthropic-agent-skills`
3. 选择 `document-skills` 或 `example-skills`
4. 选择 `Install now`

也可以直接安装任一插件：
```
/plugin install document-skills@anthropic-agent-skills
/plugin install example-skills@anthropic-agent-skills
```

安装插件后，只需在对话中提及该 Skill 即可使用。例如，从市场安装 `document-skills` 插件后，可以对 Claude Code 说：「用 PDF skill 从 `path/to/some-file.pdf` 提取表单字段」。

## Claude.ai

这些示例 Skills 已对 Claude.ai 的付费套餐开放。

要使用本仓库中的任意 Skill，或上传自定义 Skills，请按照 [在 Claude 中使用 Skills](https://support.claude.com/en/articles/12512180-using-skills-in-claude#h_a4222fa77b) 中的说明操作。

## Claude API

可通过 Claude API 使用 Anthropic 预置的 Skills，也可上传自定义 Skills。详见 [Skills API 快速入门](https://docs.claude.com/en/api/skills-guide#creating-a-skill)。

# 创建基础 Skill

创建 Skill 很简单——只需一个包含 `SKILL.md` 的文件夹，文件中带有 YAML frontmatter 和指令。可以使用本仓库中的 **template-skill** 作为起点：

```markdown
---
name: my-skill-name
description: A clear description of what this skill does and when to use it
---

# My Skill Name

[Add your instructions here that Claude will follow when this skill is active]

## Examples
- Example usage 1
- Example usage 2

## Guidelines
- Guideline 1
- Guideline 2
```

frontmatter 只需要两个字段：
- `name` - Skill 的唯一标识符（小写，空格用连字符）
- `description` - 完整说明该 Skill 做什么、何时使用

下方的 Markdown 内容是 Claude 会遵循的指令、示例和指南。更多细节见 [如何创建自定义 Skills](https://support.claude.com/en/articles/12512198-creating-custom-skills)。

# 合作方 Skills

Skills 很适合用来教 Claude 更好地使用特定软件。当我们看到优秀的合作方示例 Skills 时，可能会在此收录：

- **Notion** - [Notion Skills for Claude](https://www.notion.so/notiondevs/Notion-Skills-for-Claude-28da4445d27180c7af1df7d8615723d0)
