# 八字助手 (Bazi Agent)

一个基于 Python 的八字命理分析工具，提供八字计算、运势分析、风水建议等功能。

## 功能特性

- 八字排盘
- 大运流年分析
- 五行分析
- 纳音分析
- 神煞查询
- 调候用神分析
- 塔罗占卜
- 多模态分析

## 安装

```bash
pip install -r requirements.txt
```

## 使用

```bash
python src/main.py
```

## 项目结构

```
bazi-agent/
├── src/
│   ├── agents/          # 代理模块
│   │   ├── bazi_agent.py    # 八字分析代理
│   │   └── tarot_agent.py   # 塔罗分析代理
│   ├── api/             # API 接口
│   │   ├── bazi_api.py      # 八字 API
│   │   ├── chat_api.py      # 聊天 API
│   │   └── health.py        # 健康检查 API
│   ├── cache/           # 缓存模块
│   │   └── redis_cache.py   # Redis 缓存
│   ├── config/          # 配置文件
│   │   ├── model_config.py      # 模型配置
│   │   ├── middleware_config.py # 中间件配置
│   │   └── rag_config.py        # RAG 配置
│   ├── core/            # 核心逻辑
│   │   ├── bazi_calculator.py   # 八字计算
│   │   ├── tarot_data.py        # 塔罗数据
│   │   └── city_coords.py       # 城市坐标
│   ├── graph/           # 图谱模块
│   │   ├── bazi_graph.py    # 八字图谱
│   │   ├── tarot_graph.py   # 塔罗图谱
│   │   └── state_manager.py # 状态管理
│   ├── llm/             # 大语言模型
│   │   ├── dashscope_llm.py # 阿里云 DashScope
│   │   └── base.py          # LLM 基类
│   ├── memory/          # 记忆模块
│   │   └── memory_manager.py # 记忆管理
│   ├── middleware/      # 中间件
│   │   ├── logging_middleware.py # 日志中间件
│   │   ├── rate_limit.py         # 限流中间件
│   │   └── timeout.py            # 超时中间件
│   ├── prompts/         # 提示词
│   │   ├── chat_prompt.py   # 聊天提示词
│   │   ├── report_prompt.py # 报告提示词
│   │   └── safety_prompt.py # 安全提示词
│   ├── rag/             # RAG 模块
│   │   ├── bm25_retriever.py  # BM25 检索器
│   │   ├── hybrid_retriever.py # 混合检索器
│   │   ├── reranker.py        # 重排序
│   │   └── vector_store.py    # 向量存储
│   ├── skills/          # 技能模块
│   │   ├── context_skill.py   # 上下文技能
│   │   ├── conversation_skill # 对话技能
│   │   └── memory_skill.py    # 记忆技能
│   └── storage/         # 存储模块
│       ├── file_storage.py  # 文件存储
│       └── async_storage.py # 异步存储
├── data/                # 数据文件
├── static/              # 静态文件
└── tests/               # 测试文件
```

## 高可用特性

- **Redis 缓存**：使用 Redis 进行高性能缓存
- **限流中间件**：防止系统过载
- **超时控制**：避免请求长时间挂起
- **降级策略**：系统故障时提供降级服务
- **熔断机制**：防止雪崩效应

## 许可证

MIT License
