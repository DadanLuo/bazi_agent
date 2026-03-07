# 赛博司命 - Bazi-Agent v0.2.0

<div align="center">

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-green.svg)
![Version](https://img.shields.io/badge/version-0.2.0-orange.svg)

**基于 LangGraph 的四柱八字智能分析 Agent**

[项目介绍](#项目介绍) • [功能特性](#功能特性) • [快速开始](#快速开始) • [技术架构](#技术架构) • [使用说明](#使用说明) • [更新日志](#更新日志)

</div>

---

## 项目介绍

**Bazi-Agent** 是一个基于 LangGraph 构建的智能四柱八字分析系统，旨在将传统命理学与现代人工智能技术相结合。系统通过分析用户的出生时间（年、月、日、时），自动计算八字信息，并提供五行分析、格局判断、喜用神推荐、流年运势预测等专业服务。

### 核心理念

- **传统智慧 + AI 技术**：融合传统命理学理论与现代机器学习技术
- **可解释性**：每个分析结果都有详细的推导过程和理论依据
- **个性化**：基于用户历史对话提供个性化的分析服务
- **安全合规**：内置安全检查机制，确保输出内容符合规范
- **高性能**：引入 Redis 缓存、HNSW 索引等优化技术

---

## 功能特性

### 🎯 核心功能

| 功能 | 描述 |
|------|------|
| **八字排盘** | 根据出生时间自动计算四柱八字（年柱、月柱、日柱、时柱） |
| **五行分析** | 分析五行（金、木、水、火、土）的旺衰和平衡状态 |
| **格局判断** | 识别八字格局（如正官格、七杀格、从格等） |
| **喜用神分析** | 推荐适合用户的喜用神，指导人生决策 |
| **流年分析** | 分析特定年份的运势变化 |
| **大运分析** | 提供十年大运走势预测 |

### 🚀 v0.2.0 新增优化功能

| 功能 | 描述 |
|------|------|
| **Redis 缓存** | 引入 Redis 缓存层，提高查询响应速度 50-70% |
| **HNSW 索引** | 使用 HNSW 索引加速向量检索，提升检索速度 30-50% |
| **自动策略选择** | 根据查询类型和模型自动选择最优上下文策略 |
| **会话摘要** | 长对话自动摘要，减少 token 消耗 20-40% |

### 🤖 AI 能力

| 功能 | 描述 |
|------|------|
| **多轮对话** | 支持上下文感知的多轮交互式分析 |
| **知识检索** | 基于 RAG 技术检索命理学知识库 |
| **混合检索** | 结合向量检索（Vector）和 BM25 算法 |
| **重排序** | 使用重排序模型提升检索结果质量 |
| **记忆管理** | 记录用户历史对话，提供个性化服务 |

### 📊 输出内容

- 八字排盘结果（含天干地支、五行、神煞）
- 五行旺衰分析（含缺失和过旺情况）
- 格局判断及理论依据
- 喜用神推荐及使用建议
- 流年运势预测（含吉凶提示）
- 专业分析报告（可导出为文档）

---

## 快速开始

### 环境要求

- Python >= 3.10
- pip >= 21.0
- Redis >= 5.0（可选，用于缓存优化）

### 安装步骤

1. **克隆项目**

```bash
git clone https://github.com/your-username/bazi-agent.git
cd bazi-agent
```

2. **创建虚拟环境**（推荐）

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate     # Windows
```

3. **安装依赖**

```bash
pip install -r requirements.txt
```

4. **配置环境变量**

复制 `.env.example` 文件并重命名为 `.env`：

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入必要的 API Key：

```env
# 通义千问 API Key（必填）
DASHSCOPE_API_KEY=your_dashscope_api_key_here

# ChromaDB 路径
CHROMA_DB_PATH=./chroma_db

# Redis 配置（可选，用于缓存优化）
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# 日志级别
LOG_LEVEL=INFO

# 服务配置
HOST=0.0.0.0
PORT=8000
```

5. **启动服务**

```bash
# 启动 API 服务
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# 或使用 Python 模块方式
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

6. **访问服务**

- API 文档：http://localhost:8000/docs
- ReDoc 文档：http://localhost:8000/redoc

7. **运行测试**

```bash
# 运行所有测试
pytest tests/ -v

# 或使用自定义测试运行器
python tests/run_tests.py
```

---

## 技术架构

### 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        API Layer (FastAPI)                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     LangGraph Workflow                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │  Chat    │  │  Bazi    │  │  Memory  │  │  RAG     │    │
│  │  Nodes   │  │  Nodes   │  │  Nodes   │  │  Nodes   │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌──────────────────────────┐    ┌─────────────────────────────┐
│      Core Engine         │    │       Skills & RAG          │
│  ┌────────────────────┐  │    │  ┌───────────────────────┐  │
│  │  BaziCalculator    │  │    │  │  Context Skill        │  │
│  │  WuxingCalculator  │  │    │  │  Memory Skill         │  │
│  │  GejuCalculator    │  │    │  │  Conversation Skill   │  │
│  │  DayunCalculator   │  │    │  │  Export Skill         │  │
│  │  LiunianCalculator │  │    │  └───────────────────────┘  │
│  └────────────────────┘  │    └─────────────────────────────┘
└──────────────────────────┘
```

### 核心模块

| 模块 | 路径 | 描述 |
|------|------|------|
| **核心引擎** | [`src/core/engine/`](src/core/engine/) | 八字计算核心逻辑 |
| **LangGraph 工作流** | [`src/graph/`](src/graph/) | 对话工作流定义 |
| **技能模块** | [`src/skills/`](src/skills/) | 各类技能实现 |
| **RAG 检索** | [`src/rag/`](src/rag/) | 知识检索相关功能 |
| **API 接口** | [`src/api/`](src/api/) | FastAPI 接口定义 |
| **配置管理** | [`src/config/`](src/config/) | 系统配置管理 |
| **缓存管理** | [`src/cache/`](src/cache/) | Redis 缓存管理 |
| **摘要管理** | [`src/memory/`](src/memory/) | 会话摘要管理 |

### 技术栈

| 类别 | 技术 |
|------|------|
| **AI 框架** | LangGraph, LangChain, LangChain Core |
| **LLM 服务** | DashScope (通义千问), OpenAI API |
| **向量数据库** | ChromaDB |
| **嵌入模型** | Sentence Transformers, Text2Vec |
| **Web 框架** | FastAPI, Uvicorn |
| **数据处理** | Pydantic, Pandas |
| **缓存** | Redis, cachetools |
| **测试** | pytest, pytest-asyncio |

---

## 使用说明

### API 接口

#### 1. 八字分析接口

**POST** `/api/v1/bazi/analyze`

请求体：
```json
{
  "name": "张三",
  "gender": "male",
  "birthday": {
    "year": 1990,
    "month": 1,
    "day": 1,
    "hour": 12,
    "minute": 0
  },
  "location": "北京"
}
```

响应：
```json
{
  "success": true,
  "data": {
    "bazi": {
      "year": "庚午",
      "month": "丙子",
      "day": "己丑",
      "hour": "壬申"
    },
    "wuxing": {
      "jin": 2,
      "mu": 1,
      "shui": 2,
      "huo": 2,
      "tu": 2
    },
    "geju": "正官格",
    "yongshen": ["火", "土"]
  }
}
```

#### 2. 多轮对话接口

**POST** `/api/v1/chat/analyze`

请求体：
```json
{
  "message": "我今年运势如何？",
  "conversation_id": "conv_123",
  "user_id": "user_123"
}
```

### 命令行使用

```bash
# 运行测试
pytest tests/ -v

# 代码检查
flake8 src/
mypy src/

# 代码格式化
black src/

# 生成测试报告
python tests/run_tests.py
```

---

## 更新日志

### v0.2.0 (2026-03-07)

#### 新增功能
- ✅ Redis 缓存层优化
- ✅ HNSW 索引加速向量检索
- ✅ 自动策略选择功能
- ✅ 会话摘要功能

#### 新增模块
- `src/cache/` - 缓存模块
- `src/memory/summarizer.py` - 会话摘要器

#### 新增测试
- `tests/test_cache/` - 缓存功能测试
- `tests/test_vector_store/` - 向量存储测试
- `tests/test_strategy/` - 策略选择测试
- `tests/test_summarizer/` - 摘要功能测试
- `tests/test_integration/` - 集成测试

#### 优化改进
- 提高查询响应速度 50-70%
- 提高向量检索速度 30-50%
- 减少 token 消耗 20-40%
- 智能上下文策略选择

### v0.1.0 (初始版本)

- ✅ 八字排盘计算
- ✅ 五行分析
- ✅ 格局判断
- ✅ 喜用神分析
- ✅ 流年分析
- ✅ RAG 知识检索
- ✅ 安全合规检查
- ✅ 报告生成

---

## 项目结构

```
bazi-agent/
├── src/                          # 源代码目录
│   ├── __init__.py
│   ├── main.py                   # 主应用入口
│   ├── logging_config.py         # 日志配置
│   ├── cache/                    # 缓存模块 (v0.2.0 新增)
│   │   ├── __init__.py
│   │   └── redis_cache.py        # Redis 缓存管理器
│   ├── config/                   # 配置模块
│   │   ├── __init__.py
│   │   ├── model_config.py       # 模型配置
│   │   ├── rag_config.py         # RAG 配置
│   │   └── optimized_config.py   # 优化配置 (v0.2.0 新增)
│   ├── core/                     # 核心引擎
│   │   ├── __init__.py
│   │   └── engine/
│   │       ├── bazi_calculator.py    # 八字计算器
│   │       ├── wuxing_calculator.py  # 五行计算器
│   │       ├── geju.py               # 格局判断
│   │       ├── yongshen.py           # 喜用神分析
│   │       ├── dayun.py              # 大运计算
│   │       ├── liunian.py            # 流年计算
│   │       └── rules/                # 规则文件
│   ├── graph/                    # LangGraph 工作流
│   │   ├── __init__.py
│   │   ├── state.py                  # 状态定义
│   │   ├── nodes.py                  # 节点定义
│   │   ├── chat_nodes.py             # 聊天节点
│   │   └── bazi_graph.py             # 八字图谱
│   ├── skills/                   # 技能模块
│   │   ├── __init__.py
│   │   ├── context_skill.py          # 上下文技能
│   │   ├── memory_skill.py           # 记忆技能
│   │   ├── conversation_skill.py     # 对话技能
│   │   └── export_skill.py           # 导出技能
│   ├── rag/                      # RAG 检索模块
│   │   ├── __init__.py
│   │   ├── retriever.py              # 检索器
│   │   ├── bm25_retriever.py         # BM25 检索器
│   │   ├── reranker.py               # 重排序
│   │   ├── hybrid_retriever.py       # 混合检索
│   │   ├── vector_store.py           # 向量存储
│   │   └── knowledge_base/           # 知识库
│   ├── memory/                   # 记忆管理
│   │   ├── __init__.py
│   │   ├── memory_manager.py         # 记忆管理器
│   │   └── summarizer.py             # 会话摘要器 (v0.2.0 新增)
│   ├── prompts/                  # 提示词模块
│   │   ├── __init__.py
│   │   ├── chat_prompt.py            # 聊天提示词
│   │   ├── safety_prompt.py          # 安全提示词
│   │   └── report_prompt.py          # 报告提示词
│   ├── api/                      # API 接口
│   │   ├── __init__.py
│   │   └── bazi_api.py               # 八字 API
│   └── storage/                  # 存储模块
│       ├── __init__.py
│       ├── models.py                 # 数据模型
│       └── file_storage.py           # 文件存储
├── tests/                        # 测试目录 (v0.2.0 新增)
│   ├── __init__.py
│   ├── conftest.py                 # 测试配置
│   ├── run_tests.py                # 测试运行器
│   ├── test_cache/                 # 缓存测试
│   │   ├── __init__.py
│   │   └── test_redis_cache.py
│   ├── test_vector_store/          # 向量存储测试
│   │   ├── __init__.py
│   │   └── test_hnsw_index.py
│   ├── test_strategy/              # 策略选择测试
│   │   ├── __init__.py
│   │   └── test_auto_selection.py
│   ├── test_summarizer/            # 摘要测试
│   │   ├── __init__.py
│   │   └── test_conversation_summarizer.py
│   ├── test_integration/           # 集成测试
│   │   ├── __init__.py
│   │   └── test_end_to_end.py
│   └── reports/                    # 测试报告
│       ├── __init__.py
│       └── test_report_generator.py
├── data/                         # 数据文件
│   ├── bazi_train.json
│   ├── test_complete.json
│   └── test_run.json
├── scripts/                      # 脚本文件
│   ├── generate_alpaca_data.py
│   └── generate_training_data.py
├── plans/                        # 项目计划
│   ├── tech-upgrade-plan.md        # 技术升级计划
│   ├── optimization-report-2026-03-07.md  # 优化报告 (v0.2.0)
│   └── tech-upgrade-plan-v0.3.0.md  # v0.3.0 升级计划
├── .env.example                  # 环境变量示例
├── pyproject.toml                # 项目配置
├── requirements.txt              # 依赖列表
└── README.md                     # 项目说明
```

---

## 开发指南

### 代码规范

- Python 版本：>= 3.10
- 代码风格：PEP 8
- 类型注解：使用 Pydantic 和 Type Hints
- 文档字符串：遵循 Google Python Style Guide

### 运行测试

```bash
pytest tests/ -v --cov=src --cov-report=html
```

### 代码检查

```bash
# 语法检查
flake8 src/

# 类型检查
mypy src/

# 格式化
black src/
```

---

## 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

---

## 许可证

本项目采用 MIT 许可证 - 查看 [`LICENSE`](LICENSE) 文件了解详情。

---

## 联系方式

如有问题或建议，欢迎通过以下方式联系：

- 提交 Issue：https://github.com/your-username/bazi-agent/issues
- 邮件：dev@bazi-agent.local

---

## 致谢

感谢所有为本项目做出贡献的开发者和用户！

---

<div align="center">

**赛博司命 - 让传统智慧照亮未来**

**v0.2.0 - 性能优化版 (2026-03-07)**

</div>
