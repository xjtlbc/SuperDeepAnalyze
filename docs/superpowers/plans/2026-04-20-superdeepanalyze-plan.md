# SuperDeepAnalyze - 开发计划

> **基于:** 2026-04-20 设计文档
> **目标:** 构建公检法卷宗深度分析系统

---

## 项目阶段总览

| 阶段 | 名称 | 核心目标 | 预计Skills |
|------|------|---------|-----------|
| Phase 0 | 项目骨架 | 前后端项目初始化，基础框架搭建 | - |
| Phase 1 | 模型配置与LLM层 | OpenAI兼容的LLM调用层，模型路由器 | claude-api |
| Phase 2 | 文件解析管线 | Docling + VLM OCR + 多格式解析 | pdf, xlsx, docx |
| Phase 3 | 预编译引擎 | L0/L1/L2三层编译，智能chunking | writing-plans |
| Phase 4 | 存储与检索 | SQLite + FAISS + 混合检索 | - |
| Phase 5 | Agent问答引擎 | reAct loop + Tool Registry | skill-creator |
| Phase 6 | 前端核心 | 知识库管理 + 图谱可视化 + 对话界面 | frontend-design, web-artifacts-builder, theme-factory |
| Phase 6.5 | 前后端联调 | 每完成一个前端模块立即与后端联调验证 | frontend-testing-best-practices |
| Phase 7 | 系统设置与打磨 | 模型配置UI + 主题切换 + 端到端联调 | frontend-testing-best-practices, systematic-debugging |

---

## Phase 0: 项目骨架搭建

**目标:** 建立前后端项目结构，基础依赖安装

### Task 0.1: 后端项目初始化

**Files:**
- `backend/pyproject.toml` - Python 项目配置
- `backend/requirements.txt` - 依赖列表
- `backend/app/__init__.py`
- `backend/app/main.py` - FastAPI 入口
- `backend/app/config.py` - 配置管理
- `.env.example` - 环境变量模板

**Steps:**
1. 创建 `backend/` 目录结构
2. 编写 `pyproject.toml`，包含核心依赖：
   - `fastapi`, `uvicorn[standard]` - Web 框架
   - `sqlalchemy`, `aiosqlite` - ORM
   - `pydantic`, `pydantic-settings` - 数据验证
   - `python-multipart` - 文件上传
   - `openai` - OpenAI 兼容 SDK
   - `faiss-cpu` - 向量检索
   - `docling` - 文档解析
   - `python-docx` - DOCX 解析
   - `calamine` - Excel 解析
3. 编写最小 FastAPI 入口，包含 `/api/health` 端点
4. 验证后端可启动

### Task 0.2: 前端项目初始化

**Files:**
- `frontend/package.json`
- `frontend/vite.config.ts`
- `frontend/tsconfig.json`
- `frontend/index.html`
- `frontend/src/main.tsx`
- `frontend/src/App.tsx`
- `frontend/src/index.css`
- `frontend/tailwind.config.ts`

**Steps:**
1. 创建 `frontend/` 目录结构
2. 配置 Vite + React + TypeScript + Tailwind CSS v4
3. 安装核心依赖：`react`, `react-dom`, `zustand`, `react-router-dom`
4. 编写最小 App 组件，显示 "SuperDeepAnalyze"
5. 验证前端可启动
6. 配置 Vite 代理指向后端

**Skills:** `web-artifacts-builder` (前端组件开发)

---

## Phase 1: 模型配置与LLM层

**目标:** 统一的 OpenAI 兼容 LLM 调用层，支持多模型角色

### Task 1.1: 模型配置管理

**Files:**
- `backend/app/models/__init__.py`
- `backend/app/models/config.py` - 模型配置 Schema
- `backend/app/models/provider.py` - Provider 接口
- `backend/app/models/openai_provider.py` - OpenAI 兼容实现
- `backend/app/models/router.py` - 模型路由器

**Steps:**
1. 定义模型配置 Schema (Pydantic)：
   ```python
   class ModelConfig(BaseModel):
       base_url: str
       model_name: str
       api_key: str
       max_tokens: int = 8192
       dimension: int | None = None  # embedding 专用
   ```
2. 实现 OpenAI 兼容 Provider：
   - `chat()` - 同步聊天
   - `chat_stream()` - 流式聊天（AsyncGenerator）
   - `estimate_tokens()` - CJK 感知 token 估算
3. 实现 Model Router：
   - 读取配置，注册 providers
   - `get_provider(role)` - 按角色获取 provider
   - `chat(role, messages)` - 按角色调用
4. 写入 SQLite model_configs 表的 CRUD

**Skills:** `claude-api` (OpenAI SDK 使用经验)

### Task 1.2: LLM 调用封装

**Files:**
- `backend/app/services/llm/client.py` - 高层 LLM 调用封装
- `backend/app/services/llm/prompts.py` - Prompt 模板管理

**Steps:**
1. 封装高层调用接口：
   - `analyze_document(content)` - 文档分析
   - `summarize_chunk(content)` - 段落摘要
   - `extract_entities(content)` - 实体抽取
   - `build_timeline(content)` - 时间线构建
2. 实现 Prompt 模板系统（支持 Jinja2 或 f-string）
3. 实现流式输出回调机制（WebSocket 推送）

---

## Phase 2: 文件解析管线

**目标:** 多格式文档解析，统一输出 Structured Markdown

### Task 2.1: Docling 解析器

**Files:**
- `backend/app/services/parsing/docling_parser.py`
- `backend/app/services/parsing/types.py` - 解析结果类型

**Steps:**
1. 封装 Docling DocumentConverter
2. 输出 Structured Markdown + 表格数据 + 元数据
3. 处理 PDF 直接文本解析
4. 验证：上传测试 PDF，确认解析结果

**Skills:** `pdf` (PDF 解析经验)

### Task 2.2: VLM OCR 解析器

**Files:**
- `backend/app/services/parsing/vlm_ocr.py`

**Steps:**
1. 实现 PDF 扫描件检测逻辑（文本密度阈值）
2. PDF 扫描件 → 逐页渲染为图片 → VLM OCR
3. 实现 VLM 多模态调用（base_url + model_name + api_key）
4. 图片解析：直接送 VLM 解析
5. 验证：上传扫描件 PDF 和图片，确认 OCR 结果

### Task 2.3: 多格式解析器

**Files:**
- `backend/app/services/parsing/docx_parser.py`
- `backend/app/services/parsing/excel_parser.py`
- `backend/app/services/parsing/image_parser.py`
- `backend/app/services/parsing/dispatcher.py` - 解析调度器

**Steps:**
1. DOCX 解析：python-docx → Markdown（标题/列表/表格）
2. Excel 解析：calamine → Markdown 表格 + 结构化数据
3. 图片解析：复用 VLM OCR
4. 调度器：根据文件类型自动选择解析器
5. 统一输出：`ParsedDocument` 类型

**Skills:** `xlsx` (Excel 处理), `docx` (Word 处理)

### Task 2.4: 智能 Chunking

**Files:**
- `backend/app/services/parsing/chunking.py`

**Steps:**
1. 实现智能 chunking 算法：
   - 优先按自然段落切分
   - 段落 token 数 500-1000 → 保持
   - 段落 token 数 > 1000 → 句子边界拆分
   - 段落 token 数 < 500 → 合并相邻段落
   - 100 tokens overlap
2. 实现 CJK 感知 token 估算
3. 输出 `Chunk` 列表，包含元数据

---

## Phase 3: 预编译引擎

**目标:** L0/L1/L2 三层编译管线，纯函数 Pipeline 模式

### Task 3.1: L2 层编译器

**Files:**
- `backend/app/services/compilation/l2_compiler.py`

**Steps:**
1. 输入：ParsedDocument + Chunks
2. 保存每个 chunk 到文件系统
3. 写入 SQLite wiki_pages 表
4. 生成 FTS5 全文索引
5. 调用 embedding 模型生成向量，存入 FAISS
6. 验证：上传文档，确认 L2 文件生成

### Task 3.2: L1 层编译器

**Files:**
- `backend/app/services/compilation/l1_compiler.py`

**Steps:**
1. 输入：一组 L2 chunks（10-20 个为一批）
2. 调用轻量 LLM 生成段落摘要
3. 抽取段落内人物关系
4. 标注矛盾点/疑点
5. 写入 SQLite + FAISS
6. 验证：确认 L1 摘要生成质量

### Task 3.3: L0 层编译器

**Files:**
- `backend/app/services/compilation/l0_compiler.py`

**Steps:**
1. 输入：所有 L1 摘要 + 文档元数据
2. 调用主模型 (Claude/GPT) 进行全局分析：
   - 实体抽取（人物/组织/地点/时间）
   - 时间线构建
   - 事件图谱
   - 交叉引用
3. 写入 SQLite（实体表、事件表、关系表）
4. 生成 FAISS 向量索引
5. 验证：确认 L0 图谱数据完整

### Task 3.4: 预编译缓存管理

**Files:**
- `backend/app/services/compilation/cache_manager.py`

**Steps:**
1. 实现 SHA256 缓存检测
2. 跨知识库复用预编译结果
3. 支持强制重新编译
4. 验证：同一文件上传两次，确认跳过编译

**Skills:** `writing-plans` (复杂管线设计)

---

## Phase 4: 存储与检索

**目标:** SQLite + FAISS 混合检索引擎

### Task 4.1: 数据库模型与迁移

**Files:**
- `backend/app/models/database.py`
- `backend/app/models/schema.py` - SQLAlchemy 模型
- `backend/app/models/migrations/` - Alembic 迁移

**Steps:**
1. 定义所有数据库表（知识 bases、文档、Wiki pages、实体、事件、会话、消息、模型配置、预编译缓存）
2. 创建 FTS5 虚拟表
3. 实现 Alembic 迁移脚本
4. 验证：启动时自动迁移

### Task 4.2: FAISS 向量索引管理

**Files:**
- `backend/app/services/retrieval/faiss_index.py`

**Steps:**
1. 实现 FAISS 索引创建/更新/删除
2. 支持 L0/L1/L2 三层独立索引
3. 实现向量相似度搜索
4. 持久化索引到磁盘
5. 验证：插入向量，确认搜索结果

### Task 4.3: 混合检索引擎

**Files:**
- `backend/app/services/retrieval/vector_search.py`
- `backend/app/services/retrieval/keyword_search.py`
- `backend/app/services/retrieval/rrf_merge.py`
- `backend/app/services/retrieval/hybrid_search.py`

**Steps:**
1. 向量检索：FAISS 相似度搜索
2. 关键词检索：SQLite FTS5
3. RRF 融合排序（k=60）
4. 统一检索入口：`hybrid_search(query, kb_id, top_k)`
5. 验证：测试文档，确认两路结果融合

---

## Phase 5: Agent 问答引擎

**目标:** 自建 reAct tool-use loop，参考 Claude Code 模式

### Task 5.1: Tool 接口定义

**Files:**
- `backend/app/services/agent/tool.py` - Tool 基类
- `backend/app/services/agent/registry.py` - Tool Registry

**Steps:**
1. 定义 Tool 接口：
   ```python
   class Tool(ABC):
       name: str
       description: str
       input_schema: dict  # JSON Schema
       
       @abstractmethod
       async def execute(self, **kwargs) -> str:
           ...
   ```
2. 实现 Tool Registry：
   - 注册/注销工具
   - 生成 tool_definitions（供 LLM 使用）
   - 并发控制（只读工具可并发）
3. 验证：注册测试工具，确认可调用

### Task 5.2: 工具实现

**Files:**
- `backend/app/services/agent/tools/search_vector.py`
- `backend/app/services/agent/tools/search_keyword.py`
- `backend/app/services/agent/tools/read_l0.py`
- `backend/app/services/agent/tools/read_l1.py`
- `backend/app/services/agent/tools/read_l2.py`
- `backend/app/services/agent/tools/expand_entity.py`
- `backend/app/services/agent/tools/get_timeline.py`
- `backend/app/services/agent/tools/ask_user.py`
- `backend/app/services/agent/tools/report_findings.py`

**Steps:**
1. 逐一实现上述工具
2. 每个工具包含：
   - 输入验证（Pydantic）
   - 核心逻辑
   - 错误处理
3. 注册到 Tool Registry
4. 验证：手动调用每个工具，确认结果

### Task 5.3: reAct Loop 实现

**Files:**
- `backend/app/services/agent/loop.py`
- `backend/app/services/agent/prompt_builder.py`

**Steps:**
1. 实现 reAct loop：
   ```python
   async def agent_loop(user_query, session_id, kb_id):
       messages = build_system_prompt() + load_history()
       messages.append({"role": "user", "content": user_query})
       
       for _ in range(max_iterations):
           response = await call_model(messages, tools=get_tool_definitions())
           
           if response.tool_calls:
               for tc in response.tool_calls:
                   result = await execute_tool(tc)
                   messages.append(tool_result_message(tc, result))
                   yield ToolCallEvent(tc.name, tc.input, result)
               continue
           else:
               yield FinalAnswer(response.content)
               break
   ```
2. 实现渐进式披露的 system prompt
3. 实现流式输出（WebSocket SSE）
4. 实现对话历史持久化
5. 验证：端到端测试会话，确认多轮 tool-use 循环

**Skills:** `skill-creator` (工具系统设计), `systematic-debugging` (调试 Agent loop)

---

## Phase 6: 前端核心

**目标:** 知识库管理 + 图谱可视化 + 对话界面

### Task 6.1: 基础设施

**Files:**
- `frontend/src/api/client.ts` - HTTP 客户端
- `frontend/src/api/websocket.ts` - WebSocket 客户端
- `frontend/src/store/app.ts` - 全局状态 (Zustand)

**Steps:**
1. 实现 HTTP 客户端（fetch wrapper）
2. 实现 WebSocket 客户端（流式消息接收）
3. 创建 Zustand store（知识库、对话、图谱、设置）
4. 验证：连接后端，获取健康检查

### Task 6.2: 主题系统

**Files:**
- `frontend/src/components/theme/ThemeToggle.tsx`
- `frontend/src/index.css` - Tailwind 主题变量

**Steps:**
1. 使用 `frontend-design` skill 设计暗色/明亮双主题方案：
   
   **明亮主题（默认）："现代档案室"风格**
   - 背景：暖米色 `#faf7f0`，模拟纸质卷宗质感
   - 卡片：纯白 `#ffffff` + 柔和阴影
   - 导航栏：深海军蓝 `#1e293b` 渐变，底部金色细线点缀
   - 强调色：暖金色 `#b8860b`（而非泛用的靛蓝）
   - 字体：`Noto Serif SC`（正文，衬线档案感）+ `Noto Sans SC`（导航/标签）
   - 质感：轻微噪点纹理 + 细边框（1px）模拟档案纸边缘
   
   **暗色主题：深蓝灰档案室**
   - 背景：深蓝灰 `#0f172a`，保留专业感
   - 卡片：深蓝灰 `#1e293b`
   - 导航栏：更深的 `#0c1220`
   - 强调色：暖金色 `#d4a017`
   - 字体：同明亮主题
   - 质感：保留阴影和边框，增加微妙光泽感
   
   **关键原则**：
   - 避免 AI 同质化审美（不用 Inter/Roboto/Purple 渐变）
   - L0/L1 层级标签：渐变胶囊 + 微光效，比截图更精致
   - 文件树：带缩进线的树形结构，hover 有精致过渡
   - 微交互：展开折叠动画、选中态过渡、hover 微光
2. 配置 Tailwind CSS v4 主题变量
3. 实现主题切换组件
4. 持久化到 localStorage
5. 验证：切换主题，确认颜色正确

**Skills:** `frontend-design` (主题视觉设计), `theme-factory` (配色方案)

### Task 6.3: 侧边导航与路由

**Files:**
- `frontend/src/components/sidebar/Sidebar.tsx`
- `frontend/src/App.tsx` - 路由配置

**Steps:**
1. 使用 `frontend-design` skill 设计侧边导航：
   - 独特的图标 + 文字组合，避免通用的 Material Icons 风格
   - 悬停状态有精致的微交互效果
   - 当前选中页面有清晰的视觉指示器
2. 配置 React Router
3. 响应式布局（移动端隐藏侧边栏）
4. 验证：页面切换正常

**Skills:** `frontend-design` (导航视觉设计)

### Task 6.4: 知识库管理页面

**Files:**
- `frontend/src/components/knowledge-base/KnowledgeBaseList.tsx`
- `frontend/src/components/knowledge-base/KnowledgeBaseCard.tsx`
- `frontend/src/components/knowledge-base/CreateKnowledgeBase.tsx`

**Steps:**
1. 使用 `frontend-design` skill 设计知识库卡片：
   - 卡片有层次感和视觉深度（阴影、边框、hover 效果）
   - 预编译状态用独特的视觉指示器（非通用绿色圆点）
   - 卡片布局有呼吸感，避免拥挤
2. 新建知识库表单
3. 删除知识库（带确认对话框）
4. 验证：CRUD 操作正常

**Skills:** `frontend-design` (卡片视觉设计)

### Task 6.5: 卷宗上传页面

**Files:**
- `frontend/src/components/upload/FileUpload.tsx`
- `frontend/src/components/upload/UploadProgress.tsx`

**Steps:**
1. 使用 `frontend-design` skill 设计上传区域：
   - 独特的拖拽上传区域，有创意的视觉引导
   - 进度条设计精致，有层次感（非原生 `<progress>` 样式）
   - 文件状态用独特的图标和颜色区分
2. 多文件上传
3. 实时进度条（WebSocket 推送解析状态）
4. 上传完成显示文件列表
5. 触发预编译（后台任务）
6. 验证：上传 PDF/DOCX/XLSX，确认解析和预编译

**Skills:** `frontend-design` (上传区域视觉设计)

### Task 6.6: 知识图谱页面

**Files:**
- `frontend/src/components/graph/GraphView.tsx`
- `frontend/src/components/graph/GraphFilterPanel.tsx`
- `frontend/src/components/graph/GraphNodeDetail.tsx`

**Steps:**
1. 使用 `frontend-design` skill 设计图谱可视化界面：
   - 力导向图节点有独特的视觉风格（非默认圆形）
   - 边的样式根据关系类型区分
   - 悬停和点击有精致的交互动画
   - 过滤面板与主区域有清晰的视觉层次
2. 集成 sigma.js 或 Recharts ForceGraph
3. 节点交互：拖拽、缩放、悬停显示详情、点击高亮
4. 左侧过滤面板：按实体类型/时间范围筛选
5. 点击节点 → 右侧面板显示实体详情
6. Louvain 社区检测着色
7. 验证：加载测试图谱，确认交互正常

**Skills:** `frontend-design` (图谱视觉设计)

### Task 6.7: 对话分析页面

**Files:**
- `frontend/src/components/chat/ChatView.tsx`
- `frontend/src/components/chat/MessageList.tsx`
- `frontend/src/components/chat/ToolCallPanel.tsx`
- `frontend/src/components/chat/MessageInput.tsx`
- `frontend/src/components/chat/SessionList.tsx`

**Steps:**
1. 使用 `frontend-design` skill 设计对话界面：
   - 消息气泡有独特的设计风格（非通用聊天 UI）
   - 工具调用过程有精致的展开/折叠动画
   - Agent 思考过程用独特的视觉样式区分（如代码块风格）
   - 引用溯源面板有层次感
   - 输入框设计精致，发送按钮有创意交互
2. 对话消息列表（用户/Agent 气泡）
3. Agent 工具调用过程可视化（折叠/展开）
4. Agent 思考过程显示（折叠/展开）
5. 引用溯源面板（点击引用跳转到原文）
6. 底部输入框 + 发送按钮
7. 右侧会话列表
8. 流式输出渲染
9. 验证：创建会话，提问，确认 Agent 回复和工具调用显示

**Skills:** `frontend-design` (对话界面视觉设计), `frontend-testing-best-practices` (E2E 测试)

---

## Phase 6.5: 前后端联调（每完成一个前端模块立即验证）

**核心原则：** 每完成一个前端组件，**立即**与后端真实 API 联调验证，确保前端打开就能正常工作，避免积累到最后的"开屏即报错"问题。

### Task 6.5.1: 基础设施联调

**时机：** Task 6.1 (API 客户端 + WebSocket + Store) 完成后

**验证清单：**
- [ ] 前端 HTTP Client 连接后端 `/api/health`，确认响应正常
- [ ] 前端 WebSocket 连接后端，确保持续连接不断开
- [ ] Zustand store 正确同步后端返回的数据
- [ ] 前端 Vite proxy 配置正确（开发环境），生产环境 baseURL 可配置
- [ ] 后端 CORS 配置允许前端请求
- [ ] 网络错误时前端显示正确的错误提示（Toast）

**常见问题预防：**
- 确认后端 CORS 配置包含 `http://localhost:5173`（Vite 默认端口）
- 确认 WebSocket 协议正确（`ws://` vs `wss://`）
- 确认 API 路径前后一致（如 `/api/v1/` vs `/api/`）

### Task 6.5.2: 知识库管理页面前端联调

**时机：** Task 6.4 完成后

**验证清单：**
- [ ] 页面加载时调用 `GET /api/knowledge-bases`，正确显示知识库列表
- [ ] 创建知识库表单提交调用 `POST /api/knowledge-bases`，成功后刷新列表
- [ ] 删除知识库调用 `DELETE /api/knowledge-bases/{id}`，确认后删除
- [ ] 加载状态显示骨架屏/Spinner
- [ ] 空状态显示"暂无知识库"提示
- [ ] API 错误时显示 Toast 通知
- [ ] 页面首次打开即无报错，UI 渲染正常

### Task 6.5.3: 卷宗上传页面前端联调

**时机：** Task 6.5 完成后

**验证清单：**
- [ ] 拖拽上传区域能正确接收文件
- [ ] 文件上传调用 `POST /api/knowledge-bases/{id}/documents`，返回正确
- [ ] 上传进度条实时更新（通过 WebSocket 推送）
- [ ] 上传完成后显示文件列表，状态正确
- [ ] 触发预编译后，状态实时更新（等待中 → 解析中 → 编译中 → 完成）
- [ ] 预编译失败时显示错误信息
- [ ] 测试上传 PDF/DOCX/XLSX/图片，确认解析结果正确显示

### Task 6.5.4: 知识图谱页面前端联调

**时机：** Task 6.6 完成后

**验证清单：**
- [ ] 图谱数据加载 `GET /api/knowledge-bases/{id}/graph` 成功
- [ ] 力导向图正确渲染节点和边
- [ ] 节点拖拽、缩放、悬停交互正常
- [ ] 点击节点 → 右侧面板显示实体详情（调用 `GET /api/entities/{id}`）
- [ ] 过滤面板按实体类型筛选生效
- [ ] 时间范围过滤生效
- [ ] Louvain 社区检测颜色区分正常
- [ ] 无图谱数据时显示空状态提示
- [ ] 大数据量图谱渲染性能可接受（1000+ 节点）

### Task 6.5.5: 对话分析页面前端联调

**时机：** Task 6.7 完成后

**验证清单：**
- [ ] 创建新会话调用 `POST /api/sessions`，成功创建
- [ ] 发送消息调用 `POST /api/sessions/{id}/messages`，用户消息正确显示
- [ ] Agent 流式输出实时渲染（SSE/WebSocket）
- [ ] Agent 工具调用过程可视化（展开/折叠）
- [ ] 工具调用的输入和输出正确显示
- [ ] Agent 思考过程显示（展开/折叠）
- [ ] 引用溯源面板显示引用来源，点击可跳转到原文
- [ ] `ask_user` 交互：Agent 提问 → 用户回答 → 继续分析
- [ ] 多轮对话历史记录正确加载
- [ ] 会话列表正确显示和切换
- [ ] 对话过程中断网 → 重连后恢复

### Task 6.5.6: 主题切换联调

**时机：** Task 6.2 完成后

**验证清单：**
- [ ] 暗色主题切换正常，所有组件颜色适配
- [ ] 明亮主题切换正常，所有组件颜色适配
- [ ] 主题偏好持久化（localStorage），刷新后保持
- [ ] 系统主题偏好检测（prefers-color-scheme）
- [ ] 图谱节点颜色在两种主题下都清晰可见
- [ ] 代码块、引用等在两种主题下可读

**Skills:** `frontend-testing-best-practices` (组件测试 + E2E 测试), `systematic-debugging` (调试前后端交互问题)

---

## Phase 7: 系统设置与打磨

**目标:** 模型配置 UI + 主题切换 + 端到端全流程联调 + 打磨

### Task 7.1: 系统设置页面

**Files:**
- `frontend/src/components/settings/SettingsView.tsx`
- `frontend/src/components/settings/ModelConfigForm.tsx`

**Steps:**
1. 使用 `frontend-design` skill 设计设置页面：
   - 设置表单有精致的视觉风格（非泛用表单组件）
   - 模型配置卡片有层次感
   - 测试连接按钮有精致的交互反馈
2. 模型配置表单（main/embedding/vlm 三角色）
3. 每个角色：base_url、model_name、api_key
4. 测试连接按钮（显示成功/失败）
5. 知识库管理（创建/删除）
6. 预编译触发按钮
7. 验证：配置模型，测试连接成功

### Task 7.2: 底部状态栏

**Files:**
- `frontend/src/components/layout/StatusBar.tsx`

**Steps:**
1. 显示当前知识库名称
2. 预编译状态（完成/进行中/失败）
3. LLM 模型名称
4. 验证：状态实时更新

### Task 7.3: 端到端全流程联调

**前提：** Phase 6.5 所有联调任务已完成

**验证清单：**
- [ ] 完整流程测试（真实数据）：
   - 创建知识库 → 上传卷宗（PDF/DOCX/XLSX/图片）→ 等待预编译 → 查看图谱 → 发起对话 → 获取分析结论
- [ ] 预编译缓存复用：同一文件上传到不同知识库，确认跳过编译
- [ ] 混合检索效果：同一查询对比向量检索、关键词检索、融合结果
- [ ] Agent 多轮 tool-use：一个复杂问题触发 3+ 次工具调用
- [ ] 渐进式披露：Agent 从 L0 → L1 → L2 逐步深入
- [ ] ask_user 交互：Agent 主动提问 → 用户回答 → 继续分析
- [ ] 并发场景：同时上传多个文件 + 发起对话，系统不崩溃
- [ ] 异常场景：API key 错误、LLM 超时、文件解析失败，前端正确提示
- [ ] 修复所有发现的 bug

### Task 7.4: 性能优化

**Steps:**
1. 预编译批量处理（减少 LLM 调用次数）
2. FAISS 索引加载优化
3. 前端虚拟列表（长消息列表优化）
4. WebSocket 连接心跳/重连
5. 后端连接池配置

### Task 7.5: 错误处理与用户体验

**Steps:**
1. 全局错误边界（React Error Boundary）
2. API 错误提示（Toast 通知）
3. 加载状态（骨架屏）
4. 空状态（无数据提示）
5. 预编译失败重试机制
6. Agent loop 超时处理

**Skills:** `frontend-testing-best-practices` (E2E 测试), `systematic-debugging` (调试问题), `verification-before-completion` (完成前验证)

---

## Skills 使用总览

| 阶段 | Skill | 使用场景 |
|------|-------|---------|
| Phase 0 | - | 项目初始化 |
| Phase 1 | `claude-api` | OpenAI SDK 使用、prompt caching |
| Phase 2 | `pdf`, `xlsx`, `docx` | 多格式文档解析 |
| Phase 3 | `writing-plans` | 复杂预编译管线设计 |
| Phase 4 | - | 存储与检索 |
| Phase 5 | `skill-creator` | 工具系统设计 |
| Phase 5 | `systematic-debugging` | 调试 Agent loop |
| Phase 6.2 | `frontend-design` | **暗色/明亮双主题视觉设计** |
| Phase 6.3 | `frontend-design` | **侧边导航视觉设计** |
| Phase 6.4 | `frontend-design` | **知识库卡片视觉设计** |
| Phase 6.5 | `frontend-design` | **上传区域视觉设计** |
| Phase 6.6 | `frontend-design` | **图谱可视化视觉设计** |
| Phase 6.7 | `frontend-design` | **对话界面视觉设计** |
| Phase 7.1 | `frontend-design` | **设置页面视觉设计** |
| Phase 6 | `theme-factory` | 主题配色方案参考 |
| Phase 6 | `web-artifacts-builder` | 复杂前端组件代码生成 |
| Phase 6.5 | `frontend-testing-best-practices` | **前后端联调测试（每个模块完成后立即联调）** |
| Phase 6.5 | `systematic-debugging` | **调试前后端交互问题** |
| Phase 7 | `frontend-testing-best-practices` | 端到端全流程测试 |
| Phase 7 | `systematic-debugging` | 调试端到端问题 |
| Phase 7 | `verification-before-completion` | 完成前验证 |
| 全程 | `simplify` | 代码审查，去冗余 |

---

## 开发顺序建议

按照依赖关系，推荐以下开发顺序：

1. **Phase 0** → 骨架就绪
2. **Phase 1** → 模型配置 + LLM 调用层（后续所有模块依赖）
3. **Phase 2** → 文件解析管线（预编译的前置条件）
4. **Phase 3** → 预编译引擎（依赖 Phase 1 + 2）
5. **Phase 4** → 存储与检索（依赖 Phase 3 的数据结构）
6. **Phase 5** → Agent 问答引擎（依赖 Phase 4 的检索能力）
7. **Phase 6** → 前端核心（可与 Phase 1-5 并行开发，使用 Mock 数据）
8. **Phase 6.5** → 前后端联调（**每完成一个前端模块立即联调，不积压**）
9. **Phase 7** → 系统设置 + 端到端全流程联调 + 打磨

**并行开发建议：**
- 后端开发者负责 Phase 1-5
- 前端开发者在 Phase 0 完成后即可开始 Phase 6，使用 Mock API
- **每个前端模块完成后立即进入 Phase 6.5 联调，不允许积累**
- Phase 7 由两人协作完成

**联调强制规则：**
- 每个前端 Task 完成后，必须立即执行对应的 Phase 6.5 联调验证
- 联调中发现的 bug 必须当场修复，不进入下一个 Task
- 后端 API 变更时，必须同步更新前端对应组件并重新联调
