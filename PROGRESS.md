# 进度跟踪

> 跨对话同步用。每次对话开始先读这个文件知道做到哪。每次结束更新这个文件。

---

## 当前焦点

**Stage 0：热身 —— 把 Telegram bot 接到千问，能收能回**

不做 PROJECT_BRIEF 里的完整阶段 1-4。先用最小代码跑通"消息进来 → 千问回答 → 消息出去"这条链路，让开发者熟悉 Python web/API 开发的手感。Stage 0 完成后，才进入 PROJECT_BRIEF 的 Stage 1（项目骨架、数据库、Alembic 等）。

### 工作模式
- **Claude 教，开发者动手**。不要替开发者写代码，让他自己敲。
- 开发者背景：Java/Spring Boot 全栈 10 年，Python 只用过 pandas/numpy 处理数据，**没用过 Python 写 web/接 API**。
- 解释时多用 Java 类比（pyproject.toml ≈ pom.xml，uv ≈ Maven，virtualenv ≈ 项目级 classpath 隔离）。

---

## Stage 0 拆解

| 步骤 | 状态 | 说明 |
|------|------|------|
| 0.1 装 Python 3.11+ 和 uv | ✅ 完成 | Python 3.14.5；uv 0.11.14 |
| 0.2 用 uv init 初始化项目 | ✅ 完成 | 已生成 pyproject.toml / main.py / .python-version / README.md / .gitignore；`.venv/` 和 `uv.lock` 已建；`uv run main.py` 输出 hello world OK。注意 `requires-python = ">=3.14"` 偏严，进 Stage 1 时改成 `>=3.11` |
| 0.3 装 python-telegram-bot v21 | ⬜ | 理解 async/await、polling |
| 0.4 写一个 echo bot | ⬜ | 收到啥消息就原样回啥，跑通最小链路 |
| 0.5 拿到 DashScope API Key | ⬜ | 阿里云控制台开通 |
| 0.6 装 openai SDK，调一次千问 | ⬜ | 单独写个脚本验证能调通 |
| 0.7 把 echo 替换成"千问回答" | ⬜ | 收到消息 → 转给千问 → 回复给用户 |

图例：⬜ 未开始 / ⏳ 进行中 / ✅ 完成 / ❌ 阻塞

---

## 已做的决策

- **2026-05-15**：把 AI provider 从 Anthropic Claude 换成阿里千问（DashScope），用 `openai` SDK + 兼容端点调用。原因：千问有免费额度，开发者优先想跑起来不付钱。
- **2026-05-15**：先做 Stage 0（学习/热身），再进 PROJECT_BRIEF 的正式 4 个阶段。
- **2026-05-15**：PROJECT_BRIEF 加入 6.8 节"编码统一 UTF-8"，所有文件读写、日志、数据库、subprocess 强制 UTF-8，避免 Windows 开发机和 Linux 服务器之间的编码差异踩坑。

## 待开发者补充

- [ ] Telegram Bot Token（@BotFather 拿）
- [ ] Telegram User ID（@userinfobot 查自己 ID）
- [ ] DashScope API Key

## 阻塞项

无。

---

## 上次对话结尾状态

2026-05-15：
- ✅ Stage 0.1：Python 3.14.5 + uv 0.11.14 装好
- ✅ Stage 0.2：`uv init` 完成，hello world 跑通
- ✅ PROJECT_BRIEF 加入 6.8 UTF-8 强制规定
- 准备进入 Stage 0.3：装 `python-telegram-bot v21`，理解 async/await 和 Telegram polling 模式
