# Skill Garden 个人 Skill 合集 — 设计文档

- 日期：2026-07-31
- 状态：已批准

## 1. 背景与目标

创建一个可分享的个人 Claude Skill 合集仓库，用于统一管理、版本控制和分享自己编写的 Claude Code Skills。

**目标：**

1. 用 git 版本管理自己的 skills，可备份、可回溯。
2. 整理成规范结构，可以发布到 GitHub 或 Marketplace 分享给别人使用。
3. 提供清晰的收录规范和安装方法，方便后续持续补充。

**非目标（本次不做）：**

- 不收录任何 skill 本体（本次只搭骨架）。
- 不做自动化构建/发布工具（如打包、CI）。
- 不做文档站/网站。

## 2. 收录范围

- **只收自己写的 skills**：如 cocos 系列、git-commit、theme-factory、playwriter 等自己创作或深度定制的 skills。
- **不收通用型 skills**：如 superpowers 系列（brainstorming、writing-plans 等第三方通用 skill）不纳入本仓库。
- 收录时逐个确认是否为自己写的，避免误收第三方内容。

## 3. 目录结构

采用 Claude 官方标准 skill 结构，兼容直接安装到 `~/.claude/skills/`：

```
skill-garden/
├── README.md               # 仓库介绍、目录说明、收录规范、安装方法
├── LICENSE                 # MIT 许可证
├── CONTRIBUTING.md         # skill 编写/收录规范（供贡献者参考）
├── .gitignore              # 忽略临时文件
├── skills/                 # skill 根目录（官方标准结构）
│   └── .gitkeep            # 占位文件，保持空目录被 git 跟踪
└── docs/                   # 项目文档
    ├── superpowers/specs/  # 设计文档
    └── 收录规范.md          # 详细的 skill 收录/编写规范（中文）
```

### 单个 skill 的标准结构

每个 skill 放在 `skills/<skill-name>/` 目录下：

```
skills/<skill-name>/
├── SKILL.md                # 必填：skill 说明，含 frontmatter（name/description）
├── scripts/                # 可选：辅助脚本
├── references/             # 可选：参考资料
└── assets/                 # 可选：静态资源
```

SKILL.md 的 frontmatter 必须包含 `name` 和 `description`，这是 Claude 识别 skill 的最低要求。

## 4. 文件内容要点

### README.md

- 项目简介：个人 Claude Skill 合集。
- 收录原则：只收自己写的 skills。
- 目录结构说明。
- 安装方法：如何将仓库中的 skill 安装到 `~/.claude/skills/`（复制或 symlink）。
- 从本地回收到仓库的方法说明（链接到收录规范）。
- 贡献指南入口（链接 CONTRIBUTING.md）。

### LICENSE

MIT 许可证：允许任何人自由使用、复制、修改、合并、发布，只需保留版权声明。

### CONTRIBUTING.md

- skill 目录规范。
- SKILL.md frontmatter 要求。
- 命名规范（kebab-case，英文小写）。
- 文件大小与组织建议。

### .gitignore

- macOS 临时文件（`.DS_Store`）
- 编辑器临时文件
- 本地环境文件（`.env`、`.local`）

## 5. 安装与使用

用户在本地使用合集中的 skill 有两种方式：

1. **复制**：`cp -r skills/<name> ~/.claude/skills/` — 简单直接，但不同步。
2. **symlink**：`ln -s <仓库路径>/skills/<name> ~/.claude/skills/` — 实时同步，开发时推荐。

## 6. 错误处理与边界情况

- 重名冲突：安装时若 `~/.claude/skills/` 已有同名 skill，应先备份再覆盖。
- 空目录问题：用 `.gitkeep` 占位，保证 `skills/` 目录进入版本库。
- 文档语言：全部中文（符合用户全局规范）。

## 7. 验收标准

- [ ] 仓库骨架创建完成，目录结构符合上述设计。
- [ ] README、LICENSE（MIT）、CONTRIBUTING、.gitignore 就绪。
- [ ] 设计文档与收录规范写入 `docs/`。
- [ ] 初始提交完成。
