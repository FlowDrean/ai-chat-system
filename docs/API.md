# API 文档

- 交互式文档：`http://127.0.0.1:8000/docs`（Swagger UI）、`/redoc`
- 统一前缀：`/api`
- 统一响应：

```json
{ "code": 0, "message": "success", "data": {} }
```

失败时 `code != 0`（详见「错误码」），HTTP 状态码同步语义化（400/401/403/404/409/413/422/500/502）。

## 认证

除 `POST /api/auth/login`、`POST /api/auth/register`、`GET /api/health` 外，所有接口都需要：

```
Authorization: Bearer <access_token>
```

（SSE 场景也支持 `X-Access-Token` 头或 `?token=` 查询参数，方便 EventSource 使用。）

## 接口清单

### 认证 `/api/auth`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/auth/register` | 注册（系统首个用户自动成为管理员） |
| POST | `/auth/login` | 登录，返回 `access_token` + 用户信息 |
| GET | `/auth/me` | 当前用户信息 |
| POST | `/auth/logout` | 退出登录 |
| POST | `/auth/password` | 修改密码 |

### 聊天与会话

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/chat` | 聊天（非流式，适合脚本调用） |
| POST | `/chat/stream` | 聊天（SSE 流式） |
| GET | `/conversations` | 会话列表（`keyword` / `favorite` / `archived` / 分页） |
| POST | `/conversations` | 新建会话 |
| GET | `/conversations/{id}` | 会话详情 |
| PUT | `/conversations/{id}` | 更新会话（标题 / 收藏 / 归档 / 模型 / 知识库 / 参数） |
| DELETE | `/conversations/{id}` | 删除会话（级联删除消息） |
| POST | `/conversations/{id}/clear` | 清空当前对话（保留会话） |
| GET | `/conversations/{id}/messages` | 消息列表（`limit` / `before_id` 滚动加载） |
| DELETE | `/messages/{id}` | 删除单条消息及其之后的消息（用于重新编辑） |

### 模型管理

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/models` | 模型列表（`keyword` / `provider` / `enabled` / 分页） |
| POST | `/models` | 新增模型（管理员） |
| GET | `/models/{id}` | 模型详情（API Key 脱敏） |
| PUT | `/models/{id}` | 编辑模型（管理员，`api_key` 留空表示不修改） |
| DELETE | `/models/{id}` | 删除模型（管理员） |
| POST | `/models/{id}/test` | 测试连接（管理员） |
| POST | `/models/{id}/default` | 设为默认模型（管理员） |
| PATCH | `/models/{id}/enabled` | 启用 / 禁用（管理员） |
| POST | `/models/{id}/duplicate` | 复制模型配置（管理员） |
| GET | `/models/providers` | 供应商清单与默认地址 |
| GET | `/models/embedding-options` | Embedding 供应商与预置模型 |

### 知识库与文档

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/knowledge-bases` | 知识库列表 |
| POST | `/knowledge-bases` | 新建知识库 |
| GET | `/knowledge-bases/{id}` | 详情（含文档列表） |
| PUT | `/knowledge-bases/{id}` | 编辑（Embedding / Chunk / Retriever 配置） |
| DELETE | `/knowledge-bases/{id}` | 删除（含向量与物理文件） |
| POST | `/knowledge-bases/{id}/retrieval-test` | 检索测试（不调用 LLM） |
| GET | `/knowledge-bases/{id}/embedding-check` | 校验 Embedding 配置并返回维度 |
| GET | `/knowledge-bases/{id}/documents` | 文档列表（`status` / `keyword` / 分页） |
| POST | `/knowledge-bases/{id}/documents` | 上传文档（multipart/form-data，字段名 `file`） |
| GET | `/documents` | 全部文档（管理后台，跨知识库） |
| GET | `/documents/{id}` | 文档详情（含分块预览） |
| GET | `/documents/{id}/chunks` | 分块分页列表 |
| DELETE | `/documents/{id}` | 删除文档（含向量与物理文件） |
| POST | `/documents/{id}/reindex` | 重新向量化 |
| GET | `/documents/meta/supported-types` | 支持的文件类型 |
| GET | `/documents/meta/limits` | 上传大小与扩展名限制 |

### Prompt

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/prompts` | 列表（系统内置 + 自己的） |
| POST | `/prompts` | 新建 |
| GET | `/prompts/{id}` | 详情 |
| PUT | `/prompts/{id}` | 编辑（内置不可改） |
| DELETE | `/prompts/{id}` | 删除（内置不可删） |
| POST | `/prompts/{id}/render` | 变量渲染预览 |
| POST | `/prompts/{id}/duplicate` | 复制为我的 Prompt |

### 技能 `/api/skills`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/skills` | 技能列表（管理员，含配置与脱敏字段） |
| POST | `/skills` | 新建技能（管理员） |
| GET | `/skills/available` | 聊天可用的技能（任意登录用户，仅返回已启用 + 已完成配置 + 允许用户使用的） |
| GET | `/skills/specs` | 技能类型规格（动态配置表单用：字段定义 / 工具入参 / 是否动态入参） |
| GET | `/skills/{id}` | 技能详情（管理员） |
| PUT | `/skills/{id}` | 编辑技能（管理员；敏感配置留空表示不修改） |
| PATCH | `/skills/{id}/enabled` | 启用 / 禁用（管理员） |
| DELETE | `/skills/{id}` | 删除技能（管理员；系统预置技能不可删除） |
| POST | `/skills/{id}/test` | 试运行已保存的技能 |
| POST | `/skills/test-run` | 未保存的配置试运行（`?skill_type=` + body 里带 `config`） |

内置技能类型：`calculator`（计算器）、`current_time`（当前时间）、`web_search`（联网搜索，需 API Key）、
`web_fetch`（网页抓取，默认禁内网）、`http_request`（自定义 HTTP 接口，入参 schema 自定义）。

```http
POST /api/skills/1/test
{ "arguments": { "expression": "(88+12)/4*3" } }
```

```json
{ "code": 0, "message": "试运行完成",
  "data": { "success": true, "output": "表达式 (88+12)/4*3 = 75", "latency_ms": 0.3,
            "tool_name": "calculator", "arguments": { "expression": "(88+12)/4*3" } } }
```

聊天时通过 `skill_ids` 指定本次要用的技能（会保存到会话上，下次进入自动恢复）：

```http
POST /api/chat
{ "content": "帮我算 (88+12)/4*3", "model_id": 1, "skill_ids": [1], "stream": false }
```

响应里的 `message.skills` 记录调用明细：

```json
{ "skills": [ { "id": 1, "name": "计算器", "type": "calculator", "tool_name": "calculator_1",
                "status": "ok", "arguments": { "expression": "(88+12)/4*3" },
                "output": "表达式 (88+12)/4*3 = 75", "latency_ms": 0.8 } ] }
```

### MCP `/api/mcp`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/mcp/transports` | 传输方式说明（前端动态表单用） |
| GET | `/mcp/available` | 聊天可用的 MCP 服务（任意登录用户） |
| GET | `/mcp/servers` | MCP 服务列表（管理员，含脱敏配置与工具数） |
| POST | `/mcp/servers` | 接入 MCP 服务（管理员） |
| GET | `/mcp/servers/{id}` | 详情（含缓存的工具清单） |
| PUT | `/mcp/servers/{id}` | 编辑（管理员；`env` / `headers` 敏感值留空表示不修改） |
| PATCH | `/mcp/servers/{id}/enabled` | 启用 / 禁用 |
| DELETE | `/mcp/servers/{id}` | 删除 |
| POST | `/mcp/servers/{id}/test` | **连接测试 + 拉取 `tools/list` 并缓存** |
| POST | `/mcp/servers/{id}/refresh-tools` | 同上（刷新工具清单） |
| GET | `/mcp/servers/{id}/tools` | 已缓存的工具清单（含 JSON Schema） |
| POST | `/mcp/servers/{id}/call-tool` | 调试调用某个 MCP 工具 |
| POST | `/mcp/import` | **导入 mcpServers 配置**（Claude Desktop / Cursor 格式），支持冲突策略与自动测试 |
| GET | `/mcp/export` | 导出 mcpServers 配置（`include_secrets=true` 时含明文密钥） |

传输方式：`stdio`（本地进程，需 `command`/`args`）、`sse`、`http`（远程，需 `url`）。
`env` / `headers` 中的敏感值加密存储，出参只返回掩码。

```http
POST /api/mcp/servers
{ "name": "文件系统", "transport": "stdio", "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "D:\\资料"],
  "enabled": true, "visible_to_users": true, "timeout": 60 }
```

```http
POST /api/mcp/servers/1/test           连接成功：发现 3 个工具
POST /api/mcp/servers/1/call-tool
{ "tool_name": "add", "arguments": { "a": 100, "b": 23 } }
 { "success": true, "output": "100 + 23 = 123", "latency_ms": 812.4 }
```

导入 `mcpServers` 配置（可直接粘贴 Claude Desktop / Cursor 的配置）：

```http
POST /api/mcp/import
{ "payload": "{\"mcpServers\":{\"amap-maps\":{\"command\":\"npx\",\"args\":[...],\"env\":{...}}}}",
  "strategy": "rename", "auto_test": true, "visible_to_users": true }
 { "total": 1, "created": 1, "updated": 0, "skipped": 0, "failed": 0,
    "items": [ { "name": "amap-maps", "slug": "amap-maps", "transport": "stdio",
                 "action": "created", "success": true,
                 "message": "导入成功，连接正常（发现 12 个工具）", "tool_count": 12 } ] }
```

`strategy`：`skip` 跳过同名 / `rename` 自动重命名（默认）/ `overwrite` 覆盖。
`payload` 也接受对象形式，以及 `servers` / `{"mcp":{"servers":}}` / 单个服务 / 服务数组等写法。
非法的 JSON 或无法识别的结构会返回 `40000` 与可读提示。

聊天时用 `mcp_server_ids` 指定要启用的 MCP 服务（会保存到会话上）：

```http
POST /api/chat
{ "content": "请用 add 工具计算 123+456", "model_id": 1, "mcp_server_ids": [1], "stream": false }
```

MCP 工具的调用会与「技能」共用同一套 `skill` SSE 事件与 `message.skills` 记录，
只是多了 `source: "mcp"` 与 `server` 字段用于区分来源。

### 用户与系统

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/PUT | `/profile` | 我的资料 |
| GET | `/users` | 用户列表（管理员） |
| POST | `/users` | 新建用户（管理员） |
| PUT | `/users/{id}` | 编辑用户（管理员） |
| DELETE | `/users/{id}` | 删除用户（管理员） |
| POST | `/users/{id}/reset-password` | 重置密码（管理员） |
| GET | `/dashboard` | Dashboard 统计（`days` 参数控制趋势天数） |
| GET | `/system/info` | 系统信息（管理员） |
| GET | `/health` | 健康检查 |

## 请求 / 响应示例

### 流式聊天

```http
POST /api/chat/stream
Authorization: Bearer <token>
Content-Type: application/json

{
  "content": "根据知识库回答问题：RAG 的检索流程是什么？",
  "conversation_id": 12,
  "model_id": 1,
  "knowledge_base_id": 3,
  "prompt_id": null,
  "params": { "temperature": 0.7, "top_p": 1, "max_tokens": 4096, "streaming": true },
  "use_rag": true,
  "regenerate": false
}
```

响应（`text/event-stream`）：

```
data: {"type":"start"}

data: {"type":"meta","conversation":{...},"user_message":{...},"assistant_message":{"id":88,"status":"streaming"},"model":{"id":1,"model_name":"deepseek-chat"},"knowledge_base":{"id":3,"name":"产品文档"},"use_rag":true}

data: {"type":"route","use_rag":true,"knowledge_base_id":3,"knowledge_base_name":"产品文档"}

data: {"type":"sources","sources":[{"document_id":5,"filename":"手册.pdf","page":12,"score":0.91,"content":"…"}],"count":1}

data: {"type":"token","content":"RAG 的检索流程"}

data: {"type":"token","content":"分为四步…"}

data: {"type":"done","message":{"id":88,"content":"RAG 的检索流程分为四步…","status":"done","total_tokens":1284,"sources":[...]},"usage":{"total_tokens":1284,"latency_ms":2310.4,"retrieved_chunks":1},"conversation":{...},"stopped":false}
```

`type` 取值：`start` / `meta` / `route` / `sources` / `skill` / `token` / `notice` / `error` / `done`。

技能调用会额外推送三条 `skill` 事件（事件名固定为 `skill`，技能类型在 `skill_type` 字段里）：

```
data: {"type":"skill","phase":"planned","calls":[{"name":"calculator_1","arguments":{"expression":"45*2+10"}}]}

data: {"type":"skill","phase":"call","call_id":"call_calculator","name":"计算器","tool_name":"calculator_1","skill_type":"calculator","arguments":{"expression":"45*2+10"}}

data: {"type":"skill","phase":"result","call_id":"call_calculator","name":"计算器","status":"ok","output":"表达式 45*2+10 = 100","latency_ms":0.7}
```
`error` 事件示例：`data: {"type":"error","code":50101,"message":"鉴权失败：API Key 无效或已过期","partial":"已生成的部分内容"}`。

### 非流式聊天

```http
POST /api/chat
{ "content": "FastAPI 是什么？", "stream": false }
```

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "conversation_id": 12,
    "message": { "id": 89, "role": "assistant", "content": "…", "total_tokens": 340, "latency_ms": 1430.4 },
    "sources": [],
    "usage": { "prompt_tokens": 120, "completion_tokens": 220, "total_tokens": 340, "latency_ms": 1430.4 }
  }
}
```

### 上传文档

```http
POST /api/knowledge-bases/3/documents
Content-Type: multipart/form-data; boundary=----x

file=@手册.pdf
```

```json
{ "code": 0, "message": "文件已上传，正在后台解析与向量化",
  "data": { "id": 21, "filename": "手册.pdf", "file_type": "pdf", "status": "pending", "progress": 0 } }
```

随后轮询 `GET /api/knowledge-bases/3/documents` 或 `GET /api/documents/21` 观察
`status`：`pending → parsing → splitting → embedding → completed|failed`，`progress` 0-100。

## 错误码

| code | HTTP | 含义 |
| --- | --- | --- |
| 0 | 200 | 成功 |
| 40000 / 40001 | 400 / 422 | 参数错误 / 参数校验失败 |
| 40100 / 40101 / 40102 | 401 | 未登录 / Token 过期 / Token 无效 |
| 40300 / 40301 | 403 | 无权限 / 账号被禁用 |
| 40400 | 404 | 资源不存在 |
| 40900 | 409 | 资源冲突（重名等） |
| 413 | 413 | 文件过大（`FILE_TOO_LARGE` 50202） |
| 50000 | 500 | 服务器内部错误 |
| 50001 / 50002 | 500 | 配置错误 / 数据库错误 |
| 50101 / 50102 / 50103 | 502 / 404 / 400 | 模型调用失败 / 模型不存在 / 模型已禁用 |
| 50104 / 50105 | 502 | Embedding 失败 / 检索失败 |
| 50201 / 50202 / 50203 / 50204 | 400 / 413 / 400 / 500 | 文件类型不支持 / 文件过大 / 解析失败 / 存储失败 |
| 50301 | 502 | 上游服务调用失败 |

> 生产环境不会返回 traceback、SQL、文件路径、API Key 等敏感信息，问题定位请结合响应头 `X-Request-ID` 查询服务端日志。
