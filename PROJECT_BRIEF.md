# English Buddy Bot — Project Brief

> 这份文档是给 Claude Code 看的，包含完整的项目背景、需求、技术决策和开发路线。请在动手前完整读一遍，遇到歧义先问，不要自己脑补。

---

## 1. 项目背景

**用户**：单人使用，开发者本人。新西兰奥克兰，Java/Spring Boot 全栈背景，Python 是为这个项目临时学的，所以代码风格要清晰、注释适度、便于学习理解。

**目标**：
1. 做一个**自己每天会用**的 Telegram bot，帮助持续学习英语
2. 作为 GitHub 上的求职作品集项目，能在面试中讲清楚架构决策
3. 部署在自有的 AWS EC2 服务器上

**不是什么**：
- 不是给多人用的 SaaS
- 不是聊天机器人，不要做泛泛的 "AI 助手" 功能
- 不是英语词典 / 翻译工具的替代品

---

## 2. 功能需求

### 2.1 推送功能

**自动推送**
- 时间：每周一、三、五、日 **早上 8:00（新西兰时间，Pacific/Auckland）**
- 内容：1 条英语俚语 + 1 期 BBC 6 Minute English 的最新内容
- 推过的内容要记录，避免重复

**手动推送**
- 命令：`/today`
- 用户在非推送日（周二、四、六）或任何时候触发，返回当天该有的内容

**推送内容格式**

俚语部分：
```
📚 今日俚语

**[俚语词条]**

含义：[中文解释]

例句：
1. [English example]
   [中文翻译]
2. [English example]
   [中文翻译]
3. [English example]
   [中文翻译]
```

BBC 部分：
```
🎧 BBC 6 Minute English

**[Episode Title]**
🔗 [原始链接]

📝 中文要点：
[AI 基于 transcript 生成的 3-5 个要点]

📖 重点词汇：
- word1: 释义 + 用法
- word2: 释义 + 用法
- ...
```

### 2.2 对话功能

**命令 1：`/improve <英文文本>`**
功能：改进英文表达
返回：
- 改进版本
- 修改原因（逐条说明改了什么、为什么改）

**命令 2：`/express <中文意图>`**
功能：把中文意图转成地道英文
返回：
- 地道英文表达（书面 / 口语都要覆盖，AI 根据上下文判断给哪种或都给）
- 用法说明（什么场景用、为什么这么说）
- 1-2 个相关替换说法

### 2.3 不做的功能（明确砍掉）

- 翻译功能（Claude 网页/DeepL 已经够好）
- 单词查询（同上）
- 语音对话 / Voice mode
- 多用户支持
- Web 管理后台

---

## 3. 技术栈（已决定，不要改）

| 模块 | 选型 |
|------|------|
| 语言 | Python 3.11+ |
| 包管理 | `uv` |
| Telegram 库 | `python-telegram-bot` v21+ |
| AI SDK | `openai` Python SDK（指向 DashScope OpenAI 兼容端点，调千问） |
| ORM | SQLAlchemy 2.0 (async 模式) |
| 数据库迁移 | Alembic |
| 数据库 | PostgreSQL 16 |
| 定时任务 | APScheduler |
| HTTP 客户端 | `httpx` |
| 配置管理 | `pydantic-settings` |
| 容器化 | Docker + docker-compose |
| 部署 | AWS EC2 |

**关于 AI 模型的选择策略**（千问系列，通过 DashScope 调用）：

| 任务 | 模型 | 理由 |
|------|------|------|
| 生成俚语 | `qwen-turbo` | 简单生成，最便宜（有免费额度） |
| BBC 内容讲解 | `qwen-plus` | 需要理解 transcript |
| 改英文 (`/improve`) | `qwen-plus` | 质量是核心价值 |
| 地道表达 (`/express`) | `qwen-plus` | 同上 |

**这个选择是面试讲点**：不同任务用不同模型，平衡质量和成本。代码里要有清晰的封装让这件事可见。

**为什么用 OpenAI SDK 调千问**：DashScope 提供了 OpenAI 兼容的 endpoint（`https://dashscope.aliyuncs.com/compatible-mode/v1`），可以直接用 `openai` Python 库，把 `base_url` 指过去就行。这样未来想换 OpenAI / DeepSeek / Moonshot 等任何 OpenAI 兼容的 provider，只改两行配置。

---

## 4. 项目结构

```
english-buddy-bot/
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── docker-compose.yml      # 本地起 Postgres
├── Dockerfile              # 部署用
│
├── src/
│   ├── __init__.py
│   ├── main.py             # 入口
│   ├── config.py           # pydantic-settings 配置
│   │
│   ├── bot/
│   │   ├── __init__.py
│   │   ├── app.py          # Telegram Application 初始化
│   │   ├── handlers.py     # 命令处理函数
│   │   └── middleware.py   # 权限检查（限定单一用户）
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── idiom.py
│   │   ├── bbc.py
│   │   ├── writing.py      # /improve
│   │   ├── expression.py   # /express
│   │   └── push.py         # 推送编排
│   │
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── client.py       # Anthropic 客户端封装
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
│   │   └── jobs.py
│   │
│   └── utils/
│       ├── __init__.py
│       └── logger.py
│
└── tests/
```

**架构原则**：
1. **services 层不依赖 bot 层** —— services 只懂业务，不懂 Telegram。换成 Discord 或 CLI，services 不用动。
2. **prompts 集中** —— 所有 prompt 模板放在 `ai/prompts.py`，便于版本化、迭代、对比。
3. **配置走环境变量** —— 任何 secret、可变参数全部从 `.env` 读，代码里不出现 magic string。
4. **handler 薄，service 厚** —— Telegram handler 只做解析参数、调 service、格式化回复。业务逻辑都在 service。

---

## 5. 数据库 Schema

```sql
-- 推送历史
CREATE TABLE push_history (
    id SERIAL PRIMARY KEY,
    push_date DATE NOT NULL,
    content_type VARCHAR(20) NOT NULL,  -- 'idiom' / 'bbc'
    content_id VARCHAR(255),             -- 俚语词条 / BBC episode url
    content_summary TEXT,
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT
);

-- 俚语历史（避免短期内重复推送）
CREATE TABLE idiom_history (
    id SERIAL PRIMARY KEY,
    idiom VARCHAR(255) UNIQUE NOT NULL,
    meaning TEXT,
    examples JSONB,
    generated_at TIMESTAMPTZ DEFAULT NOW()
);

-- BBC 内容缓存
CREATE TABLE bbc_episodes (
    id SERIAL PRIMARY KEY,
    episode_url VARCHAR(500) UNIQUE NOT NULL,
    title VARCHAR(500),
    publish_date DATE,
    transcript TEXT,
    ai_summary TEXT,
    ai_vocabulary JSONB,
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    pushed BOOLEAN DEFAULT FALSE,
    pushed_at TIMESTAMPTZ
);

-- 用户设置（虽然只有一个用户，但保留扩展性）
CREATE TABLE user_settings (
    user_id BIGINT PRIMARY KEY,           -- Telegram user id
    push_time TIME DEFAULT '08:00',
    timezone VARCHAR(50) DEFAULT 'Pacific/Auckland',
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 对话日志（用于后续分析 token 用量）
CREATE TABLE conversation_log (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    command VARCHAR(50),                  -- 'improve' / 'express'
    user_input TEXT,
    bot_response TEXT,
    model_used VARCHAR(100),
    input_tokens INTEGER,
    output_tokens INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

所有迁移用 Alembic 管理。不要手写 SQL 建表。

---

## 6. 关键工程要求

### 6.1 权限控制
Bot 必须只响应一个 Telegram User ID（写在 `.env` 里）。其他人发消息直接忽略或回 "Not authorized"。

### 6.2 时区
- 服务器时区可能是 UTC，所有定时任务用 `Pacific/Auckland`。
- APScheduler 调度时显式指定时区。
- 数据库时间用 `TIMESTAMPTZ`（带时区）。

### 6.3 错误处理
- 所有 AI 调用要有重试逻辑（指数退避，最多 3 次）
- BBC 抓取失败不能阻塞俚语推送（独立失败）
- 任何失败都要写日志 + 写入 `push_history.error_message`
- Bot 收到 unknown command 要友好回复，不能崩

### 6.4 日志
- 用 Python 标准 logging，配置成 JSON 格式（部署到 EC2 后方便用 CloudWatch 或 ELK 处理）
- 关键操作（推送、AI 调用、错误）必须有日志
- 不要 print

### 6.5 Token 用量追踪
- 每次 AI 调用记录 `input_tokens` / `output_tokens` 到 `conversation_log`
- 写一个简单的 `/stats` 命令（可选 v2 加），返回本月 token 用量和估算成本

### 6.6 BBC 内容源
**待调研**（在阶段 3 开始时调研）：
- 优先尝试 BBC Learning English 的 RSS / podcast feed
- 如果没有，解析 https://www.bbc.co.uk/learningenglish/english/features/6-minute-english 页面
- **重要**：不要把完整 transcript 推给用户（版权问题）。只推链接 + AI 生成的摘要 + 重点词汇。

### 6.7 Webhook vs Polling
- 本地开发：Polling
- 生产部署：Webhook（HTTPS + Nginx 反代 + Let's Encrypt）
- 代码层面通过环境变量切换：`BOT_MODE=polling|webhook`

### 6.8 编码统一 UTF-8（强制，无例外）

开发机是 Windows，PowerShell 控制台和 Python 在 Windows 上的默认编码是系统区域编码（中文 Windows 通常是 GBK / cp936），不显式指定会出现"本地能跑、Linux 服务器乱码"或"读 .env 中文注释报错"等坑。**全链路强制 UTF-8**：

1. **所有源文件保存为 UTF-8（无 BOM）**。`.py` / `.toml` / `.md` / `.env` / `.sql` 全部 UTF-8。IDE 和编辑器默认编码必须设成 UTF-8。
2. **任何 `open()` 必须显式传 `encoding="utf-8"`**。绝对禁止 `open(path)` 不带 encoding 参数 —— 在 Windows 上等于按 GBK 打开。
   ```python
   # ❌ 错
   with open("data.txt") as f: ...
   # ✅ 对
   with open("data.txt", encoding="utf-8") as f: ...
   ```
3. **`logging` 文件 handler 必须显式 `encoding="utf-8"`**：
   ```python
   logging.FileHandler("app.log", encoding="utf-8")
   ```
4. **数据库连接强制 UTF-8**。PostgreSQL DSN 加 `client_encoding=utf8`，建库时用 `ENCODING 'UTF8'`。
5. **启动入口设置 `PYTHONUTF8=1`**（Python 3.7+ UTF-8 mode），让所有 I/O 默认 UTF-8。Docker 镜像里写到 `ENV`，本地开发写到 `.env` 或启动脚本。
6. **HTTP 客户端响应处理显式 decode**。`httpx` 拿到 bytes 后 `.decode("utf-8")`，不依赖响应头里的 charset 推断。
7. **subprocess / 外部命令调用** 加 `encoding="utf-8"`：
   ```python
   subprocess.run([...], capture_output=True, text=True, encoding="utf-8")
   ```

**这条规则没有例外**。如果某个第三方库不支持显式编码、必须依赖系统默认，在 PR 描述里单独标注并讨论。

---

## 7. 开发路线（按阶段交付）

### 阶段 1：基础骨架（必须最先完成）
**目标**：bot 能收能发，部署能跑

- [ ] `uv init` 初始化项目，配置 pyproject.toml
- [ ] 完整目录结构搭建（src/ 下所有 `__init__.py`）
- [ ] `config.py` 用 pydantic-settings 加载 .env
- [ ] `.env.example` 列出所有需要的配置
- [ ] docker-compose.yml 起一个 Postgres 16
- [ ] SQLAlchemy + Alembic 初始化，写第一个迁移
- [ ] 实现 `/ping` 命令，回复 "pong"
- [ ] 权限中间件（只响应配置的 user id）
- [ ] 基础日志配置
- [ ] README 写起来（架构图、本地运行步骤）

**交付物**：本地 `uv run python -m src.main` 能跑，给 bot 发 /ping 收到 pong。

### 阶段 2：对话功能（先做，因为最简单也最实用）
**目标**：`/improve` 和 `/express` 能用

- [ ] `ai/client.py` 封装 Anthropic 调用，支持模型切换、重试、token 统计
- [ ] `ai/prompts.py` 写 improve 和 express 的 prompt 模板
- [ ] `services/writing.py` 实现 improve 业务逻辑
- [ ] `services/expression.py` 实现 express 业务逻辑
- [ ] handler 接入，把命令路由到 service
- [ ] 写入 conversation_log
- [ ] 测试：发 `/improve I want apply your company` 看输出

**交付物**：两个对话命令可用，输出格式良好，token 用量有记录。

### 阶段 3：BBC 推送
**目标**：能抓 BBC 内容并生成讲解

- [ ] 调研 BBC 内容源（RSS / Page / Podcast feed），写一个 spike 脚本验证
- [ ] `services/bbc.py` 实现：检查最新一期、抓取 transcript、调 AI 生成摘要和词汇
- [ ] 存到 `bbc_episodes` 表
- [ ] 写格式化函数，组织成推送消息
- [ ] 临时用一个测试命令 `/test_bbc` 触发，验证完整流程

**交付物**：手动触发能拿到一期 BBC 的完整推送内容。

### 阶段 4：俚语 + 定时调度 + 收尾
**目标**：自动推送跑起来，项目完整

- [ ] `services/idiom.py` 生成俚语，去重（检查 idiom_history）
- [ ] `services/push.py` 编排：俚语 + BBC 一起组装发送
- [ ] `scheduler/jobs.py` APScheduler 配置周一三五日 8:00 任务
- [ ] `/today` 命令实现手动触发
- [ ] 错误处理 + 重试完善
- [ ] Dockerfile 写好
- [ ] 部署文档（EC2 上怎么跑）
- [ ] Webhook 模式实现 + Nginx 配置示例
- [ ] README 最终完善（含架构图、技术决策说明、部署步骤、成本估算）

**交付物**：完整项目，部署到 AWS 上跑起来，每周一三五日 8 点收到推送。

---

## 8. .env 需要的配置

```
# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_USER_ID=

# DashScope (千问)
DASHSCOPE_API_KEY=
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/english_buddy

# App
BOT_MODE=polling                # polling | webhook
WEBHOOK_URL=                    # 仅 webhook 模式需要
WEBHOOK_PORT=8443
TIMEZONE=Pacific/Auckland
PUSH_TIME=08:00
LOG_LEVEL=INFO

# Models
MODEL_IDIOM=qwen-turbo
MODEL_BBC=qwen-plus
MODEL_WRITING=qwen-plus
MODEL_EXPRESSION=qwen-plus
```

---

## 9. README 必须包含的内容

这个项目要给面试官看，README 不能糊弄。必须有：

1. **项目简介**（一句话说清楚做什么）
2. **架构图**（mermaid 画的那种，展示各组件关系）
3. **技术选型理由**（为什么 Postgres / 为什么 APScheduler / 为什么不同任务用不同模型）
4. **本地开发步骤**（clone → 装 uv → 配 .env → docker-compose up → migration → run）
5. **部署步骤**（AWS EC2 + Docker + Nginx + HTTPS）
6. **成本估算**（每月大概多少美元 token）
7. **未来计划 / 已知限制**

---

## 10. 给 Claude Code 的注意事项

1. **先读完整份文档再动手**。不要读到第 3 节就开始写代码。
2. **遇到歧义先问**。比如某个 prompt 怎么写、某个抓取策略不确定，先问开发者再动手。
3. **不要扩展功能**。文档没说的功能就是不做。比如不要自己加"翻译"命令，不要自己加 web 后台。
4. **按阶段交付**。完成阶段 1 让开发者验证，再进阶段 2。每个阶段完成时给出"如何验证"的具体步骤。
5. **代码风格**：
   - 用 type hints（开发者是 Java 背景，喜欢类型）
   - 关键函数有 docstring
   - 复杂逻辑写注释（不是每行都写，是关键决策处写）
   - 不要过度抽象（YAGNI），但分层要清晰
6. **Git commit 风格**：用 conventional commits（feat: / fix: / chore: / docs:）
7. **测试**：核心 service 写单元测试。AI 调用用 mock。不要追求 100% 覆盖率，关键路径覆盖即可。
8. **不要用过时模式**：
   - 不用 `requirements.txt`，用 `pyproject.toml`
   - 不用同步 SQLAlchemy 1.x，用 2.0 async 模式
   - 不用 `print`，用 `logging`
   - 不用 `os.getenv` 散落各处，配置统一过 pydantic-settings

---

## 11. 当前状态

**开发者已准备好**：
- Telegram Bot Token（会在本地 .env 配置）
- Anthropic API Key（同上）
- Telegram User ID（同上）
- AWS EC2 服务器（具体情况待开发者补充）

**第一步**：从阶段 1 开始，初始化项目骨架。

---

完。
