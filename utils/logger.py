"""
utils/logger.py
统一日志配置 - 结构化日志 + 文件轮转 + 彩色控制台输出
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path


def setup_logging(
    level: str = "INFO",
    log_dir: str = "logs",
    app_name: str = "cybersec-compliance",
    retention_days: int = 7,
) -> None:
    """
    初始化全局日志配置。
    - 控制台：彩色输出，INFO 及以上
    - 文件：按天轮转，保留 N 天，记录 DEBUG 及以上
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    normalized_level = getattr(logging, level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(normalized_level)

    # 清除已有 handler，避免重复
    root_logger.handlers.clear()

    # ---- 格式 ----
    verbose_fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    simple_fmt = _ColorFormatter(
        fmt="%(asctime)s %(levelname_colored)s %(name_short)s %(message)s",
        datefmt="%H:%M:%S",
    )

    # ---- 控制台 handler ----
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(normalized_level)
    console.setFormatter(simple_fmt)
    root_logger.addHandler(console)

    # ---- 文件 handler（按天轮转）----
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_path / f"{app_name}.log",
        when="midnight",
        interval=1,
        backupCount=retention_days,
        encoding="utf-8",
        utc=True,
    )
    file_handler.setLevel(normalized_level)
    file_handler.setFormatter(verbose_fmt)
    root_logger.addHandler(file_handler)

    # ---- 错误日志单独文件 ----
    error_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_path / f"{app_name}.error.log",
        when="midnight",
        interval=1,
        backupCount=retention_days,
        encoding="utf-8",
        utc=True,
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(verbose_fmt)
    root_logger.addHandler(error_handler)

    # 抑制三方库过多日志
    for noisy in ["urllib3", "httpx", "httpcore", "asyncio"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.info("📋 日志系统初始化完成 [level=%s, dir=%s]", level, log_dir)


class _ColorFormatter(logging.Formatter):
    """彩色控制台格式化器"""

    _COLORS = {
        "DEBUG":    "\033[36m",   # 青色
        "INFO":     "\033[32m",   # 绿色
        "WARNING":  "\033[33m",   # 黄色
        "ERROR":    "\033[31m",   # 红色
        "CRITICAL": "\033[35m",   # 紫色
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self._COLORS.get(record.levelname, "")
        record.levelname_colored = f"{color}[{record.levelname[0]}]{self._RESET}"
        # 截短 logger 名
        parts = record.name.split(".")
        record.name_short = f"\033[90m{'.'.join(parts[-2:]):<20}\033[0m"
        return super().format(record)
