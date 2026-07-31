---
name: boss-auto-apply
description: BOSS直聘自动投递简历。解析用户简历、建立偏好档案、智能筛选岗位、自动点击「立即沟通」。当用户需要自动投递简历、批量打招呼、筛选匹配岗位时使用。
---

# Boss Auto Apply — BOSS直聘自动投递

## 免责声明
自动投递可能违反 BOSS直聘用户协议，有账号被风控（临时停用至永久封禁）风险。使用前请知悉，建议控制单批数量，谨慎操作。

## 工作流程（agent 按此编排执行）

### 0. 环境准备
- 首次使用安装依赖：`pip install -r scripts/requirements.txt`（含 cloakbrowser、python-docx、PyMuPDF）
- 浏览器 profile 目录：`data/browser_profile/`（自动创建，登录态持久化）

### 1. 解析简历
- 输入：用户提供简历文件路径（.docx / .pdf）
- 执行：`python3 scripts/parse_resume.py <简历路径> [--output data/resume.md]`
- 输出：结构化简历 Markdown（姓名/经验/技能/期望岗位/城市/薪资）

### 2. 建立/更新偏好档案
- 读取 `data/profile.md`（不存在则创建）
- 从简历 + 对话收集：岗位关键词、城市、薪资范围、类型（实习/全职）、黑名单（公司/岗位）
- 每次对话中新要求随时追加写入；档案长期复用
- CLI：`python3 scripts/profile_manager.py --profile data/profile.md --action get|update --key <小节> --value <值>`

### 3. 搜索岗位
- 执行：`python3 scripts/search_filter.py search --keyword <岗位> --city <城市> [--page 1] [--output jobs.json]`
- 用 CloakBrowser 打开 BOSS 搜索页，等待登录态，抓取岗位列表

### 4. 智能筛选（双层漏斗）
- 规则过滤（第一层，免费确定性）：黑名单公司/岗位、岗位类型、HR 活跃度（--min-active-days）、猎头排除（--exclude-headhunter）
- LLM 匹配分（第二层，可选）：简历 vs JD 匹配度评分，阈值跳过（--llm-threshold）；评分失败 fail-open 放行
- 执行：`python3 scripts/search_filter.py filter --jobs <jobs.json> --keyword <岗位> [--job-type 全职] [--blacklist-companies 公司A,公司B] [--blacklist-keywords 关键词A] [--min-active-days 14] [--exclude-headhunter] [--resume data/resume.md --llm-threshold 50] [--output filtered.json]`

### 5. 点击「立即沟通」
- 执行：`python3 scripts/apply_action.py --job-id <id> [--state data/state.md]`
- 跳转岗位详情页后真实点击「立即沟通」（非 API 构造）；120 弹窗自动应答；150 硬顶停止；记录投递数

### 6. 循环与限额
- 每岗位 3-10 秒随机延迟；每 20 个休息 1-3 分钟；单批 30-50 个
- 当日 120 提示弹窗自动点「好/继续沟通」；150 硬顶停止并通知用户
- 更新 `data/state.md`（日期/当日投递数/批次）

## 风控即停（agent 必须遵守）
- 检测到 code 37 / "环境异常" / 页面回退循环 / "操作过于频繁" → **立即停止**，通知用户人工判断，不得重试
- 检测到验证码/滑块 → 暂停，通知用户人工处理，用户完成后恢复
- 登录页跳转 → 提示用户扫码登录（约每周一次）

## 人工介入点（仅 3 个）
1. 首次扫码登录（约每周一次，cookie 自动持久化在 data/browser_profile/）
2. 验证码出现时暂停处理
3. 风控信号时停止

## 选择器
页面选择器集中管理在 `references/selectors.md`。改版失效时只改该文件（控制层），业务逻辑不动。若某选择器失效，可用视觉兜底（截图观察）临时定位，但必须随后更新 selectors.md。

## 数据文件

| 文件 | 用途 |
|---|---|
| `data/profile.md` | 用户偏好档案（长期复用，可手改） |
| `data/state.md` | 运行状态（日期/当日投递数/批次/风控暂停，跨天自动重置） |
| `data/applied.md` | 已投递记录（去重，运行时生成） |
| `data/browser_profile/` | 浏览器 profile（登录态 cookie 持久化，运行时生成） |

## 风控信号详细清单

| 信号 | 处理 |
|---|---|
| code 37 / 页面出现「环境存在异常」 | 立即停止，通知用户，不得重试 |
| 页面回退循环（URL 回首页 / 刷新循环） | 立即停止，通知用户 |
| 「操作过于频繁」提示 | 立即停止，等待后再试（至少 30 分钟） |
| 验证码 / 滑块 | 暂停，通知用户人工处理，用户完成后恢复 |

## 选择器失效时的视觉兜底流程

1. 脚本报错（找不到元素）时，用截图观察页面当前结构：
   - CloakBrowser 截图：`page.screenshot(path="data/debug.png")`
2. agent 从截图中识别新结构，确定目标元素的当前位置
3. 用视觉定位临时完成该次操作（如坐标点击）
4. **必须**随后更新 `references/selectors.md`，记录新选择器
5. 若视觉兜底触发率超过 20% 的操作，说明选择器策略需要重写，停止并报告用户

## Agent 决策流程示例（每个岗位）

1. 检查 `data/state.md`：是否已达 150 硬顶 / 风控暂停 → 是则停止（跨天自动重置）
2. 检查岗位卡片是否有 `.is-seen` 标记 → 有则跳过
3. 检查岗位 ID 是否在 `data/applied.md` → 有则跳过
4. 规则过滤（黑名单/关键词/类型/活跃度/猎头）→ 不匹配跳过
5. （可选）LLM 匹配分 → 低于阈值跳过，评分失败 fail-open 放行
6. 执行 `apply_action.py --job-id <id>` 跳转详情页点击「立即沟通」→ 处理 120 弹窗 → 风控检测
7. 记录到 `data/applied.md`，更新 `data/state.md`
8. 下一岗位，循环
