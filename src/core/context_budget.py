"""
上下文 Token 预算分配与压缩

核心目标：
1. 感知最终模型上下文窗口
2. 为不同 prompt 模块分配 token 预算
3. 超预算时根据模块策略执行压缩
4. 如果上下文涉及多个领域（健康/财运/学业/事业/爱情等），尽量为每个领域保留部分内容
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
from typing import Callable, Dict, Iterable, List, Optional

from src.core.tokenizer import BaseTokenizer, get_tokenizer_for_model

logger = logging.getLogger(__name__)


DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "健康": ["健康", "身体", "疾病", "病症", "睡眠", "情绪", "养生", "压力"],
    "财运": ["财运", "财富", "金钱", "收入", "理财", "投资", "偏财", "正财", "赚钱"],
    "学业": ["学业", "考试", "学习", "成绩", "升学", "读书", "论文", "研究"],
    "事业": ["事业", "工作", "职业", "岗位", "晋升", "面试", "求职", "官运", "创业"],
    "爱情": ["爱情", "感情", "婚姻", "恋爱", "桃花", "伴侣", "对象", "关系", "姻缘"],
}


FOLLOWUP_STRATEGY_PROFILES: Dict[str, Dict[str, float]] = {
    "FULL_CONTEXT": {
        "structured_context": 0.48,
        "retrieval_context": 0.24,
        "recent_history": 0.28,
    },
    "SLIDING_WINDOW": {
        "structured_context": 0.28,
        "retrieval_context": 0.14,
        "recent_history": 0.58,
    },
    "HYBRID": {
        "structured_context": 0.40,
        "retrieval_context": 0.30,
        "recent_history": 0.30,
    },
}


REPORT_STRATEGY_PROFILES: Dict[str, Dict[str, float]] = {
    "FULL_CONTEXT": {
        "analysis_data": 0.62,
        "knowledge_context": 0.38,
    },
    "SLIDING_WINDOW": {
        "analysis_data": 0.70,
        "knowledge_context": 0.30,
    },
    "HYBRID": {
        "analysis_data": 0.60,
        "knowledge_context": 0.40,
    },
}


@dataclass
class ContextModule:
    """单个上下文模块"""

    name: str
    content: str
    ratio: float
    strategy: str = "head_tail"
    preserve_domains: bool = False
    priority: int = 50


@dataclass
class BudgetedModule:
    """预算分配后的模块结果"""

    name: str
    content: str
    original_tokens: int
    allocated_tokens: int
    final_tokens: int
    strategy: str
    preserve_domains: bool
    detected_domains: List[str] = field(default_factory=list)
    truncated: bool = False


@dataclass
class BudgetAllocationResult:
    """一次 prompt 的预算分配结果"""

    model_name: str
    context_window: int
    reserved_output_tokens: int
    safety_margin_tokens: int
    prompt_overhead_tokens: int
    available_context_tokens: int
    strategy_name: str
    modules: Dict[str, BudgetedModule]
    source_modules: Dict[str, ContextModule]
    tokenizer: BaseTokenizer
    recompress_fn: Callable[[ContextModule, int], str] = field(repr=False)
    log_prompt_assembly_fn: Callable[[int, int, bool, List[str]], None] = field(repr=False)

    def get(self, module_name: str) -> str:
        module = self.modules.get(module_name)
        return module.content if module else ""

    @property
    def max_prompt_tokens(self) -> int:
        return self.available_context_tokens + self.prompt_overhead_tokens

    def finalize_prompt(
        self,
        build_prompt,
        min_module_tokens: int = 24,
    ) -> "PromptAssemblyResult":
        """
        最终 prompt 组装后再做一次 token 复核。

        目的：
        - 防止模板拼接、分隔符、查询文本等导致的二次超预算
        - 在最终 prompt 超限时，继续按模块优先级回收 token
        """
        trimmed_modules: List[str] = []
        adjusted = False
        prompt_text = build_prompt({name: module.content for name, module in self.modules.items()})
        prompt_tokens = self.tokenizer.count_text(prompt_text)
        iteration = 0

        while prompt_tokens > self.max_prompt_tokens and iteration < 20:
            overflow = prompt_tokens - self.max_prompt_tokens
            candidate_names = sorted(
                self.modules.keys(),
                key=lambda name: (
                    self.source_modules.get(name, ContextModule(name, "", 0)).priority,
                    -self.modules[name].final_tokens,
                ),
                reverse=True,
            )
            changed = False

            for name in candidate_names:
                source = self.source_modules.get(name)
                module = self.modules.get(name)
                if not source or not module:
                    continue

                domain_floor = max(len(module.detected_domains), 1) * 12 if module.preserve_domains else 12
                lower_bound = max(min_module_tokens, domain_floor)
                if module.final_tokens <= lower_bound:
                    continue

                shrink_by = max(min(overflow + 8, max(module.final_tokens // 4, 16)), 16)
                new_budget = max(module.final_tokens - shrink_by, lower_bound)
                new_content = self.recompress_fn(source, new_budget)
                new_tokens = self.tokenizer.count_text(new_content)
                if new_tokens >= module.final_tokens:
                    continue

                module.content = new_content
                module.final_tokens = new_tokens
                module.allocated_tokens = min(module.allocated_tokens, new_budget)
                module.truncated = module.original_tokens > new_tokens
                trimmed_modules.append(name)
                adjusted = True
                changed = True
                break

            if not changed:
                break

            prompt_text = build_prompt({name: module.content for name, module in self.modules.items()})
            prompt_tokens = self.tokenizer.count_text(prompt_text)
            iteration += 1

        self.log_prompt_assembly_fn(
            prompt_tokens,
            self.max_prompt_tokens,
            adjusted,
            trimmed_modules,
        )

        return PromptAssemblyResult(
            prompt_text=prompt_text,
            prompt_tokens=prompt_tokens,
            max_prompt_tokens=self.max_prompt_tokens,
            adjusted=adjusted,
            trimmed_modules=trimmed_modules,
            module_tokens={name: module.final_tokens for name, module in self.modules.items()},
        )


@dataclass
class PromptAssemblyResult:
    """最终 prompt 组装结果。"""

    prompt_text: str
    prompt_tokens: int
    max_prompt_tokens: int
    adjusted: bool
    trimmed_modules: List[str]
    module_tokens: Dict[str, int]


class ContextBudgetAllocator:
    """
    统一上下文预算分配器

    注意：
    - 当前实现基于 token 估算，不是模型原生 tokenizer
    - 但已经比“纯字符截断”更接近真实上下文预算控制
    """

    def __init__(
        self,
        model_name: str,
        context_window: int,
        reserved_output_tokens: int,
        safety_margin_tokens: Optional[int] = None,
        tokenizer: Optional[BaseTokenizer] = None,
    ):
        self.model_name = model_name
        self.context_window = max(context_window, 1024)
        self.reserved_output_tokens = max(reserved_output_tokens, 256)
        default_margin = min(max(int(self.context_window * 0.05), 512), 16384)
        self.safety_margin_tokens = safety_margin_tokens or default_margin
        self.tokenizer = tokenizer or get_tokenizer_for_model(model_name)

    @classmethod
    def for_llm(
        cls,
        llm,
        reserved_output_tokens: Optional[int] = None,
        safety_margin_tokens: Optional[int] = None,
    ) -> "ContextBudgetAllocator":
        model_name = getattr(llm, "model_name", "unknown-model")
        context_window = getattr(llm, "context_window", 32768)
        output_tokens = reserved_output_tokens or getattr(llm, "max_tokens", 4096)
        return cls(
            model_name=model_name,
            context_window=context_window,
            reserved_output_tokens=output_tokens,
            safety_margin_tokens=safety_margin_tokens,
            tokenizer=get_tokenizer_for_model(model_name),
        )

    def allocate(
        self,
        modules: Iterable[ContextModule],
        prompt_overhead_text: str = "",
        strategy_name: str = "HYBRID",
    ) -> BudgetAllocationResult:
        modules = [m for m in modules if m.content and m.content.strip()]
        overhead_tokens = self.tokenizer.count_text(prompt_overhead_text)
        available_context_tokens = max(
            self.context_window
            - self.reserved_output_tokens
            - self.safety_margin_tokens
            - overhead_tokens,
            128,
        )

        if not modules:
            return BudgetAllocationResult(
                model_name=self.model_name,
                context_window=self.context_window,
                reserved_output_tokens=self.reserved_output_tokens,
                safety_margin_tokens=self.safety_margin_tokens,
                prompt_overhead_tokens=overhead_tokens,
                available_context_tokens=available_context_tokens,
                strategy_name=strategy_name,
                modules={},
                source_modules={},
                tokenizer=self.tokenizer,
                recompress_fn=self._compress_module_for_rebalance,
                log_prompt_assembly_fn=self._log_prompt_assembly,
            )

        total_ratio = sum(max(m.ratio, 0.01) for m in modules)
        budget_map: Dict[str, int] = {}

        remaining = available_context_tokens
        for index, module in enumerate(modules):
            if index == len(modules) - 1:
                budget_map[module.name] = max(remaining, 32)
            else:
                allocated = max(int(available_context_tokens * (module.ratio / total_ratio)), 32)
                budget_map[module.name] = allocated
                remaining -= allocated

        result_modules: Dict[str, BudgetedModule] = {}

        for module in modules:
            allocated_tokens = budget_map[module.name]
            compressed = self._compress_module(module, allocated_tokens)
            final_tokens = self.tokenizer.count_text(compressed)
            result_modules[module.name] = BudgetedModule(
                name=module.name,
                content=compressed,
                original_tokens=self.tokenizer.count_text(module.content),
                allocated_tokens=allocated_tokens,
                final_tokens=final_tokens,
                strategy=module.strategy,
                preserve_domains=module.preserve_domains,
                detected_domains=self._detect_domains(module.content),
                truncated=self.tokenizer.count_text(module.content) > final_tokens,
            )

        self._redistribute_leftover_tokens(result_modules, modules, available_context_tokens)
        self._log_budget_plan(result_modules, available_context_tokens, strategy_name)

        return BudgetAllocationResult(
            model_name=self.model_name,
            context_window=self.context_window,
            reserved_output_tokens=self.reserved_output_tokens,
            safety_margin_tokens=self.safety_margin_tokens,
            prompt_overhead_tokens=overhead_tokens,
            available_context_tokens=available_context_tokens,
            strategy_name=strategy_name,
            modules=result_modules,
            source_modules={module.name: module for module in modules},
            tokenizer=self.tokenizer,
            recompress_fn=self._compress_module_for_rebalance,
            log_prompt_assembly_fn=self._log_prompt_assembly,
        )

    def _redistribute_leftover_tokens(
        self,
        result_modules: Dict[str, BudgetedModule],
        original_modules: List[ContextModule],
        available_context_tokens: int,
    ) -> None:
        used_tokens = sum(module.final_tokens for module in result_modules.values())
        leftover = max(available_context_tokens - used_tokens, 0)
        if leftover < 32:
            return

        priority_map = {module.name: module.priority for module in original_modules}
        refill_order = sorted(
            [name for name, module in result_modules.items() if module.truncated],
            key=lambda name: priority_map.get(name, 50),
        )

        if not refill_order:
            return

        original_by_name = {module.name: module for module in original_modules}

        for name in refill_order:
            if leftover < 32:
                break
            current = result_modules[name]
            original = original_by_name[name]
            expanded_budget = current.allocated_tokens + leftover
            expanded_content = self._compress_module(original, expanded_budget)
            expanded_tokens = self.tokenizer.count_text(expanded_content)
            token_gain = expanded_tokens - current.final_tokens
            if token_gain <= 0:
                continue
            current.content = expanded_content
            current.final_tokens = expanded_tokens
            current.allocated_tokens = expanded_budget
            current.truncated = current.original_tokens > expanded_tokens
            leftover = max(leftover - token_gain, 0)

    def _compress_module(self, module: ContextModule, token_budget: int) -> str:
        if token_budget <= 0:
            return ""
        text = module.content.strip()
        if not text:
            return ""
        if self.tokenizer.count_text(text) <= token_budget:
            return text

        strategy = module.strategy
        if strategy == "recent_history":
            return self._compress_recent_history(text, token_budget)
        if strategy == "rag_documents":
            return self._compress_rag_documents(text, token_budget, module.preserve_domains)
        if strategy == "structured_context":
            return self._compress_structured_context(text, token_budget, module.preserve_domains)
        if strategy == "json_fields":
            return self._compress_structured_context(text, token_budget, module.preserve_domains)
        return self._compress_head_tail(text, token_budget)

    def _compress_module_for_rebalance(self, module: ContextModule, token_budget: int) -> str:
        return self._compress_module(module, token_budget)

    def _compress_recent_history(self, text: str, token_budget: int) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return self._compress_head_tail(text, token_budget)

        kept: List[str] = []
        for line in reversed(lines):
            candidate = "\n".join(reversed([line] + kept))
            if self.tokenizer.count_text(candidate) <= token_budget:
                kept.insert(0, line)
            else:
                break

        if kept:
            result = "\n".join(kept)
            if self.tokenizer.count_text(result) <= token_budget:
                return result

        # 兜底：至少保留最后一条消息的尾部上下文
        return self._compress_head_tail(lines[-1], token_budget)

    def _compress_rag_documents(
        self,
        text: str,
        token_budget: int,
        preserve_domains: bool,
    ) -> str:
        blocks = self._split_blocks(text)
        if len(blocks) <= 1:
            return self._compress_structured_context(text, token_budget, preserve_domains)

        per_block_budget = max(token_budget // max(len(blocks), 1), 48)
        selected: List[str] = []
        for block in blocks:
            if not block.strip():
                continue
            compressed = self._compress_structured_context(block, per_block_budget, preserve_domains)
            if compressed.strip():
                selected.append(compressed.strip())

        merged = "\n\n".join(selected)
        if self.tokenizer.count_text(merged) <= token_budget:
            return merged
        return self._compress_head_tail(merged, token_budget)

    def _compress_structured_context(
        self,
        text: str,
        token_budget: int,
        preserve_domains: bool,
    ) -> str:
        if not preserve_domains:
            return self._compress_head_tail(text, token_budget)

        detected_domains = self._detect_domains(text)
        if len(detected_domains) <= 1:
            return self._compress_head_tail(text, token_budget)

        intro_blocks = self._extract_intro_blocks(text)
        selected_parts: List[str] = []

        intro_budget = max(int(token_budget * 0.20), 64)
        if intro_blocks:
            intro_text = "\n\n".join(intro_blocks)
            selected_parts.append(self._compress_head_tail(intro_text, intro_budget))

        remaining_budget = max(token_budget - sum(self.tokenizer.count_text(p) for p in selected_parts), 64)
        per_domain_budget = max(remaining_budget // max(len(detected_domains), 1), 48)

        for domain in detected_domains:
            excerpt = self._extract_domain_excerpt(text, domain, per_domain_budget)
            if excerpt and excerpt not in selected_parts:
                selected_parts.append(f"【{domain}相关】\n{excerpt}")

        merged = "\n\n".join(part for part in selected_parts if part.strip())
        if merged and self.tokenizer.count_text(merged) <= token_budget:
            return merged

        if merged:
            return self._shrink_preserved_parts(selected_parts, token_budget)
        return self._compress_head_tail(text, token_budget)

    def _shrink_preserved_parts(self, parts: List[str], token_budget: int) -> str:
        if not parts:
            return ""

        parsed_parts = []
        label_tokens = 0
        for part in parts:
            match = re.match(r"^(【.*?】\n)", part, re.S)
            if match:
                label = match.group(1)
                body = part[len(label):]
            else:
                label = ""
                body = part
            label_tokens += self.tokenizer.count_text(label)
            parsed_parts.append((label, body))

        remaining_budget = max(token_budget - label_tokens, max(len(parts) * 24, 24))
        per_part_budget = max(remaining_budget // max(len(parsed_parts), 1), 24)

        while per_part_budget >= 12:
            compressed_parts = []
            for label, body in parsed_parts:
                compressed_body = self._compress_head_tail(body, per_part_budget)
                compressed_parts.append(f"{label}{compressed_body}".strip())

            merged = "\n\n".join(part for part in compressed_parts if part.strip())
            if self.tokenizer.count_text(merged) <= token_budget:
                return merged
            per_part_budget = int(per_part_budget * 0.85)

        return self._compress_head_tail("\n\n".join(parts), token_budget)

    def _extract_intro_blocks(self, text: str) -> List[str]:
        blocks = self._split_blocks(text)
        intros: List[str] = []
        for block in blocks[:3]:
            if any(marker in block for marker in ("四柱八字", "用户八字分析结果", "抽牌结果", "牌阵", "综合解读")):
                intros.append(block)
        return intros

    def _extract_domain_excerpt(self, text: str, domain: str, token_budget: int) -> str:
        keywords = DOMAIN_KEYWORDS.get(domain, [])
        blocks = self._split_blocks(text)

        for block in blocks:
            if any(keyword in block for keyword in keywords):
                return self._compress_head_tail(block, token_budget)

        # 找不到独立块时，保留命中关键词附近的窗口
        position = -1
        keyword_hit = ""
        for keyword in keywords:
            idx = text.find(keyword)
            if idx != -1:
                position = idx
                keyword_hit = keyword
                break

        if position == -1:
            return ""

        approx_chars = max(token_budget * 2, 80)
        start = max(position - approx_chars // 2, 0)
        end = min(position + approx_chars // 2, len(text))
        excerpt = text[start:end].strip()
        if keyword_hit and keyword_hit not in excerpt:
            excerpt = f"{keyword_hit}：{excerpt}"
        return self._compress_head_tail(excerpt, token_budget)

    def _compress_head_tail(self, text: str, token_budget: int) -> str:
        if self.tokenizer.count_text(text) <= token_budget:
            return text
        if token_budget <= 32:
            return self._trim_to_budget(text, token_budget)

        head_chars = max(int(token_budget * 1.4), 80)
        tail_chars = max(int(token_budget * 0.8), 40)
        head = text[:head_chars]
        tail = text[-tail_chars:] if tail_chars < len(text) else ""
        candidate = f"{head}\n...\n{tail}".strip()

        while self.tokenizer.count_text(candidate) > token_budget and len(head) > 20:
            head = head[: int(len(head) * 0.85)]
            tail = tail[-int(len(tail) * 0.85):] if tail else ""
            candidate = f"{head}\n...\n{tail}".strip()

        if self.tokenizer.count_text(candidate) <= token_budget:
            return candidate
        return self._trim_to_budget(text, token_budget)

    def _trim_to_budget(self, text: str, token_budget: int) -> str:
        if self.tokenizer.count_text(text) <= token_budget:
            return text
        return self.tokenizer.trim_text(text, token_budget)

    def _split_blocks(self, text: str) -> List[str]:
        blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
        if blocks:
            return blocks
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return []

        grouped: List[str] = []
        current: List[str] = []
        for line in lines:
            if re.match(r"^(【.*】|---|#|\d+\.)", line) and current:
                grouped.append("\n".join(current).strip())
                current = [line]
            else:
                current.append(line)
        if current:
            grouped.append("\n".join(current).strip())
        return grouped

    def _detect_domains(self, text: str) -> List[str]:
        detected: List[str] = []
        for domain, keywords in DOMAIN_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                detected.append(domain)
        return detected

    def _log_budget_plan(
        self,
        modules: Dict[str, BudgetedModule],
        available_context_tokens: int,
        strategy_name: str,
    ) -> None:
        if not modules:
            return
        module_logs = []
        for module in modules.values():
            module_logs.append(
                f"{module.name}: {module.final_tokens}/{module.allocated_tokens} tokens"
                f" ({module.strategy}, domains={module.detected_domains or 'none'})"
            )
        logger.info(
            "上下文预算分配完成: strategy=%s, available=%s, modules=%s",
            strategy_name,
            available_context_tokens,
            "; ".join(module_logs),
        )

    def _log_prompt_assembly(
        self,
        prompt_tokens: int,
        max_prompt_tokens: int,
        adjusted: bool,
        trimmed_modules: List[str],
    ) -> None:
        logger.info(
            "最终 prompt 复核完成: prompt_tokens=%s, max_prompt_tokens=%s, adjusted=%s, trimmed_modules=%s",
            prompt_tokens,
            max_prompt_tokens,
            adjusted,
            trimmed_modules or [],
        )


def get_followup_ratios(strategy_name: str) -> Dict[str, float]:
    return FOLLOWUP_STRATEGY_PROFILES.get(strategy_name, FOLLOWUP_STRATEGY_PROFILES["FULL_CONTEXT"])


def get_report_ratios(strategy_name: str) -> Dict[str, float]:
    return REPORT_STRATEGY_PROFILES.get(strategy_name, REPORT_STRATEGY_PROFILES["FULL_CONTEXT"])
