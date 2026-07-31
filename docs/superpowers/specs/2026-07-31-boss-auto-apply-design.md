# Boss Auto Apply Skill — 设计文档

- 日期：2026-07-31
- 状态：已批准

## 1. 背景与目标

创建一个**通用 Agent Skill**，实现 BOSS 直聘的**自动智能投递**：解析用户简历 → 建立偏好档案 → 智能筛选岗位 → 自动点击「立即沟通」。帮助用户从重复的筛选和点击中解放出来。

**通用 Agent Skill 定位**：不依赖 Claude Code 特定机制，采用通用 skill 格式（`SKILL.md` + Python 脚本 + 数据文件），任何支持 skill 约定的 agent（Claude Code、其他 agent 框架）均可加载执行。仓库目录结构按此定位组织。

**核心原则（用户拍板）：**

1. **打招呼 = 点击「立即沟通」即可**。不做招呼语生成、不填输入框、不发简历、不跟进回复——后续全部交给用户。BOSS 平台自身的默认机制会带上默认招呼语，我们只需触发点击。
2. **这是 Skill 不是定式脚本**。SKILL.md 指挥 agent 动态决策，每次运行根据页面状态决定用什么工具（DOM 自动化 / 视觉兜底），而不是写死一个 Python 脚本跑完所有事。
3. **不因过度谨慎降低可用性**。人工介入只保留行业共识的必要项：首次扫码登录、验证码暂停处理、风控信号停止。不用 DRY_RUN 逐条人工审核。

**非目标：**

- 不生成打招呼语、不自动发简历、不跟进 HR 回复。
- 不处理换微信/约面等红线动作（这些永远交给用户）。
- 不支持多平台（架构预留，但本次只做 BOSS 直聘）。

## 2. 技术选型（五轮调研收敛）

### 2.1 浏览器引擎：CloakBrowser

**选型过程**：最初选 Playwright/patchright + stealth 注入 → 调研发现 BOSS 的 CDP 端口扫描（127.0.0.1:9222/9223/9229）检测绕不过，patchright 路线已死（get_jobs 1 月起停更失效）→ 考虑 DrissionPage（FuckJob 用），但核实其本质仍是 CDP，与 Playwright 无防检测差异且生态更小 → 用户拍板用 Playwright → 找到 CloakBrowser 作为「不暴露 CDP 的浏览器引擎」。

**CloakBrowser 关键事实**（29.4K★，MIT，2026-07-30 活跃更新）：
- **Drop-in Playwright replacement**：API 与 Playwright 完全兼容，`pip install cloakbrowser` 后 `from cloakbrowser import launch` 替换 `from playwright.sync_api import sync_playwright` 即可。
- **71 个 C++ 源码级补丁**：canvas、WebGL、audio、fonts、GPU、screen、WebRTC、network timing、automation signals、**CDP input behavior**——是真实 Chromium 二进制改源码，不是 JS 注入。
- **CDP detection: Not detected**（`isAutomatedWithCDP: false`）——解决 BOSS 端口扫描痛点。
- **`humanize=True`**：内置拟人化鼠标曲线、键盘时序、滚动模式——解决行为层检测（L3）。
- 通过 Cloudflare Turnstile、FingerprintJS、BrowserScan 等 30+ 检测站点。

### 2.2 混合策略：DOM 为主 + Computer Use 兜底

调研结论（四轮）：纯 Computer Use 不可行（日投 150 岗位需 8-12 小时、$45-225/天、中文滑块成功率仅 10-20%）；纯 DOM 的 CDP 暴露已被验证。业界最佳实践是 **DOM 优先 + 视觉兜底**（browser-use vision fallback、Stagehand hybrid 同款模式）：

| 环节 | 用什么 | 理由 |
|---|---|---|
| 搜索/浏览/筛选/点击立即沟通（主链路） | CloakBrowser DOM 自动化 | 快（秒级）、零成本、humanize=True 拟人化 |
| 验证码出现 | 检测到 → 暂停 → 通知用户人工处理 | 行业共识；视觉解滑块成功率仅 10-20% |
| 选择器失效/改版 | Computer Use 视觉兜底 | 视觉看渲染结果不受改版影响；触发率应 <20%，超了说明选择器策略该重写 |
| 风控信号（code 37/页面回退） | 立即停止 + 通知用户 | 不可自动化，必须人工判断 |

### 2.3 登录态：独立 profile + 扫码登录（cookie 自动持久化）

- 用 `user_data_dir` 指定独立 profile 目录（类似 Chrome 用户数据目录），**cookie 全自动持久化，无需手动维护**。
- 首次启动 → 浏览器打开登录页 → 用户扫码登录一次 → 登录态（含 `__zp_stoken__`）自动保存在 profile 目录。
- 之后每次运行用同一 `user_data_dir` 启动 → **cookie 自动加载，直接保持登录**。
- BOSS cookie 有效期约 7 天；过期后浏览器自动跳登录页，skill 检测到登录页即提示用户再扫一次码（约每周一次，是扫码不是维护 cookie）。
- 不用 CDP 接管已打开浏览器（会暴露调试端口）。

### 2.4 限速与限额

- 每岗位 3-10 秒随机延迟（humanize 拟人化 + 显式限速）。
- 每 15-20 个岗位休息 1-3 分钟。
- BOSS 每日 120 次弹窗提示（自动点「好/继续沟通」）+ 150 次硬顶（停止）。
- 单批安全线 30-50 个（LinkedIn 数据：自动化用户 90 天 23% 被限）。

## 3. 工作流（主链路）

```
用户提供简历(Word/PDF) + 对话说明偏好
        ↓
[1] 解析简历 → 提取：姓名、经验、技能、期望岗位、期望城市、期望薪资
        ↓
[2] 建立/更新偏好档案（Markdown 存于 skill 数据目录）
     ├─ 首次：从简历 + 对话收集（岗位关键词、城市、薪资、类型：实习/全职）
     ├─ 后续：对话中用户新要求随时追加
     └─ 黑名单（公司/岗位）、偏好记录，长期复用
        ↓
[3] 搜索岗位（BOSS 搜索页，按偏好条件）
        ↓
[4] 智能筛选（双层漏斗）
     ├─ 规则过滤（免费确定性）：黑名单公司/岗位、薪资范围、HR 活跃度>2周、猎头排除
     └─ LLM 匹配分（阈值 + fail-open）：简历 vs JD 匹配度评分，低于阈值跳过，
         评分失败不静默跳过（fail-open 放行）
        ↓
[5] 点击「立即沟通」（唯一投递动作）
     ├─ 真实点击（CloakBrowser DOM），非 API 构造
     ├─ 120 弹窗自动点「好/继续沟通」，150 硬顶停止
     └─ 记录已投递岗位 ID（去重，不重复打扰）
        ↓
[6] 循环下一批 → 直到当日限额或用户停止
```

## 4. 数据文件（Markdown，存 skill 数据目录）

```
skills/boss-auto-apply/
├── SKILL.md              # skill 入口（frontmatter: name + description）
├── data/                 # 数据目录（运行时生成，gitignore）
│   ├── profile.md        # 用户偏好档案（岗位/城市/薪资/类型/黑名单/备注）
│   ├── applied.md        # 已投递记录（岗位ID/时间/状态）
│   └── state.md          # 运行状态（当日投递数/批次/风控状态）
├── scripts/              # Python 辅助脚本
│   ├── parse_resume.py   # 解析 Word/PDF 简历
│   ├── search_filter.py  # 搜索 + 规则过滤 + LLM 匹配
│   └── apply_action.py   # 点击「立即沟通」+ 限额处理
└── references/
    └── selectors.md      # BOSS 页面选择器地图（集中管理，防改版）
```

## 5. 风控设计（三档分类，不过度谨慎）

**必须做（行业共识，几乎所有长期项目都在做）：**
- 每岗位 3-10 秒随机延迟 + 每 15-20 个休息 1-3 分钟
- 120/150 限额自动应答
- 已投递去重
- 过滤不活跃 HR（省配额 = 省风控面）
- 独立 profile + 登录态持久化（避免频繁登录触发风控）
- 风控信号识别即停（code 37 / 页面回退 / "操作过于频繁" → 停止 + 通知）

**可做可不做（有更好，没有也能跑）：**
- 高斯抖动/长停顿细节（humanize=True 已覆盖大部分）
- 投递日志（便于用户每天扫一眼）

**明确不做（过度谨慎降低可用性）：**
- ❌ 招呼语生成 + 人工逐条审核（用户拍板：只点「立即沟通」）
- ❌ DRY_RUN 先审后发
- ❌ 换微信/约面红线自动化（但也不自动确认，留给用户）

## 6. 人工介入点（仅 3 个，行业共识最少必要）

1. **首次扫码登录**（约每 7 天一次）
2. **验证码出现时暂停处理**（检测到 → 暂停 → 通知 → 用户处理 → 恢复）
3. **风控信号时停止**（code 37 / 页面回退 → 停止 + 通知用户判断）

## 7. 架构分层（应对军备竞赛）

- **控制层**（浏览器引擎层）：CloakBrowser + 选择器地图（references/selectors.md）。BOSS 检测更新/改版时，只改这一层。
- **业务层**（skill 逻辑层）：SKILL.md 指挥 agent 的决策流程（筛选规则、限额处理、风控判断）。不随平台变化。
- 两者分离，检测更新只改控制层，业务逻辑不动。

## 8. 通用 Agent Skill 适配性

- **格式**：`SKILL.md`（frontmatter 用通用约定 name/description）+ Python 脚本 + Markdown 数据文件。不依赖特定 agent 框架的专有机制。
- **执行**：agent 读取 SKILL.md 的编排指导，调用 scripts/ 下的 Python 脚本（子进程执行），脚本间通过数据文件/JSON 交换状态。
- **可移植**：skills/boss-auto-apply/ 目录可整体复制到任意支持 skill 约定的 agent 环境。
- **说明**：虽然以 Claude Code 环境开发测试，但所有交互（脚本 CLI 参数、数据格式、状态文件）均为通用设计，不绑定 Claude Code API。

## 9. 风险与免责声明

- 本项目仅供学习交流使用；使用者自行承担使用本项目的一切后果与责任，作者不对任何使用行为负责。
- 自动化操作可能触发目标平台的风控机制，导致账号被临时停用或功能受限。
- 求职端打招呼被封极罕见（大量项目长期跑），封号多发生在高频刷新/掉线重连风暴——本设计已通过限速/即停规避。
- 军备竞赛现实：BOSS 平均 1-3 个月更新检测，CloakBrowser 需跟进其发布节奏。
- SKILL.md 与 README.md 中均写入免责声明（学习交流用途 + 责任自担 + 风控风险客观陈述）。

## 10. 验收标准

- [ ] SKILL.md 可被 Claude Code 正确识别（frontmatter 规范）
- [ ] 简历解析脚本可解析 Word/PDF，提取关键字段
- [ ] 偏好档案可建立、更新、持久化（Markdown）
- [ ] 搜索 + 双层筛选（规则 + LLM）可用
- [ ] 点击「立即沟通」+ 120/150 限额处理可用
- [ ] 已投递去重记录可用
- [ ] 风控信号即停 + 通知用户
- [ ] 选择器地图集中管理，控制层/业务层分离
