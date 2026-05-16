"""日志配置。当前 Stage 2 用简单 basicConfig；Stage 5 部署时换 JSON 格式。"""

import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """初始化全局 logging。stream 显式用 sys.stdout，避免 Windows stderr 乱码。"""
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=level,
        stream=sys.stdout,
    )
