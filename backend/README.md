# 后端（FastAPI + LangChain / LangGraph）

## 快速开始

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # Windows: copy .env.example .env
python run.py              # http://127.0.0.1:8000/docs
```

首次启动会自动建表、创建管理员（`admin / admin123456`）、创建默认模型（内置 `mock`，无需 API Key）、写入内置 Prompt。

## 目录说明

```
app/
├── main.py           应用入口：lifespan、CORS、请求上下文中间件、异常处理、路由挂载
├── api/              路由层（auth/chat/models/knowledge/documents/prompts/users/dashboard + deps）
├── core/             config（.env 配置）· security（密码/JWT/Key 加解密）· exceptions（错误码+处理器）
│                     logging（含脱敏过滤器）· middleware · response（统一响应）
├── db/               base（Base + PK/Timestamp Mixin）· session（async engine / AsyncSessionLocal / get_db）
├── models/           ORM 模型（users models conversations messages knowledge_bases documents
│                     document_chunks prompts usage_logs）
├── schemas/          Pydantic 出入参
├── repositories/     数据访问层（base + 各表仓储，含分页与统计查询）
├── services/         auth / user / model / knowledge / document / prompt / chat / rag / dashboard
├── llm/              factory（LLM Factory）· embeddings（Embedding Factory）· mock（本地离线模型）
├── rag/              loader · splitter · vector_store · retriever · pipeline · prompts
└── graph/            state · nodes · workflow（LangGraph）
alembic/              数据库迁移（env.py 从 .env 读取连接串）
scripts/smoke_test.py 端到端自检（59 项）
```

## 数据库

**当前 `.env` 已指向本机 MySQL 8.0：`root@127.0.0.1:3306/ai_chat`（utf8mb4），表结构已由 Alembic 建好。**

```env
DATABASE_URL=mysql+aiomysql://root:<你的MySQL密码>@127.0.0.1:3306/ai_chat?charset=utf8mb4
AUTO_CREATE_TABLES=false
```

```bash
alembic upgrade head      # 建表 / 升级（MySQL 环境统一用迁移管理表结构）
python run.py             # 启动；首次会自动写入管理员 / 默认模型 / 内置 Prompt
```

启动时会调用 `check_schema_ready()` 做表结构自检：缺表则直接在日志里提示执行 `alembic upgrade head`，
不会静默 `create_all` 绕过迁移（SQLite / `AUTO_CREATE_TABLES=true` 时才自动建表）。

### 数据落库位置

| 数据 | 位置 |
| --- | --- |
| 会话与消息（对话记忆） | `conversations` / `messages`（含 `messages.sources` 引用 JSON、`conversations.summary` 摘要） |
| 知识库配置 | `knowledge_bases` |
| 文档元数据与解析状态 | `documents` |
| 文档正文（Chunk） | `document_chunks.content`（`MEDIUMTEXT`） |
| **向量数据** | `document_chunks.embedding`（`LONGBLOB`，float32；512 维 = 2048 字节/条） |
| 模型配置（含加密 Key） | `models` |
| Prompt 模板 | `prompts` |
| Token / 调用统计 | `usage_logs` |

> 只有「上传的原始文件」在磁盘 `storage/uploads/`（RAG 检索只需库里的分块 + 向量）。
> 验证向量：`SELECT id, embedding_dim, OCTET_LENGTH(embedding) FROM document_chunks;`

### 跨库注意事项（均已实测）

- SQLite：`NullPool` + 关闭 `pool_pre_ping`（避免文件锁与 aiosqlite 的 `MissingGreenlet`）；
- MySQL：`pool_pre_ping` + `pool_recycle`；
- 大文本列在 MySQL 下用 `MEDIUMTEXT`（`LongText` 变体）MySQL `TEXT` 只有 64KB，utf8mb4 中文易超限；
- 向量列 `LargeBinary(2**24)`  MySQL `LONGBLOB`、SQLite `BLOB`；
- `updated_at` 一律使用 Python 端 `onupdate`（服务端表达式会导致异步下 `MissingGreenlet`）；
- 统计查询全部显式 `GROUP BY`，兼容 MySQL 8 默认的 `ONLY_FULL_GROUP_BY`。

## 模型接入

在「模型管理」页面配置，或写入 `.env` 预置默认模型。支持的供应商：

| provider | 协议 | 默认 Base URL | 备注 |
| --- | --- | --- | --- |
| `openai` | OpenAI | `https://api.openai.com/v1` | |
| `deepseek` | OpenAI 兼容 | `https://api.deepseek.com/v1` | |
| `qwen` | OpenAI 兼容 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 通义千问 |
| `ollama` | OpenAI 兼容 | `http://127.0.0.1:11434/v1` | 本地模型，无需 Key |
| `moonshot` / `zhipu` / `siliconflow` | OpenAI 兼容 | 见 `/api/models/providers` | |
| `gemini` | Google 原生 SDK | — | 需要 `langchain-google-genai` |
| `claude` | Anthropic 原生 SDK | — | 需要 `langchain-anthropic` |
| `custom` | OpenAI 兼容 | 必填 | 任意网关 / 私有部署 |
| `mock` | 内置 | — | 离线可用，返回结构化 Markdown 并引用检索内容 |

新增供应商：在 `app/llm/factory.py` 的 `_BUILDERS` 中注册构造函数，并在 `Provider` 中加常量与默认地址，
聊天 / RAG / Agent 代码无需任何修改。

## 后台任务与并发

- 文档向量化走 `asyncio.create_task`（`document_service.schedule_ingestion`），进度实时写回数据库；
- 服务启动时会自动恢复上次中断的文档任务（`recover_unfinished`）；
- 并发入库受信号量限制（`rag/pipeline.py::_ingest_lock`，默认 2）；
- 如需分布式部署，把该函数替换为 Celery 任务即可，接口层无需改动。

## 自检

```bash
python scripts/smoke_test.py                  # 需要后端已启动
python scripts/smoke_test.py --wait-seconds 120
```

覆盖登录、模型、非流式与流式聊天、会话消息、知识库、上传 PDF/CSV/TXT、检索、RAG 引用、
Prompt、Dashboard、权限、停止生成、重新生成、清空会话等 59 项断言。

## 常见问题

| 现象 | 原因 / 处理 |
| --- | --- |
| `MissingGreenlet` | 在异步上下文里访问了已过期的 ORM 属性或做了同步懒加载。本项目 `updated_at` 已改为 Python 端 `onupdate`；新增模型时注意关系加载策略（`lazy="noload"` / `selectin`） |
| `alembic` 报编码错误 | `alembic.ini` 必须是 ASCII（Alembic 用系统 locale 读取） |
| 启动报「数据库表结构不完整」 | 未执行迁移：`cd backend && alembic upgrade head`（或临时把 `AUTO_CREATE_TABLES=true`） |
| MySQL 里看不到向量内容 | 向量是二进制 `LONGBLOB`，客户端显示为 `<BLOB>` 属正常；用 `OCTET_LENGTH(embedding)` 查看长度 |
| 模型调用 401 / 超时 | 用「模型管理 → 测试连接」定位：鉴权失败 / 网络不通 / Base URL 缺 `/v1` |
| 检索结果为空 | 降低相似度阈值、提高 Top K，或更换语义 Embedding 后重新向量化 |
| 向量维度不一致 | 更换 Embedding 模型后需「重新向量化」；系统会跳过维度不匹配的旧向量并记录告警 |
