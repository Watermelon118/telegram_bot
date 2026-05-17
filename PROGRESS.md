# 进度跟踪

> 跨对话同步用。每次对话开始先读这个文件知道做到哪。每次结束更新这个文件。

---

## 当前焦点

**项目已转型** —— 从英语学习 bot 改为 **Daily X Digest Bot**，每日 NZ 20:00 自动总结 X 博主 @李老师不是你老师 的当日推文，推给经管理员审批的订阅者。详细需求看 `PROJECT_BRIEF.md`。

**当前阶段**：Stage 2 已完成（项目骨架、Postgres、ORM、迁移、爬虫 service、worker scheduler、bot 权限分级 + 命令骨架），准备进 **Stage 3（AI 摘要管线 + 媒体处理）**。

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
- **2026-05-17 dev-conventions 元规则**：开发者要求在 conventions 第 0 节加规则"教训随手记 + 项目结束清理"。**适用所有项目**。AI 开发过程中遇到坑当时立刻追加到第 13 节，项目交付时主动回顾、去重、把通用教训抽到主章节。
- **2026-05-17 跑 2.7 时**：第一次抓只拿 17 条，2.7 验证时抓到 20 条。X 首页加载量随时间窗变化，不固定。后续 stage 实现"今日推文"逻辑时不能假设固定数量。
- **2026-05-17 worker / bot 分进程已落地**：本地开发需要同时开 3 个东西：①`docker compose up -d`（Postgres）②`uv run python -m src.main`（bot）③`uv run python -m src.worker`（scheduler）。生产 Stage 5 会用 systemd 或 docker-compose 统一编排。

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

### Stage 2：项目骨架 + 持久化 ✅ 已完成

| 子任务 | 状态 | 备注 |
|--------|------|------|
| 2.1 src/ 目录骨架 | ✅ | 8 个包，全空 `__init__.py` |
| 2.2 main.py 重构进 src/ | ✅ | src/main.py + bot/app.py + handlers/user.py + utils/logger.py；运行方式改为 `uv run python -m src.main` |
| 2.3 pydantic-settings | ✅ | src/config.py 集中所有 env 配置；当前 Stage 用到的必填，未来 Stage 用到的可选 |
| 2.4 docker-compose Postgres | ✅ | postgres:16 + UTF8 + 命名卷 + healthcheck |
| 2.5 SQLAlchemy 2.0 async models | ✅ | 8 张表全建好，typed declarative (Mapped/mapped_column) |
| 2.6 Alembic 初始化 + 第一个 migration | ✅ | env.py 用 settings.DATABASE_URL；autogenerate 出 revision 716d73449a12；upgrade head 后 Postgres 里 9 张表 |
| 2.7 services/twitter.py | ✅ | TwitterScraper（async context manager）+ DB UPSERT；验证抓 20 条入库 OK；spike/ 已清空 |
| 2.8 APScheduler + worker.py | ✅ | AsyncIOScheduler，cron minute=5 每小时触发；src/worker.py 独立进程入口 |
| 2.9 bot 权限中间件 + handler 重构 | ✅ | src/bot/middleware.py（Role admin/subscriber/guest + require_role 装饰器）；user.py 重写（/start /subscribe /unsubscribe /status + unknown 兜底）；admin.py 5 个占位命令；10 handler 注册 |

### Stage 3-5 ⬜ 未开始

见 `PROJECT_BRIEF.md` 第 7 节。

---

## 待开发者补充

- ⬜ OpenAI API Key（进 Stage 3 前充值）
- ⬜ 家里废笔记本环境（Stage 1.4/1.5 EC2 IP 被 X 风控时启用）

## 阻塞项

无。

---

## 上次对话结尾状态

2026-05-17：
- **Stage 2 全部完成**（9 个子任务）
- 项目目前形态：标准 Python web 后端骨架
  - `src/` 分层（bot/services/ai/db/scheduler/utils）
  - 8 张 Postgres 表已建（通过 Alembic）
  - TwitterScraper service 验证可用，DB UPSERT 工作
  - APScheduler 注册了 hourly scrape job
  - Bot 权限分级骨架就位，10 个 handler 注册（subscribe/admin 类全是占位，Stage 4 才接业务逻辑）
- **本地开发要同时跑的 3 件事**：
  1. `docker compose up -d`（Postgres）
  2. `uv run python -m src.main`（bot polling）
  3. `uv run python -m src.worker`（scheduler，每小时 :05 抓一次）
- 下次对话第一步：进 **Stage 3** —— AI 摘要管线（openai SDK 封装、prompts、digest service、媒体下载）+ 临时 `/test_digest` 命令验证全流程
