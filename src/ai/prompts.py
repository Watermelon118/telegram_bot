"""Prompt 模板集中管理。

为什么单独一个文件：
- 提示词是项目的"配方"，需要版本化迭代和 A-B 测试
- 散落在 service 里改起来很难追踪效果
- 想换 prompt 风格只改这一个文件

约定：
- 所有 prompt 是 system + user 两段；system 写"你是谁、规则"，user 写"具体输入"
- 输出格式严格指定（一句话 / JSON / 编号列表等），降低 parse 失败概率
"""

from openai.types.chat import ChatCompletionMessageParam

# ============ per-tweet 摘要（用便宜模型批量跑）============

_PER_TWEET_SYSTEM = """你是一名中文新闻聚合编辑。任务：把一条 X (Twitter) 推文压缩成**一句中文摘要**。

要求：
1. 只输出摘要本身，不加引号、不加前缀（如"摘要："）、不加 emoji
2. 长度严格控制在 **30 字以内**
3. 保留人名、地名、机构、关键数字
4. 客观陈述事实，不加评论、不加猜测
5. 如果推文是纯链接 / 纯转发提示 / 纯 emoji 没有信息，输出：[无实质内容]
"""


def per_tweet_summary(tweet_text: str) -> list[ChatCompletionMessageParam]:
    """返回 chat messages，供 ai.client.complete() 用。"""
    return [
        {"role": "system", "content": _PER_TWEET_SYSTEM},
        {"role": "user", "content": tweet_text},
    ]


# ============ 整体看点（用强模型综合）============

_OVERALL_SYSTEM = """你是一名中文新闻聚合编辑。下面是某博主今日所有推文的一句话摘要列表。

任务：用 **2-3 句中文** 总结"今天这位博主主要在关注什么"。

要求：
1. 不要逐条复述，要归纳话题 / 趋势
2. 不输出列表 / 编号，纯散文
3. 客观陈述，不加评论
4. 总字数控制在 **80-150 字之间**
5. 直接输出正文，不加"今日看点："等前缀
"""


def overall_takeaway(
    per_tweet_summaries: list[str],
) -> list[ChatCompletionMessageParam]:
    """传入 [每条推文的一句话摘要]，要 AI 写 2-3 句整体看点。"""
    joined = "\n".join(f"- {s}" for s in per_tweet_summaries if s)
    return [
        {"role": "system", "content": _OVERALL_SYSTEM},
        {"role": "user", "content": joined},
    ]
