# 进度跟踪

> 跨对话同步用。每次对话开始先读这个文件知道做到哪。每次结束更新这个文件。

---

## 当前焦点

**项目已转型** —— 从英语学习 bot 改为 **Daily X Digest Bot**，每日 NZ 20:00 自动总结 X 博主 @李老师不是你老师 的当日推文，推给经管理员审批的订阅者。详细需求看 `PROJECT_BRIEF.md`。

**当前阶段**：Stage 0 热身已完成，准备进 **Stage 1（X 爬虫 spike）**。

### 工作模式
- **Claude 教，开发者动手**。不要替开发者写代码，让他自己敲。
- 开发者背景：Java/Spring Boot 全栈 10 年，Python 只用过 pandas/numpy，**没用过 Python 写 web/接 API**。
- 解释时多用 Java 类比（pyproject.toml ≈ pom.xml，uv ≈ Maven，virtualenv ≈ 项目级 classpath 隔离）。
- 节奏要慢，每条消息只讲一小步、一个概念。开发者抱怨过"一次出来太多"。

---

## 已做的决策（重要，按时间倒序）

- **2026-05-15 项目转型**：
  - 不再做英语学习 bot
  - 改做 X 博主每日推文总结 + 推送
  - 跟踪博主：**@李老师不是你老师**
  - 推送时间：每日 **NZ 20:00**
  - 头条选择：评论 + 点赞 + 浏览 三者之和最高的一条
  - 媒体处理：原图原视频下载后用 Telegram 原生消息发送
  - 订阅模式：**管理员审批制**（开发者本人是 admin）
  - AI 切换：**OpenAI GPT，不能用千问**（国产模型对新闻类内容审查严，无法用）
  - 爬虫方案：**twscrape 自建**，先 AWS EC2 悉尼，失败降级到家里废笔记本
  - 数据库：PostgreSQL，schema 重新设计了 6 张表（见 brief 第 5 节）
- **2026-05-15 6.8 UTF-8 收紧**：从"代码里用 UTF-8"扩展到"所有读写 I/O 边界全部 UTF-8"，覆盖文件、日志、数据库、网络、subprocess、进程级 env、模板/prompt。
- **2026-05-15 Python 降版**：3.14 → 3.12.13（PTB v21 不兼容 3.14）。`requires-python = ">=3.11,<3.14"`。
- **2026-05-15 跨阶段决策**：先做 Stage 0 热身（最简 echo bot）熟悉 Python，再进正式开发。

---

## Stage 进度

### Stage 0：热身 ✅ 已完成

| 子任务 | 状态 | 备注 |
|--------|------|------|
| 0.1 装 Python 和 uv | ✅ | Python 3.12.13；uv 0.11.14 |
| 0.2 uv init 项目骨架 | ✅ | pyproject.toml / main.py / .venv / uv.lock |
| 0.3 装 python-telegram-bot v21 | ✅ | 21.11.1 + python-dotenv 1.2.2 |
| 0.4 写 echo bot 并跑通 | ✅ | polling 模式，发 /start 和文字消息能正常回复，中文 OK |

### Stage 1：X 爬虫 spike ⬜ 下一步

**目标**：验证 twscrape 能在 EC2 或本地稳定抓 @李老师不是你老师 的推文。

| 子任务 | 状态 | 备注 |
|--------|------|------|
| 1.1 注册 X 爬虫小号 | ⬜ 待开发者 | **不要用日常 X 账号** |
| 1.2 `uv add twscrape` | ⬜ | |
| 1.3 写 spike 脚本本地跑通 | ⬜ | `spike/x_scrape.py` |
| 1.4 EC2 悉尼部署 spike | ⬜ | 验证 IP 是否被 X 风控 |
| 1.5 24 小时观察成功率 | ⬜ | 决定走 EC2 还是降级笔记本 |

### Stage 2-5 ⬜ 未开始

见 `PROJECT_BRIEF.md` 第 7 节。

---

## 待开发者补充

- ⬜ OpenAI API Key（进 Stage 3 前充值）
- ⬜ X 爬虫小号（进 Stage 1 前注册）
- ⬜ 家里废笔记本环境（Stage 1.5 失败时启用）

## 阻塞项

无。

---

## 上次对话结尾状态

2026-05-15：
- Stage 0 完成，echo bot 跑通（Python 3.12.13）
- 项目重大转型：英语学习 → X 每日新闻总结
- PROJECT_BRIEF.md 完全重写
- 准备进 Stage 1：X 爬虫 spike（**最高优先级，因为最大不确定性**）
- 下次对话第一步：让开发者注册 X 爬虫小号 + `uv add twscrape`
