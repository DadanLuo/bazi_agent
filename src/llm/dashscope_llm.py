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
    3. 第三方 API 配置管理
    4. 错误处理和日志记录

==============================================================================
"""

import asyncio
import json
import logging
import threading
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional
from openai import OpenAI

from src.config.model_config import ModelConfig, get_default_model_config
from src.llm.base import LLMConfig, ToolCallResult
from src.core.tokenizer import get_tokenizer_for_model

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
    
    使用场景：
        - 八字分析报告生成
        - 塔罗占卜回复生成
        - 通用对话交互
    
    ==============================================================================
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        """
        ==============================================================================
        初始化，从统一配置中心读取第三方 API 配置
        ==============================================================================
        
        功能说明：
            初始化 LLM 实例，模型名、base_url、上下文窗口、输出 token
            均由 src.config.model_config 统一提供。

        ==============================================================================
        """
        runtime_model_config = (
            ModelConfig(config.model_name)
            if config and config.model_name
            else get_default_model_config()
        )
        self.runtime_model_config = runtime_model_config
        self.config = runtime_model_config.apply_override(config)
        self.model_name = self.config.model_name or runtime_model_config.model_name
        self.max_tokens = self.config.max_tokens or runtime_model_config.max_tokens
        self.context_window = self.config.context_window or runtime_model_config.context_window
        self.temperature = (
            self.config.temperature
            if self.config.temperature is not None
            else runtime_model_config.temperature
        )
        self.timeout = self.config.timeout or runtime_model_config.timeout
        self.max_retries = (
            self.config.max_retries
            if self.config.max_retries is not None
            else runtime_model_config.max_retries
        )
        self.base_url = self.config.base_url or runtime_model_config.base_url
        self.api_key = self.config.api_key or runtime_model_config.api_key
        self.extra_body = dict(runtime_model_config.extra_body)
        self.extra_body.update(self.config.extra_body or {})
        tokenizer_model = (
            self.config.tokenizer_model
            or runtime_model_config.tokenizer_model
            or self.model_name
        )
        self.tokenizer = get_tokenizer_for_model(tokenizer_model)
        self.client: Optional[OpenAI] = None

        if not self.api_key:
            logger.warning("⚠️ 未配置 LLM API Key，请在 config/.env 中设置相关凭据")
        else:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
                max_retries=self.max_retries,
            )

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
        if not self.client:
            return "⚠️ 系统提示：LLM API Key 未配置，无法生成智能分析。请在 config/.env 中设置相关凭据。"

        messages = self._build_messages(prompt, system_prompt, history)

        try:
            logger.info(f"正在调用模型: {self.model_name} (max_tokens={self.max_tokens})...")
            response = self.client.chat.completions.create(
                **self._build_completion_kwargs(messages=messages, stream=False)
            )
            choice = response.choices[0]
            content = self._extract_choice_content(choice)
            usage = getattr(response, "usage", None)
            actual_tokens = getattr(usage, "total_tokens", 0) if usage else 0
            logger.info(f"✅ LLM 调用成功 (消耗 {actual_tokens} tokens)")
            return content

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

    def stream(
            self,
            prompt: str,
            system_prompt: str = None,
            history: List[Dict] = None
    ) -> Iterator[str]:
        """同步流式对话调用。"""
        if not self.client:
            yield "⚠️ 系统提示：LLM API Key 未配置，无法生成智能分析。请在 config/.env 中设置相关凭据。"
            return

        messages = self._build_messages(prompt, system_prompt, history)

        try:
            logger.info(f"正在流式调用模型: {self.model_name} (max_tokens={self.max_tokens})...")
            responses = self.client.chat.completions.create(
                **self._build_completion_kwargs(messages=messages, stream=True)
            )

            for response in responses:
                if not getattr(response, "choices", None):
                    continue
                delta = response.choices[0].delta
                content = self._extract_content_parts(getattr(delta, "content", None))
                if content:
                    yield content

            logger.info("✅ 流式 LLM 调用完成")
        except Exception as e:
            logger.error(f"❌ 流式 LLM 调用异常: {e}", exc_info=True)
            yield "分析生成过程发生异常，请稍后重试"

    async def astream(
            self,
            prompt: str,
            system_prompt: str = None,
            history: List[Dict] = None
    ) -> AsyncIterator[str]:
        """异步流式对话调用。"""
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Any] = asyncio.Queue()
        sentinel = object()

        def worker() -> None:
            try:
                for chunk in self.stream(prompt, system_prompt, history):
                    asyncio.run_coroutine_threadsafe(queue.put(chunk), loop).result()
            except Exception as exc:  # pragma: no cover - 线程异常兜底
                asyncio.run_coroutine_threadsafe(queue.put(exc), loop).result()
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(sentinel), loop).result()

        threading.Thread(target=worker, daemon=True).start()

        while True:
            item = await queue.get()
            if item is sentinel:
                break
            if isinstance(item, Exception):
                raise item
            yield item

    def call_with_tools(
            self,
            messages: List[Dict],
            tools: List[Dict],
            system_prompt: str = None
    ) -> ToolCallResult:
        """带 tool calling 的调用"""
        if not self.client:
            return ToolCallResult(
                content="⚠️ 系统提示：LLM API Key 未配置，无法完成塔罗占卜。",
                finish_reason="stop"
            )

        request_messages = []
        if system_prompt:
            request_messages.append({"role": "system", "content": system_prompt})
        available_history_budget = self._get_message_budget(
            system_prompt=system_prompt or "",
            prompt_text="工具调用消息",
        )
        request_messages.extend(
            self._trim_messages_to_budget(messages or [], available_history_budget)
        )

        try:
            logger.info(f"正在调用模型工具模式: {self.model_name}")
            response = self.client.chat.completions.create(
                **self._build_completion_kwargs(
                    messages=request_messages,
                    stream=False,
                    tools=tools,
                )
            )
            choice = response.choices[0]
            message = getattr(choice, "message", None)
            tool_calls = self._normalize_tool_calls(message)
            content = self._extract_content_parts(getattr(message, "content", None))
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

    def _get_message_budget(self, system_prompt: str, prompt_text: str) -> int:
        safety_margin = min(max(int(self.context_window * 0.05), 512), 16384)
        available = (
            self.context_window
            - self.max_tokens
            - safety_margin
            - self.tokenizer.count_text(system_prompt)
            - self.tokenizer.count_text(prompt_text)
        )
        return max(available, 256)

    def _build_messages(
            self,
            prompt: str,
            system_prompt: str = None,
            history: List[Dict] = None
    ) -> List[Dict]:
        messages: List[Dict] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if history:
            available_history_budget = self._get_message_budget(
                system_prompt=system_prompt or "",
                prompt_text=prompt,
            )
            messages.extend(self._trim_messages_to_budget(history, available_history_budget))

        available_prompt_budget = self._get_message_budget(
            system_prompt=system_prompt or "",
            prompt_text="",
        ) - self.tokenizer.count_messages(messages)
        if self.tokenizer.count_text(prompt) > available_prompt_budget:
            original_tokens = self.tokenizer.count_text(prompt)
            prompt = self.tokenizer.trim_text(prompt, max(available_prompt_budget, 64))
            logger.warning(
                "最终 prompt 超预算，已执行 LLM 调用前兜底裁剪: %s -> %s tokens",
                original_tokens,
                self.tokenizer.count_text(prompt),
            )

        messages.append({"role": "user", "content": prompt})
        return messages

    def _build_completion_kwargs(
        self,
        *,
        messages: List[Dict],
        stream: bool,
        tools: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": stream,
        }
        if tools:
            kwargs["tools"] = tools
        if self.extra_body:
            kwargs["extra_body"] = dict(self.extra_body)
        return kwargs

    @classmethod
    def _extract_choice_content(cls, choice: Any) -> str:
        message = getattr(choice, "message", None)
        if message is None:
            return getattr(choice, "text", "") or ""

        return cls._extract_content_parts(getattr(message, "content", None))

    @staticmethod
    def _extract_content_parts(content: Any) -> str:
        if not content:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    parts.append(str(item.get("text") or item.get("content") or ""))
                else:
                    text = getattr(item, "text", None) or getattr(item, "content", None)
                    if text:
                        parts.append(str(text))
            return "".join(parts)
        if isinstance(content, dict):
            return str(content.get("text") or content.get("content") or "")
        return str(content)

    @staticmethod
    def _normalize_tool_calls(message: Any) -> List[Dict[str, Any]]:
        if message is None:
            return []

        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls and isinstance(message, dict):
            tool_calls = message.get("tool_calls")

        normalized: List[Dict[str, Any]] = []
        for tool_call in tool_calls or []:
            function = getattr(tool_call, "function", None)
            if function is None and isinstance(tool_call, dict):
                function = tool_call.get("function", {})
            normalized.append({
                "id": getattr(tool_call, "id", "") if not isinstance(tool_call, dict) else tool_call.get("id", ""),
                "type": getattr(tool_call, "type", "function") if not isinstance(tool_call, dict) else tool_call.get("type", "function"),
                "function": {
                    "name": getattr(function, "name", "") if not isinstance(function, dict) else function.get("name", ""),
                    "arguments": getattr(function, "arguments", "{}") if not isinstance(function, dict) else function.get("arguments", "{}"),
                },
            })
        return normalized

    def _trim_messages_to_budget(self, messages: List[Dict], token_budget: int) -> List[Dict]:
        if not messages:
            return []

        def message_tokens(message: Dict) -> int:
            return self.tokenizer.count_messages([message])

        total_tokens = sum(message_tokens(message) for message in messages)
        if total_tokens <= token_budget:
            return messages

        trimmed: List[Dict] = []
        running_tokens = 0
        for message in reversed(messages):
            current_tokens = message_tokens(message)
            if running_tokens + current_tokens > token_budget and trimmed:
                break
            trimmed.insert(0, message)
            running_tokens += current_tokens
            if running_tokens >= token_budget:
                break

        if not trimmed:
            last_message = messages[-1].copy()
            content = str(last_message.get("content", ""))
            char_budget = max(token_budget * 2, 80)
            if len(content) > char_budget:
                last_message["content"] = content[-char_budget:]
            return [last_message]

        return trimmed

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

        from src.core.context_budget import (
            ContextBudgetAllocator,
            ContextModule,
            get_report_ratios,
        )

        strategy_name = "HYBRID"
        ratios = get_report_ratios(strategy_name)
        prompt_overhead = BAZI_REPORT_USER_PROMPT.format(bazi_data="", knowledge_context="")
        allocator = ContextBudgetAllocator.for_llm(self)
        bazi_data_text = json.dumps(bazi_data, ensure_ascii=False, indent=2)
        allocation = allocator.allocate(
            modules=[
                ContextModule(
                    name="analysis_data",
                    content=bazi_data_text,
                    ratio=ratios["analysis_data"],
                    strategy="json_fields",
                    preserve_domains=True,
                    priority=10,
                ),
                ContextModule(
                    name="knowledge_context",
                    content=knowledge_context,
                    ratio=ratios["knowledge_context"],
                    strategy="rag_documents",
                    preserve_domains=True,
                    priority=20,
                ),
            ],
            prompt_overhead_text=BAZI_REPORT_SYSTEM_PROMPT + "\n" + prompt_overhead,
            strategy_name=strategy_name,
        )

        prompt_result = allocation.finalize_prompt(
            lambda module_texts: BAZI_REPORT_USER_PROMPT.format(
                bazi_data=module_texts.get("analysis_data", ""),
                knowledge_context=module_texts.get("knowledge_context", ""),
            )
        )
        user_prompt = prompt_result.prompt_text

        logger.info("正在生成八字分析报告...")

        # 调用 LLM（max_tokens 由统一模型配置控制）
        report = self.call(
            prompt=user_prompt,
            system_prompt=BAZI_REPORT_SYSTEM_PROMPT
        )

        return report
