import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional


class BaziLogger:

    # 日志目录
    LOG_DIR = Path(__file__).parent.parent / "logs"

    # 日志格式
    CONSOLE_FORMAT = (
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )

    FILE_FORMAT = (
        "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | "
        "%(funcName)s | %(message)s"
    )

    # 日志级别映射
    LEVEL_MAP = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR,
        'critical': logging.CRITICAL
    }

    def __init__(
            self,
            level: str = 'info',
            log_file: Optional[str] = None,
            console_output: bool = True,
            file_output: bool = True
    ):
        """
        初始化日志配置

        Args:
            level: 日志级别 (debug/info/warning/error/critical)
            log_file: 日志文件名（不指定则按日期自动生成）
            console_output: 是否输出到控制台
            file_output: 是否输出到文件
        """
        self.level = self.LEVEL_MAP.get(level.lower(), logging.INFO)
        self.console_output = console_output
        self.file_output = file_output

        # 创建日志目录
        self.LOG_DIR.mkdir(parents=True, exist_ok=True)

        # 生成日志文件名
        if log_file:
            self.log_file = self.LOG_DIR / log_file
        else:
            date_str = datetime.now().strftime("%Y%m%d")
            self.log_file = self.LOG_DIR / f"bazi_agent_{date_str}.log"

        # 配置根日志器
        self._setup_root_logger()

    def _setup_root_logger(self):
        """配置根日志记录器"""
        root_logger = logging.getLogger()
        root_logger.setLevel(self.level)

        # 清除现有处理器（避免重复）
        root_logger.handlers.clear()

        # 添加控制台处理器
        if self.console_output:
            console_handler = self._create_console_handler()
            root_logger.addHandler(console_handler)

        # 添加文件处理器
        if self.file_output:
            file_handler = self._create_file_handler()
            root_logger.addHandler(file_handler)

    def _create_console_handler(self) -> logging.StreamHandler:
        """创建控制台处理器"""
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(self.level)

        # 尝试添加颜色（需要 colorama 库）
        try:
            from colorama import Fore, Style
            self._add_color_formatter(handler, Fore, Style)
        except ImportError:
            # 无颜色版本
            formatter = logging.Formatter(self.CONSOLE_FORMAT)
            handler.setFormatter(formatter)

        return handler

    def _add_color_formatter(self, handler, Fore, Style):
        """添加彩色格式器"""

        class ColorFormatter(logging.Formatter):
            COLORS = {
                'DEBUG': Fore.CYAN,
                'INFO': Fore.GREEN,
                'WARNING': Fore.YELLOW,
                'ERROR': Fore.RED,
                'CRITICAL': Fore.RED + Style.BRIGHT
            }

            def format(self, record):
                color = self.COLORS.get(record.levelname, '')
                reset = Style.RESET_ALL
                record.levelname = f"{color}{record.levelname}{reset}"
                return super().format(record)

        formatter = ColorFormatter(self.CONSOLE_FORMAT)
        handler.setFormatter(formatter)

    def _create_file_handler(self) -> logging.FileHandler:
        """创建文件处理器"""
        handler = logging.FileHandler(
            self.log_file,
            encoding='utf-8',
            mode='a'
        )
        handler.setLevel(self.level)
        formatter = logging.Formatter(self.FILE_FORMAT)
        handler.setFormatter(formatter)
        return handler

    def get_logger(self, name: str) -> logging.Logger:
        """
        获取指定名称的日志记录器

        Args:
            name: 日志器名称（通常使用 __name__）

        Returns:
            配置好的 Logger 对象
        """
        logger = logging.getLogger(name)
        logger.setLevel(self.level)
        return logger


# ============================================================================
# 便捷函数
# ============================================================================

def setup_logging(
        level: str = 'info',
        log_file: Optional[str] = None,
        console_output: bool = True,
        file_output: bool = True
) -> BaziLogger:
    """
    快速配置日志系统

    Args:
        level: 日志级别
        log_file: 日志文件名
        console_output: 是否输出到控制台
        file_output: 是否输出到文件

    Returns:
        BaziLogger 实例
    """
    logger_config = BaziLogger(
        level=level,
        log_file=log_file,
        console_output=console_output,
        file_output=file_output
    )
    return logger_config


def get_logger(name: str) -> logging.Logger:
    """
    快速获取日志记录器

    Args:
        name: 日志器名称（通常使用 __name__）

    Returns:
        Logger 对象
    """
    return logging.getLogger(name)


# ============================================================================
# 默认配置（模块导入时自动执行）
# ============================================================================

# 创建默认日志配置
_default_logger: Optional[BaziLogger] = None


def init_default_logging():
    """初始化默认日志配置"""
    global _default_logger
    if _default_logger is None:
        _default_logger = setup_logging(
            level='info',
            log_file='bazi_agent.log',
            console_output=True,
            file_output=True
        )
    return _default_logger

# 自动初始化（可选，如不需要可注释掉）
# init_default_logging()