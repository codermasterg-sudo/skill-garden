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

详细规范见 [docs/收录规范.md](docs/收录规范.md)，贡献指南见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

[MIT](LICENSE) — 允许自由使用、修改、分享。
