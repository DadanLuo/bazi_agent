"""
LLM调用封装类
基于阿里云通义千问
"""
import os
import json
import logging
import re
from typing import List, Dict, Optional
from dashscope import Generation
from http import HTTPStatus

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
    # 续写配置
    MAX_RETRIES = 2  # 最大续写次数
    MIN_TOKENS_THRESHOLD = 5500  # 触发续写的 token 阈值
    COMPLETION_INDICATORS = [r'\d+\.$', r'。$', r'！$', r'？$', r'\n\n$']  # 完整性检测模式

    def __init__(self):
        """初始化，从环境变量读取 API Key"""
        self.api_key = os.getenv("DASHSCOPE_API_KEY")

        if not self.api_key:
            logger.warning("⚠️ DASHSCOPE_API_KEY 未配置，LLM调用将返回默认文本")
        else:
            # 设置全局 API Key
            Generation.api_key = self.api_key

    def call(
            self,
            prompt: str,
            system_prompt: str = None,
            history: List[Dict] = None,
            stream: bool = False
    ) -> str:
        """
        基础调用方法

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词（可选）
            history: 对话历史（可选）
            stream: 是否流式输出

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
                stream=stream
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

    def _is_content_complete(self, content: str, tokens_used: int) -> bool:
        """
        检查内容是否完整
        Args:
            content: 生成的文本内容
            tokens_used: 已使用的 token 数
        Returns:
            bool: 内容是否完整
        """
        # 检查 token 使用量是否接近上限
        if tokens_used >= self.MIN_TOKENS_THRESHOLD:
            logger.warning(f"⚠️ Token 使用量接近上限 ({tokens_used}/{self.MAX_TOKENS})")
            return False

        # 检查内容是否以完整的句子或列表项结尾
        for pattern in self.COMPLETION_INDICATORS:
            if re.search(pattern, content):
                return True

        # 检查内容长度是否合理（避免过短）
        if len(content) < 100:  # 假设 100 字是合理的最小长度
            return False

        return False

    def _generate_continuation(
            self,
            previous_content: str,
            context: str,
            max_retries: int = 1
    ) -> str:
        """
        生成续写内容
        Args:
            previous_content: 之前生成的内容
            context: 上下文信息
            max_retries: 最大重试次数
        Returns:
            续写的内容
        """
        retry_count = 0
        continuation = ""

        while retry_count < max_retries:
            try:
                # 构建续写提示词
                continuation_prompt = (
                    "请继续完成以下未完成的分析报告内容，不要重复之前的内容：\n\n"
                    f"【已生成内容】\n{previous_content}\n\n"
                    f"【上下文】\n{context}\n\n"
                    "请继续生成剩余的分析内容，确保报告完整。"
                )

                logger.info(f"正在生成续写内容 (尝试 {retry_count + 1}/{max_retries})...")

                # 调用 LLM 生成续写内容
                continuation = self.call(
                    prompt=continuation_prompt,
                    system_prompt="你是一位专业的八字命理大师，请继续完成未完成的分析报告。"
                )

                # 检查续写内容是否有效
                if continuation and len(continuation.strip()) > 10:
                    logger.info("✅ 续写内容生成成功")
                    break
                else:
                    logger.warning("⚠️ 续写内容为空或过短，尝试重新生成")
                    retry_count += 1
                    continue

            except Exception as e:
                logger.error(f"❌ 续写过程异常: {e}")
                retry_count += 1
                continue

        return continuation

    def generate_bazi_report(
            self,
            bazi_data: Dict,
            knowledge_context: str
    ) -> str:
        """
        生成八字分析报告（带智能续写机制）

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

        # 第一次生成
        report_content = self.call(
            prompt=user_prompt,
            system_prompt=BAZI_REPORT_SYSTEM_PROMPT
        )

        # 检查内容完整性
        if not self._is_content_complete(report_content, self.MAX_TOKENS):
            logger.warning("⚠️ 检测到报告可能被截断，开始续写过程...")

            # 生成续写内容
            continuation = self._generate_continuation(
                previous_content=report_content,
                context=user_prompt
            )

            # 合并内容
            if continuation:
                report_content += "\n\n" + continuation
                logger.info("✅ 报告续写完成")
            else:
                logger.warning("⚠️ 续写失败，返回原始内容")

        return report_content

    def generate_streaming_report(
            self,
            bazi_data: Dict,
            knowledge_context: str
    ) -> str:
        return self.generate_bazi_report(bazi_data, knowledge_context)
