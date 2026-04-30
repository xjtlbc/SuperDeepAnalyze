# 文档跨KB去重 + 文档详情页 Design Spec

> **日期:** 2026-04-23
> **参考:** `D:\lbc\LLMwiki\DeepAnalyze\src\server\routes\documents.ts`

---

## 一、上传时跨 KB 去重

### 问题
同名同内容文件（SHA256 相同）在不同 KB 中各自触发完整编译，浪费 LLM 调用成本。

### 已有基础设施
- `CacheManager` 类 (`backend/app/services/compilation/cache_manager.py`) — 完整实现但未调用
- `precompile_cache` 表 — schema 已存在，key 为 `file_hash`
- `documents.file_hash` 列 — 上传时已计算 SHA256

### 方案
在 `upload_document` endpoint 中，保存文件后、解析前：
1. 查询 `SELECT kb_id, id FROM documents WHERE file_hash = ?`
2. 如果命中，检查源文档目录是否存在 `l1_summaries.json`（编译完成标志）
3. 如果已编译：
   - 生成新的 `doc_id`
   - 复制源文档目录到 `{KB_DIR}/{kb_id}/documents/{doc_id}/`
   - 复制 FAISS 索引到 `{FAISS_DIR}/{kb_id}/{doc_id}/`
   - 重建 FTS5 条目（从已有 chunk 文件读取内容写入 `fts_content` 表）
   - 写入 `documents` 表：`parse_status = completed`
   - 更新 KB `compile_status = completed`
   - 返回结果（标记 `duplicated_from: source_doc_id`）
4. 如果未编译（源文档不存在或未完成）：正常走解析→分块→L2 编译流程

### 修改文件
- `backend/app/api/documents.py` — `upload_document` 增加去重检查（约 +30 行）
- `backend/app/services/compilation/cache_manager.py` — 补充 `reuse_compiled_doc` 方法

---

## 二、文档详情独立页面

### 参考
DeepAnalyze 的 `DocumentDetailView.tsx` + `ChunkedL2Viewer.tsx` 实现了一个三 Tab（L0/L1/L2）页面：
- L1：直接渲染 wiki 摘要文本
- L2：通过 TOC + batch 加载章节，支持小说章节自动检测

### 我们项目的适配

我们的 L1/L2 数据结构与 DeepAnalyze 不同（我们用 JSON 数组 + 文件，不用 wiki pages），但核心交互模式相同。

#### 后端 API

**新增 endpoint：**

| Method | Route | 功能 |
|--------|-------|------|
| GET | `/api/documents/{doc_id}/detail?kb_id=...` | 获取文档详情概览：基本信息 + L1 统计 + L2 统计 |
| GET | `/api/documents/{doc_id}/l1-summaries?kb_id=...&offset=0&limit=50` | 分页获取 L1 摘要列表 |
| GET | `/api/documents/{doc_id}/l2-toc?kb_id=...&offset=0&limit=200` | 获取 L2 chunk 目录（含章节检测） |
| GET | `/api/documents/{doc_id}/l2-batch?kb_id=...&indices=0,1,2,...` | 批量获取 L2 chunk 内容（含重叠去重合并） |
| GET | `/api/documents/{doc_id}/l0-entities?kb_id=...` | 从 L1 entities_mentioned 反查 L0 实体信息 |

**复用已有 endpoint：**
- `GET /api/documents/{doc_id}` — 基本信息（已存在）
- `GET /api/documents/{doc_id}/chunks` — L2 chunk 列表（已存在，但需要优化）

**章节检测逻辑（适配 DeepAnalyze 模式）：**
在 `l2-toc` endpoint 中扫描 chunk 内容的前几行，检测中文小说章节标题：
```python
chapter_patterns = [
    r'^第[一二三四五六七八九十百千万\d]+\s*[章节回卷集篇幕]',
    r'^#\s*(第.+)$',
    r'^Chapter\s+\d+',
]
```

#### 前端页面

**路由：** `/knowledge-bases/:kbId/documents/:docId`

**页面结构：**

```
┌──────────────────────────────────────────────────────────────┐
│ ← 返回    1-28册）出版精校版.txt                                │
│           20.3 MB · TXT · 2026-04-21 · 编译完成                │
├──────────────────────────────────────────────────────────────┤
│ [L1 摘要 (23 条)]  [L2 全文 (17108 chunks)]  [L0 关联实体]    │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ L1 Tab: 同 DeepAnalyze DocumentDetailView 模式                │
│ 每批 L1 摘要为一个卡片，点击展开查看完整内容                     │
│                                                              │
│ L2 Tab: 左右分栏（参考 DeepAnalyze ChunkedL2Viewer）           │
│ ┌─────────────┬──────────────────────────────────────────┐   │
│ │ 章节列表     │ 正文内容                                   │   │
│ │ 共 17108 片  │                                          │   │
│ │ 47 个章节    │  ← 未选章节时显示：                        │   │
│ │             │    "点击左侧章节加载内容"                    │   │
│ │ ─ 第一卷 ─  │                                          │   │
│ │ 第一章 落魄山│  ← 选中后：                               │   │
│ │ 第二章 崔诚 │    ← 返回  / 第一章 落魄山                 │   │
│ │ 第三章 ...  │    ┌──────────────────────────────────┐   │   │
│ │             │    │ Markdown 渲染正文                   │   │   │
│ │ ─ 第二卷 ─  │    │ 滚动加载                             │   │   │
│ │ 第四章 ...  │    └──────────────────────────────────┘   │   │
│ │             │                                          │   │
│ │ 加载更多 ▼  │                                          │   │
│ └─────────────┴──────────────────────────────────────────┘   │
│                                                              │
│ L0 Tab: 展示本文涉及的实体列表                                  │
│ 从 L1 entities_mentioned 反查 L0 entities.json                 │
│ 列表：实体名称 | 类型 | 属性                                    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**L2 交互细节：**
- 左侧章节列表：首次加载时扫描前 200 个 chunk 检测章节标题（后端 `l2-toc` endpoint）
- 后端章节检测复用 DeepAnalyze 的 regex patterns，同时支持卷/回/章/节等标记
- 无章节标记的文档：按 100 chunks 一组分组显示
- 右侧正文：点击章节后调用 `l2-batch` 获取该章节范围内的所有 chunks，服务端合并去重（去除 overlap），返回合并后的 Markdown 文本
- chunk 重叠处理：与 DeepAnalyze 相同，检测后一个 chunk 的前缀是否匹配前一个 chunk 的后缀（最长 500 字符），去重后合并

#### 入口

1. **KB 详情页面 Documents Tab** — 每行右侧增加"详情"按钮（📋 图标）
2. **KB 侧边栏** — 增加一个"文档"Tab，点击后进入当前 KB 的文档列表页（可选，先做入口 1）

#### 修改/新增文件
- `backend/app/api/documents.py` — 新增 4 个 endpoint
- `frontend/src/components/pages/DocumentDetail.tsx` — 新建
- `frontend/src/App.tsx` — 添加路由
- `frontend/src/components/pages/KnowledgeBaseDetail.tsx` — DocumentsTab 增加详情按钮

---

## 三、实施顺序

### Phase 1: 跨 KB 去重（后端）
1. `cache_manager.py` — 补充 `reuse_compiled_doc` 方法
2. `documents.py` upload endpoint — 增加去重检查

### Phase 2: 文档详情后端 API
3. 新增 `/detail`、`/l1-summaries`、`/l2-toc`、`/l2-batch` endpoint

### Phase 3: 前端文档详情页
4. `DocumentDetail.tsx` 新建
5. `App.tsx` 路由
6. `KnowledgeBaseDetail.tsx` 入口

---

## 验证方法

1. 上传与 `lbctest_jl` 中相同的 txt 文件到另一个 KB，验证：
   - 文件秒传（不触发解析+编译）
   - 编译状态直接变为 `completed`
   - L1/L2/FAISS 数据已复制
2. 点击详情按钮，验证：
   - L1 摘要列表正常加载（折叠/展开）
   - L2 章节列表正常加载（有章节标记时按章节分组）
   - 点击章节后正文正常渲染
   - 17000+ chunks 的文档不卡顿
