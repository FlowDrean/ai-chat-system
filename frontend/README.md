# 前端（Vue 3 + Vite + TypeScript + Ant Design Vue）

## 快速开始

```bash
npm install
npm run dev          # http://127.0.0.1:5173
```

开发环境已把 `/api` 代理到 `http://127.0.0.1:8000`（见 `vite.config.ts`），无需处理跨域。
如需指向其它后端，修改 `.env.development` 中的 `VITE_API_BASE_URL`。

> 前端不直接接触数据库：会话记忆、知识库、文档分块与**向量**都由后端持久化在 MySQL（`ai_chat` 库）中，
> 前端只通过 `/api` 读写。

## 脚本

| 命令 | 说明 |
| --- | --- |
| `npm run dev` | 启动开发服务器 |
| `npm run build` | 类型检查 + 生产构建 |
| `npm run preview` | 预览构建产物 |
| `npm run type-check` | `vue-tsc` 类型检查（0 error） |
| `npm run test:e2e` | 前端端到端冒烟测试（Playwright，31 项，含 UI 无 emoji 扫描） |
| `npm run test:e2e:rag` | RAG 端到端测试（Playwright，9 项） |
| `npm run test:e2e:sidebar` | 侧边栏折叠 / 移动端抽屉几何检查（Playwright，98 项） |
| `npm run test:e2e:skills` | 技能配置 / 试运行 / Tool Calling 端到端（Playwright，18 项） |
| `npm run test:e2e:mcp` | MCP 接入 / 工具发现 / 聊天调用 / 配置导入导出（Playwright，21 项） |

> E2E 默认复用系统已安装的 Edge / Chrome（`channel: 'msedge'` → 回退 `chrome`），无需下载浏览器内核；
> 运行前请先启动后端与 `npm run dev`。

## 目录结构

```
src/
├── api/             request.ts（axios 封装：注入 Token / 拆包 / 401 / 统一报错）
│                    auth chat model knowledge document prompt user dashboard + index
├── components/
│   ├── chat/        ChatMessage ChatInput ChatHeader ConversationList ModelSelector
│   │                KnowledgeSelector PromptSelector ModelParamsPanel RagSource
│   │                MarkdownRenderer CodeBlock
│   ├── knowledge/   KnowledgeCard KnowledgeConfigForm DocumentList
│   ├── model/       ModelConfigForm
│   ├── skill/       SkillSelector SkillConfigForm SkillCallList
│   ├── mcp/         McpSelector McpConfigForm McpImportModal McpExportModal
│   └── common/      AppLogo EmptyState LoadingView StatCard
├── layouts/         ChatLayout（会话列表 + 内容区，移动端抽屉）· AdminLayout（侧边菜单 + 顶部栏）
├── pages/           Login Home Chat Model Knowledge KnowledgeDetail Documents
│                    Prompt Users Settings Dashboard NotFound
├── stores/          user settings model knowledge chat（Pinia，Composition 风格）
├── router/          路由 + 登录 / 管理员守卫
├── utils/           request 之外的工具：sse（流式解析）· markdown（marked+hljs+DOMPurify）· format
├── types/           与后端 Pydantic Schema 一一对应的 TS 类型
└── styles/          设计变量与全局样式（主色 #1677FF、背景 #F7F8FA、圆角/边框/留白）
```

## 关键实现

### 1. 流式输出（SSE）

`utils/sse.ts` 用 `fetch` + `ReadableStream` 手工解析 SSE 帧，而不是 `EventSource`，原因：

- 需要 POST 请求体；
- 需要携带 `Authorization` 头（EventSource 无法自定义请求头）；
- 需要 `AbortController` 支持「停止生成」。

`stores/chat.ts` 中的处理：

1. 用户消息**乐观插入**（临时 id 为负数），收到 `meta` 事件后用服务端消息替换；
2. 助手消息先插入占位对象，token 直接追加到该响应式对象上（不重建数组，性能更好）；
3. 点击停止 → `controller.abort()`，后端在生成器 `finally` 中把已生成内容以 `stopped` 状态落库；
4. 错误区分「模型调用失败（带 error 事件）」与「网络失败（fetch 抛错）」，都提供「重新生成」。

### 2. 会话级参数

`stores/settings.ts` 持久化到 localStorage：当前模型、知识库、Prompt、Temperature / Top P / Max Tokens /
Frequency Penalty / Presence Penalty / Streaming、是否自动 RAG、是否展示 Token 统计。
「模型参数」抽屉修改后**只影响当前会话**（随请求一起发送）。

### 3. Markdown 安全渲染

`utils/markdown.ts`：`marked` 解析 → `highlight.js` 高亮 → **`DOMPurify` 清洗**（禁 `script`/`iframe`/`style`/内联事件）。
代码块的「复制」按钮由组件在渲染后通过 DOM 注入并绑定事件，避免内联脚本被清洗 / 造成 XSS。

### 4. 状态三态

所有列表（会话、模型、知识库、文档、Prompt、用户、Dashboard）都有
Loading（`LoadingView`）/ Empty（`EmptyState`）/ Error（统一 toast + 重新生成按钮）状态。

### 5. 响应式

- ≥ 992px：左侧会话列表 + 右侧聊天；管理后台左侧菜单；
- < 992px：聊天页会话列表变为抽屉（浮动按钮呼出）；管理后台菜单自动收起；
- < 768px：聊天页隐藏次要信息（参数提示、上下文标签），表格 `scroll` 横向滚动。

### 6. 布局约定（重要）

页面以 `<ChatLayout>` / `<AdminLayout>` 包裹自身，布局内部使用 `<slot />` 而非 `<router-view>`。
如果把布局写成父路由并同时使用 `<router-view>`，会造成「页面内嵌同路由视图」的递归渲染，
Vue Router 会静默渲染空内容 —— 这是本项目开发过程中实际踩过并修复的坑。

## UI 规范

- **MCP**：`McpConfigForm.vue` 按传输方式（stdio / sse / http）切换表单字段；`McpSelector.vue` 供聊天选择服务；
  调用记录复用 `SkillCallList`（`source === 'mcp'` 时显示 MCP 徽标与服务名）
- **技能动态表单**：`SkillConfigForm.vue` 完全由后端 `SkillSpec.fields` 驱动渲染（string/password/textarea/json/number/boolean/select），
  新增技能类型无需改前端；聊天工具栏 `SkillSelector` 负责选择，`SkillCallList` 展示调用记录
- **不使用 emoji**：图标一律使用 `@ant-design/icons-vue`；空状态组件 `EmptyState` 只接受 `icon`（图标组件），
  从组件层面约束规范
- 状态用 `a-tag` / `a-badge` 表达，不用符号表情；文案使用中文全角标点
- `npm run test:e2e` 会逐页扫描 DOM 文本，出现 emoji 即判定失败（回归守卫）

## 主题

`App.vue` 通过 `a-config-provider` 覆盖 Ant Design Vue 设计变量：

```ts
colorPrimary: '#1677FF'   colorText: '#1F2329'   colorTextSecondary: '#86909C'
colorBorder: '#E5E6EB'    borderRadius: 8        colorBgLayout: '#F7F8FA'
```

风格遵循需求：浅色、留白、轻边框、少量品牌色，不使用大面积渐变 / 玻璃拟态 / 粒子动画。
