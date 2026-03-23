# TarotAgent 类结构和接口规范

## 1. 类定义

```python
class TarotAgent(BaseAgent):
    """塔罗牌占卜 Agent - 多模态RAG支持"""
    
    def __init__(self):
        """初始化塔罗牌Agent"""
        self.retriever = None
        self.prompt_registry = PromptRegistry()
```

## 2. 核心属性

### 2.1 agent_id 和 display_name

```python
@property
def agent_id(self) -> str:
    return "tarot"

@property
def display_name(self) -> str:
    return "塔罗牌占卜"
```

### 2.2 slot_schema (槽位定义)

```python
@property
def slot_schema(self) -> SlotSchema:
    """塔罗牌占卜所需的槽位定义"""
    return SlotSchema({
        "question_type": {
            "required": True, 
            "pattern": r"(爱情|事业|财运|综合|健康|学业|人际关系|其他)",
            "keywords": ["爱情", "事业", "财运", "综合", "健康", "学业", "人际关系", "其他"]
        },
        "spread_type": {
            "required": False,
            "pattern": r"(单张|三张|凯尔特十字|五张|六张)",
            "keywords": ["单张", "三张", "凯尔特十字", "五张", "六张", "牌阵"]
        },
        "deck_version": {
            "required": False,
            "pattern": r"(维特|RWS|通用|经典)",
            "keywords": ["维特", "RWS", "通用", "经典", "牌面", "版本"]
        },
        "specific_question": {
            "required": False,
            "pattern": r".*",
            "keywords": ["问题", "想问", "关于", "想知道"]
        }
    })
```

### 2.3 intent_keywords (意图关键词)

```python
@property
def intent_keywords(self) -> Dict[str, List[str]]:
    """塔罗牌占卜的意图关键词"""
    return {
        "NEW_ANALYSIS": [
            "塔罗", "占卜", "牌", "算牌", "抽牌", "塔罗牌", "塔罗占卜",
            "问塔罗", "塔罗预测", "塔罗解读", "帮我抽牌", "抽一张牌",
            "塔罗牌阵", "塔罗牌面", "塔罗画面"
        ],
        "FOLLOW_UP": [
            "这张牌", "解释一下", "什么意思", "代表什么", "画面里",
            "为什么", "怎么理解", "详细说说", "能看清楚", "图片中",
            "牌面上", "这个符号", "那个图案", "颜色代表"
        ],
        "TOPIC_SWITCH": [
            "换一个", "换个话题", "说说", "聊聊", "谈谈", "讲讲",
            "重新抽", "再抽一次", "换牌阵"
        ],
        "CLARIFICATION": [
            "什么意思", "为什么", "怎么", "如何", "哪个", "什么",
            "解释", "说明", "不清楚", "不明白", "看不懂"
        ],
        "GENERAL_QUERY": [
            "你好", "在吗", "谢谢", "感谢", "再见", "拜拜"
        ]
    }
```

## 3. 核心方法

### 3.1 handle_analysis (主分析流程)

```python
async def handle_analysis(
    self,
    session: UnifiedSession,
    slots: Dict[str, Any],
    mode: str = "full",
) -> Dict[str, Any]:
    """执行塔罗牌分析 - 多模态RAG集成"""
    # 1. 验证必要槽位
    # 2. 初始化多模态检索器
    # 3. 构建查询
    # 4. 执行多模态检索
    # 5. 组装响应（包含图片URL）
    # 6. 返回结果
```

### 3.2 handle_followup (追问处理)

```python
async def handle_followup(
    self,
    session: UnifiedSession,
    query: str,
) -> str:
    """处理塔罗牌追问"""
    # 1. 检查是否有之前的分析结果
    # 2. 构建追问上下文
    # 3. 使用LLM生成回答
    # 4. 返回回答文本
```

### 3.3 get_domain_constraints (领域约束)

```python
def get_domain_constraints(self) -> str:
    """返回塔罗牌领域的LLM约束"""
    return TAROT_CONSTRAINTS
```

## 4. 辅助方法

### 4.1 _build_tarot_query (构建查询)

```python
def _build_tarot_query(self, slots: Dict[str, Any]) -> str:
    """构建塔罗牌查询文本"""
    # 根据用户输入的槽位构建自然语言查询
```

### 4.2 _get_deck_version (获取牌组版本)

```python
def _get_deck_version(self, slots: Dict[str, Any]) -> str:
    """获取牌组版本"""
    # 将用户友好的版本名称映射到内部标识符
```

### 4.3 _assemble_response (组装响应)

```python
def _assemble_response(
    self, 
    results: List[Dict[str, Any]], 
    slots: Dict[str, Any]
) -> str:
    """组装塔罗牌占卜响应"""
    # 1. 主要牌义解读
    # 2. 图片引用（Markdown格式）
    # 3. 正逆位含义
    # 4. 相关牌义
```

## 5. 领域约束常量

```python
TAROT_CONSTRAINTS = """
你是一位专业的塔罗牌占卜师，需要根据塔罗牌的牌面画面和传统解读为用户提供准确的占卜服务。

重要规则：
1. 必须基于塔罗牌的实际画面进行解读，不能凭空编造
2. 解读时要结合用户的具体问题和抽牌情况
3. 保持专业但温和的语调，避免过于绝对的预测
4. 如果涉及心理健康问题，要提供积极正面的建议
5. 严格遵守中国法律法规，不涉及迷信和违法内容

塔罗牌知识要点：
- 大阿卡纳（22张）：代表人生重大课题和精神成长
- 小阿卡纳（56张）：代表日常生活中的具体事件
- 正位/逆位：同一张牌正逆位含义可能完全不同
- 牌阵：不同牌阵（单张、三张、凯尔特十字等）有不同的解读方式
"""
```

## 6. 依赖关系

### 6.1 导入依赖

```python
from src.agents.base import BaseAgent, SlotSchema
from src.core.contracts import UnifiedSession
from src.prompts.registry import PromptRegistry
from src.rag.multimodal_retriever import MultiModalRetriever
from src.config.rag_config import RAGConfigManager
from src.dependencies import llm
```

### 6.2 外部服务

- **MultiModalRetriever**: 多模态检索服务
- **PromptRegistry**: 提示词模板管理
- **RAGConfigManager**: 配置管理
- **llm**: LLM服务实例

## 7. 错误处理

- **槽位验证失败**: 返回缺失信息提示
- **检索失败**: 返回友好错误消息
- **LLM调用失败**: 记录日志并返回错误提示
- **异常捕获**: 全局异常处理，避免服务中断

## 8. 性能考虑

- **懒加载**: 检索器在首次使用时初始化
- **缓存**: 利用现有缓存机制
- **异步**: 所有I/O操作异步执行
- **批量**: 支持批量检索优化

## 9. 扩展性设计

- **配置驱动**: 检索参数通过配置文件控制
- **插件化**: 多模态编码器可替换
- **多版本支持**: 支持不同塔罗牌版本
- **多语言**: 预留国际化支持