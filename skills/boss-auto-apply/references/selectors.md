# BOSS 直聘页面选择器清单

> 脚本使用的页面元素选择器。页面改版导致脚本找不到元素时，按此清单核对；确认变化后更新本文件并同步脚本。

## 登录
| 元素 | 选择器 | 说明 |
|---|---|---|
| 登录页检测 | URL 含 `/web/user/` 或出现 `.qrcode` | 出现即未登录，提示用户扫码 |
| 二维码 | `.qrcode` | 扫码区域 |

## 搜索
| 元素 | 选择器 | 说明 |
|---|---|---|
| 搜索页 URL | `https://www.zhipin.com/web/geek/job?query={keyword}&city={cityCode}` | 岗位搜索；筛选参数（jobType/degree/experience/salary/financingStage/scale）加在 URL 上 |
| 岗位列表容器 | `.rec-job-list` | 列表根节点 |
| 岗位卡片 | `.job-card-wrap` | 每张卡片 |
| 卡片内岗位名 | `.job-name` | 岗位名链接 |
| 公司名 | `.boss-name` | 公司名 |
| 薪资 | API `salaryDesc`（明文） | 页面内 XHR 调 `/wapi/zpgeek/search/joblist.json` 获取明文薪资；页面元素 `.job-salary` 为专用区字符，仅降级用 |
| 岗位 ID | href 中 `job_detail/{id}.html` 或 API `encryptJobId` | id 为字母数字混合 |

### 搜索筛选（search_jobs.py）
- 接口（joblist.json）筛选参数：`jobType`（1901全职/1902实习/1903兼职）、`degree`（**202大专/203本科/204硕士**，注意与 URL 值不同）、`experience`（仅 101 经验不限）、`salary`（402/403/404 等，区间模糊）
- **注意：URL 参数值与接口参数值是两套体系**（如 URL `degree=202` 是本科，接口 `degree=203` 才是本科）；脚本 `FILTER_MAPS` 存双映射，URL 过滤页面、接口过滤数据
- 接口不支持的筛选（`financingStage`/`scale` 返回 code 37）：只加 URL 过滤页面，数据仍为接口全量，agent 按返回字段自行筛选

## 详情页
| 元素 | 选择器 | 说明 |
|---|---|---|
| 立即沟通按钮 | `.btn-startchat` | 点此即打招呼（BOSS 默认带招呼语） |
| 残障人士弹窗 | `.handicapped-dialog` → `.btn-sure` | BOSS 新版必填弹窗，点「确定」关闭 |
| 确认弹窗「好」 | `text="好"` / `.confirm-btn` | 120 限额弹窗自动应答 |
| 聊天输入框 | `input[type=text], .chat-input, textarea, .send-msg, [contenteditable]` | 投递成功验证 |

## JD 详情页（view_job.py）
| 元素 | 选择器 | 说明 |
|---|---|---|
| 详情页 URL | `https://www.zhipin.com/job_detail/{jobId}.html` | 按岗位 ID 直接跳转 |
| JD 正文容器 | `.job-sec-text` | 岗位职责/任职要求，页面渲染，完整 |
| 岗位名 | `.job-primary .name h1` | 岗位名（h1 title 属性或文本） |
| 薪资 | `.job-primary .name .salary` | 薪资（如 30-50K·13薪） |
| 城市/经验/学历 | `.text-city` / `.text-experiece` / `.text-degree` | `.job-primary` 内带语义 class 的 span |
| 福利标签 | `.tag-all.job-tags` 下 `span` | 逐个标签元素，无需切词 |
| 公司基本信息 | `.sider-company` | 公司名在 `a[title]`；阶段/规模/行业在带语义 icon 的 `p`（`p > i.icon-stage` / `.icon-scale` / `.icon-industry`） |
| 公司介绍 | `.job-detail-company` 内 `.job-sec-text` | 公司介绍全文 |
| 工商信息 | `.job-detail-company` 内 `li.company-name` / `li.company-user` / `li.res-time` / `li.company-type` / `li.manage-state` / `li.company-fund` | 公司名称/法定代表人/成立日期/企业类型/经营状态/注册资金；label 在 `span`，值在 `li` 尾部文本 |
| 工作地址 | `.location-address` | 纯地址文本 |
| 经纬度 | `.job-location-map` 的 `data-lat` | 如 `116.31,39.98` |
| BOSS 信息 | `.job-boss-info` | BOSS 称呼/在线状态/职位 |
| 内嵌岗位变量 | `_jobInfo` | 页面内嵌的精简岗位信息（job_name/job_salary/company 等），字段兜底 |
| 改版处理 | 页面结构变化时，`.job-sec-text` 找不到即报错；先在有头窗口确认新结构，更新本文件并同步脚本 |

## 风控信号
| 信号 | 检测方式 |
|---|---|
| code 37 / 环境异常 | 页面出现「环境存在异常」「安全验证」文本 |
| 页面回退 | URL 回到首页 / 页面刷新循环 |
| 操作过于频繁 | 弹窗/提示「操作过于频繁」 |
