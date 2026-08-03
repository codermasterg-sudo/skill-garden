---
name: boss-auto-apply
description: BOSS直聘自动投递。提供浏览器实例管理（browser.py open/close/port）、搜索岗位（search_jobs.py）、查看岗位JD详情（view_job.py）、点击「立即沟通」（apply_action.py）四个能力，由 agent 根据用户需求和简历自主判断、决策投递。当用户需要自动投简历、批量打招呼、筛选投递岗位时使用。
---

# Boss Auto Apply — BOSS直聘自动投递

## 免责声明

- 本项目仅供学习交流使用。
- 使用者自行承担使用本项目的一切后果与责任，作者不对任何使用行为负责。
- 注意：自动化操作可能触发目标平台的风控机制，导致账号被临时停用或功能受限。

## 定位

本 skill 提供**操作 BOSS 直聘页面的动手能力**：搜索岗位、查看岗位 JD 详情、点击「立即沟通」。agent 负责全部决策——是否值得投、投几个、节奏怎么控制、记录什么，都根据用户需求自主判断，skill 不替 agent 做决定。

脚本通过**命令行子进程**调用，输出为 JSON/文本，agent 解析后自主决策。skill 目录可整体复制到任意支持 skill 约定的 agent 环境。

## 依赖与安装

脚本需要 Python 3.9+ 和以下依赖（`scripts/requirements.txt`）：

```
cloakbrowser>=0.5.0
playwright>=1.40
```

**agent 在使用前先确认依赖可用**：执行任一脚本，若报 `ModuleNotFoundError`（如 `No module named 'cloakbrowser'`）则说明缺依赖，自行安装：

```bash
pip install -r scripts/requirements.txt
```

安装后重试脚本。若 `pip` 不在 PATH 或需要用户环境（如 venv/conda），先确认用户使用的 Python 解释器再安装。

**浏览器二进制**：skill 通过 `cloakbrowser.launch_persistent_context` 启动浏览器（自动附带 stealth 指纹参数）。CloakBrowser 首次运行会自动下载其自带 Chromium 二进制到 `~/.cloakbrowser/`（需网络且耗时约 1 分钟），二进制路径由 cloakbrowser 自动发现（`ensure_binary`），无需手动配置；也可用环境变量 `CLOAKBROWSER_BINARY_PATH` 显式指定。若启动报"未找到 Chromium 二进制"，按提示安装依赖后重试即可。

## 运行时数据位置

所有运行时数据统一存**用户目录 `~/.boss-auto-apply/`**（skill 目录本身只含代码与文档，可整体复制/只读/升级，不产生本机路径依赖）：

```
~/.boss-auto-apply/
├── state.db           # 统一状态库（browser 表/投递记录/节流计数）
├── browser_profile/   # 浏览器 profile（登录态 cookie 持久化）
├── profile.md         # 用户偏好档案（agent 维护）
└── resume.md          # 结构化简历（agent 维护）
```

环境变量 `BOSS_SKILL_DATA_DIR` 可覆盖数据目录（测试/多配置场景用）。

## 配置修改

限流/拟人化等行为参数通过 `config/throttle.json` 修改（推荐改这里，git 入库可选），只填想改的项，其余自动用 `config/config.default.json` 内置默认合并。**所有值单位：秒/次**。修改后无需重启（脚本每次调用重新加载）。

| 配置项 | 默认 | 说明 |
|---|---|---|
| `apply.min_apply_interval` | 8 | 两次投递最小间隔（秒，脚本强制） |
| `apply.delay_after_click` | [1, 3] | 点击后随机延迟区间（秒） |
| `search.min_search_interval` | 10 | 两次搜索最小间隔（秒） |
| `search.request_throttle_max` | 30 | 单会话 API 请求上限（次） |
| `search.delay_before_api` | [2, 6] | API 请求前随机延迟区间（秒） |
| `search.page_transition_delay` | [3, 8] | 翻页间随机延迟区间（秒） |
| `view.min_view_interval` | 5 | 两次查看详情最小间隔（秒） |
| `backoff.max_retries` | 3 | 连续失败最大重试次数 |
| `login.timeout_seconds` | 300 | 等待扫码登录最长时间（秒） |
| `login.poll_interval` | 5 | 登录状态轮询间隔（秒） |
| `risk.keywords` | 见默认文件 | 风控关键词列表（命中即停止） |

## 提供的动作

所有脚本通过命令行调用（Python 3.9+，依赖见 `scripts/requirements.txt`），输出到 stdout，错误到 stderr，退出码非 0 表示失败。

### 0. 浏览器实例（有头/无头）

所有操作都基于**一个浏览器实例**：先 `browser.py open` 打开，搜索/投递脚本通过 CDP 连接复用它。有头/无头只是"是否展示窗口"的开关：

```bash
# 打开浏览器实例（默认有头窗口；加 --headless 则无头纯后台，不抢屏幕）
python3 scripts/browser.py open [--url <初始URL>] [--headless]
# → 实例信息写入状态库 ~/.boss-auto-apply/state.db 的 browser 表（pid + 随机调试端口 + 有头/无头），同时打印到返回

# 查询当前实例的调试端口（供 agent 读取，输出仅端口号）
python3 scripts/browser.py port

# 关闭浏览器实例
python3 scripts/browser.py close
```

- **有头模式**（`open` 默认）：窗口可见，供用户手动查看/扫码登录；脚本 CDP 复用同一窗口。
- **无头模式**（`open --headless`）：纯后台运行，**不产生窗口、不抢鼠标/焦点/屏幕**；脚本同样 CDP 复用，登录态与有头共用同一 profile。
- **每次只开一个实例**（Chromium profile 单例）：已有实例运行时再 `open` 会直接复用；冲突时脚本明确报错，需先 `close`。
- 实例信息记录在状态库 `~/.boss-auto-apply/state.db` 的 `browser` 表（pid + 随机调试端口 + 有头/无头），agent 可用 `port` 命令或查表获取端口。
- **运行时数据位置**：所有运行时数据（state.db、浏览器 profile）统一存用户目录 `~/.boss-auto-apply/`，skill 目录本身只含代码与文档，可整体复制/只读/升级，不产生本机路径依赖。
- **安全**：端口为系统随机（避开 9222/9223/9229 常见调试端口）、仅监听 127.0.0.1、关闭即释放。
- **开实例时机**：需要用户扫码/手动操作时用有头；纯自动化用无头。**关闭时机**：用户确认不再操作后。
- **不抢前台**：无头模式天然后台；有头模式下脚本只操作新开的 tab，不抢当前焦点、不移动鼠标；除非用户明确希望看到效果，否则不在前台做干扰性操作。

### 1. 搜索岗位

```bash
python3 scripts/search_jobs.py --keyword <岗位关键词> --city <城市> [--pages start,end] [--output jobs.json]

# 筛选条件（可选，可组合）
python3 scripts/search_jobs.py --keyword "Python" --city "北京" --job-type 实习 --degree 本科
python3 scripts/search_jobs.py --keyword "Python" --city "北京" --experience 经验不限 --salary 5-10K
```

- 在已有浏览器实例中（CDP 复用 `browser.py open` 打开的实例，有头/无头均可）打开搜索页，抓取岗位卡片，输出 JSON 列表
- **默认翻第 1 页（30 个岗位，token 友好）**；`--pages start,end` 指定翻页范围（闭区间，如 `2,4` = 第 2~4 页共 90 个，每页 30 个；列表信息不足时再翻页或查详情）
- **token 友好**：加 `--output jobs.json` 把结果写入文件（stdout 只输出概要），agent 筛选时只读文件对应条目、不把全部 JSON 灌进上下文
- **失败约定**：脚本失败时退出码非 0，stdout 输出 `{"error": "原因"}`（agent 解析 stdout 即可感知失败），stderr 为详细原因；未打开实例时报错提示先运行 `browser.py open`
- 每个岗位含：`id`（详情页 ID）、`title`（岗位名）、`company`（公司名）、`salary`（薪资）、`href` 及经验/学历/规模等字段
- **筛选条件**（`--help` 查看全部选项，可组合使用）：
  - `--job-type`：求职类型（全职/实习/兼职）—— **接口精确筛选**
  - `--experience`：工作经验（经验不限）—— **接口精确筛选**
  - `--degree`：学历（大专/本科/硕士）—— **接口精确筛选**
  - `--salary`：薪资待遇（3K以下/3-5K/5-10K）—— **接口筛选，区间模糊匹配**（如 5-10K 会含 4-6K 等附近区间，BOSS 侧行为）
  - `--financing-stage`：融资阶段（未融资/天使轮/.../已上市）—— **仅页面过滤**（接口不支持，脚本 XHR 仍返回全量数据，agent 需按返回的 `stage` 字段自行筛选）
  - `--scale`：公司规模（0-20人/.../10000人以上）—— **仅页面过滤**（接口不支持，同上，agent 按返回的 `scale` 字段自行筛选）
- **筛选实现说明**：脚本用 XHR 调列表接口拿数据（明文薪资）；接口支持的筛选条件直接透传接口精确过滤；接口不支持的（融资阶段/规模）只加在搜索页 URL 上（页面展示过滤），**数据仍为接口返回的全量**，由 agent 按字段自行判断
- **需先打开实例**（运行 browser.py open），未打开则脚本报错提示
- 首次使用需扫码登录（登录态自动持久化在 `~/.boss-auto-apply/browser_profile/`）

### 2. 查看岗位 JD 详情

```bash
# 默认输出概要（岗位名/薪资/公司/城市/经验/学历/融资/规模/行业 + JD 正文前 120 字）
python3 scripts/view_job.py --job-id <id>

# 只输出指定字段（token 友好，适合只关心某些信息）
python3 scripts/view_job.py --job-id <id> --fields description
python3 scripts/view_job.py --job-id <id> --fields welfare,address,location_gps

# 输出全部字段（JD 全文/公司介绍全文/工商信息/福利/BOSS/经纬度，token 较大）
python3 scripts/view_job.py --job-id <id> --full
```

- 在已有浏览器实例中（CDP 复用 `browser.py open` 打开的实例，有头/无头均可）按岗位 ID 直接跳转岗位详情页，抓取页面渲染的 JD 内容，输出 JSON
- **需先打开实例**（运行 browser.py open），未打开则脚本报错提示
- **按 ID 直取**：不依赖搜索列表点击（列表动态，可能找不到目标岗位），也不依赖接口请求（页面直接渲染，无额外请求）
- **抓取能力**（`--full` 时全部返回；`--fields` 可选字段）：
  - 岗位：`title`（岗位名）、`salary`（薪资）、`city`（城市）、`experience`（经验）、`degree`（学历）、`description`（JD 正文全文）
  - 福利/BOSS：`welfare`（福利标签列表）、`boss`（BOSS 称呼/职位/在线状态）
  - 公司：`stage`（融资阶段）、`scale`（规模）、`industry`（行业）、`company_intro`（公司介绍全文）、`address`（工作地址）、`location_gps`（经纬度）
  - 工商信息：`company_legal_name`（公司全称）、`company_legal_representative`（法定代表人）、`company_founded`（成立日期）、`company_type`（企业类型）、`company_status`（经营状态）、`company_capital`（注册资金）
- **输出控制（token 友好）**：默认概要即可判断岗位匹配度；JD 全文、公司介绍等大文本按需用 `--fields` 或 `--full` 展开，避免每次返回全部内容
- **截断标记（agent 必须注意）**：概要/字段模式下，`description`（JD 正文）等大文本截断到 **120 字**，截断时：
  - `description` 末尾带 `…`，并输出 `description_truncated: true` 标记
  - **agent 看到的 description 是不完整的**，如需完整 JD 用 `--fields description`（注意：字段模式同样截断到 120 字）或 `--full`（全文不截断）
  - **agent 判断以输出为准**，被截断的字段不要当作完整内容使用
- 页面无 JD 正文（岗位已下架/页面结构变化）时报错退出，由 agent 判断是否人工确认
- **是否查详情由 agent 决定**：查看是读操作（不产生投递记录），建议只对列表信息合适、需要确认 JD 细节的岗位查详情，不必每条都查

### 3. 点击「立即沟通」

```bash
python3 scripts/apply_action.py --job-id <id>
```

- 在已有浏览器实例中（CDP 复用 `browser.py open` 打开的实例，有头/无头均可）跳转岗位详情页，点击「立即沟通」（BOSS 自动带上默认招呼语）
- **需先打开实例**（运行 browser.py open），未打开则脚本报错提示
- 脚本强制约束（安全底线，agent 不可跳过）：
  - **风控即停**：检测到风控信号（code 37 / 环境异常 / 操作过于频繁）则停止并返回原因
  - **投递间隔**：距上次投递不足 `apply.min_apply_interval` 秒（默认 8 秒）时等待补齐，防连续高频触发风控。间隔以上次投递记录（`applied` 表 `ts`）为准
  - **限额处理**：点击后检测 BOSS 页面的投递限额提示——**120 提醒弹窗自动点掉（「好/继续沟通」），投递继续**；**150 不允许投递停下等用户**（继续投会一直报错，需人工判断）
- 返回结果：`{'ok': bool, 'reason': str, 'quota': {...}}`：
  - `ok=true` 投递成功
  - `ok=false` 时 agent 根据 `reason` 处理（风控→停止通知用户、按钮缺失→视觉兜底、`quota.quota=limit_blocked`→BOSS 已达投递硬顶，等待用户处理）
  - `quota.quota`：`None`（正常）/ `limit_remind`（120 提醒，**已自动关掉弹窗，投递继续**）/ `limit_blocked`（150 硬顶，**已停下等用户**）。`limit_remind` 无需 agent 处理，`limit_blocked` 时 agent 应停止投递并告知用户

## Agent 使用指引（自主编排，非固定流程）

agent 根据用户需求灵活编排以下能力，不是必须按顺序全做：

### 理解需求与档案
- 询问/确认用户：简历位置、期望岗位、城市、薪资、类型（实习/全职）、黑名单、投递数量上限等
- 用 `~/.boss-auto-apply/profile.md` 长期记录用户偏好（期望岗位/城市/薪资/类型/黑名单/备注），对话中用户的新要求随时追加；每次会话先读该文件，避免重复询问

### 解析简历（可选，用户提供简历时）
- 简历格式多样（docx / pdf / 扫描件 / 图片），自行选择合适方式：
  - docx：用 python-docx 或直接读文本
  - PDF：先尝试文本提取（如 PyMuPDF / pdftotext）；**提取不出文字（扫描件/图片型 PDF）用视觉读图解析**
- 将结构化结果（姓名/技能/经验/期望）记录到 `~/.boss-auto-apply/resume.md`，供后续判断

### 搜索岗位
- 先 `browser.py open` 打开浏览器实例（纯自动化用 `--headless` 无头不抢屏幕；需扫码/查看用有头），再按偏好关键词+城市执行 `search_jobs.py`，输出岗位列表

### 筛选与判断（agent 自主）
- 对每个岗位，结合用户需求、简历、偏好档案判断是否合适：
  - 岗位职责/要求与技能匹配度（列表信息不足时，用 `view_job.py --job-id <id>` 查看 JD 再判断；**默认概要已含 JD 前 120 字（带 `description_truncated` 截断标记）**，需要完整 JD 用 `--fields description`，需要公司实力（成立日期/注册资金/规模等）用 `--fields` 展开）
  - 薪资范围、城市、公司、类型是否符合偏好
  - 黑名单公司/岗位排除
- **判断是 agent 的责任**，不依赖任何脚本规则
- **按需抓取**：view_job 默认输出概要，JD 全文/公司介绍/工商信息等大字段用 `--fields` 或 `--full` 按需展开，避免每次返回全部内容（token 友好）
- 查看 JD 是读操作（不产生投递记录、不占用每日投递上限），节奏自行把握；**是否查、查哪些，agent 自主决定**，skill 不强制

### 投递
- 对判断合适的岗位，逐个执行 `apply_action.py --job-id <id>`
- 脚本已强制两次投递最小间隔（默认 8 秒，可配 `apply.min_apply_interval`），agent 无需额外限速；批量投递时按自己节奏分批即可
- 处理脚本返回：`quota.quota=limit_blocked` → BOSS 已达投递硬顶，今日停止并告知用户；风控 → 立即停止通知用户，不得重试

### 记录（agent 负责）
每次投递后，**必须**把投递记录写入状态库 `~/.boss-auto-apply/state.db` 的 `applied` 表——脚本的投递间隔判断依赖此表的时间戳（`ts` 字段），同时供存档/去重。**投递上限不依赖此表**（以 BOSS 页面返回的 quota 信息为准）。记录内容由 agent 判断，建议包含：日期时间（`YYYY-MM-DD HH:MM:SS` 含秒）、job_id、状态（成功/失败/风控暂停/达上限），以及用户要求的其他信息（公司、岗位、备注等）。示例 SQL：

```sql
-- 写入一条投递记录（ts 格式必须是 YYYY-MM-DD HH:MM:SS，间隔判断依赖）
INSERT INTO applied (ts, job_id, status, note) VALUES ('2026-07-31 10:23:45', '12345', '成功', '字节跳动 Python后端');

-- 投递前查询：某 job_id 是否已投过（去重）
SELECT COUNT(*) FROM applied WHERE job_id = '12345';

-- 查询今日已投数量（汇报用，非限制）
SELECT COUNT(*) FROM applied WHERE ts >= date('now') || ' 00:00:00';
```

- 也可用 `scripts/state.py` 自检查看最近记录（`python3 scripts/state.py`）

### 收尾
- 用户确认不再操作后关闭浏览器实例（`browser.py close`）
- 向用户汇报：投递数量、成功/失败明细、风控情况、下一步建议

## 前台体验约束

- **自动化用无头**：`browser.py open --headless` 无头运行，**从机制上不产生窗口、不抢鼠标/焦点/屏幕**
- **有头仅用于用户主动查看/扫码**：`browser.py open` 默认有头，显式打开，用户可关闭
- 有头模式下脚本只操作新开的 tab，不抢当前焦点、不移动鼠标；除非用户明确要求"看效果"，否则不在前台做干扰性操作
- 开/关实例、投递节奏都要在对话中说明，让用户有掌控感

## 风控即停（agent 必须遵守）

- 脚本返回风控信号 / 页面出现「环境存在异常」「安全验证」「操作过于频繁」→ **立即停止**，通知用户人工判断，不得重试
- 验证码/滑块出现 → 暂停，通知用户人工处理，完成后恢复
- 登录页跳转 → 提示用户扫码登录（cookie 约 7 天过期）

## 页面结构变化时的处理

- BOSS 页面改版可能导致脚本找不到元素（报错如"未找到「立即沟通」按钮"）。脚本使用的选择器清单见 `references/selectors.md`。
- 脚本报错找不到元素时，先让用户在有头窗口中打开对应页面确认新结构，或截图观察页面结构（有头窗口用户可直接截图；无头实例可让用户切到有头查看），从截图中识别目标元素新位置，用视觉定位完成该次操作。
- 确认新选择器后更新 `references/selectors.md`，便于后续脚本使用。
