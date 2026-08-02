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
| 搜索页 URL | `https://www.zhipin.com/web/geek/job?query={keyword}&city={cityCode}` | 岗位搜索 |
| 岗位列表容器 | `.rec-job-list` | 列表根节点 |
| 岗位卡片 | `.job-card-wrap` | 每张卡片 |
| 卡片内岗位名 | `.job-name` | 岗位名链接 |
| 公司名 | `.boss-name` | 公司名 |
| 薪资 | API `salaryDesc`（明文） | 页面内 XHR 调 `/wapi/zpgeek/search/joblist.json` 获取明文薪资；DOM `.job-salary` 为字体加密，仅降级用 |
| 岗位 ID | href 中 `job_detail/{id}.html` 或 API `encryptJobId` | id 为字母数字混合 |

## 详情页
| 元素 | 选择器 | 说明 |
|---|---|---|
| 立即沟通按钮 | `.btn-startchat` | 点此即打招呼（BOSS 默认带招呼语） |
| 残障人士弹窗 | `.handicapped-dialog` → `.btn-sure` | BOSS 新版必填弹窗，点「确定」关闭 |
| 确认弹窗「好」 | `text="好"` / `.confirm-btn` | 120 限额弹窗自动应答 |
| 聊天输入框 | `input[type=text], .chat-input, textarea, .send-msg, [contenteditable]` | 投递成功验证 |

## 风控信号
| 信号 | 检测方式 |
|---|---|
| code 37 / 环境异常 | 页面出现「环境存在异常」「安全验证」文本 |
| 页面回退 | URL 回到首页 / 页面刷新循环 |
| 操作过于频繁 | 弹窗/提示「操作过于频繁」 |
