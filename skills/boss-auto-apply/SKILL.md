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

安装后重试脚本。若 `pip` 不在 PATH 或需要用户环境（如 venv/conda），先确认用户使用的 Python 解释器再安装。CloakBrowser 首次运行会自动下载其自带 Chromium 二进制，需网络且耗时约 1 分钟，属正常现象。

## 提供的动作

所有脚本通过命令行调用（Python 3.9+，依赖见 `scripts/requirements.txt`），输出到 stdout，错误到 stderr，退出码非 0 表示失败。

### 0. 浏览器实例（有头/无头）

所有操作都基于**一个浏览器实例**：先 `browser.py open` 打开，搜索/投递脚本通过 CDP 连接复用它。有头/无头只是"是否展示窗口"的开关：

```bash
# 打开浏览器实例（默认有头窗口；加 --headless 则无头纯后台，不抢屏幕）
python3 scripts/browser.py open [--url <初始URL>] [--headless]
# → 实例信息写入临时文件 data/browser_window.json：{"pid": ..., "port": ...}
#   （pid=进程号，port=随机调试端口），同时打印到返回

# 查询当前实例的调试端口（供 agent 读取，输出仅端口号）
python3 scripts/browser.py port

# 关闭浏览器实例
python3 scripts/browser.py close
```

- **有头模式**（`open` 默认）：窗口可见，供用户手动查看/扫码登录；脚本 CDP 复用同一窗口。
- **无头模式**（`open --headless`）：纯后台运行，**不产生窗口、不抢鼠标/焦点/屏幕**；脚本同样 CDP 复用，登录态与有头共用同一 profile。
- **每次只开一个实例**（Chromium profile 单例）：已有实例运行时再 `open` 会直接复用；冲突时脚本明确报错，需先 `close`。
- 实例信息记录在临时文件 `data/browser_window.json`（pid + 随机调试端口 + 有头/无头），agent 可读该文件或 `port` 命令获取端口。
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
- **默认翻第 1~3 页（90 个岗位）**；`--pages start,end` 指定翻页范围（闭区间，如 `2,4` = 第 2~4 页共 90 个，每页 30 个）
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
- 首次使用需扫码登录（登录态自动持久化在 `data/browser_profile/`）

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
python3 scripts/apply_action.py --job-id <id> [--applied data/applied.md]
```

- 在已有浏览器实例中（CDP 复用 `browser.py open` 打开的实例，有头/无头均可）跳转岗位详情页，点击「立即沟通」（BOSS 自动带上默认招呼语）
- **需先打开实例**（运行 browser.py open），未打开则脚本报错提示
- 脚本强制约束（安全底线，agent 不可跳过）：
  - **每日投递上限**：投递前检查 `data/applied.md` 今日条数，达到则拒绝
  - **风控即停**：检测到风控信号（code 37 / 环境异常 / 操作过于频繁）则停止并返回原因
- 返回结果：`{'ok': bool, 'reason': str}`。`ok=false` 时 agent 需根据 `reason` 处理（上限→停止、风控→通知用户、按钮缺失→视觉兜底）

## Agent 使用指引（自主编排，非固定流程）

agent 根据用户需求灵活编排以下能力，不是必须按顺序全做：

### 理解需求与档案
- 询问/确认用户：简历位置、期望岗位、城市、薪资、类型（实习/全职）、黑名单、投递数量上限等
- 用 `data/profile.md` 长期记录用户偏好（期望岗位/城市/薪资/类型/黑名单/备注），对话中用户的新要求随时追加；每次会话先读该文件，避免重复询问

### 解析简历（可选，用户提供简历时）
- 简历格式多样（docx / pdf / 扫描件 / 图片），自行选择合适方式：
  - docx：用 python-docx 或直接读文本
  - PDF：先尝试文本提取（如 PyMuPDF / pdftotext）；**提取不出文字（扫描件/图片型 PDF）用视觉读图解析**
- 将结构化结果（姓名/技能/经验/期望）记录到 `data/resume.md`，供后续判断

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
- 控制节奏：每岗位之间间隔数秒（拟人化，避免过密），数量到用户上限或每日投递上限即停
- 处理脚本返回：上限→停止告知用户；风控→立即停止通知用户，不得重试

### 记录（agent 负责）
每次投递后，**必须**把投递记录追加到 `data/applied.md`，一行一条。记录内容由 agent 判断，建议包含：日期、时间（**含秒，用于节奏控制**）、job_id、状态（成功/失败/风控暂停/达上限），以及用户要求的其他信息（公司、岗位、备注等）：

```markdown
2026-07-31 10:23:45 job_id=12345 状态=成功 备注=字节跳动 Python后端
```

- 投递前可读 `applied.md` 判断：今日已投几条、某 job_id 是否已投过（去重）

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
