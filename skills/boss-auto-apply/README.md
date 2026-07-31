# Boss Auto Apply — BOSS直聘自动投递 Skill

提供 BOSS直聘「搜索岗位」「点击立即沟通」两个动手能力的通用 Agent Skill。**skill 只提供动手能力，不做决策**——解析简历、判断岗位合适度、筛选、节奏、记录全部由 agent 根据用户需求自主完成。

## 免责声明

- 本项目仅供学习交流使用。
- 使用者自行承担使用本项目的一切后果与责任，作者不对任何使用行为负责。
- 注意：自动化操作可能触发目标平台的风控机制，导致账号被临时停用或功能受限。

## 提供的动作

| 脚本 | 功能 | 输出 |
|---|---|---|
| `scripts/search_jobs.py` | 用 CloakBrowser 搜索岗位 | JSON 岗位列表（id/title/company/salary） |
| `scripts/apply_action.py` | 跳详情页点击「立即沟通」 | `{'ok': bool, 'reason': str}` |

脚本保留的强制约束（安全底线）：每日 150 硬顶检查、风控信号即停。

## 安装与依赖

```bash
pip install -r scripts/requirements.txt   # cloakbrowser（含 playwright）
```

浏览器 profile 目录 `data/browser_profile/` 自动创建，登录态（cookie）自动持久化，无需手动维护。

## 使用

1. 首次使用扫码登录一次（cookie 有效期约 7 天，过期后需重新扫码）
2. 告诉 agent 你的简历位置和投递偏好（岗位、城市、薪资、类型、黑名单等）
3. agent 按 `SKILL.md` 工作流程执行：解析简历 → 判断 → 搜索 → 筛选 → 投递 → 记录
4. 投递记录由 agent 维护在 `data/applied.md`（一行一条）

## 注意事项

- **风控信号立即停止**：code 37 / "环境异常" / 页面回退循环 / "操作过于频繁" → 立即停止并通知用户，不得重试。
- **验证码出现时暂停**：通知用户人工处理，完成后恢复。
- **页面选择器集中管理**：改版失效时只改 `references/selectors.md`；失效时可用视觉兜底临时定位，但必须随后更新该文件。

## 目录结构

```
skills/boss-auto-apply/
├── SKILL.md              # skill 入口（agent 读取并编排执行）
├── README.md             # 本文件
├── data/                 # 运行时数据（gitignore，不入库）
│   ├── applied.md        # 已投递记录（agent 维护，一行一条）
│   └── browser_profile/  # 浏览器 profile（登录态持久化）
├── scripts/              # 2 个动作脚本
│   ├── search_jobs.py    # 搜索岗位 → JSON
│   ├── apply_action.py   # 点击「立即沟通」+ 150 硬顶 + 风控即停
│   └── requirements.txt
└── references/
    └── selectors.md      # BOSS 页面选择器地图（控制层）
```

> 测试在仓库 `tests/boss-auto-apply/`。详细设计见 `docs/superpowers/specs/2026-07-31-boss-auto-apply-design.md`。
