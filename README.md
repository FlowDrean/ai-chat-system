# AI 问答聊天助手平台（AI Chat Assistant）

一个可长期扩展的通用 AI 应用平台：**多模型配置 + AI 对话（SSE 真流式）+ RAG 知识库 + 文档解析与向量检索 + Prompt 管理 + LangChain / LangGraph 工作流 + 用户与权限 + 运营统计**。

> 本项目由 `开发文档.md` 的完整需求实现而来，前后端分离，可直接运行。

```
┌──────────────────────────────────────────────────────────────┐
│  Vue 3 + Vite + TS + Ant Design Vue + Pinia + Axios          │
│  登录 │ 首页 │ AI 聊天 │ 模型 │ 知识库 │ 文档 │ Prompt │ 后台 │
└───────────────────────────┬──────────────────────────────────┘
                            │ HTTP / SSE
┌───────────────────────────▼──────────────────────────────────┐
│  FastAPI（异步）                                              │
│  API Router → Service → Repository → SQLAlchemy 2.x Async    │
│  LLM / Embedding Factory · RAG Pipeline · LangGraph 工作流    │
└──────────┬──────────────────────────────┬────────────────────┘
           │                              │
      MySQL 8.x / SQLite            向量库（内置 SQL 实现 / Chroma 可插拔）
```

---

## 一、已实现功能

### 1. AI 聊天

- 新建 / 删除 / 重命名 / 收藏 / 归档 / 搜索会话，左侧按「今天 / 昨天 / 近 7 天 / 更早」分组
- 多轮上下文（按条数 + 字符预算裁剪，超长时后台自动生成历史摘要）
- **SSE 真流式输出**（逐字返回，非「等 5 秒一次性出现」）
- **停止生成**（客户端中断 → 已生成内容仍以 `stopped` 状态落库）
- **重新生成**、**编辑用户消息并重新提问**、复制回答、点赞 / 点踩、清空当前对话
- Markdown 渲染（标题 / 列表 / 表格 / 引用 / 代码块）+ highlight.js 代码高亮 + 一键复制
- 会话级模型参数：Temperature / Top P / Max Tokens / Frequency Penalty / Presence Penalty / Streaming
- 会话级切换模型、切换知识库、应用 Prompt
- 显示耗时与 Token 统计；错误态区分「模型调用失败 / 网络失败」并提供重新生成

### 2. 模型管理

- 供应商：OpenAI、DeepSeek、通义千问、Ollama、Gemini、Claude、Moonshot、智谱、SiliconFlow、任意 OpenAI Compatible、内置 Mock（离线可用）
- 新增 / 编辑 / 删除 / 复制 / 启用禁用 / 设为默认 / **测试连接**
- 统一模型配置结构，**业务代码不出现任何厂商 SDK 调用**（全部经 LLM Factory）
- API Key：前端密码框输入 → 后端 Fernet **加密存储** → 接口只返回脱敏值（`sk-a********1234`）→ 日志自动脱敏

### 3. RAG 知识库

- 知识库 CRUD，Embedding / Chunk / Retriever 参数全部可配（含 **测试检索** 与 **Embedding 校验**）
- 文档：PDF / DOCX / TXT / Markdown / CSV / XLSX（可扩展 PPTX / HTML / URL / OCR）
- 上传 → 解析 → 清洗 → 切分 → Embedding → 写入向量库，**进度实时回写**（等待处理 / 处理中 xx% / 完成 / 失败）
- 支持重新向量化、分块预览、重复文件去重（内容 SHA256）
- 检索链路：Query → Embedding → 向量检索 →（可选轻量 ReRank：向量相似度 + 词法重合度）→ 上下文
- **引用来源**：回答下方展示来源卡片（文件名 / 页码 / 相似度），点击查看 Chunk 内容与 Metadata
- 检索失败自动降级为普通对话，不会让整个聊天请求失败

### 4. LangChain / LangGraph

- LLM：`create_llm(runtime_config)` 统一工厂；Embedding：`create_embeddings(config)` 统一工厂
- RAG：Document Loader / Text Splitter / Retriever / 向量库全部模块化，向量库可替换（内置 SQL 实现，可切 Chroma）
- LangGraph 工作流（独立于 API 层）：

```
START → route（是否使用知识库） ─┬─ rag    → retrieve → generate ─┐
                                └─ direct →            generate ─┴→ finalize → END
```

- 未使用任何已废弃 API（无 `ConversationChain` / `ConversationBufferMemory`），全部为 Runnable / Message / Retriever / LangGraph 现代架构

### 5. Prompt 管理

- Prompt CRUD、变量自动提取（`{{question}}` / `{{context}}` / `{{user_name}}`）、变量渲染预览、复制为我的 Prompt
- 内置 5 个模板（专业程序员助手、RAG 知识库问答、简洁问答、Vue3 专家、SQL 助手），内置模板不可修改删除

### 6. 技能（Skills）

让模型具备「动手能力」：把外部能力配置成技能，聊天时勾选，模型会在需要时自动调用（Function Calling）。

- **内置技能类型**（无需写代码，管理后台可视化配置）：

  | 类型 | 说明 | 需要配置 |
  | --- | --- | --- |
  | 计算器 | 安全 AST 求值（sqrt/log/sin/幂/百分比），**不使用 eval** | 无 |
  | 当前时间 | 当前日期时间与星期（时区可配） | 无 |
  | 网页抓取 | 抓取 URL 正文；默认禁止访问内网 / 本地地址（SSRF 防护，可配置放开） | 无 |
  | 联网搜索 | Tavily 兼容搜索接口 | API Key |
  | 自定义 HTTP 接口 | 把任意 HTTP API / Webhook 包装成技能，**入参 schema 自定义**，支持按路径取响应字段 | URL + 入参定义 |

- **管理后台「技能管理」**：列表（启用状态 / 是否已配置 / 调用次数）、动态配置表单（由后端 `SkillSpec` 驱动，新增技能类型无需改前端）、**试运行**（未保存的配置也能试）、新建 / 编辑 / 启停 / 删除
- **聊天中**：输入框工具栏  勾选技能（未完成配置的不可选并标注「未配置」）；回答下方展示技能调用记录（技能名 / 入参 / 结果 / 耗时，可展开）
- **会话级记忆**：勾选的技能保存在会话上，刷新或下次进入该会话自动恢复
- **安全**：技能配置里的 API Key 等敏感项加密存储、接口只返回脱敏值，更新时留空即保持原值；计算器用 AST 白名单而非 `eval`
- **兼容性**：由模型 Function Calling 能力驱动（DeepSeek / OpenAI / 通义 等均支持）；若当前模型不支持，会自动降级为普通对话并提示

> 联网搜索默认是「待配置」状态：到「技能管理  联网搜索」填入 Tavily API Key 并启用即可；
> Tavily 兼容的自建 / 代理网关可通过修改「搜索接口地址」接入。

### 7. MCP 管理（Model Context Protocol）

接入标准 MCP 服务，把它们暴露的工具直接交给 AI 调用（与「技能」共用同一套 tool-calling 链路）。

- **三种传输方式**：
  | 传输 | 用途 | 关键配置 |
  | --- | --- | --- |
  | `stdio` | 本地进程（`npx @modelcontextprotocol/server-filesystem`、自研脚本） | 命令 / 参数 / 环境变量 / 工作目录 |
  | `sse` | 远程 SSE 端点（MCP 旧版 HTTP 传输） | 服务地址 / 请求头 |
  | `http` | 远程 Streamable HTTP（MCP 新版传输，推荐） | 服务地址 / 请求头 |
- **管理后台「MCP 管理」**：接入 / 编辑 / 启用禁用 / 删除；**一键测试连接**（拉取 `tools/list` 并缓存）；查看工具清单与入参 JSON Schema；**调试调用**任意工具（填参数直接执行看返回）
- **工具发现与缓存**：连接时发现工具、把 JSON Schema 缓存到本地；聊天时直接用缓存构建工具，不必每次握手；服务端工具变更后点「测试连接」即可刷新
- **聊天中**：输入框工具栏  勾选 MCP 服务；回答下方调用记录会标注 **MCP** 徽标，并显示「服务名  工具名 / 入参 / 结果 / 耗时」
- **会话级记忆**：勾选的服务保存在会话上（`conversations.mcp_server_ids`），刷新或下次进入自动恢复
- **配置导入 / 导出**（兼容 Claude Desktop / Cursor / VS Code）：
  在「MCP 管理  导入配置」里**直接粘贴**或**上传** `claude_desktop_config.json`，一键批量接入：

  ```json
  {
    "mcpServers": {
      "amap-maps": {
        "command": "npx",
        "args": ["-y", "@amap/amap-maps-mcp-server"],
        "env": { "AMAP_MAPS_API_KEY": "你的高德 Key" }
      }
    }
  }
  ```

  - 识别多种写法：`mcpServers` / `servers` / `{"mcp": {"servers": }}` / 单个服务对象 / 服务数组
  - 自动判定传输方式：有 `command`  `stdio`；有 `url`  按 `type`/`transport` 判定（`sse` / `http`，缺省为 Streamable HTTP）
  - 名称冲突策略：**跳过 / 自动重命名 / 覆盖**；导入时可**自动测试连接并发现工具**（并发执行，首次 `npx` 需要下载依赖会稍慢）
  - 导入前本地预解析预览（服务名 / 传输方式 / 目标命令 / 是否含密钥），导入后逐个展示结果与发现的工具
  - **导出**：一键生成 mcpServers JSON（默认**密钥脱敏**，可切换包含明文用于迁移）；同时支持 `disabled: true` 映射为「禁用」
  - **Windows 兼容**：`npx` / `npm` / `pnpm` / `yarn` / `uvx` 等 `.cmd` shim 会自动改写为 `cmd /c ` 执行，
    所以从别人的 `mcpServers` 配置直接粘过来就能跑


- **安全**：`env` / `headers` 中的敏感值（KEY / TOKEN / SECRET / PASSWORD / Authorization）**加密存储 + 出参脱敏**，编辑时留空表示不修改；连接失败只返回可读原因
- **兼容性**：`mcp` SDK 1.x 与 2.x 的差异收敛在 `app/mcp/client.py`；模型不支持 Function Calling 时自动降级为普通对话

> 示例：接入本地文件系统服务  传输选 `stdio`，
> 命令 `npx`，参数 `-y @modelcontextprotocol/server-filesystem D:\资料`，保存后点「测试连接」即可看到工具出现在聊天页的  选择器里。

### 8. 界面规范

- **界面不使用 emoji**：图标统一使用 Ant Design Vue 图标（空状态、状态提示、操作按钮等），
  并在 E2E 中逐页扫描 DOM 文本作为回归守卫
- 登录页不展示默认账号 / 密码等敏感提示（初始账号只写在本文档「快速开始」里）
- 色彩、字体、圆角、留白遵循 `frontend/README.md` 的「UI 规范」

### 9. 后台与系统

- Dashboard：今日对话 / 消息 / Token / 模型调用 / 检索片段、累计数据、AI 调用趋势、模型使用比例、知识库检索次数、最近会话（ECharts）
- 用户管理：列表 / 新建 / 编辑 / 角色（普通用户、管理员）/ 状态 / 重置密码 / 删除
- 权限：普通用户只能访问自己的会话、知识库、文档、Prompt；模型管理与用户管理仅管理员
- 统一响应 `{code, message, data}`、统一异常处理（业务错误码 + 不返回 traceback）、请求 ID 贯穿日志、日志脱敏
- 上传安全：类型白名单 + 大小限制 + 文件名清洗 + 随机存储名；SQL 全部走 ORM；Markdown 经 DOMPurify 清洗（防 XSS）
- 响应式：桌面 / 平板 / 移动端（聊天页移动端为抽屉式会话列表）

---

## 二、快速开始

### 0. 环境要求

| 依赖 | 版本 |
| --- | --- |
| Python | 3.11+（已在 3.13 验证） |
| Node.js | 18+（已在 22 验证） |
| 数据库 | **本机 MySQL 8.0.41（已配置：`root@127.0.0.1:3306/ai_chat`）**，也可切回 SQLite |

### 1. 启动后端

```bash
cd backend

# 1) 创建虚拟环境并安装依赖
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt

# 2) 生成配置（含随机密钥）
cp .env.example .env          # Windows: copy .env.example .env

# 3) 启动（.env 已指向本机 MySQL，表结构已由 Alembic 建好）
python run.py                 # 或：uvicorn app.main:app --reload --port 8000
```

启动后：

- API 文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/health
- 首次启动会自动：建表 → 创建管理员 → 创建默认模型（内置 `mock`，**无需任何 API Key 即可完整演示**）→ 初始化内置 Prompt

> 默认管理员：`admin / admin123456`（可在 `.env` 中用 `DEFAULT_ADMIN_USERNAME` / `DEFAULT_ADMIN_PASSWORD` 修改，**生产环境请务必修改**）
>
> 首次启动会在 MySQL 里自动写入：管理员、默认模型（内置 `mock`）、5 个内置 Prompt；
> 库里已预置一个 **示例知识库（RAG / FastAPI 资料）**（3 个文档 / 5 个分块 / 5 条 512 维向量），
> 登录后到「知识库  示例知识库」或直接在聊天页选择它即可体验带引用的 RAG 回答。
> 数据库配置与各表存放内容见「三、数据库」。

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev            # http://127.0.0.1:5173
```

Vite 已配置 `/api` 代理到 `http://127.0.0.1:8000`，无需处理跨域。

### 3. 接入真实模型（可选）

方式一：登录后在「模型管理 → 新增模型」中配置；<br>
方式二：在 `backend/.env` 中预置：

```env
DEFAULT_PROVIDER=deepseek
DEFAULT_MODEL_NAME=deepseek-chat
DEFAULT_BASE_URL=https://api.deepseek.com/v1
DEFAULT_API_KEY=sk-xxxxxxxx
```

支持 Ollama（`http://127.0.0.1:11434/v1`）、通义（DashScope 兼容模式）、Gemini、Claude、任意 OpenAI 兼容网关。

---

## 三、数据库（当前已接入本机 MySQL）

> **当前 `backend/.env` 已指向本机 MySQL：`root@127.0.0.1:3306/ai_chat`（utf8mb4），
> 表结构已通过 Alembic 建好，并已初始化管理员、默认模型、内置 Prompt 与一个示例知识库。**

### 3.1 数据都落在哪（全部在 MySQL 的 `ai_chat` 库里）

| 你要的东西 | 落库位置 | 说明 |
| --- | --- | --- |
| **记忆**（会话历史） | `conversations` + `messages` | 多轮上下文；`messages.role/content` 保存完整对话，`conversations.summary` 保存超长上下文的历史摘要，`messages.sources`（JSON）保存该条回答的引用来源 |
| **知识库** | `knowledge_bases` | 名称 / 描述 / Embedding 配置 / Chunk 配置 / Top K / 相似度阈值 / ReRank 开关 |
| **文档元数据与解析结果** | `documents` | 文件名、类型、大小、SHA256、处理状态与进度、分块数、字符数、解析元数据 |
| **文档正文（切分后的 Chunk）** | `document_chunks.content` | 解析 → 清洗 → 切分后的全部文本，**RAG 回答只依赖它，不再依赖磁盘文件** |
| **向量数据库** | `document_chunks.embedding` | float32 二进制（512 维 = 2048 字节/条），列类型 `LONGBLOB`；检索时在内存中做余弦相似度 |
| 模型配置（含加密 API Key） | `models` | `api_key` 为 Fernet 密文，接口只返回脱敏值 |
| Prompt 模板 | `prompts` | 内置 5 条 + 你的自定义模板 |
| 技能配置 | `skills` | 技能类型 / 配置（敏感项加密）/ 启用状态 / 调用次数 |
| 会话启用技能 | `conversations.skill_ids` | 会话级技能选择 |
| 技能调用记录 | `messages.skills` | 每条回答调用了哪些技能 / MCP 工具、入参、结果、耗时 |
| MCP 服务配置 | `mcp_servers` | 传输方式 / 命令 / 地址（敏感值加密）/ 状态 / **工具清单缓存** |
| 会话启用 MCP | `conversations.mcp_server_ids` | 会话级 MCP 服务选择 |
| 调用与 Token 统计 | `usage_logs` | Dashboard 的对话数 / Token / 模型调用 / 检索次数都来自这里 |
| 迁移版本 | `alembic_version` | 当前 `e9c27de799d4`（Alembic 版本号） |

> 只有「上传的原始文件」保存在磁盘 `backend/storage/uploads/`。
> 这是刻意的设计：把几十 MB 的原始文件塞进数据库会让备份体积、`max_allowed_packet`、流式读取都变糟；
> 而 RAG 检索所需的一切（文本分块 + 向量 + 元数据）都已经在 MySQL 里。
> 如果你确实想连原始文件也一起存库，可以按 `docs/架构说明.md` 的「扩展点」加一个 `file_blob LONGBLOB` 列即可。

### 3.2 初始化步骤（新环境 / 换库时执行）

```bash
# 1) 建库（已执行过可跳过）
mysql -uroot -p<你的MySQL密码> -e "CREATE DATABASE IF NOT EXISTS ai_chat DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;"

# 2) 配置连接串（backend/.env）
DATABASE_URL=mysql+aiomysql://root:<你的MySQL密码>@127.0.0.1:3306/ai_chat?charset=utf8mb4
AUTO_CREATE_TABLES=false        # MySQL 环境用 Alembic 管理表结构

# 3) 建表（已执行过可跳过）
cd backend
alembic upgrade head

# 4) 启动（首次会自动写入管理员 / 默认模型 / 内置 Prompt）
python run.py
```

常用迁移命令：

```bash
alembic current                                # 查看当前版本
alembic revision --autogenerate -m "add xxx"   # 模型变更后生成迁移
alembic upgrade head                           # 应用迁移
alembic downgrade -1                           # 回滚一步
```

> `DATABASE_URL` 同时被「应用」与「Alembic」复用，无需在两处维护连接串。
> `AUTO_CREATE_TABLES=false` 时，应用启动会做一次表结构自检（`check_schema_ready`），
> 缺表会在日志里直接提示你去跑 `alembic upgrade head`，不会静默建表绕过迁移。

### 3.3 回到 SQLite（可选，零依赖演示）

```env
DATABASE_URL=sqlite+aiosqlite:///./data/app.db
AUTO_CREATE_TABLES=true
```

### 3.4 安全建议

生产环境 / 多人使用建议不要把 `root` 交给应用，改用最小权限账号：

```sql
CREATE USER 'ai_chat'@'127.0.0.1' IDENTIFIED BY '你的强密码';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES ON ai_chat.* TO 'ai_chat'@'127.0.0.1';
FLUSH PRIVILEGES;
```

```env
DATABASE_URL=mysql+aiomysql://ai_chat:你的强密码@127.0.0.1:3306/ai_chat?charset=utf8mb4
```

### 3.5 MySQL 相关的两个细节（已在本项目内处理）

1. **`STRICT_TRANS_TABLES` + `TEXT` 只有 64KB**：`messages.content` / `prompts.content` /
   `documents_chunks.content` 等大文本列在 MySQL 下统一映射为 `MEDIUMTEXT`（`LongText` 类型变体），
   避免 utf8mb4 下中文内容超过 64KB 直接报错。
2. **`ONLY_FULL_GROUP_BY`**：Dashboard 的按天聚合查询全部显式 `GROUP BY` 聚合列，已在 MySQL 8 默认 sql_mode 下验证通过。

向量列使用 `LONGBLOB`（`LargeBinary(2**24)` 在 MySQL 下映射为 `LONGBLOB`），
即使使用 8192 维 Embedding（32KB/条）也有充足余量。

---

## 四、验证与测试

项目自带三层自检脚本，均已通过。

### 1. 后端端到端自检（103 项）

```bash
cd backend
python scripts/smoke_test.py
```

覆盖：健康检查 → 登录 → 模型 CRUD / API Key 脱敏 → 非流式聊天 → **SSE 流式** → 会话与消息 → 知识库 → 上传 PDF/CSV/TXT → 解析与向量化 → 检索测试 → **RAG 问答 + 引用来源** → Prompt → Dashboard → 权限与异常 → 模型连接测试 → 技能管理 / 试运行 / MCP 接入与工具发现 / **Tool Calling** / 停止生成（中断落库） → 重新生成 → 清空会话 → 清理。

```
自检结果：通过 103 项，失败 0 项
```

### 2. 前端 E2E（Playwright，31 项）

```bash
cd frontend
npm run test:e2e        # 登录 → 流式聊天 → 停止生成 → 后台各页面 → 无控制台报错
```

```
前端 E2E 结果：通过 31 项，失败 0 项
```

### 3. RAG E2E（Playwright，9 项）

```bash
npm run test:e2e:rag    # 界面创建知识库 → 上传 PDF → 向量化 → 检索测试 → RAG 问答 → 引用详情
```

```
RAG E2E 结果：通过 9 项，失败 0 项
```

> E2E 默认复用系统已安装的 Edge / Chrome（无需下载浏览器内核）；可先分别启动后端与 `npm run dev`。
>
> 登录凭据可用环境变量覆盖（默认 `admin / admin123456`，改过密码请显式传入）：
> `$env:E2E_USERNAME='xxx'; $env:E2E_PASSWORD='xxx'; npm run test:e2e`

### 4. 技能 E2E（Playwright，18 项）

```bash
npm run test:e2e:skills   # 技能管理页  动态表单  试运行  新建自定义技能  聊天调用  会话记忆
```

```
技能 E2E 结果：通过 18 项，失败 0 项
```

### 5. MCP E2E（Playwright，21 项）

```bash
npm run test:e2e:mcp   # 接入 stdio 服务  连接测试/工具发现  聊天调用  导入/导出 mcpServers 配置
```

```
MCP E2E 结果：通过 21 项，失败 0 项
```

### 6. 侧边栏 / 移动端布局检查（Playwright，98 项）

```bash
npm run test:e2e:sidebar
```

用「包围盒 + `elementFromPoint` 命中测试」逐项验证侧边栏折叠 / 展开按钮的可见性与可点击性，
而不是靠肉眼判断：

- 展开态 / 折叠态：按钮**完全位于侧边栏矩形内**（早期版本超出 26px，被右侧聊天区盖住）
- 按钮尺寸  3232、水平居中、`scrollWidth <= clientWidth`（无横向溢出）
- 5 档桌面视口（1680 / 1440 / 1280 / 1100 / 1024）各校验一遍
- 窄屏（418 / 390）：顶部菜单按钮可打开会话抽屉、抽屉有关闭入口、浮动「新建聊天」不与输入区重叠
- 管理后台侧边栏折叠 / 展开，logo 不溢出

```
侧边栏 / 抽屉检查：通过 98 项，失败 0 项
```

### 7. 类型检查与构建

```bash
cd frontend
npm run type-check      # vue-tsc：0 error
npm run build           # 生产构建
```

---

## 五、目录结构

```
AI-Chat-System/
├── 开发文档.md                  # 需求文档（本项目实现依据）
├── README.md                    # 本文件
├── docs/
│   ├── 架构说明.md              # 模块划分 / 数据流 / 扩展点
│   └── API.md                   # 接口清单与 SSE 协议
│
├── backend/                     # FastAPI 后端
│   ├── app/
│   │   ├── main.py              # 应用入口（lifespan / 中间件 / 路由挂载）
│   │   ├── api/                 # 路由层：auth chat models knowledge documents prompts users dashboard
│   │   ├── core/                # config / security / exceptions / logging / middleware / response
│   │   ├── db/                  # SQLAlchemy 2.x async engine、Base、Mixin
│   │   ├── models/              # ORM：user model conversation message knowledge document prompt usage
│   │   ├── schemas/             # Pydantic 出入参（与前端 types 一一对应）
│   │   ├── repositories/        # 数据访问层
│   │   ├── services/            # 业务编排层（chat / rag / document / model / knowledge / prompt ...）
│   │   ├── llm/                 # LLM / Embedding 工厂 + mock 本地模型
│   │   ├── rag/                 # loader / splitter / vector_store / retriever / pipeline / prompts
│   │   └── graph/               # LangGraph：state / nodes / workflow
│   ├── alembic/                 # 数据库迁移
│   ├── scripts/smoke_test.py    # 后端端到端自检
│   ├── requirements.txt
│   ├── .env.example
│   └── run.py
│
└── frontend/                    # Vue 3 前端
    ├── src/
    │   ├── api/                 # axios 封装 + 各模块接口 + SSE 客户端
    │   ├── components/          # chat / knowledge / model / common 业务组件
    │   ├── layouts/             # ChatLayout / AdminLayout
    │   ├── pages/               # Login Home Chat Model Knowledge KnowledgeDetail Documents Prompt Users Settings Dashboard
    │   ├── stores/              # Pinia：user chat model knowledge settings
    │   ├── router/ utils/ types/ styles/
    │   ├── App.vue / main.ts
    ├── e2e/                     # Playwright 端到端测试
    └── vite.config.ts / tsconfig.json
```

---

## 六、配置说明（backend/.env）

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `DATABASE_URL` | 数据库连接串（MySQL / SQLite） | `mysql+aiomysql://root:<你的MySQL密码>@127.0.0.1:3306/ai_chat?charset=utf8mb4` |
| `AUTO_CREATE_TABLES` | 启动时自动 create_all（MySQL 环境建议 false，用 Alembic） | `false` |
| `SECRET_KEY` | JWT 签名密钥 | 需替换 |
| `API_KEY_ENCRYPTION_KEY` | 模型 Key 加密密钥（Fernet），留空由 SECRET_KEY 派生 | 空 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 登录有效期（分钟） | 10080 |
| `CORS_ORIGINS` | 允许的前端来源，逗号分隔 | `http://localhost:5173,...` |
| `MAX_UPLOAD_SIZE_MB` / `ALLOWED_EXTENSIONS` | 上传限制 | 50MB / 6 种类型 |
| `VECTOR_STORE` | `sql`（内置）或 `chroma` | `sql` |
| `DEFAULT_EMBEDDING_PROVIDER` / `_MODEL` | 默认 Embedding | `local` / `local-hash-512` |
| `DEFAULT_CHUNK_SIZE` / `_OVERLAP` / `TOP_K` / `SIMILARITY_THRESHOLD` | RAG 默认参数 | 800 / 120 / 4 / 0.2 |
| `MAX_CONTEXT_MESSAGES` / `MAX_CONTEXT_CHARS` | 上下文预算 | 20 / 24000 |
| `DEFAULT_PROVIDER` / `_MODEL_NAME` / `_BASE_URL` / `_API_KEY` | 首次启动创建的默认模型 | `mock` |
| `DEFAULT_ADMIN_USERNAME` / `_PASSWORD` | 首次启动创建的管理员 | `admin / admin123456` |
| `LOG_LEVEL` / `LOG_TO_FILE` | 日志 | INFO / true |

---

## 七、扩展指引

| 需求 | 做法 |
| --- | --- |
| 新增模型供应商 | 在 `app/llm/factory.py` 的 `_BUILDERS` 注册一个构造函数 + `Provider` 中加常量，业务代码零改动 |
| 新增 Embedding 供应商 | 在 `app/llm/embeddings.py` 的 `create_embeddings` 中加分支 + `PRESETS` 补预置 |
| 替换向量数据库 | 实现 `app/rag/vector_store.py::BaseVectorStore` 子类，并在工厂中按配置返回（Milvus / Qdrant / PGVector…） |
| 新增文档格式 | 在 `app/rag/loader.py` 的 `_LOADERS` 注册一个 `(Path) -> list[Document]` 函数 |
| 工作流增加节点（意图识别 / Tool Calling / Agent） | 在 `app/graph/nodes.py` 增加节点，`workflow.py` 中加边；状态字段加到 `ChatState` |
| 引入 Redis / Celery | 文档向量化目前用后台任务，`schedule_ingestion()` 可替换为 Celery 任务；JWT 黑名单可挂 Redis |

---

## 八、路线图

已预留但未实现：Web Search / 联网搜索、Agent + Function Calling、MCP、多模态与图片理解、OCR、语音输入输出、工作流可视化编排、企业级权限与团队空间、知识库共享、开放 API 平台。

---

## 九、常见问题

**Q：没有 API Key 能跑吗？**
可以。内置 `mock` 模型会返回结构化 Markdown 回答，并会引用检索到的知识库内容，用于完整演示链路；配置真实模型后把默认模型切过去即可。

**Q：内置 `local` Embedding 召回不准怎么办？（建议换成语义 Embedding）**
`local` 是 hashing 词法向量（512 维），只有关键词重合才召回，**不理解语义** 
例如问「检查点是怎么实现的」，可能匹配不到写「持久化 / checkpointer」的段落；文档量大时差距更明显。
换成语义 Embedding 只要三步：

1. **准备一个 Embedding Key**（任选其一）：
   - **SiliconFlow 硅基流动**：`BAAI/bge-m3`（1024 维，中文效果好、有免费额度） Base URL `https://api.siliconflow.cn/v1`
   - **通义千问**：`text-embedding-v3`（1024 维） Base URL `https://dashscope.aliyuncs.com/compatible-mode/v1`
   - **Ollama 本地**（免费离线）：`ollama pull bge-m3`  Base URL `http://127.0.0.1:11434`
   - **OpenAI**：`text-embedding-3-small`（1536 维）
   > 注意：DeepSeek 目前**不提供** Embedding 接口，DeepSeek 的 Key 不能用于向量化。
2. **改配置**：「知识库  编辑配置」把 Embedding 供应商 / 模型改成上面选项并保存（可点「校验 Embedding 配置」确认连通性与维度）。
3. **重新向量化**：到文档列表对每个文档点「重新向量化」。换模型后旧向量维度不匹配会被自动跳过，**必须重建**。
   完成后用「检索测试」对比换模型前后的相似度与命中片段；建议先拿 1~2 个文档试，确认效果再全量重建。

**Q：知识库检索不到内容？**
先点「测试检索」定位问题：① 文档是否 `处理完成`；② 相似度阈值是否过高（可先降到 0.1）；③ 内置 `local` Embedding 是词法级向量，中文问题配英文文档时召回较弱，建议换 `openai` / `qwen` / `ollama` 等真实 Embedding 后「重新向量化」。

**Q：更换 Embedding 模型后没有生效？**
向量库中仍是旧向量，需要在文档列表点击「重新向量化」。系统会检测维度不一致并跳过，不会静默给出错误结果。

**Q：数据存在哪里？重启会不会丢？**
不会。会话与消息（记忆）、知识库、文档分块、**向量**、模型配置、Prompt、调用统计全部在 MySQL 的 `ai_chat` 库里（见「三、数据库」的对照表），
已实测：停止服务  重启  会话/知识库/文档/向量全部原样可用。只有上传的原始文件放在 `backend/storage/uploads/`（RAG 检索只依赖库里的分块与向量）。

**Q：MySQL 里为什么看不到向量数据？**
向量是二进制 float32（`document_chunks.embedding`，`LONGBLOB`），在 Navicat / Workbench 里会显示为 `<BLOB>` 或乱码，这是正常的。
用 SQL 看长度即可：`SELECT id, document_id, embedding_dim, OCTET_LENGTH(embedding) FROM document_chunks;`
（512 维 = 2048 字节/条）。

**Q：Windows 上 alembic 报编码错误？**
`alembic.ini` 保持 ASCII（本仓库已如此），因为 Alembic 使用系统 locale 读取 ini 文件。

**Q：生产部署注意什么？**
① 修改 `SECRET_KEY`、`API_KEY_ENCRYPTION_KEY`、默认管理员密码；② `DEBUG=false` 并改用 Alembic 迁移；③ 用 MySQL + 外部向量库；④ 反向代理需关闭 SSE 缓冲（`X-Accel-Buffering: no` 已在响应头设置）；⑤ 限制 CORS 来源。
