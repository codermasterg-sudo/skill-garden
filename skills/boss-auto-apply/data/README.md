# 数据目录

本目录存放 boss-auto-apply skill 的运行时数据：

| 文件 | 用途 |
|---|---|
| `profile.md` | 用户偏好档案（模板入库；运行时由 agent 对话更新，长期复用） |
| `state.md` | 运行状态（当日投递数/批次/风控暂停） |
| `applied.md` | 已投递记录（去重用，运行时生成，不入库） |
| `browser_profile/` | CloakBrowser 浏览器 profile（登录态 cookie 持久化，运行时生成，不入库） |

> 模板文件（profile.md / state.md 初始内容）由本仓库维护；运行后的实际数据由脚本写入。
> 运行时生成的数据（applied.md、browser_profile/）被 .gitignore 忽略，不纳入版本库。
