"""
LLM调用封装类
基于阿里云通义千问
"""
import os
import json
import logging
import dashscope
from dashscope import Generation
from http import HTTPStatus
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class DashScopeLLM:
    """
    通义千问 LLM 封装类
    支持基础对话和八字报告生成
    """

    # 模型配置
    MODEL_NAME = "qwen-plus"
    MAX_TOKENS = 6000  # ✅ 修复：从 2000 提升到 6000，避免报告截断
    TEMPERATURE = 0.7

    def __init__(self):
        """初始化，从环境变量读取 API Key"""
        self.api_key = os.getenv("DASHSCOPE_API_KEY")

        if not self.api_key:
            logger.warning("⚠️ DASHSCOPE_API_KEY 未配置，LLM调用将返回默认文本")
        else:
            # 设置全局 API Key
            dashscope.api_key = self.api_key

    def call(
            self,
            prompt: str,
            system_prompt: str = None,
            history: List[Dict] = None
    ) -> str:
        """
        基础调用方法

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词（可选）
            history: 对话历史（可选）

        Returns:
            LLM生成的回复文本
        """
        if not self.api_key:
            return "⚠️ 系统提示：LLM API Key 未配置，无法生成智能分析。请配置 DASHSCOPE_API_KEY。"

        # 构建消息列表
        messages = []

        # 添加系统提示词
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # 添加历史对话
        if history:
            messages.extend(history)

        # 添加当前用户输入
        messages.append({"role": "user", "content": prompt})

        try:
            logger.info(f"正在调用模型: {self.MODEL_NAME} (max_tokens={self.MAX_TOKENS})...")

            # 调用通义千问 API
            response = Generation.call(
                model=self.MODEL_NAME,
                messages=messages,
                result_format='message',  # 获取结构化响应
                max_tokens=self.MAX_TOKENS,
                temperature=self.TEMPERATURE,
                stream=False  # 暂不使用流式输出
            )

            # 检查响应状态
            if response.status_code == HTTPStatus.OK:
                content = response.output.choices[0].message.content
                actual_tokens = response.usage.get('total_tokens', 0)
                logger.info(f"✅ LLM 调用成功 (消耗 {actual_tokens} tokens)")
                return content
            else:
                logger.error(f"❌ LLM 调用失败: {response.code} - {response.message}")
                return f"分析生成失败（错误代码：{response.code}）"

        except Exception as e:
            logger.error(f"❌ LLM 调用异常: {e}", exc_info=True)
            return "分析生成过程发生异常，请稍后重试"

    def generate_bazi_report(
            self,
            bazi_data: Dict,
            knowledge_context: str
    ) -> str:
        """
        生成八字分析报告

        Args:
            bazi_data: 包含所有分析结果的字典（排盘、五行、格局、喜用神等）
            knowledge_context: RAG检索到的知识上下文

        Returns:
            生成的八字报告文本
        """
        # 尝试导入提示词模板
        try:
            from src.prompts.report_prompt import (
                BAZI_REPORT_SYSTEM_PROMPT,
                BAZI_REPORT_USER_PROMPT
            )
        except ImportError:
            logger.warning("⚠️ 提示词模块未找到，使用默认提示词模板")
            # 默认提示词
            BAZI_REPORT_SYSTEM_PROMPT = (
                "你是一位专业的八字命理大师，精通《子平真诠》《滴天髓》《穷通宝鉴》等经典著作。"
                "请根据提供的八字信息和相关知识，生成专业、客观、通俗易懂的分析报告。"
            )
            BAZI_REPORT_USER_PROMPT = (
                "请根据以下八字分析数据和知识背景，生成一份详细的命理分析报告：\n\n"
                "【分析数据】\n{bazi_data}\n\n"
                "【相关知识】\n{knowledge_context}\n\n"
                "请从命局总论、性格特征、事业财运、感情婚姻、流年运势等方面进行分析。"
            )

        # 格式化用户提示词
        user_prompt = BAZI_REPORT_USER_PROMPT.format(
            bazi_data=json.dumps(bazi_data, ensure_ascii=False, indent=2),
            knowledge_context=knowledge_context
        )

        logger.info("正在生成八字分析报告...")

        # 调用 LLM（使用默认的 6000 tokens）
        report = self.call(
            prompt=user_prompt,
            system_prompt=BAZI_REPORT_SYSTEM_PROMPT
        )

        return report
