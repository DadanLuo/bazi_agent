# 赛博司命 — 启动与演示教程

## 一、环境准备

### 1.1 前置条件

- Python 3.11+
- Redis（可选，不装也能跑，限流会降级为内存计数器）
- 通义千问 API Key（DashScope）

### 1.2 安装依赖

```bash
# 克隆项目
git clone <repo_url>
cd bazi-agent

# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 1.3 配置环境变量

```bash
# 复制示例配置
cp .env.example .env

# 编辑 .env，填入你的 API Key
```

`.env` 文件内容：

```env
# 必填：通义千问 API Key
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx

# 可选：中间件配置（有默认值，不填也行）
RATE_LIMIT_PER_MINUTE=30        # 普通接口每分钟限流
RATE_LIMIT_LLM_PER_MINUTE=10   # LLM 接口每分钟限流
REQUEST_TIMEOUT_DEFAULT=30      # 普通接口超时（秒）
REQUEST_TIMEOUT_LLM=120         # LLM 接口超时（秒）
LOG_FORMAT=json                 # 日志格式：json / text
```

### 1.4 Redis（可选）

```bash
# Windows: 下载 Redis for Windows 或使用 WSL
# Linux/Mac:
sudo apt install redis-server  # Ubuntu
brew install redis              # Mac

# 启动 Redis
redis-server
```

不装 Redis 的影响：
- 限流降级为内存计数器（单进程有效）
- 八字结果不缓存（每次重新计算）
- 会话数据仅文件存储

---

## 二、启动服务

### 方式一：脚本启动（推荐）

```bash
# Windows
start.bat

# Linux/Mac
chmod +x start.sh
./start.sh
```

### 方式二：手动启动

```bash
# 激活虚拟环境后
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

### 启动成功标志

```
INFO: BaziAgent, TarotAgent 已注册
INFO: 多轮对话路由已注册
INFO: Uvicorn running on http://0.0.0.0:8000
```

### 访问地址

| 地址 | 说明 |
|------|------|
| http://localhost:8000 | 前端页面 |
| http://localhost:8000/docs | Swagger API 文档 |
| http://localhost:8000/health | 存活探针 |
| http://localhost:8000/ready | 就绪探针（检查依赖状态） |

---

## 三、功能演示流程

### 3.1 八字分析演示

1. 打开 http://localhost:8000
2. 左栏默认在「八字分析」Tab
3. 填写出生信息（默认值已填好，可直接用）
4. 点击「完整分析」→ 等待 1-3 分钟
5. 中栏展示：四柱排盘、五行柱状图、格局、喜用神、流年、大运、AI 报告
6. 右栏展示：RAG 检索到的古籍片段
7. 在右下角对话框追问：「我的事业运如何？」「今年适合跳槽吗？」

### 3.2 塔罗占卜演示

1. 点击左栏「塔罗占卜」Tab
2. 输入问题：「我最近的感情运势如何？」
3. 牌阵选择：「三张牌」或留空自动推荐
4. 点击「开始占卜」→ 等待 30 秒 - 1 分钟
5. 中栏展示：牌阵名称 + 牌卡（正/逆位颜色区分、关键词、位置含义）+ AI 解读报告
6. 在右下角对话框追问：「第一张牌代表什么？」「这个结果整体是好是坏？」

### 3.3 中间件演示

**健康检查：**
```bash
# 存活探针
curl http://localhost:8000/health
# → {"status":"alive","uptime_seconds":123.4}

# 就绪探针
curl http://localhost:8000/ready
# → {"status":"ready","checks":{"redis":{"status":"healthy"},"llm":{"status":"healthy"},...}}
```

**限流演示：**
```bash
# 快速发 15 次请求，观察第 11 次开始返回 429
for i in $(seq 1 15); do
  echo -n "Request $i: "
  curl -s -o /dev/null -w "%{http_code}" \
    -X POST http://localhost:8000/api/v1/chat/chat \
    -H "Content-Type: application/json" \
    -d '{"query":"你好","user_id":"test"}'
  echo ""
done
```

**结构化日志观察：**

启动后控制台输出 JSON 格式日志：
```json
{
  "timestamp": "2026-03-21 14:30:00",
  "level": "INFO",
  "logger": "access",
  "message": "POST /api/v1/chat/chat 200 1523.45ms",
  "trace_id": "a1b2c3d4e5f6",
  "method": "POST",
  "path": "/api/v1/chat/chat",
  "status_code": 200,
  "latency_ms": 1523.45,
  "client_ip": "127.0.0.1"
}
```

**响应头检查：**
```bash
curl -v http://localhost:8000/api/v1/chat/chat \
  -X POST -H "Content-Type: application/json" \
  -d '{"query":"你好","user_id":"test"}' 2>&1 | grep -i "x-"

# 预期：
# X-Trace-Id: a1b2c3d4e5f6
# X-RateLimit-Limit: 10
# X-RateLimit-Remaining: 9
# X-RateLimit-Reset: 60
```

---

## 四、API 快速测试

### 八字分析
```bash
curl -X POST http://localhost:8000/api/v1/chat/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "请帮我分析八字",
    "user_id": "demo",
    "birth_data": {
      "year": 1990, "month": 5, "day": 15,
      "hour": 14, "gender": "男",
      "longitude": 116.4, "latitude": 39.9
    },
    "analysis_mode": "simple"
  }'
```

### 塔罗占卜
```bash
curl -X POST http://localhost:8000/api/v1/chat/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "帮我用塔罗牌占卜一下爱情运势",
    "user_id": "demo",
    "agent_type": "tarot"
  }'
```

### 追问（用返回的 conversation_id）
```bash
curl -X POST http://localhost:8000/api/v1/chat/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "这张牌代表什么意思？",
    "user_id": "demo",
    "conversation_id": "<替换为实际ID>"
  }'
```

---

## 五、常见问题

| 问题 | 解决方案 |
|------|----------|
| `DASHSCOPE_API_KEY 未配置` | 在 `.env` 中填入通义千问 API Key |
| `Redis 未安装` | 正常现象，限流自动降级为内存模式 |
| `多轮对话路由注册失败` | 检查 `pip install -r requirements.txt` 是否完整 |
| 八字分析超时 | LLM 调用较慢，完整分析需 1-3 分钟，可先用「快速分析」 |
| 塔罗占卜无响应 | 检查 `/ready` 端点确认 LLM 状态为 healthy |
| 前端页面空白 | 确认 `static/` 目录存在且包含 `index.html` |
