"""
日志配置模块 — 统一管理日志输出

术语讲解：
- 日志级别：DEBUG(调试细节) < INFO(正常信息) < WARNING(警告) < ERROR(错误) < CRITICAL(致命)
- 日志轮转：日志文件太大了自动切割，避免一个文件几十G
- Handler：日志输出到哪里（控制台、文件、网络等）
- Formatter：日志的格式（时间、级别、消息等）
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 全局日志配置标记
_configured = False


def setup_logging(
    level: str = "INFO",
    log_file: str = "logs/app.log",
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 30,
    fmt: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
) -> None:
    """
    配置全局日志系统

    Args:
        level: 日志级别（DEBUG/INFO/WARNING/ERROR）
        log_file: 日志文件路径（相对于项目根目录）
        max_bytes: 单个日志文件最大字节数
        backup_count: 保留的日志文件数量
        fmt: 日志格式
    """
    global _configured
    if _configured:
        return

    # 转换日志级别字符串为logging常量
    log_level = getattr(logging, level.upper(), logging.INFO)

    # 创建根logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 清除已有的handler（避免重复输出）
    root_logger.handlers.clear()

    # 日志格式
    formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")

    # ===== 控制台输出 =====
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # ===== 文件输出（带轮转）=====
    if log_file:
        # 处理相对路径
        if not os.path.isabs(log_file):
            log_file = os.path.join(PROJECT_ROOT, log_file)

        # 确保日志目录存在
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    _configured = True
    logging.info("日志系统初始化完成")


def get_logger(name: str) -> logging.Logger:
    """
    获取指定名称的logger

    Args:
        name: logger名称，通常传 __name__

    Returns:
        Logger实例
    """
    if not _configured:
        setup_logging()
    return logging.getLogger(name)


def log_exception(logger: logging.Logger, message: str = "发生异常") -> None:
    """
    记录异常（包含完整的Traceback）

    Args:
        logger: logger实例
        message: 附加消息
    """
    logger.exception(message)  # exception()方法会自动包含Traceback
