# 进度跟踪

> 跨对话同步用。每次对话开始先读这个文件知道做到哪。每次结束更新这个文件。

---

## 当前焦点

**项目已转型** —— 从英语学习 bot 改为 **Daily X Digest Bot**，每日 NZ 20:00 自动总结 X 博主 @李老师不是你老师 的当日推文，推给经管理员审批的订阅者。详细需求看 `PROJECT_BRIEF.md`。

**当前阶段**：Stage 1 spike 已通过（用 Playwright 不是 twscrape），准备进 **Stage 2（项目骨架 + 持久化）**。

### 工作模式
- **Claude 直接写代码**（2026-05-16 改的：之前是"教不写"，开发者觉得自己敲效率太低）。开发者看不懂会主动问。
- 写完代码要简短解释关键点（新概念、关键决策、坑点），不用逐行讲。
- 开发者背景：Master of IT 应届毕业生，Java/Spring Boot 学习背景，Python 只用过 pandas/numpy，**没用过 Python 写 web/接 API**。
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
  - 数据库：PostgreSQL，schema 重新设计了 8 张表（见 brief 第 5 节）
- **2026-05-15 6.8 UTF-8 收紧**：从"代码里用 UTF-8"扩展到"所有读写 I/O 边界全部 UTF-8"，覆盖文件、日志、数据库、网络、subprocess、进程级 env、模板/prompt。
- **2026-05-15 Python 降版**：3.14 → 3.12.13（PTB v21 不兼容 3.14）。`requires-python = ">=3.11,<3.14"`。
- **2026-05-15 跨阶段决策**：先做 Stage 0 热身（最简 echo bot）熟悉 Python，再进正式开发。
- **2026-05-16 爬虫库换 Playwright（关键转向）**：原计划 `twscrape` 不可用。验证过程：
  - twscrape 0.17.0（PyPI 最新）有 issue #305 —— X 改了 JS bundle obfuscation，`load_keys()` 解析不到 `x-client-transaction-id`，所有 GraphQL 调用空响应。
  - PR #303 的修复分支只是把崩溃改成"优雅失败"，没真正解决问题。
  - 改用 Playwright（headless Chromium）+ cookies 注入，拦截 X 自家的 GraphQL 响应。这条路工作良好。
  - 代价：Chromium 镜像 ~290MB；每次抓取启动浏览器 ~10s；部署到 EC2 需要预装 Chromium。
  - 收益：fingerprint 是真浏览器、不依赖第三方库跟进 X 反爬变化、JSON 结构稳定。
- **2026-05-16 工作模式调整**：从"Claude 教不写"改为"Claude 直接写"，开发者觉得自己敲效率太低。Claude 写完简短解释关键点。
- **2026-05-16 协作风格**：开发者明确要 Claude 严格记忆事实、不要补细节（之前编"10 年经验"被指出）。

---

## Stage 进度

### Stage 0：热身 ✅ 已完成

| 子任务 | 状态 | 备注 |
|--------|------|------|
| 0.1 装 Python 和 uv | ✅ | Python 3.12.13；uv 0.11.14 |
| 0.2 uv init 项目骨架 | ✅ | pyproject.toml / main.py / .venv / uv.lock |
| 0.3 装 python-telegram-bot v21 | ✅ | 21.11.1 + python-dotenv 1.2.2 |
| 0.4 写 echo bot 并跑通 | ✅ | polling 模式，发 /start 和文字消息能正常回复，中文 OK |

### Stage 1：X 爬虫 spike ✅ 本地通过（EC2 验证延后）

**目标**：验证能稳定抓 @whyyoutouzhele（李老师不是你老师）的推文。**最终方案：Playwright + cookies，不是 twscrape**。

| 子任务 | 状态 | 备注 |
|--------|------|------|
| 1.1 注册 X 爬虫账号 | ✅ | 第一个新号被秒封；改用开发者老号 watermelon1448，浏览器手动登录 + 导出 cookies |
| 1.2 装爬虫库 | ✅ | 原计划 twscrape 不可用，改装 `playwright` + Chromium |
| 1.3 写 spike 脚本本地跑通 | ✅ | `spike/x_scrape.py`：headless Chromium + cookies + 拦截 GraphQL，本地一次抓 17 条今日推文，所有字段（含 views）正确 |
| 1.4 EC2 悉尼部署 spike | ⏸️ 延后 | 等 Stage 5 部署阶段一起做 |
| 1.5 24 小时观察成功率 | ⏸️ 延后 | 跟 1.4 一起 |

### Stage 2-5 ⬜ 未开始

见 `PROJECT_BRIEF.md` 第 7 节。

---

## 待开发者补充

- ⬜ OpenAI API Key（进 Stage 3 前充值）
- ⬜ 家里废笔记本环境（Stage 1.4/1.5 EC2 IP 被 X 风控时启用）

## 阻塞项

无。

---

## 上次对话结尾状态

2026-05-16：
- Stage 1 spike 本地通过 ✅
- 关键转向：twscrape 被 X 反爬干掉，改用 **Playwright + cookies + 拦截 GraphQL**
- spike 脚本 `spike/x_scrape.py` 一次抓 17 条今日推文，所有字段（含 views）正确，头条选择算法验证通过
- EC2 验证（1.4/1.5）延后到 Stage 5 部署阶段一起做
- 工作模式改成 "Claude 直接写，开发者看不懂会问"
- 下次对话第一步：进 Stage 2 —— 项目骨架（src/ 目录树）+ pydantic-settings 配置 + docker-compose Postgres + Alembic 初始化 + SQLAlchemy 2.0 async models
