# Daily X Digest Bot — Project Brief

> 这份文档是给 Claude Code 看的，包含完整的项目背景、需求、技术决策和开发路线。请在动手前完整读一遍，遇到歧义先问，不要自己脑补。

---

## 1. 项目背景

**用户**：开发者本人（管理员）+ 经管理员审批的少量订阅者。开发者在新西兰奥克兰，Java/Spring Boot 全栈背景，Python 是为这个项目临时学的，所以代码风格要清晰、注释适度、便于学习理解。

**目标**：
1. 做一个**每天自动总结某个 X 博主当日推文**的 Telegram bot
2. 作为 GitHub 上的求职作品集项目，能在面试中讲清楚架构决策
3. 部署在自有的 AWS EC2 服务器上（悉尼区）

**核心数据源**：X (Twitter) 博主 **@李老师不是你老师**（中文新闻聚合类博主，每日发文量较大）。

**不是什么**：
- 不是开放给所有人订阅的 SaaS（订阅需管理员审批）
- 不是 X 全站搜索 / 实时新闻流（只跟踪一个博主）
- 不是英语学习工具（项目早期 brief 是这个方向，已转型）

---

## 2. 功能需求

### 2.1 每日推送

**触发时间**：每天 **新西兰时间 20:00（Pacific/Auckland）** 自动推送给所有已批准的订阅者。

**推送内容**：当日（NZ 时间 00:00 - 20:00 这 20 小时内，按 X 博主推文的发布时间过滤）该博主发布的所有推文，分两段呈现：

#### 第一段：头条推文（一条）

**选择规则**：在当日所有推文里，按 **`comments + likes + views`** 三者之和最大的一条作为头条。

**格式（按公众号头条样式排版）**：

```
🔥 今日头条

[推文正文，原文照抄]

📊 评论 1,234 · 点赞 5,678 · 浏览 123,456
🔗 [原推文链接]
```

如果该推文带图片或视频：**下载原始媒体，作为 Telegram 原生 photo / video 消息独立发送一条**，配上面的文字作为 caption。多张图（X 最多 4 张）用 `sendMediaGroup` 组合发。视频如果超过 Telegram 50MB 限制（普通 bot），只发缩略图 + 链接，并在 caption 里说明"原视频较大，点击链接查看"。

#### 第二段：今日要闻（其余推文摘要）

剩下所有推文做一个**AI 生成的摘要列表**，让用户一眼看完今天发生了什么。格式：

```
📰 今日要闻（共 X 条）

• [一句话提炼推文 1 核心] 🔗 [链接]
• [一句话提炼推文 2 核心] 🔗 [链接]
• ...

📝 整体看点：
[AI 综合所有推文给出 2-3 句话的"今天主要在关注什么"总结]
```

**特殊情况**：
- 当日博主没发推：发一条"今天 @李老师不是你老师 没有更新"
- 当日只有 1 条推：那一条就是头条，不出"今日要闻"段
- 爬虫当日失败：发一条"今天数据抓取失败，请联系管理员"并通知管理员

### 2.2 订阅管理（管理员审批制）

**用户视角命令**：

| 命令 | 行为 |
|------|------|
| `/start` | 显示欢迎信息和使用说明 |
| `/subscribe` | 提交订阅申请。bot 把申请放进 `pending_requests` 表，**同时把申请通知发给管理员**（含申请人的 telegram user_id、用户名、申请时间） |
| `/unsubscribe` | 取消自己的订阅。从 `subscribers` 表删除 |
| `/status` | 查询自己当前状态：未申请 / 待审批 / 已订阅 / 已拒绝 |

**管理员视角命令**（只有 `ADMIN_USER_ID` 能用）：

| 命令 | 行为 |
|------|------|
| `/pending` | 列出所有待审批申请 |
| `/approve <user_id>` | 批准某个申请，从 `pending_requests` 移到 `subscribers`，bot 通知该用户"你已被批准订阅" |
| `/deny <user_id> [原因]` | 拒绝申请，记录拒绝原因，通知申请人 |
| `/revoke <user_id>` | 撤销某个已订阅用户的订阅，通知该用户 |
| `/subscribers` | 列出当前所有订阅者 |
| `/broadcast <消息>` | 临时手动广播一条消息给所有订阅者（用于公告） |
| `/test_push` | 立即触发一次今日推送（用于调试，只推给管理员自己） |

### 2.3 不做的功能（明确砍掉）

- 多博主跟踪（只一个）
- 全文搜索历史推文
- 评论互动 / 转发 / 引用功能
- Web 管理后台
- 推送时间个性化（所有订阅者统一 NZ 20:00）
- 多语言界面（中文为主）

---

## 3. 技术栈（已决定，不要改）

| 模块 | 选型 |
|------|------|
| 语言 | Python 3.12（不能用 3.14，PTB v21 不兼容） |
| 包管理 | `uv` |
| Telegram 库 | `python-telegram-bot` v21+ |
| AI SDK | `openai` 官方 Python SDK（直连 OpenAI，不走兼容端点） |
| X 爬虫 | `playwright`（headless Chromium）+ cookies 注入 + 拦截 X 自家 GraphQL 响应。**不是** twscrape（2026-05-16 spike 验证后切换，见决策记录） |
| ORM | SQLAlchemy 2.0（async 模式） |
| 数据库迁移 | Alembic |
| 数据库 | PostgreSQL 16 |
| 数据库驱动 | `asyncpg` |
| 定时任务 | APScheduler |
| HTTP 客户端 | `httpx`（下载推文媒体） |
| 配置管理 | `pydantic-settings` |
| 容器化 | Docker + docker-compose |
| 部署 | AWS EC2 悉尼区（ap-southeast-2） |

**关于 AI 模型的选择策略**（OpenAI GPT 系列）：

| 任务 | 模型 | 理由 |
|------|------|------|
| 单条推文摘要（要闻段每条一句话） | `gpt-4o-mini` | 数量多、任务简单、便宜 |
| "今日整体看点" 2-3 句总结 | `gpt-4o` | 需要综合理解 |
| （可选）头条推文深度解读 | `gpt-4o` | 高价值内容用好模型 |

**这个选择是面试讲点**：不同任务用不同模型，平衡质量和成本。代码里要有清晰的封装（`ai/client.py`）让"换模型"只改一行。

**为什么不能用国产模型（千问、文心等）**：本项目核心是新闻聚合，中文 AI 服务对新闻类内容有严格的内容审查，会拒绝处理大量政治、社会议题。OpenAI GPT 没有这个问题。**这个项目永远不要切回千问。**

---

## 4. 项目结构

```
daily-x-digest-bot/
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── docker-compose.yml      # 本地起 Postgres
├── Dockerfile              # 部署用
│
├── src/
│   ├── __init__.py
│   ├── main.py             # Telegram bot 入口
│   ├── worker.py           # 爬虫 + 推送 worker 入口（与 bot 进程分离）
│   ├── config.py           # pydantic-settings 配置
│   │
│   ├── bot/
│   │   ├── __init__.py
│   │   ├── app.py          # PTB Application 初始化
│   │   ├── handlers/
│   │   │   ├── __init__.py
│   │   │   ├── user.py     # /start /subscribe /unsubscribe /status
│   │   │   └── admin.py    # /pending /approve /deny /revoke /subscribers /broadcast /test_push
│   │   └── middleware.py   # 权限分级（admin / subscriber / guest）
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── twitter.py      # twscrape 封装：抓取指定博主的推文
│   │   ├── media.py        # 下载推文媒体到本地临时文件
│   │   ├── summary.py      # AI 摘要：单条摘要 + 整体看点
│   │   ├── digest.py       # 编排"今日头条 + 今日要闻"的组装
│   │   ├── push.py         # 广播给所有 subscribers
│   │   └── subscription.py # 订阅状态机：申请/批准/拒绝/撤销
│   │
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── client.py       # OpenAI 客户端封装，含重试/超时/token 统计
│   │   └── prompts.py      # Prompt 模板集中管理
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py       # SQLAlchemy 模型
│   │   ├── session.py
│   │   └── migrations/     # Alembic
│   │
│   ├── scheduler/
│   │   ├── __init__.py
│   │   └── jobs.py         # APScheduler 任务：每小时爬取、每天 20:00 推送
│   │
│   └── utils/
│       ├── __init__.py
│       └── logger.py       # JSON 日志配置
│
└── tests/
```

**架构原则**：
1. **services 不依赖 bot 层** —— services 只懂业务（抓推文、摘要、推送），不懂 Telegram。换平台只改 bot 层。
2. **bot 和 worker 分进程跑** —— Telegram bot 一直 polling 响应命令；worker 跑爬虫和定时推送。它们共享数据库但不共享内存。这样某一边崩了不影响另一边。
3. **prompts 集中** —— 所有 prompt 模板放在 `ai/prompts.py`，便于版本化、迭代、A/B。
4. **handler 薄，service 厚** —— handler 只做参数解析 + 调 service + 格式化回复。业务逻辑都在 service。
5. **配置走环境变量** —— 任何 secret、可变参数全部从 `.env` 读，代码里不出现 magic string。

---

## 5. 数据库 Schema

```sql
-- X 博主元数据（理论上支持未来加多个，目前只 1 个）
CREATE TABLE x_authors (
    id SERIAL PRIMARY KEY,
    screen_name VARCHAR(64) UNIQUE NOT NULL,    -- 不带 @ 的 X username
    display_name VARCHAR(128),
    user_id_x VARCHAR(64),                       -- X 平台内部 user id
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 抓取到的推文
CREATE TABLE tweets (
    id BIGINT PRIMARY KEY,                       -- X 平台的 tweet id（snowflake，去重用）
    author_id INTEGER REFERENCES x_authors(id),
    text TEXT NOT NULL,
    posted_at TIMESTAMPTZ NOT NULL,              -- 推文发布时间（X 原始）
    reply_count INTEGER DEFAULT 0,
    like_count INTEGER DEFAULT 0,
    view_count INTEGER DEFAULT 0,
    retweet_count INTEGER DEFAULT 0,
    quote_count INTEGER DEFAULT 0,
    media JSONB,                                  -- [{type:'photo'|'video'|'gif', url:'...', ...}]
    permalink VARCHAR(500),                       -- 原推文 URL
    raw_payload JSONB,                            -- 原始抓取数据，留底
    scraped_at TIMESTAMPTZ DEFAULT NOW(),
    last_metric_update_at TIMESTAMPTZ DEFAULT NOW()  -- 统计数据最后一次更新
);

CREATE INDEX idx_tweets_posted_at ON tweets(posted_at);
CREATE INDEX idx_tweets_author_posted ON tweets(author_id, posted_at);

-- 每日推送摘要（落库，方便回溯和调试）
CREATE TABLE daily_digests (
    id SERIAL PRIMARY KEY,
    digest_date DATE NOT NULL,                    -- NZ 时区的日期
    author_id INTEGER REFERENCES x_authors(id),
    featured_tweet_id BIGINT REFERENCES tweets(id),
    other_tweet_ids BIGINT[],                     -- 当日其他推文 id 列表
    summary_per_tweet JSONB,                      -- {tweet_id: "一句话摘要"}
    overall_takeaway TEXT,                        -- "整体看点" 2-3 句
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    model_used VARCHAR(64),
    input_tokens INTEGER,
    output_tokens INTEGER,
    UNIQUE(digest_date, author_id)
);

-- 订阅者
CREATE TABLE subscribers (
    user_id BIGINT PRIMARY KEY,                   -- Telegram user id
    username VARCHAR(64),                          -- Telegram @username（可能为空）
    first_name VARCHAR(128),
    approved_at TIMESTAMPTZ DEFAULT NOW(),
    approved_by BIGINT,                            -- 哪个管理员批的（目前只有一个，未来扩展）
    enabled BOOLEAN DEFAULT TRUE,                  -- 订阅者可以暂停而不删除
    last_pushed_at TIMESTAMPTZ
);

-- 待审批申请
CREATE TABLE pending_requests (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR(64),
    first_name VARCHAR(128),
    requested_at TIMESTAMPTZ DEFAULT NOW()
);

-- 拒绝记录（避免被拒了反复申请）
CREATE TABLE denied_users (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR(64),
    denied_at TIMESTAMPTZ DEFAULT NOW(),
    reason TEXT
);

-- 推送历史
CREATE TABLE push_history (
    id SERIAL PRIMARY KEY,
    digest_id INTEGER REFERENCES daily_digests(id),
    user_id BIGINT REFERENCES subscribers(user_id),
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT
);

-- AI 调用日志（成本追踪）
CREATE TABLE ai_call_log (
    id SERIAL PRIMARY KEY,
    purpose VARCHAR(64),                          -- 'per_tweet_summary' / 'overall_takeaway' / ...
    model VARCHAR(64),
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd NUMERIC(10, 6),
    duration_ms INTEGER,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

所有迁移用 Alembic 管理。不要手写 SQL 建表。

---

## 6. 关键工程要求

### 6.1 权限分级

三个等级：
- **Admin**：`ADMIN_USER_ID`（写在 `.env`），独占所有 `/admin` 类命令
- **Subscriber**：在 `subscribers` 表里且 `enabled = TRUE` 的用户，能收每日推送
- **Guest**：其他任何 Telegram 用户，**只能用 `/start` `/subscribe` `/status`**，发其他消息忽略或回 "Not authorized"

中间件（`bot/middleware.py`）在 handler 触发前做权限检查，未授权直接拦截。

### 6.2 时区

- 服务器时区可能 UTC，所有定时任务用 `Pacific/Auckland` 显式指定
- "当日"定义：NZ 时间 00:00 - 20:00 这 20 小时（按推文 `posted_at` 转 NZ 时区过滤）
- 数据库时间统一 `TIMESTAMPTZ`

### 6.3 错误处理

- 所有 AI 调用：指数退避重试 3 次
- 爬虫失败：单次任务失败记日志，下次定时再试
- 推送失败：单个用户失败不影响其他用户（继续循环）
- Bot 收到 unknown command：友好回复 "Unknown command, send /start for help"
- 关键错误（爬虫连续 N 次失败、推送任务整体失败）：通过 bot 把告警消息发给管理员

### 6.4 日志

- Python 标准 `logging`，JSON 格式（生产部署便于 CloudWatch / ELK 处理）
- 关键操作必须有日志：爬虫每次抓取（数量 + 时长）、AI 调用、推送结果、订阅状态变化
- **不要 print**
- 所有 logging handler 显式 `encoding="utf-8"`（见 6.8）

### 6.5 Token / 成本追踪

- 每次 OpenAI 调用记录 `model` / `input_tokens` / `output_tokens` / `cost_usd` 到 `ai_call_log`
- cost_usd 在记录时按当前模型价格表算好（不在查询时算，避免历史价格变了对不上）
- 提供 admin 命令 `/cost [days]` 查看近 N 天 AI 总开销

### 6.6 X 爬虫策略

**关键风险**：X 对爬虫极不友好，2024 年起匿名访问基本不可用，必须登录才能拿数据。**2026 年起 X 加了 JS bundle obfuscation + `x-client-transaction-id` header 强制要求**，主流开源 Python 爬虫库（twscrape、snscrape 等）基本全废。

#### 选定方案：Playwright + cookies 注入 + 拦截 GraphQL

**原理**：
1. 起一个 headless Chromium，注入预先在浏览器获取的 X session cookies（`auth_token` + `ct0`）
2. 用真实 Chrome UA 访问目标博主主页 `https://x.com/<screen_name>`
3. **X 自家的前端 JS 会自动调 GraphQL 加载推文**（因为是真浏览器，X 的反爬通过 — fingerprint 真、cookies 真、JS 真在跑）
4. 我们用 Playwright 的 `page.on("response", ...)` 拦截响应，专门收集 `UserTweets` 端点的 JSON
5. 从 JSON 里挖出 `data.user.result.timeline.timeline.instructions[*].entries[*]` 里的推文数据

**为什么这条路比 twscrape 稳**：
- 不依赖任何 Python 库去反解 X 的反爬 → X 改 JS bundle 跟我们无关
- fingerprint 是真 Chrome，被风控概率低
- JSON 响应结构相对稳定（X 自家前端也要消费）
- 缺点：Chromium 镜像 ~290MB；每次抓取启动浏览器 ~10 秒；CPU/RAM 占用比纯 HTTP 高

**Windows 开发环境用 `channel="chrome"` 而不是 Playwright 自带 Chromium**：
- 国产杀毒（火绒等）会把 Playwright 下载的 Chromium 当可疑文件删掉
- Playwright 支持指定 `channel="chrome"` 让它用系统已装的 Google Chrome
- 用系统 Chrome 火绒不会动（已被白名单），开发体验顺
- 部署到 EC2 Linux 不用这个 channel，正常用 Playwright 下的 Chromium 即可

#### 爬虫账号
- 用一个**已经"养"过几个月的老号**（新号会被秒封，spike 阶段已验证）
- **不要用日常账号**（被风控时连日常用号一起完蛋）
- 账号 cookies 存 `.env`：
  ```
  X_SCRAPER_USERNAME=...           # 仅做记录
  X_SCRAPER_COOKIES=auth_token=xxx; ct0=yyy
  ```
- cookies 过期检测：抓取连续 N 次返回空 / 重定向到 `/login` → 告警，需要人工到浏览器重新登录并更新 cookies

#### 抓取频率
- 默认：**每小时抓一次**（00:05、01:05 ... 19:05）。最后一次抓取 19:05 完成后，19:30 跑 AI 摘要，20:00 推送
- 不要在整点（00:00）抓 —— 跟其他爬虫日常请求高峰错开
- 每次抓首页一次加载量（约 17-25 条），按 tweet id 去重；如需更多用 `page.evaluate("window.scrollBy(...)")` 触发翻页
- 浏览器实例**复用**：worker 进程启动时建一个 browser context，多次抓取共用，不要每次启停（启停浪费 10s）

#### IP 风险
- 先在 **AWS EC2 悉尼区** 试。AWS IP 段被 X 限流的可能性中等
- 监控指标：连续 24 小时内若爬取失败率 > 30%（含拿到空响应、重定向、TLS 错误），告警准备降级
- **降级方案**：把 worker 进程单独搬到开发者家里那台废笔记本（新西兰住宅 IP），跑同样的 worker，数据库放云上 RDS 或笔记本直连 EC2 Postgres
- 长期方案：如果 EC2 也活、笔记本也活，**笔记本主 / EC2 备**（家里偶尔停电就 EC2 顶上）

#### 媒体下载
- 推文带图/视频时，从 `legacy.entities.media[]` 拿 `media_url_https`（图）或 `video_info.variants[-1].url`（视频高码率版）
- 用 `httpx` 下载到本地临时文件（不入库，太大）
- 立刻上传给 Telegram，Telegram 拿到后会返回一个 `file_id`，下次重发同一个文件用 `file_id` 不用重新上传
- 推送完毕删除本地临时文件
- 视频超 Telegram bot 50MB 限制时，只发缩略图 + 链接

### 6.7 Webhook vs Polling

- 本地开发：Polling
- 生产部署：Webhook（HTTPS + Nginx 反代 + Let's Encrypt）
- 代码层面通过环境变量切换：`BOT_MODE=polling|webhook`

### 6.8 全链路 UTF-8（强制，无例外）

**核心原则**：项目里任何涉及"字节 ↔ 字符串"转换的地方，**全部显式 UTF-8**。不依赖任何"系统默认编码"。看到字符串和字节流交界处必须问自己"这里编码是什么"，答案永远是 UTF-8。

**为什么这么严**：开发机 Windows 默认 GBK/cp936，生产 Linux 默认 UTF-8。不显式指定会出现"本地跑得好好的、上线就乱码"这种最难查的 bug。

**适用范围 —— 所有读写操作，无例外**：

#### 文件 I/O

- **所有源代码、配置、文档、数据文件保存为 UTF-8（无 BOM）**：`.py` / `.toml` / `.md` / `.env` / `.sql` / `.json` / `.yaml` / `.csv` / `.txt` 全部。IDE 默认编码强制设 UTF-8。
- **任何 `open()` 必须显式传 `encoding="utf-8"`**，包括读、写、追加。禁止裸 `open(path)`。
  ```python
  # ❌ 错
  with open("data.txt") as f: ...
  open("out.txt", "w").write(s)
  # ✅ 对
  with open("data.txt", encoding="utf-8") as f: ...
  open("out.txt", "w", encoding="utf-8").write(s)
  ```
- `pathlib.Path` 的 `read_text` / `write_text` 同样强制：
  ```python
  Path("x.txt").read_text(encoding="utf-8")
  Path("x.txt").write_text(s, encoding="utf-8")
  ```

#### 日志

- 控制台 handler 在 Windows 上要确保 stream 是 UTF-8（设 `PYTHONIOENCODING=utf-8` 或 `PYTHONUTF8=1`）。
- 文件 handler 显式：`logging.FileHandler("app.log", encoding="utf-8")`。
- 第三方 logging 框架（`structlog` 等）同样要确认底层 handler UTF-8。

#### 数据库

- PostgreSQL：建库 `ENCODING 'UTF8'`、`LC_COLLATE='C.UTF-8'`，连接字符串加 `client_encoding=utf8`。
- 所有 schema 的 `VARCHAR` / `TEXT` 字段都默认存 UTF-8 不需要额外字段，但要确认 server 端 encoding 是 UTF8。

#### 网络 I/O

- `httpx` / `requests` 拿到响应：显式 `.content.decode("utf-8")`，不要依赖响应头 charset 推断（很多 API 不带或带错）。
- 发请求 body 是 dict 用 json：库会自动 UTF-8，OK。手动构造 bytes 时显式 `.encode("utf-8")`。
- 第三方 SDK（telegram、openai、twscrape 等）内部 UTF-8 由库保证，但**我们传给它的字符串必须确认是 UTF-8 字符串**（Python 3 的 `str` 内部本来就是 Unicode，从文件/网络读进来时按 UTF-8 解码即可）。

#### 进程间通信

- `subprocess.run` / `Popen`：必须传 `encoding="utf-8"`，否则 Windows 上按 GBK 解码子进程输出会乱码。
  ```python
  subprocess.run([...], capture_output=True, text=True, encoding="utf-8")
  ```
- 管道、socket 同理。

#### 进程级兜底

- 容器入口、systemd unit、PowerShell 启动脚本统一设：
  ```
  PYTHONUTF8=1
  PYTHONIOENCODING=utf-8
  LANG=C.UTF-8
  LC_ALL=C.UTF-8
  ```
- Dockerfile 必须有 `ENV PYTHONUTF8=1 PYTHONIOENCODING=utf-8 LANG=C.UTF-8`。

#### 模板 / Prompt / 提示词

- 任何提示词模板文件（`prompts/*.txt` 或 `*.md`）保存 UTF-8，读取时显式 `encoding="utf-8"`。
- jinja2 / 字符串模板渲染产物用前确认是 `str`（已经是 Unicode），落盘或发送时再 `.encode("utf-8")`。

#### 例外处理

**这条规则没有例外**。如果某个第三方库不支持显式编码、必须依赖系统默认，在代码处用 `# noqa: utf8` 注释并在 commit message 里单独说明原因。Code review 时此处会被反复盯。

### 6.9 隐私 / 安全

- `subscribers` / `pending_requests` 表里存的是 Telegram user_id + username + first_name，属个人数据
- 用户 `/unsubscribe` 时硬删除（不留 soft-delete 历史）
- 不存任何聊天内容，只存订阅状态
- `.env` 里的 X 账号密码、OpenAI key、Telegram bot token 永远不入库不入 log
- `ai_call_log` 不存推文原文（避免重复存储 + 隐私），只存 token 数

### 6.10 Telegram 速率限制

- Telegram bot API：约**每秒 30 条**到不同 chat 的消息（同一 chat 内更紧）
- 推送时遍历订阅者循环发送，**每条之间 sleep 50ms**（保守，应对几百订阅者绰绰有余）
- 单个用户连续失败 3 次（被 block 等）：标记 `enabled = FALSE`，下次不再推

---

## 7. 开发路线（按阶段交付）

> **当前所在阶段**：Stage 0 热身已完成（uv + Python 3.12 + 最简 echo bot 跑通）。下面是正式 4 个阶段。**Stage 1 故意是 X 爬虫验证而不是项目骨架**，因为爬虫是最大不确定性，先证明能拿到数据再投入其他工作。

### Stage 1：X 爬虫 spike（验证可行性，第一优先）✅ 本地通过

**目标**：能稳定抓到 @whyyoutouzhele 当天的所有推文

- [x] 准备爬虫账号（用养过的老号 + 浏览器手动登录 + 导出 cookies）
- [x] ~~`uv add twscrape`~~ —— **twscrape 0.17.0 被 X 反爬干掉**，issue #305，PR #303 未真正修复
- [x] `uv add playwright` + `playwright install chromium`
- [x] 写 `spike/x_scrape.py`：headless Chromium + cookies + 拦截 GraphQL
- [x] 本地 Windows 跑通，一次抓 17 条今日推文，所有字段（含 views）正确
- [ ] ⏸️ 推到 EC2 悉尼跑通（验证 IP 是否被 X 风控）—— 延后到 Stage 5 部署阶段一起做
- [ ] ⏸️ 跑 24 小时观察成功率 —— 同上延后

**spike 结论**：技术路线可行（Playwright 路线）。EC2 IP 风险等部署阶段实测。

### Stage 2：项目骨架 + 数据持久化
**目标**：可运行的项目结构，爬虫抓的推文能稳定落库

- [ ] 按第 4 节项目结构重组代码（拆出 src/ 各模块）
- [ ] `pydantic-settings` 配置管理替代直接读 os.environ
- [ ] docker-compose 起 PostgreSQL 16
- [ ] SQLAlchemy 2.0 async 模型定义
- [ ] Alembic 初始化 + 第一个迁移建所有表
- [ ] `services/twitter.py` 把 spike 脚本封装成 service，写入 `tweets` 表
- [ ] APScheduler 每小时跑一次抓取
- [ ] 现有 echo bot 重构为正式 handler，加权限中间件

**交付物**：跑一晚上，数据库 `tweets` 表里有当日所有推文。

### Stage 3：AI 摘要管线 + 媒体处理
**目标**：能生成完整的"今日头条 + 今日要闻"内容包

- [ ] `uv add openai`
- [ ] `ai/client.py` 封装 OpenAI 调用，含重试、超时、token 统计 → 写入 `ai_call_log`
- [ ] `ai/prompts.py` 写 per-tweet 摘要 + overall_takeaway 两个 prompt
- [ ] `services/summary.py` 实现摘要业务逻辑
- [ ] `services/media.py` 下载推文图片 / 视频到本地临时目录
- [ ] `services/digest.py` 编排：取当日推文 → 选头条 → AI 摘要其余 → 组装内容包 → 落 `daily_digests`
- [ ] 临时命令 `/test_digest` 让管理员手动触发，回复完整内容到管理员对话

**交付物**：管理员发 `/test_digest`，收到格式完美的头条 + 要闻内容包。

### Stage 4：订阅管理 + 管理员审批流
**目标**：完整的订阅生命周期

- [ ] `services/subscription.py` 实现状态机（申请→批准/拒绝→订阅/撤销）
- [ ] `bot/handlers/user.py` 实现 `/subscribe` `/unsubscribe` `/status`
- [ ] `bot/handlers/admin.py` 实现 `/pending` `/approve` `/deny` `/revoke` `/subscribers`
- [ ] 申请到达时 bot 自动通知管理员
- [ ] 审批结果自动通知申请人

**交付物**：从一个陌生 Telegram 账号 `/subscribe`，管理员收到通知，`/approve`，对方收到"已批准"。

### Stage 5：每日推送 + 调度 + 部署
**目标**：项目完整，挂着自己跑

- [ ] `services/push.py` 实现广播：遍历 subscribers，按速率限制发头条 + 要闻
- [ ] `scheduler/jobs.py` 加上 NZ 20:00 推送任务
- [ ] `/test_push` 命令仅推给管理员，验证全流程
- [ ] `/broadcast` 临时公告命令
- [ ] 失败重试 + 错误兜底完善
- [ ] Dockerfile + docker-compose 生产配置
- [ ] EC2 部署文档（systemd 起 bot + worker 两个进程）
- [ ] Webhook 模式 + Nginx + Let's Encrypt 配置示例
- [ ] README 最终完善（架构图、技术决策说明、部署步骤、成本估算、风险）

**交付物**：EC2 上挂着跑，每天 NZ 20:00 收到推送。

---

## 8. .env 需要的配置

```
# Telegram
TELEGRAM_BOT_TOKEN=
ADMIN_USER_ID=

# OpenAI
OPENAI_API_KEY=

# X 爬虫账号（养过的老号，cookies 路线）
X_SCRAPER_USERNAME=                     # 只做记录，不参与登录
X_SCRAPER_COOKIES=auth_token=xxx; ct0=yyy   # 浏览器登录后从 DevTools 复制
# 下面三个是备用（cookies 失效时用浏览器重登）
X_SCRAPER_PASSWORD=
X_SCRAPER_EMAIL=
X_SCRAPER_EMAIL_PASSWORD=

# 跟踪的 X 博主（未来扩展多个用配置文件，目前一个写死）
TRACKED_X_AUTHOR=李老师不是你老师

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/x_digest

# App
BOT_MODE=polling                # polling | webhook
WEBHOOK_URL=
WEBHOOK_PORT=8443
TIMEZONE=Pacific/Auckland
PUSH_TIME=20:00
LOG_LEVEL=INFO

# Models
MODEL_PER_TWEET=gpt-4o-mini
MODEL_OVERALL=gpt-4o
MODEL_FEATURED_ANALYSIS=gpt-4o   # 可选，深度解读头条用

# 编码统一（见 6.8）
PYTHONUTF8=1
PYTHONIOENCODING=utf-8
```

---

## 9. README 必须包含的内容

这个项目要给面试官看，README 不能糊弄。必须有：

1. **项目简介**（一句话说清楚做什么）
2. **架构图**（mermaid 画的那种，展示 bot / worker / scraper / db / OpenAI / Telegram 之间的关系）
3. **技术选型理由**（为什么 Postgres、为什么 PTB v21、为什么 twscrape、为什么 OpenAI 不用国内模型、为什么 bot/worker 分进程）
4. **本地开发步骤**（clone → uv → 配 .env → docker-compose up Postgres → migration → 跑 bot & worker）
5. **部署步骤**（AWS EC2 悉尼 + Docker + Nginx + HTTPS + systemd）
6. **成本估算**（每月 OpenAI / EC2 / 住宅代理 大概多少美元）
7. **风险与降级方案**（X 反爬、IP 被封、爬虫账号被封时怎么办）
8. **隐私声明**（订阅者数据怎么处理）
9. **未来计划 / 已知限制**

---

## 10. 给 Claude Code 的注意事项

1. **先读完整份文档再动手**。不要读到第 3 节就开始写代码。
2. **遇到歧义先问**。比如某个 prompt 怎么写、某个抓取策略不确定，先问开发者再动手。
3. **不要扩展功能**。文档没说的功能就是不做。不要加翻译命令、不要加 web 后台、不要加多博主支持。
4. **按阶段交付**。完成一个 Stage 让开发者验证，再进下一个。每个阶段完成时给出"如何验证"的具体步骤。
5. **代码风格**：
   - 用 type hints（开发者 Java 背景，喜欢类型）
   - 关键函数有 docstring
   - 复杂逻辑写注释（关键决策处写）
   - 不要过度抽象（YAGNI），但分层要清晰
6. **Git commit 风格**：conventional commits（feat: / fix: / chore: / docs:）
7. **测试**：核心 service 写单元测试。AI / 爬虫 / Telegram 调用用 mock。不追求 100% 覆盖率，关键路径覆盖即可。
8. **不要用过时模式**：
   - 不用 `requirements.txt`，用 `pyproject.toml`
   - 不用同步 SQLAlchemy 1.x，用 2.0 async
   - 不用 `print`，用 `logging`
   - 不用 `os.getenv` 散落各处，配置走 pydantic-settings
9. **爬虫永远是脆弱环节**。任何爬虫代码必须有 try/except、有重试、有失败告警，不能让 worker 进程因为爬虫挂了整个崩。
10. **AI 调用永远走 `ai/client.py` 封装**，不要在 service 里裸调 `openai.chat.completions.create`。这样换模型、加日志、做缓存都只改一处。

---

## 11. 当前状态

**已完成**（Stage 0 热身）：
- Python 3.12.13（uv 管理，避开 3.14 的 PTB 兼容问题）
- uv + pyproject.toml + .venv 项目骨架
- python-telegram-bot 21.11.1 + python-dotenv 已装
- 最简 echo bot 跑通（用 polling 模式）
- `.env` 机制（PYTHONUTF8、TELEGRAM_BOT_TOKEN）
- `.gitignore` 含 `.idea/`、`.venv/`、`.env`
- 首个 commit 已提交

**开发者已准备好 / 待准备**：
- ✅ Telegram Bot Token
- ✅ Telegram User ID（自己当 admin）
- ⬜ OpenAI API Key（开发者承诺去充值，进 Stage 3 前准备）
- ⬜ X 爬虫小号（进 Stage 1 前注册，**不要用日常 X 账号**）
- ✅ AWS EC2 悉尼区服务器
- ⬜ 备用：家里那台废笔记本，新西兰住宅 IP，万一 EC2 被 X 风控用

**下一步**：进入 Stage 1，做 X 爬虫 spike，验证可行性。

---

完。
