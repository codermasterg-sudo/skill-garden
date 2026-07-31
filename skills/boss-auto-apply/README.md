# Boss Auto Apply — BOSS直聘自动投递 Skill

自动解析简历、建立偏好档案、智能筛选岗位并自动点击「立即沟通」的通用 Agent Skill。可在任何支持 skill 约定的 agent 环境（Claude Code、其他 agent 框架）中加载执行。

## 用途

- 解析用户简历（.docx / .pdf），提取关键字段
- 建立并长期复用偏好档案（岗位关键词、城市、薪资范围、类型、黑名单）
- 按偏好搜索 BOSS 直聘岗位
- 双层漏斗筛选（规则过滤 + LLM 匹配分，评分失败 fail-open 放行）
- 自动点击「立即沟通」打招呼，处理每日 120/150 限额
- 风控信号识别即停，仅保留 3 个人工介入点

## 免责声明

- **仅供学习交流使用，禁止用于商业用途。**
- 自动投递可能违反 BOSS直聘用户协议，有账号被风控（临时停用至永久封禁）风险。
- **使用者自行承担全部责任**（账号风险、平台追责、法律风险等），作者不承担任何责任。
- 建议使用小号测试、控制单批数量，谨慎操作。

## 安装与依赖

```bash
pip install -r scripts/requirements.txt   # cloakbrowser / python-docx / PyMuPDF（首次使用执行）
```

浏览器 profile 目录 `data/browser_profile/` 自动创建，登录态（cookie）自动持久化，无需手动维护。

## 使用

1. 提供简历文件路径，运行解析：`python3 scripts/parse_resume.py <简历路径> --output data/resume.md`
2. 确认/补充偏好档案 `data/profile.md`
3. 按需执行搜索、筛选、投递（详见 `SKILL.md` 工作流程章节，agent 按此编排）
4. 首次使用需扫码登录一次（cookie 有效期约 7 天，过期后需重新扫码）

## 注意事项

- **风控风险**：自动投递可能违反 BOSS直聘用户协议，有账号被风控风险。建议控制单批数量（30-50 个），谨慎操作。
- **检测到风控信号立即停止**：code 37 / "环境异常" / 页面回退循环 / "操作过于频繁" → 立即停止并通知用户，不得重试。
- **验证码出现时暂停**：通知用户人工处理，完成后恢复。
- **页面选择器集中管理**：改版失效时只改 `references/selectors.md`（控制层），业务逻辑不动；失效时可用视觉兜底临时定位，但必须随后更新该文件。

## 目录结构

```
skills/boss-auto-apply/
├── SKILL.md              # skill 入口（agent 读取并编排执行）
├── README.md             # 本文件
├── data/                 # 数据目录（模板入库，运行时数据 gitignore）
│   ├── profile.md        # 用户偏好档案（模板）
│   ├── state.md          # 运行状态（模板）
│   └── README.md         # 数据目录说明
├── scripts/              # Python 辅助脚本
│   ├── parse_resume.py   # 解析 Word/PDF 简历
│   ├── profile_manager.py# 偏好档案管理
│   ├── search_filter.py  # 搜索 + 规则过滤 + LLM 匹配
│   ├── llm_matcher.py    # LLM 匹配模块
│   ├── apply_action.py   # 点击「立即沟通」+ 限额处理
│   └── state_manager.py  # 运行状态管理
└── references/
    └── selectors.md      # BOSS 页面选择器地图（控制层）
```

> 详细设计见 `docs/superpowers/specs/2026-07-31-boss-auto-apply-design.md`。
