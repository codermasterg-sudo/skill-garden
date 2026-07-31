# 数据目录

本目录存放 boss-auto-apply skill 的运行时数据：

| 文件 | 用途 |
|---|---|
| `applied.md` | 已投递记录（由 agent 维护，一行一条，运行时生成，不入库） |
| `browser_profile/` | CloakBrowser 浏览器 profile（登录态 cookie 持久化，运行时生成，不入库） |

> 本目录全部为运行时生成的数据，被 .gitignore 忽略，不纳入版本库。
