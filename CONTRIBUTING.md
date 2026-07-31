# 贡献指南

本仓库是个人 Claude Skill 合集，欢迎补充和优化自己编写的 skills。

## 收录原则

- **只收自己写的 skills**，不收录第三方通用 skill。如果你用的第三方 skill 很好用，请在自己的 fork 中维护，或在 issue 中推荐，不要直接放入本仓库。
- 每个 skill 必须放在 `skills/<skill-name>/` 目录下，目录内必须包含 `SKILL.md` 作为 skill 的入口文档。
- `SKILL.md` frontmatter 必须有：
  - `name`：小写 kebab-case 命名（如 `git-commit`、`theme-factory`），用于唯一标识该 skill；
  - `description`：使用中文撰写，说明 skill 的用途与触发场景，帮助 Claude 在合适的时机自动选用。

## 规范

完整的编写与收录规范见 [docs/收录规范.md](docs/收录规范.md)，提交前请务必通读，确保命名、结构、文档要求都符合规范。

## 提交流程

1. 新建分支：`git checkout -b feat/add-<skill-name>`
2. 按规范添加或修改 skill。
3. 提交并推送到远程后开 PR：
   ```bash
   git add skills/<skill-name>/
   git commit -m "feat: add <skill-name> skill"
   git push origin feat/add-<skill-name>
   ```
4. 在 PR 描述中简要说明该 skill 的用途、触发场景和实现要点，便于审查。

## 质量要求

- 描述要具体：写清楚「做什么、什么时候用」，避免模糊描述。例如「分析 git 变更并生成提交信息」优于「一个 git 工具」。
- 文档用中文。
- 不含敏感信息（密钥、个人路径等），提交前自查 `SKILL.md` 与脚本内容，不要在示例中出现真实的 token、API key 或本机绝对路径。

## 其他

- 欢迎在 issue 中提出改进建议、报告 skill 使用中发现的问题。
- 对已有 skill 的优化（修正错误、补充示例、改进提示词）与新增 skill 同样欢迎。
