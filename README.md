# SuperDeepAnalyze - 超级卷宗深度分析系统

基于 AI Agent 的公检法卷宗深度分析平台。上传卷宗文档后，系统自动完成智能解析、三级编译（L0/L1/L2）、知识图谱构建、Wiki 知识库生成，并提供多轮对话式深度分析。

## 特性

### 文档智能解析
- **多格式支持**：PDF、DOCX、Excel/CSV、图片（VLM OCR）、纯文本
- **PDF 三级解析策略**：Docling（版面分析）→ PyMuPDF（文本提取）→ VLM OCR（扫描件），自动选择最优路径
- **智能分块**：基于章节边界的语义分块，支持中文卷/章/节结构识别
- **跨知识库缓存复用**：相同文件自动复用解析结果

### 三级编译引擎
- **L2 - 原文索引**：文本分块 + FAISS 向量索引 + FTS5 全文索引
- **L1 - 段落摘要**：LLM 批量生成段落级摘要，提取实体、关系、矛盾点
- **L0 - 全局图谱**：跨文档实体融合、时间线构建、事件图谱、交叉引用检测
- **增量编译**：支持断点续编，已编译的文档自动跳过
- **大文档采样**：500+ 文本块文档自动 20% 采样加速编译

### AI Agent 对话分析
- **ReAct 推理引擎**：7 阶段状态机（意图分析→规划→检索→评估→报告）
- **12 个专业工具**：向量搜索、关键词搜索、L0/L1/L2 逐层阅读、实体链展开、时间线查询、渐进式搜索等
- **渐进式下钻**：根据问题复杂度自动选择检索层级（L0→L1→L2），低相关度时自动深入
- **混合检索**：FAISS 向量搜索 + FTS5 关键词搜索 + 图谱搜索，RRF 融合排序
- **多轮记忆**：跨会话持久化记忆 + DAG 压缩上下文管理
- **人机协作**：Agent 主动询问用户确认矛盾点和模糊信息

### Wiki 知识库
- **4 阶段流水线**：结构化数据提取 → 质量门控 → 目录生成 → 页面生成 → 交叉链接
- **自动生成**：实体百科页、关系网络、时间线、矛盾分析、知识缺口识别
- **健康检查**：孤立页面检测、稀疏社区发现、断链检查

### 知识图谱可视化
- **力导向图**：实体关系网络可视化（React Flow）
- **时间线**：事件按时间排列，支持筛选
- **实体详情**：点击查看实体属性、关联关系、原文出处

## 架构

```
┌─────────────────────────────────────────────────┐
│                   Nginx (:80)                    │
│          SPA 静态文件 + API 反向代理              │
├──────────────────────┬──────────────────────────┤
│   React 19 前端      │    FastAPI 后端 (:8000)    │
│   TypeScript         │    Python 3.11            │
│   Vite + Tailwind    │    Uvicorn                │
│   React Flow         │                           │
├──────────────────────┼──────────────────────────┤
│                      │    ┌─────────────────┐    │
│                      │    │  AI Agent Loop   │    │
│                      │    │  (ReAct State)   │    │
│                      │    └────────┬────────┘    │
│                      │             │              │
│                      │    ┌────────┴────────┐    │
│                      │    │   12 Agent Tools │    │
│                      │    │ search_vector    │    │
│                      │    │ search_keyword   │    │
│                      │    │ read_l0/l1/l2    │    │
│                      │    │ progressive_search│    │
│                      │    │ expand_entity    │    │
│                      │    │ get_timeline     │    │
│                      │    │ ...              │    │
│                      │    └────────┬────────┘    │
│                      │             │              │
│                      │    ┌────────┴────────┐    │
│                      │    │ Retrieval Engine │    │
│                      │    │ FAISS + FTS5     │    │
│                      │    │ RRF Hybrid Fusion│    │
│                      │    │ Entity Graph     │    │
│                      │    └─────────────────┘    │
│                      │                           │
│                      │    ┌─────────────────┐    │
│                      │    │ Compile Pipeline │    │
│                      │    │ L2 Chunk Index   │    │
│                      │    │ L1 Summaries     │    │
│                      │    │ L0 Global Graph  │    │
│                      │    │ Wiki Generation  │    │
│                      │    └─────────────────┘    │
│                      │                           │
│                      │    ┌─────────────────┐    │
│                      │    │  Doc Parsers     │    │
│                      │    │ Docling/PyMuPDF  │    │
│                      │    │ python-docx      │    │
│                      │    │ VLM OCR          │    │
│                      │    └─────────────────┘    │
├──────────────────────┴──────────────────────────┤
│              SQLite + FAISS + FileSystem          │
│              (data/ volume 持久化)                 │
└─────────────────────────────────────────────────┘
```

### 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 19, TypeScript 6, Vite 8, Tailwind CSS 4, React Flow 12, Zustand 5 |
| 后端 | Python 3.11, FastAPI, Pydantic 2, Uvicorn |
| AI | OpenAI 兼容 API（GPT-4o / Qwen / DeepSeek 等） |
| 向量搜索 | FAISS-cpu |
| 全文搜索 | SQLite FTS5 |
| 图算法 | NetworkX + python-louvain 社区检测 |
| 文档解析 | Docling, PyMuPDF, python-docx, python-calamine |
| 容器化 | Docker 多阶段构建, nginx, supervisord |

## 安装部署

### 系统要求

- Docker 20.10+
- 目标平台：x86_64 Linux（支持内网离线部署）

### 1. 构建镜像

提供两种 Dockerfile：

| 文件 | 说明 | 镜像大小 |
|------|------|----------|
| `Dockerfile.cpu` | CPU 优化版（推荐） | ~4.6 GB |
| `Dockerfile` | 完整版（含 CUDA） | ~10 GB |

```bash
# 推荐：CPU 优化版
docker build -f Dockerfile.cpu -t superdeepanalyze:cpu .
```

### 2. 启动容器

```bash
docker run -d \
  --name sda \
  -p 80:80 \
  -v $(pwd)/data:/app/data \
  --restart unless-stopped \
  superdeepanalyze:cpu
```

访问 `http://<服务器IP>/` 即可使用。

### 3. 配置模型

首次使用时，在前端 **设置页面**（左侧导航栏底部）配置 AI 模型：

| 角色 | 说明 | 必填 |
|------|------|------|
| **主模型** | Agent 推理、编译、对话（需 OpenAI 兼容 API） | 是 |
| **Embedding** | 向量检索（未配置时自动降级为关键词搜索） | 否 |
| **轻量模型** | L1 段落摘要加速（未配置时使用主模型） | 否 |
| **多模态 VLM** | 图片 OCR、扫描件 PDF 解析 | 否 |

支持的 API 提供商：OpenAI、阿里云 DashScope、SiliconFlow、DeepSeek 等所有 OpenAI 兼容接口。

### 4. 验证服务

```bash
curl http://localhost/api/health
# 预期返回: {"status":"ok","version":"0.1.0"}
```

### 内网离线部署

在有网络的机器上构建并导出：

```bash
docker save superdeepanalyze:cpu | gzip > superdeepanalyze.tar.gz
```

拷贝到内网服务器后导入：

```bash
docker load < superdeepanalyze.tar.gz
```

然后按步骤 2 启动容器即可。

### 数据持久化

容器数据通过 Volume 挂载，重启不丢失：

```
data/
├── sqlite.db              # 主数据库
├── knowledge_bases/        # 文档及编译结果
├── faiss/                  # FAISS 向量索引
└── logs/                   # 应用日志
```

## 使用流程

```
1. 创建知识库 → 2. 上传文档 → 3. 一键编译 → 4. 对话分析
                                  ↓
                            知识图谱/Wiki 自动生成
```

1. **创建知识库**：在知识库页面新建一个案件知识库
2. **上传文档**：支持批量上传 PDF、DOCX、Excel 等格式的卷宗文件
3. **一键编译**：点击编译按钮，系统自动完成 L2 索引 → L1 摘要 → L0 图谱 → Wiki 生成
4. **对话分析**：在对话页面用自然语言提问，AI Agent 自动检索分析并给出带引用的回答

## 项目结构

```
SuperDeepAnalyze/
├── frontend/                    # React 前端
│   └── src/
│       ├── components/
│       │   ├── pages/           # 页面组件（知识库、文档、图谱、对话、Wiki）
│       │   ├── settings/        # 模型设置页面
│       │   ├── agent/           # Agent 事件展示组件
│       │   └── graph/           # 知识图谱可视化
│       └── api/                 # API 客户端
├── backend/
│   ├── app/
│   │   ├── api/                 # FastAPI 路由（knowledge_bases, documents, compile, chat, wiki, models）
│   │   ├── models/              # 数据模型、CRUD、模型路由
│   │   ├── services/
│   │   │   ├── agent/           # AI Agent 核心（ReAct 循环、工具注册、上下文管理）
│   │   │   ├── compilation/     # 三级编译引擎（L0/L1/L2）
│   │   │   ├── retrieval/       # 检索引擎（FAISS、FTS5、RRF 融合、图谱搜索）
│   │   │   ├── wiki/            # Wiki 生成流水线（分析、目录、页面、链接）
│   │   │   ├── parsing/         # 文档解析（Docling、PyMuPDF、DOCX、Excel、VLM OCR）
│   │   │   └── llm/             # LLM 客户端封装
│   │   └── config.py            # 应用配置
│   └── docling_models/          # Docling 预下载模型（离线使用）
├── nginx.conf                   # Nginx 配置（SPA + API 反向代理 + WebSocket）
├── supervisord.conf             # 进程管理（nginx + uvicorn）
├── entrypoint.sh                # 容器入口脚本
├── Dockerfile.cpu               # CPU 优化 Dockerfile（推荐）
├── Dockerfile                   # 完整 Dockerfile（含 CUDA）
└── docker-compose.yml           # Docker Compose（可选）
```

## 常用操作

```bash
docker logs -f sda          # 查看日志
docker stop sda             # 停止服务
docker restart sda          # 重启服务
docker rm -f sda            # 删除容器（数据不丢失）
tar czf backup.tar.gz data/ # 备份数据
```

## License

MIT
