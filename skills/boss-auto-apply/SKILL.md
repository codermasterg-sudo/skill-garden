---
name: boss-auto-apply
description: BOSS直聘自动投递简历。解析用户简历、建立偏好档案、智能筛选岗位、自动点击「立即沟通」。当用户需要自动投递简历、批量打招呼、筛选匹配岗位时使用。
---

# Boss Auto Apply — BOSS直聘自动投递

## 免责声明
自动投递可能违反 BOSS直聘用户协议，有账号被风控（临时停用至永久封禁）风险。使用前请知悉，建议控制单批数量，谨慎操作。

## 工作流程（agent 按此编排执行）

### 0. 环境准备
- 首次使用安装依赖：`pip install cloakbrowser`（含 playwright）
- 浏览器 profile 目录：`data/browser_profile/`（自动创建，登录态持久化）

### 1. 解析简历
- 输入：用户提供简历文件路径（.docx / .pdf）
- 执行：`python3 scripts/parse_resume.py <简历路径> [--output data/resume.md]`
- 输出：结构化简历 Markdown（姓名/经验/技能/期望岗位/城市/薪资）

### 2. 建立/更新偏好档案
- 读取 `data/profile.md`（不存在则创建）
- 从简历 + 对话收集：岗位关键词、城市、薪资范围、类型（实习/全职）、黑名单（公司/岗位）
- 每次对话中新要求随时追加写入；档案长期复用

### 3. 搜索岗位
- 执行：`python3 scripts/search_filter.py --mode search --keyword <岗位> --city <城市> [--page 1]`
- 用 CloakBrowser 打开 BOSS 搜索页，等待登录态，抓取岗位列表

### 4. 智能筛选（双层漏斗）
- 规则过滤（第一层，免费确定性）：黑名单公司/岗位、薪资范围、HR 活跃度>2周、猎头排除
- LLM 匹配分（第二层）：简历 vs JD 匹配度评分，阈值跳过；评分失败 fail-open 放行
- 执行：`python3 scripts/search_filter.py --mode filter --resume data/resume.md --profile data/profile.md --jobs <jobs.json>`

### 5. 点击「立即沟通」
- 执行：`python3 scripts/apply_action.py --action say_hello --job-id <id> [--resume data/resume.md]`
- 真实点击（非 API 构造）；120 弹窗自动应答；150 硬顶停止；记录已投递

### 6. 循环与限额
- 每岗位 3-10 秒随机延迟；每 15-20 个休息 1-3 分钟；单批 30-50 个
- 当日 120 提示弹窗自动点「好/继续沟通」；150 硬顶停止并通知用户
- 更新 `data/state.md`（当日投递数/批次）

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
