# Boss Auto Apply — BOSS直聘自动投递 Skill

提供 BOSS直聘「搜索岗位」「查看岗位 JD 详情」「点击立即沟通」动手能力的**通用 Agent Skill**。skill 只提供动手能力（4 个命令行脚本），不做决策——解析简历、判断岗位合适度、筛选、节奏、记录全部由 agent 根据用户需求自主完成。

**面向 agent 使用**：脚本通过命令行子进程调用，输出 JSON/文本到 stdout，agent 解析后自主决策。skill 目录可整体复制到任意支持 skill 约定的 agent 环境（Claude Code 或其他 agent 框架）。

## 免责声明

- 本项目仅供学习交流使用。
- 使用者自行承担使用本项目的一切后果与责任，作者不对任何使用行为负责。
- 注意：自动化操作可能触发目标平台的风控机制，导致账号被临时停用或功能受限。

## 提供的动作

| 脚本 | 功能 | 输出 |
|---|---|---|
| `scripts/browser.py open` | 打开浏览器实例（默认有头窗口；`--headless` 无头纯后台） | 实例 pid + 随机调试端口 |
| `scripts/browser.py close` | 关闭浏览器实例 | — |
| `scripts/browser.py port` | 返回当前实例调试端口 | 仅端口号 |
| `scripts/search_jobs.py` | 在已有实例中搜索岗位（CDP 复用，默认翻第 1~3 页，`--pages start,end` 可调）。支持筛选：`--job-type`（全职/实习/兼职）、`--experience`（经验不限）、`--degree`（大专/本科/硕士）接口精确筛选；`--salary`（3K以下/3-5K/5-10K）接口区间筛选；`--financing-stage`/`--scale` 仅页面过滤（接口不支持，agent 按返回字段自行筛选） | JSON 岗位列表（id/title/company/salary） |
| `scripts/view_job.py` | 在已有实例中按岗位 ID 查看 JD 详情（CDP 复用，跳转详情页抓取页面渲染内容）。默认输出概要（岗位名/薪资/公司/城市/经验/学历/融资/规模/行业 + JD 前 120 字，截断时带 `description_truncated` 标记）；`--fields a,b` 只输出指定字段（大文本同样截断 120 字并带标记）；`--full` 输出全部不截断（JD 全文/公司介绍/工商信息/福利/BOSS/经纬度） | JSON 岗位详情（按参数裁剪，token 友好） |
| `scripts/apply_action.py` | 在已有实例中点击「立即沟通」（CDP 复用） | `{'ok': bool, 'reason': str}` |

脚本保留的强制约束（安全底线）：每日投递上限检查、风控信号即停。

> **浏览器实例**：所有操作基于一个浏览器实例。先 `browser.py open` 打开（有头=窗口可见供用户查看/扫码；`--headless`=无头纯后台不抢屏幕），搜索/投递脚本通过 CDP 连接复用该实例。每次只开一个实例（profile 单例），已有实例时再 `open` 会直接复用。调试端口为**系统随机端口**（避开 9222/9223/9229 等常见固定调试端口），仅监听 127.0.0.1，关闭即释放。实例信息写入临时文件 `data/browser_window.json`（pid + 随机端口 + 有头/无头）。

## 安装与依赖

```bash
pip install -r scripts/requirements.txt   # cloakbrowser（含 playwright）
```

> agent 使用：脚本报 `ModuleNotFoundError` 时即缺依赖，运行 `pip install -r scripts/requirements.txt` 安装后重试。CloakBrowser 首次运行自动下载其自带 Chromium 二进制（需网络，约 1 分钟）。

浏览器 profile 目录 `data/browser_profile/` 自动创建，登录态（cookie）自动持久化，无需手动维护。

## 使用

1. 首次使用扫码登录一次（cookie 有效期约 7 天，过期后需重新扫码）——`browser.py open` 开有头窗口扫码，登录态自动持久化
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
│   ├── browser_profile/  # 浏览器 profile（登录态持久化）
│   └── browser_window.json  # 实例信息（pid + 随机调试端口 + 有头/无头，运行时生成）
├── scripts/              # 动作脚本
│   ├── browser.py        # 浏览器管理 CLI（open/close/port）
│   ├── browser_lib.py    # CDP 连接/实例管理公共模块
│   ├── search_jobs.py    # 搜索岗位 → JSON
│   ├── view_job.py       # 查看岗位 JD 详情 → JSON
│   ├── apply_action.py   # 点击「立即沟通」+ 每日投递上限 + 风控即停
│   └── requirements.txt
└── references/
    └── selectors.md      # BOSS 页面选择器清单
```

> 测试在仓库 `tests/boss-auto-apply/`。详细设计见 `docs/superpowers/specs/2026-07-31-boss-auto-apply-design.md`。
