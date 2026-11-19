# Customizations in this fork

This fork tracks [anthropics/skills](https://github.com/anthropics/skills).
Keep local changes in **new files** wherever possible; edit upstream files only by small, isolated lines.
When syncing hits a conflict, this list says which side is ours.

## Edited upstream files (conflict candidates)

| File | Change | On conflict |
|---|---|---|
| `.claude-plugin/marketplace.json` | `name` → `sk-anthropic-agent-skills` (so it does not clash with Anthropic's own plugin) | Keep ours for `name`, take upstream for everything else |
| `README.md` | Language switch line `**English** \| [中文](./README.zh-CN.md)` | Take upstream, then re-add the line |
| `skills/claude-api/*/*/README.md` | Same language switch line under the title | Take upstream, then re-add the line |
| `skills/xlsx/SKILL.md` | 1. Pointer to `HOUSE_RULES.md` under the title<br>2. Table row for flowcharts (`FLOWCHART.md`)<br>3. `lxml` in Dependencies | Take upstream, then re-add these three lines |

## Files only in this fork (never conflict)

| File | Content |
|---|---|
| `README.zh-CN.md`, `skills/claude-api/*/*/README.zh-CN.md` | Chinese translations |
| `skills/xlsx/HOUSE_RULES.md` | Fork rules: Meiryo UI, shapes, cell layout and hand-over checks. Overrides `SKILL.md` |
| `skills/xlsx/FLOWCHART.md` | Flowcharts as native Excel shapes |
| `skills/xlsx/scripts/add_shapes.py` | Writes DrawingML shapes into a workbook |
| `CUSTOMIZATIONS.md` | This file |

## Syncing with upstream

```bash
git remote add upstream https://github.com/anthropics/skills.git   # once
git config rerere.enabled true                                     # once: reuse conflict resolutions
git fetch upstream
git switch -c chore/sync-upstream-YYYY-MM main
git merge upstream/main          # merge, do not rebase
# resolve conflicts with the table above, then open a PR into main
```

Put new rules in `HOUSE_RULES.md` (or another new file), not into upstream text.
