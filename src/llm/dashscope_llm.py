"""
==============================================================================
LLM调用封装类
==============================================================================

功能说明：
    本模块实现了对阿里云通义千问大语言模型的封装，提供统一的调用接口。
    支持基础对话和八字报告生成等功能。

主要功能：
    1. 基础对话调用
    2. 八字分析报告生成
    3. API Key 管理
    4. 错误处理和日志记录

==============================================================================
"""

import asyncio
import os
import json
import logging
import dashscope
from dashscope import Generation
from http import HTTPStatus
from typing import List, Dict, Optional

from src.llm.base import LLMConfig, ToolCallResult

logger = logging.getLogger(__name__)


class DashScopeLLM:
    """
    ==============================================================================
    通义千问 LLM 封装类
    ==============================================================================
    
    功能说明：
        通义千问大语言模型的封装类，提供统一的调用接口。
        支持基础对话和八字报告生成等功能。
    
    核心方法：
        - call() - 基础对话调用
        - generate_bazi_report() - 生成八字分析报告
    
    模型配置：
        - MODEL_NAME: 模型名称（qwen-plus）
        - MAX_TOKENS: 最大 token 数（6000）
        - TEMPERATURE: 温度参数（0.7）
    
    使用场景：
        - 八字分析报告生成
        - 塔罗占卜回复生成
        - 通用对话交互
    
    ==============================================================================
    """

    # 模型配置
    MODEL_NAME = "qwen-plus"  # 模型名称
    MAX_TOKENS = 6000  # ✅ 修复：从 2000 提升到 6000，避免报告截断
    TEMPERATURE = 0.7  # 温度参数，控制生成的随机性

    def __init__(self, config: Optional[LLMConfig] = None):
        """
        ==============================================================================
        初始化，从环境变量读取 API Key
        ==============================================================================
        
        功能说明：
            初始化 LLM 实例，从环境变量中读取阿里云 API Key。
            如果 API Key 未配置，会记录警告日志。
        
        环境变量：
            - DASHSCOPE_API_KEY: 阿里云 DashScope API Key

        ==============================================================================
        """
        self.config = config
        self.model_name = config.model_name if config else self.MODEL_NAME
        self.max_tokens = config.max_tokens if config else self.MAX_TOKENS
        self.temperature = config.temperature if config else self.TEMPERATURE
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
        ==============================================================================
        基础调用方法
        ==============================================================================
        
        功能说明：
            调用通义千问模型进行基础对话，支持系统提示词和对话历史。
        
        参数说明：
            prompt (str): 用户提示词（必填）
            system_prompt (str): 系统提示词（可选），用于设定模型角色和行为
            history (List[Dict]): 对话历史（可选），格式为 [{"role": "user", "content": "..."}, ...]
        
        返回值：
            str: LLM 生成的回复文本
        
        异常处理：
            - API Key 未配置：返回提示信息
            - API 调用失败：返回错误信息
            - 其他异常：返回通用错误信息
        
        调用流程：
            1. 检查 API Key 是否配置
            2. 构建消息列表（系统提示词 + 历史对话 + 当前用户输入）
            3. 调用通义千问 API
            4. 解析响应并返回结果
        
        ==============================================================================
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
            logger.info(f"正在调用模型: {self.model_name} (max_tokens={self.max_tokens})...")

            # 调用通义千问 API
            response = Generation.call(
                model=self.model_name,
                messages=messages,
                result_format='message',  # 获取结构化响应
                max_tokens=self.max_tokens,
                temperature=self.temperature,
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

    async def acall(
            self,
            prompt: str,
            system_prompt: str = None,
            history: List[Dict] = None
    ) -> str:
        """异步对话调用"""
        return await asyncio.to_thread(self.call, prompt, system_prompt, history)

    def call_with_tools(
            self,
            messages: List[Dict],
            tools: List[Dict],
            system_prompt: str = None
    ) -> ToolCallResult:
        """带 tool calling 的调用"""
        if not self.api_key:
            return ToolCallResult(
                content="⚠️ 系统提示：LLM API Key 未配置，无法完成塔罗占卜。",
                tool_calls=[],
                finish_reason="stop"
            )

        request_messages = []
        if system_prompt:
            request_messages.append({"role": "system", "content": system_prompt})
        request_messages.extend(messages or [])

        try:
            logger.info(f"正在调用模型工具模式: {self.model_name}")
            response = Generation.call(
                model=self.model_name,
                messages=request_messages,
                tools=tools,
                result_format="message",
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                stream=False,
            )

            if response.status_code != HTTPStatus.OK:
                logger.error(f"❌ Tool Calling 失败: {response.code} - {response.message}")
                return ToolCallResult(
                    content=f"工具调用失败（错误代码：{response.code}）",
                    tool_calls=[],
                    finish_reason="stop"
                )

            choice = response.output.choices[0]
            message = choice.message
            message_dict = dict(message) if message else {}
            tool_calls = []

            for tool_call in message_dict.get("tool_calls", []) or []:
                function = tool_call.get("function", {}) if isinstance(tool_call, dict) else {}
                tool_calls.append({
                    "id": tool_call.get("id", "") if isinstance(tool_call, dict) else "",
                    "type": tool_call.get("type", "function") if isinstance(tool_call, dict) else "function",
                    "function": {
                        "name": function.get("name", "") if isinstance(function, dict) else "",
                        "arguments": function.get("arguments", "{}") if isinstance(function, dict) else "{}",
                    }
                })

            if not tool_calls and isinstance(message_dict.get("function_call"), dict):
                function = message_dict["function_call"]
                tool_calls.append({
                    "id": "",
                    "type": "function",
                    "function": {
                        "name": function.get("name", ""),
                        "arguments": function.get("arguments", "{}"),
                    }
                })

            content = message_dict.get("content", "") or ""
            finish_reason = getattr(choice, "finish_reason", "stop") or "stop"
            logger.info("✅ Tool Calling 成功")
            return ToolCallResult(
                content=content,
                tool_calls=tool_calls,
                finish_reason=finish_reason
            )

        except Exception as e:
            logger.error(f"❌ Tool Calling 异常: {e}", exc_info=True)
            return ToolCallResult(
                content="占卜过程中发生异常，请稍后重试。",
                tool_calls=[],
                finish_reason="stop"
            )

    async def acall_with_tools(
            self,
            messages: List[Dict],
            tools: List[Dict],
            system_prompt: str = None
    ) -> ToolCallResult:
        """异步 tool calling"""
        return await asyncio.to_thread(self.call_with_tools, messages, tools, system_prompt)

    def generate_bazi_report(
            self,
            bazi_data: Dict,
            knowledge_context: str
    ) -> str:
        """
        ==============================================================================
        生成八字分析报告
        ==============================================================================
        
        功能说明：
            调用 LLM 生成专业的八字分析报告，结合八字分析数据和知识库内容。
        
        参数说明：
            bazi_data (Dict): 包含所有分析结果的字典，包括：
                - birth_info: 出生信息
                - four_pillars: 四柱八字
                - wuxing_analysis: 五行分析
                - geju_analysis: 格局判断
                - yongshen_analysis: 喜用神分析
                - liunian_analysis: 流年运势分析
            knowledge_context (str): RAG 检索到的知识上下文，用于补充报告内容
        
        返回值：
            str: 生成的八字分析报告文本
        
        报告内容：
            1. 命局总论
            2. 性格特征
            3. 事业财运
            4. 感情婚姻
            5. 流年运势
            6. 趋吉避凶建议
        
        调用流程：
            1. 尝试导入自定义提示词模板
            2. 如果导入失败，使用默认提示词模板
            3. 格式化用户提示词
            4. 调用 LLM 生成报告
        
        ==============================================================================
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
