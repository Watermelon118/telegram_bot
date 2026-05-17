# 进度跟踪

> 跨对话同步用。每次对话开始先读这个文件知道做到哪。每次结束更新这个文件。

---

## 当前焦点

**项目已转型** —— 从英语学习 bot 改为 **Daily X Digest Bot**，每日 NZ 20:00 自动总结 X 博主 @李老师不是你老师 的当日推文，推给经管理员审批的订阅者。详细需求看 `PROJECT_BRIEF.md`。

**当前阶段**：Stage 5 已完成（每日推送 + 调度 + Docker 生产部署 + GitHub Actions CI/CD），等待生产 `/test_push` 验证和 24 小时观察。

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
- **2026-05-17 Stage 3 AI 管线设计决策**：
  - `ai/client.py` 是所有 OpenAI 调用的**唯一入口**（指数退避 3 次重试、token + cost 写入 `ai_call_log`、价格表硬编码在文件常量里 2026-05 抓取）。理由：换模型/加缓存只改一处；服务层不裸调 SDK。
  - per-tweet 摘要 5 并发（Semaphore 限流），单条挂用 "[摘要失败]" 占位，不拖垮整批；overall takeaway 失败时整体仍能发出。
  - digest 时间窗用"NZ 当日全天"而不是 brief 写死的"00:00-20:00"——生产 19:30 触发时与 brief 等价，开发期 `/test_digest` 任何时间都能跑。
  - 单条推（边界）跳过 AI 调用省钱；0 条推不落 `daily_digests` 行（UNIQUE 约束 + 无意义）。
  - 头条 caption ≤ 1024 字符时附在媒体上，超过自动拆成"媒体 + 文字"两条消息（Telegram bot caption 上限）；视频 > 50MB 退化为"链接 + 说明"。
  - 渲染逻辑放在 `src/bot/handlers/_digest_render.py`（前缀 `_`），Stage 5 push.py 会复用。
- **2026-05-17 Stage 3 验证数据**：本地 `/test_digest` 后台流程实测：20 条推（1 头条 + 19 要闻）→ AI 调用 20 次（19 mini + 1 4o）→ 输入 4331 tokens / 输出 498 tokens / 成本 **$0.003144 USD**（≈0.3 美分一次）。按每日 1 次推送估算月成本约 $0.10，OpenAI 不会是预算瓶颈。
- **2026-05-17 要闻段收紧到 Top 5**：原方案要把"头条之外的所有推文"都摘要进要闻（19 条），用户觉得太长不愿意看。改为"按热度排名 2-6 名共 5 条"，热度低的丢掉不进 digest 也不入库 `other_tweet_ids`。
  - **理由**：①用户体验（一屏看完）②AI 成本（20 次 → 6 次）③整体看点更聚焦（只综合热门话题不被噪声稀释）
  - **实现**：`src/services/digest.py` `_BRIEFS_MAX_COUNT=5` 常量；按 `_score()` 排序后切片 `by_heat[1:6]`。
  - **如何应用**：要改成展示更多/更少，调这个常量即可。
- **2026-05-17 Stage 4 订阅审批实现决策**：
  - `src/services/subscription.py` 是订阅状态机唯一入口，handler 不直接写三张订阅表。
  - `/unsubscribe` 按 brief 6.9 做硬删除，用户主动取消后不保留 subscriber 行。
  - `/revoke` 做 `enabled=False` 软撤销，保留管理员撤销痕迹；用户之后仍可重新 `/subscribe` 走审批。
  - 审批动作先落库，再通知用户。通知失败不回滚状态，只向管理员提示并写日志。
  - 已按"一个功能点一个 commit"执行：service、user commands、admin commands、docs 分别提交。
- **2026-05-18 Stage 5 部署决策**：
  - 生产用 Docker Compose 托管 `postgres`、`migrate`、`bot`、`worker` 四个服务；migration 作为一次性服务在 bot/worker 前执行。
  - GitHub Actions 负责 CI 和手动生产部署，不在 EC2 上手工改代码当正式流程。
  - Actions 把当前 commit 打包上传到 EC2 的 `releases/<sha>`，共享密钥只放 `shared/.env`，`current` 指向最近部署版本。
  - Compose 顶层项目名固定为 `daily-x-digest`，避免和服务器上已有项目的默认 `deploy` 项目名混淆。
  - 生产日志必须过滤 secrets；`httpx` INFO 会打印 Telegram API 完整 URL，里面包含 bot token，因此生产默认把 `httpx/httpcore` 降到 WARNING，并加全局脱敏 filter。

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

### Stage 3：AI 摘要管线 + 媒体处理 ✅ 已完成

| 子任务 | 状态 | 备注 |
|--------|------|------|
| 3.1 ai/client.py（封装 + 重试 + ai_call_log）| ✅ | openai 2.37 + httpx 0.28；价格表硬编码 gpt-4o-mini / gpt-4o；3 次指数退避 |
| 3.2 ai/prompts.py | ✅ | per-tweet 摘要（30 字以内一句话）+ overall takeaway（80-150 字 2-3 句） |
| 3.3 services/summary.py | ✅ | per-tweet 5 并发 Semaphore；单条失败 "[摘要失败]" 占位 |
| 3.4 services/media.py | ✅ | httpx 下载图/视频到 tempfile；视频 HEAD 预检 + 流式途中守 50MB；cleanup 清临时文件 |
| 3.5 services/digest.py | ✅ | DigestPackage dataclass；NZ 当日时间窗；UPSERT daily_digests by (date, author) |
| 3.6 /test_digest 命令 + render | ✅ | admin only；渲染逻辑独立到 `bot/handlers/_digest_render.py` 供 Stage 5 push 复用；handler 总数 10→11 |

**Stage 3 验证**：
- 后台流程已用真实数据跑通（20 条推 → digest 行落库 → ai_call_log 落库）
- 管理员 `/test_digest` Telegram 端到端测试**通过**（2026-05-17）：head + media + briefs 三段渲染、`sendMediaGroup` 200、所有 AI 调用成功
- 单次成本 **$0.001687 USD**（5 mini × $0.000043 + 1 4o × $0.001653）

### Stage 4：订阅管理 + 管理员审批流 ✅ 已完成

| 子任务 | 状态 | 备注 |
|--------|------|------|
| 4.1 subscription state machine | ✅ | `src/services/subscription.py`；申请/批准/拒绝/撤销/取消/状态查询 |
| 4.2 用户命令 | ✅ | `/subscribe` `/unsubscribe` `/status` 接真实业务；新申请自动通知管理员 |
| 4.3 管理员命令 | ✅ | `/pending` `/approve` `/deny` `/revoke` `/subscribers` 接真实业务；审批后通知申请人 |
| 4.4 本地验证 | ✅ | 用测试 user_id 跑通申请→批准→取消、申请→拒绝、申请→批准→撤销→重新申请 |

### Stage 5：每日推送 + 调度 + 部署 ✅ 已完成

| 子任务 | 状态 | 备注 |
|--------|------|------|
| 5.1 `services/push.py` 广播 | ✅ | 遍历 enabled subscribers，记录 `push_history`，连续 3 次失败自动禁用 |
| 5.2 NZ 19:30/20:00 调度 | ✅ | 19:30 预生成 digest，20:00 推送；失败通知 admin |
| 5.3 `/test_push` | ✅ | 只推给管理员，用于部署后端到端验证 |
| 5.4 `/broadcast` | ✅ | 管理员公告推送给所有 enabled subscribers |
| 5.5 `/cost` | ✅ | 查看近 N 天 OpenAI 成本 |
| 5.6 Docker 生产配置 | ✅ | Dockerfile + `deploy/docker-compose.prod.yml`，bot/worker/migrate/postgres 四服务 |
| 5.7 GitHub Actions CI/CD | ✅ | PR/main 跑 CI，手动 dispatch 部署到 EC2 |
| 5.8 README / `.env.example` | ✅ | 本地运行、生产部署、验证步骤已补齐 |

---

## 待开发者补充

- ✅ OpenAI API Key（已充值 + 配置）
- ✅ GitHub Actions repo secrets / variables（EC2、Telegram、OpenAI、X cookies、Postgres）
- ⏸️ 家里废笔记本环境（EC2 IP 被 X 风控时启用）

## 阻塞项

无。

---

## 上次对话结尾状态

2026-05-18（Stage 5 完成，当前分支 `feature/stage-5-daily-push-deploy`）：
- **Stage 5 全部代码和部署配置已完成**：
  - `src/services/push.py`：每日 digest 广播、公告广播、push_history、失败自动禁用。
  - `src/scheduler/jobs.py`：NZ 19:30 生成 digest，NZ 20:00 推送。
  - 管理员命令：`/test_push`、`/broadcast`、`/cost`。
  - 生产部署：Dockerfile、Compose、GitHub Actions CI/CD、README、`.env.example`。
- **本地验证已通过**：
  - `uv run python -m compileall src`
  - `uv run alembic upgrade head`
  - `build_application()` 正常构建
  - `build_scheduler()` 正常注册 3 个 job
  - `docker compose -f deploy/docker-compose.prod.yml config --quiet`
  - `docker build -t daily-x-digest-bot:stage5-local .`
- **下一步**：merge 到 `main` 后触发 GitHub Actions 手动部署，部署完成后在 Telegram 发 `/test_push` 做生产端到端验证。
