# Skill Garden 个人 Skill 合集 — 骨架搭建实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建 skill-garden 仓库骨架：README、LICENSE（MIT）、CONTRIBUTING、.gitignore、skills/ 目录占位、docs/ 收录规范，并完成初始提交。

**Architecture:** 纯静态文件仓库，无代码逻辑。按 Claude 官方 skill 标准结构组织：`skills/<skill-name>/SKILL.md`。所有文档用中文。每个任务创建一个文件并提交一次，最后统一点验。

**Tech Stack:** 无（纯 Markdown 文档仓库）

---

### Task 1: 提交设计文档

**Files:**
- Modify: `docs/superpowers/specs/2026-07-31-skill-collection-design.md`（已存在，未提交）

- [ ] **Step 1: 提交设计文档**

```bash
git add docs/superpowers/specs/2026-07-31-skill-collection-design.md
git commit -m "docs: add skill collection design spec"
```

Expected: 提交成功，`git log --oneline` 显示一条提交。

---

### Task 2: 创建 LICENSE（MIT）

**Files:**
- Create: `LICENSE`

- [ ] **Step 1: 创建 LICENSE 文件**

内容（版权年份 2026，版权人 `codermasterg-sudo`）：

```text
MIT License

Copyright (c) 2026 codermasterg-sudo

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 2: 提交**

```bash
git add LICENSE
git commit -m "docs: add MIT license"
```

---

### Task 3: 创建 .gitignore

**Files:**
- Create: `.gitignore`

- [ ] **Step 1: 创建 .gitignore 文件**

```text
# macOS
.DS_Store

# 编辑器
.idea/
.vscode/
*.swp
*.swo

# 本地环境与临时文件
.env
.env.local
*.local
*.log
tmp/
```

- [ ] **Step 2: 提交**

```bash
git add .gitignore
git commit -m "chore: add gitignore"
```

---

### Task 4: 创建 skills/ 目录占位

**Files:**
- Create: `skills/.gitkeep`

- [ ] **Step 1: 创建占位文件**

```bash
mkdir -p skills
touch skills/.gitkeep
```

- [ ] **Step 2: 提交**

```bash
git add skills/.gitkeep
git commit -m "chore: add skills directory placeholder"
```

---

### Task 5: 创建 docs/收录规范.md

**Files:**
- Create: `docs/收录规范.md`

- [ ] **Step 1: 创建收录规范文档**

内容要点（全部中文）：

```markdown
# Skill 收录规范

本文档定义如何向本仓库收录和编写 Claude Skill。收录前请先确认：**只收录自己写的 skills**，第三方通用 skill（如 superpowers 系列）不纳入。

## 目录结构

每个 skill 一个目录，放在 `skills/<skill-name>/` 下：

```
skills/<skill-name>/
├── SKILL.md        # 必填：skill 说明
├── scripts/        # 可选：辅助脚本
├── references/     # 可选：参考资料
└── assets/         # 可选：静态资源
```

## SKILL.md 要求

- 文件名必须是 `SKILL.md`（大写）。
- frontmatter 必须包含 `name` 和 `description` 两个字段：

```yaml
---
name: skill-name
description: 这个 skill 做什么、什么时候用。用中文写，描述要具体（何时使用、触发条件）。
---
```

- `name` 命名规范：全小写 kebab-case（如 `git-commit`、`cocos-exec`）。
- `description` 用中文写清楚用途和触发场景，便于 Claude 自动识别。

## 收录步骤

1. 从本地复制：`cp -r ~/.claude/skills/<name> skills/`
2. 检查 SKILL.md 是否符合上述规范，补齐 frontmatter。
3. 删除仓库内不需要的临时文件（如 `.DS_Store`、测试产物）。
4. 提交：`git add skills/<name> && git commit -m "feat: add <name> skill"`

## 安装到本地

合集中的 skill 安装回 `~/.claude/skills/` 有两种方式：

1. **复制**：`cp -r skills/<name> ~/.claude/skills/` — 简单直接，但不会随仓库更新。
2. **symlink**：`ln -s $(pwd)/skills/<name> ~/.claude/skills/` — 实时同步，开发时推荐。

> 注意：安装前若本地已有同名目录，先备份或删除再安装。
```

- [ ] **Step 2: 提交**

```bash
git add docs/收录规范.md
git commit -m "docs: add skill collection guidelines"
```

---

### Task 6: 创建 CONTRIBUTING.md

**Files:**
- Create: `CONTRIBUTING.md`

- [ ] **Step 1: 创建 CONTRIBUTING.md**

内容要点：

```markdown
# 贡献指南

本仓库是个人 Claude Skill 合集，欢迎补充和优化自己编写的 skills。

## 收录原则

- **只收自己写的 skills**，不收录第三方通用 skill。
- 每个 skill 必须放在 `skills/<skill-name>/` 目录，含 `SKILL.md`。
- `SKILL.md` frontmatter 必须有 `name`（小写 kebab-case）和 `description`（中文，说明用途与触发场景）。

## 规范

完整的编写与收录规范见 [docs/收录规范.md](docs/收录规范.md)。

## 提交流程

1. 新建分支：`git checkout -b feat/add-<skill-name>`
2. 按规范添加或修改 skill。
3. 提交并推送到远程后开 PR。

## 质量要求

- 描述要具体：写清楚「做什么、什么时候用」，避免模糊描述。
- 文档用中文。
- 不含敏感信息（密钥、个人路径等）。
```

- [ ] **Step 2: 提交**

```bash
git add CONTRIBUTING.md
git commit -m "docs: add contributing guide"
```

---

### Task 7: 创建 README.md

**Files:**
- Create: `README.md`

- [ ] **Step 1: 创建 README.md**

内容要点：

```markdown
# 🌱 Skill Garden — 个人 Claude Skill 合集

我自己编写和定制的 [Claude Code](https://claude.com/claude-code) Skills 合集，统一版本管理，方便备份、迁移和分享。

## 收录原则

只收录自己编写的 skills；第三方通用 skill（如 superpowers 系列）不纳入。

## 目录结构

```
skill-garden/
├── README.md            # 本文件
├── LICENSE              # MIT 许可证
├── CONTRIBUTING.md      # 贡献指南
├── skills/              # skill 目录（官方标准结构）
│   └── <skill-name>/    # 每个 skill 一个目录
│       └── SKILL.md     # skill 说明（frontmatter: name + description）
└── docs/                # 项目文档
    ├── 收录规范.md       # skill 收录/编写规范
    └── superpowers/     # 设计文档与实现计划
```

## Skill 列表

> 待收录。目前仓库只包含骨架，后续按 [收录规范](docs/收录规范.md) 逐个添加。

## 安装到本地

```bash
# 方式一：复制（简单直接）
cp -r skills/<skill-name> ~/.claude/skills/

# 方式二：symlink（实时同步，开发时推荐）
ln -s "$(pwd)/skills/<skill-name>" ~/.claude/skills/
```

安装后重启 Claude Code 即可生效。安装前若本地已有同名目录，先备份或删除。

## 从本地收录进仓库

```bash
cp -r ~/.claude/skills/<skill-name> skills/
git add skills/<skill-name>
git commit -m "feat: add <skill-name> skill"
```

详细规范见 [docs/收录规范.md](docs/收录规范.md)。

## 许可证

[MIT](LICENSE) — 允许自由使用、修改、分享。
```

- [ ] **Step 2: 提交**

```bash
git add README.md
git commit -m "docs: add readme"
```

---

### Task 8: 最终验收

**Files:**
- 无（只验证）

- [ ] **Step 1: 验证目录结构**

```bash
find . -not -path './.git*' -not -name '.git' | sort
```

Expected:

```text
.
./.gitignore
./CONTRIBUTING.md
./LICENSE
./README.md
./docs
./docs/收录规范.md
./docs/superpowers
./docs/superpowers/plans
./docs/superpowers/specs
./docs/superpowers/specs/2026-07-31-skill-collection-design.md
./skills
./skills/.gitkeep
```

- [ ] **Step 2: 验证 git 历史完整**

```bash
git log --oneline
```

Expected: 8 条提交（设计文档 + LICENSE + .gitignore + skills 占位 + 收录规范 + CONTRIBUTING + README + 本次计划文档如已提交）。

- [ ] **Step 3: 验证工作区干净**

```bash
git status --short
```

Expected: 无输出（或仅剩未提交的计划文档，如适用）。
