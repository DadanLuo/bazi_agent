# 赛博司命 Bazi Agent

赛博司命是一个面向八字命理与塔罗问答的 FastAPI 智能体项目。它把传统排盘规则、RAG 知识检索、DashScope/Qwen 大模型调用、LangGraph 工作流和网页交互界面整合为一个可本地运行、可扩展的垂直领域应用。

## 核心能力

- 八字分析：支持出生时间、性别、地点、真太阳时、节气边界和四柱结构分析。
- BaziChartSkill：提供结构化排盘、五行统计、十神关系、藏干、纳音、大运与流年等可复用能力。
- RAG 检索：对命理知识库进行向量检索、关键词补充、版本隔离和相关性筛选。
- 大模型适配：通过 OpenAI 兼容接口接入 DashScope/Qwen，支持上下文预算和安全降级。
- 塔罗工作流：提供塔罗抽牌、牌义解释、上下文续问和流式输出。
- 流式 API：通过 SSE 返回分析进度与最终结果，便于前端展示长任务状态。
- 安全与中间件：包含输入校验、安全审核、超时、日志、限流和健康检查。
- 前端页面：`static/index.html` 提供可直接访问的八字与塔罗交互界面。

## 项目结构

```text
bazi-agent/
├── src/
│   ├── agents/        # 八字与塔罗智能体封装
│   ├── api/           # FastAPI 路由、流式接口、健康检查
│   ├── config/        # 模型、RAG、运行参数配置
│   ├── core/          # 八字计算、排盘技能、分词与上下文预算
│   ├── graph/         # LangGraph 节点、状态与工作流
│   ├── llm/           # LLM 抽象层与 DashScope 适配器
│   ├── prompts/       # 提示词注册与复用
│   ├── rag/           # 知识处理、检索器、相关性过滤
│   └── safety/        # 安全审核与场景策略
├── static/            # 浏览器端交互页面
├── tests/             # 核心能力和 API 回归测试
├── docs/              # BaziChartSkill 设计、API、使用与基准说明
└── scripts/           # 辅助脚本与基准测试
```

本地运行产生的浏览器配置、缓存、私有记忆、知识库索引和 `.env` 不应提交到 GitHub。

## 环境要求

- Python 3.10+，推荐 Python 3.11。
- DashScope API Key，用于 Qwen 模型调用。
- Windows、macOS 或 Linux 均可运行；以下示例以 PowerShell 为主。

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

编辑 `.env`，至少设置：

```env
DASHSCOPE_API_KEY=your_dashscope_api_key_here
QWEN_API_KEY=${DASHSCOPE_API_KEY}
QWEN_MODEL=qwen3.5-plus
```

启动服务：

```powershell
.\.venv\Scripts\python.exe -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

打开：

```text
http://localhost:8000
```

健康检查：

```text
GET http://localhost:8000/health
```

## 常用 API

| 场景 | 方法与路径 | 说明 |
| --- | --- | --- |
| 八字分析 | `POST /api/bazi/analyze` | 返回完整八字分析结果 |
| 八字流式分析 | `POST /api/bazi/stream` | SSE 返回进度与结果 |
| 八字续问 | `POST /api/bazi/followup` | 基于会话上下文继续问答 |
| 排盘技能 | `POST /api/bazi/chart` | 返回结构化 BaziChartSkill 排盘 |
| 塔罗分析 | `POST /api/tarot/analyze` | 返回塔罗抽牌与解释 |
| 塔罗流式分析 | `POST /api/tarot/stream` | SSE 返回塔罗分析过程 |
| 塔罗续问 | `POST /api/tarot/followup` | 基于塔罗会话继续问答 |

FastAPI 自动文档：

```text
http://localhost:8000/docs
```

## RAG 知识库

项目支持从本地知识文件构建检索索引。默认配置在 `.env.example` 和 `src/config/rag_config.py` 中维护。

常见配置项：

```env
RAG_ENABLED=true
RAG_RETRIEVAL_TOP_K=8
RAG_RERANK_TOP_K=4
RAG_VERSION_NAMESPACE=default
```

知识库原文、向量索引和运行缓存通常包含本地数据，默认不建议提交。

## 测试

推荐使用项目虚拟环境运行核心回归测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_bazi_calendar_accuracy.py tests\test_bazi_chart_skill.py tests\test_bazi_chart_api.py tests\test_context_budget.py tests\test_model_config.py tests\test_rag_relevance.py tests\test_streaming_api.py tests\test_tokenizer_abstraction.py -q
```

也可以运行全部测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## 发布说明

本次发布只建议提交必要文件：

- 源码：`src/agents`、`src/api`、`src/config`、`src/core`、`src/graph`、`src/llm`、`src/prompts`、`src/rag`、`src/safety`。
- 前端：`static/index.html`。
- 配置：`.env.example`、`pyproject.toml`、`requirements.txt`。
- 测试：核心 API、排盘技能、上下文预算、模型配置、RAG 相关性和流式输出测试。
- 文档：BaziChartSkill 的 API、设计、使用和基准说明。

不发布本地隐私或运行数据，例如 `.env`、`data/memory`、`src/data/memory`、`.edge-profile*`、`.obsidian`、`.workbuddy`、`knowledge_base`、`chroma_db`、`logs`、缓存目录和个人面试资料。

## 许可证

MIT License
