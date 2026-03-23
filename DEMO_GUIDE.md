# 快速使用指南

## 项目已修复的问题

1. ✅ 修复了模块导入路径问题
2. ✅ 修复了性别字段验证问题（支持中英文输入）
3. ✅ 修复了图结构路由错误
4. ✅ 添加了简化版API（不依赖RAG和LLM）
5. ✅ 优化了错误处理和超时控制

## 快速启动

### 方式一：使用启动脚本（推荐）

**Windows:**
```bash
start.bat
```

**Linux/Mac:**
```bash
chmod +x start.sh
./start.sh
```

### 方式二：手动启动

```bash
# 激活虚拟环境
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# 启动服务
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

## API 端点

服务启动后，访问以下地址：

- **API 文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/api/v1/bazi/health

### 主要接口

#### 1. 简化版八字分析（推荐用于演示）

**端点**: `POST /api/v1/bazi/analyze-simple`

**特点**:
- ✅ 不依赖外部API（DashScope）
- ✅ 响应速度快（1-2秒）
- ✅ 包含完整的八字计算结果
- ✅ 适合演示和测试

**请求示例**:
```bash
curl -X POST http://localhost:8000/api/v1/bazi/analyze-simple \
  -H "Content-Type: application/json" \
  -d '{
    "year": 1990,
    "month": 1,
    "day": 1,
    "hour": 12,
    "minute": 0,
    "gender": "male"
  }'
```

**响应内容**:
```json
{
  "success": true,
  "message": "八字分析成功（简化版）",
  "data": {
    "output": {
      "basic_data": {
        "bazi": {
          "year": {"tiangan": "庚", "dizhi": "午"},
          "month": {"tiangan": "己", "dizhi": "卯"},
          "day": {"tiangan": "丙", "dizhi": "寅"},
          "hour": {"tiangan": "甲", "dizhi": "午"}
        },
        "wuxing": {
          "score": {"mu": 280, "huo": 245, "tu": 195, "jin": 100, "shui": 0}
        },
        "geju": {
          "geju_type": "正印格",
          "description": "月令正印，为人仁慈，有学识"
        },
        "yongshen": {
          "yongshen": ["火"],
          "jishen": ["木", "土"]
        },
        "liunian": {
          "year": 2026,
          "jixiong": {"level": "平吉"}
        },
        "dayun": {
          "current_dayun": {
            "analysis": {"level": "大吉"}
          }
        }
      }
    }
  }
}
```

#### 2. 完整版八字分析（需要配置API密钥）

**端点**: `POST /api/v1/bazi/analyze`

**特点**:
- 包含RAG知识检索
- 包含LLM智能分析
- 需要配置 `DASHSCOPE_API_KEY`

**配置方法**:
在 `.env` 文件中添加：
```env
DASHSCOPE_API_KEY=your_api_key_here
```

## 测试示例

### 使用 curl 测试

```bash
# 测试健康检查
curl http://localhost:8000/api/v1/bazi/health

# 测试简化版分析
curl -X POST http://localhost:8000/api/v1/bazi/analyze-simple \
  -H "Content-Type: application/json" \
  -d '{
    "year": 1990,
    "month": 1,
    "day": 1,
    "hour": 12,
    "minute": 0,
    "gender": "male"
  }'
```

### 使用 Python 测试

```python
import requests

# 测试简化版API
response = requests.post(
    "http://localhost:8000/api/v1/bazi/analyze-simple",
    json={
        "year": 1990,
        "month": 1,
        "day": 1,
        "hour": 12,
        "minute": 0,
        "gender": "male"  # 支持 "male"/"female" 或 "男"/"女"
    }
)

print(response.json())
```

## 演示建议

### 1. 展示核心功能

使用简化版API展示：
- 八字排盘（年月日时四柱）
- 五行分析（木火土金水分数）
- 格局判断（正印格、正官格等）
- 喜用神推荐
- 流年运势（2026年）
- 大运分析（当前大运）

### 2. 演示流程

```bash
# 1. 启动服务
start.bat  # 或 ./start.sh

# 2. 打开浏览器访问 API 文档
http://localhost:8000/docs

# 3. 在 Swagger UI 中测试 /api/v1/bazi/analyze-simple 接口

# 4. 展示返回的完整八字分析结果
```

### 3. 演示要点

- ✅ 系统能够正确计算八字（天干地支）
- ✅ 五行分析准确（显示各五行分数）
- ✅ 格局判断合理（基于传统命理规则）
- ✅ 喜用神推荐有理有据
- ✅ 流年和大运分析详细

## 常见问题

### Q: 服务启动失败？
A: 检查是否已安装依赖：`pip install -r requirements.txt`

### Q: 端口被占用？
A: 修改启动脚本中的端口号，或停止占用8000端口的进程

### Q: API返回空数据？
A: 使用简化版API (`/analyze-simple`)，不需要配置API密钥

### Q: 性别字段验证失败？
A: 已修复，现在支持 "male"/"female" 和 "男"/"女" 两种格式

## 项目结构

```
bazi-agent/
├── src/
│   ├── main.py                    # 主应用入口
│   ├── api/
│   │   └── bazi_api.py           # API接口（包含简化版）
│   ├── graph/
│   │   ├── bazi_graph.py         # 完整版工作流
│   │   └── simple_graph.py       # 简化版工作流 ⭐
│   ├── core/
│   │   └── engine/               # 核心计算引擎
│   └── ...
├── start.bat                      # Windows启动脚本 ⭐
├── start.sh                       # Linux/Mac启动脚本 ⭐
└── DEMO_GUIDE.md                 # 本文档 ⭐
```

## 下一步优化建议

1. 配置 DASHSCOPE_API_KEY 以启用完整版功能
2. 添加前端界面（可选）
3. 优化错误提示信息
4. 添加更多测试用例
5. 完善文档和注释

---

**祝演示顺利！** 🎉
