/**
 * 全局类型定义 —— 与后端 Pydantic Schema 保持一致
 * （见 backend/app/schemas/*.py）
 */

/* ------------------------------- 通用 ---------------------------------- */
export interface ApiEnvelope<T = unknown> {
  code: number
  message: string
  data: T
  request_id?: string
}

export interface PageMeta {
  page: number
  page_size: number
  total: number
  total_pages: number
}

export interface PageData<T> {
  items: T[]
  meta: PageMeta
}

export interface PageQuery {
  page?: number
  page_size?: number
}

/* ------------------------------- 用户 ---------------------------------- */
export interface UserInfo {
  id: number
  username: string
  email?: string | null
  nickname?: string | null
  avatar?: string | null
  role: 'user' | 'admin'
  status: number
  is_admin: boolean
  last_login_at?: string | null
  created_at?: string | null
}

export interface LoginPayload {
  username: string
  password: string
}

export interface RegisterPayload extends LoginPayload {
  email?: string | null
  nickname?: string | null
}

export interface LoginResult {
  access_token: string
  token_type: string
  expires_in: number
  user: UserInfo
}

/* ------------------------------- 模型 ---------------------------------- */
export type ProviderValue =
  | 'openai'
  | 'deepseek'
  | 'qwen'
  | 'ollama'
  | 'gemini'
  | 'claude'
  | 'moonshot'
  | 'zhipu'
  | 'siliconflow'
  | 'custom'
  | 'mock'

export interface ProviderInfo {
  value: ProviderValue
  label: string
  default_base_url?: string | null
  requires_api_key: boolean
  requires_base_url: boolean
  description?: string | null
}

export interface ModelItem {
  id: number
  name: string
  provider: ProviderValue
  provider_label: string
  model_name: string
  base_url?: string | null
  api_key_masked?: string | null
  has_api_key: boolean
  temperature: number
  top_p: number
  max_tokens: number
  frequency_penalty: number
  presence_penalty: number
  enabled: boolean
  is_default: boolean
  supports_stream: boolean
  supports_vision: boolean
  extra_params?: Record<string, unknown> | null
  description?: string | null
  status: 'ok' | 'error' | 'unknown'
  status_message?: string | null
  last_tested_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface ModelPayload {
  name: string
  provider: ProviderValue
  model_name: string
  base_url?: string | null
  api_key?: string | null
  temperature: number
  top_p: number
  max_tokens: number
  frequency_penalty: number
  presence_penalty: number
  enabled: boolean
  is_default: boolean
  supports_stream: boolean
  supports_vision: boolean
  extra_params?: Record<string, unknown> | null
  description?: string | null
}

export interface ModelTestResult {
  success: boolean
  message: string
  latency_ms: number
  model_name?: string | null
  provider?: string | null
  reply_preview?: string | null
}

/* ------------------------------ 聊天 ----------------------------------- */
export type MessageRole = 'system' | 'user' | 'assistant' | 'tool'
export type MessageStatus = 'done' | 'streaming' | 'stopped' | 'error'

export interface RagSource {
  document_id?: number | null
  chunk_id?: number | null
  chunk_index?: number | null
  filename?: string | null
  file_type?: string | null
  page?: number | null
  score: number
  content?: string | null
  metadata?: Record<string, unknown> | null
}

export interface ChatMessage {
  id: number
  conversation_id: number
  role: MessageRole
  content: string
  sources?: RagSource[] | null
  /** 本条回答调用过的技能 */
  skills?: SkillCall[] | null
  status: MessageStatus
  model_id?: number | null
  model_name?: string | null
  provider?: string | null
  knowledge_base_id?: number | null
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  latency_ms: number
  error_message?: string | null
  created_at?: string | null
  /** 仅前端使用：流式生成中 */
  streaming?: boolean
  /** 仅前端使用：失败的本地消息 */
  failed?: boolean
}

export interface ChatParams {
  temperature?: number | null
  top_p?: number | null
  max_tokens?: number | null
  frequency_penalty?: number | null
  presence_penalty?: number | null
  streaming?: boolean
}

export interface Conversation {
  id: number
  title: string
  model_id?: number | null
  knowledge_base_id?: number | null
  prompt_id?: number | null
  system_prompt?: string | null
  params?: ChatParams | Record<string, unknown> | null
  /** 会话启用的技能 id 列表 */
  skill_ids?: number[] | null
  /** 会话启用的 MCP 服务 id 列表 */
  mcp_server_ids?: number[] | null
  is_favorite: boolean
  is_archived: boolean
  message_count: number
  total_tokens: number
  last_message_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface ChatRequestPayload {
  content: string
  /** 本次对话启用的技能 id 列表 */
  skill_ids?: number[] | null
  /** 本次对话启用的 MCP 服务 id 列表 */
  mcp_server_ids?: number[] | null
  conversation_id?: number | null
  model_id?: number | null
  knowledge_base_id?: number | null
  prompt_id?: number | null
  system_prompt?: string | null
  params?: ChatParams | null
  stream?: boolean
  regenerate?: boolean
  use_rag?: boolean | null
}

/* ------------------------------- 技能 ---------------------------------- */
export type SkillFieldType =
  | 'string'
  | 'password'
  | 'text'
  | 'number'
  | 'integer'
  | 'boolean'
  | 'json'
  | 'select'

export interface SkillField {
  key: string
  label: string
  type: SkillFieldType
  required: boolean
  default?: unknown
  placeholder?: string
  help?: string
  options?: Array<{ value: string; label: string }>
  secret?: boolean
}

export interface SkillArg {
  name: string
  type: 'string' | 'number' | 'integer' | 'boolean'
  description: string
  required: boolean
  default?: unknown
}

export interface SkillSpec {
  type: string
  name: string
  description: string
  icon: string
  category: string
  fields: SkillField[]
  args: SkillArg[]
  uses_dynamic_args: boolean
  configurable: boolean
}

export interface SkillItem {
  id: number
  name: string
  slug: string
  type: string
  type_label: string
  category: string
  description?: string | null
  icon?: string | null
  config?: Record<string, unknown> | null
  config_masked_keys?: string[]
  enabled: boolean
  is_builtin: boolean
  visible_to_users: boolean
  sort_order: number
  usage_count: number
  last_used_at?: string | null
  created_at?: string | null
  updated_at?: string | null
  spec?: SkillSpec | null
}

export interface SkillOption {
  id: number
  name: string
  slug: string
  type: string
  description?: string | null
  icon?: string | null
  /** 是否已完成必要配置 */
  configured: boolean
}

export interface SkillPayload {
  name: string
  type: string
  slug?: string | null
  description?: string | null
  icon?: string | null
  enabled: boolean
  visible_to_users: boolean
  sort_order?: number
  config?: Record<string, unknown> | null
}

export interface SkillTestResult {
  success: boolean
  output: string
  error?: string | null
  latency_ms: number
  tool_name?: string | null
  arguments?: Record<string, unknown> | null
}

/** 一次技能调用记录（助手消息里展示） */
export interface SkillCall {
  id?: number | null
  name?: string | null
  type?: string | null
  tool_name?: string | null
  /** 来源：skill（本地技能）/ mcp（MCP 工具） */
  source?: 'skill' | 'mcp' | string
  /** MCP 工具所属服务名 */
  server?: string | null
  status: 'ok' | 'error' | 'running' | string
  arguments?: Record<string, unknown> | null
  output?: string | null
  latency_ms?: number
}

export interface UsageInfo {
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
  latency_ms?: number
  retrieved_chunks?: number
}

export interface ChatResult {
  conversation_id: number
  message: ChatMessage
  sources: RagSource[]
  usage?: UsageInfo
}

/* ----------------------------- 知识库 ---------------------------------- */
export interface KnowledgeBase {
  id: number
  user_id?: number | null
  name: string
  description?: string | null
  embedding_provider: string
  embedding_model: string
  embedding_base_url?: string | null
  embedding_dimension: number
  embedding_api_key_masked?: string | null
  has_embedding_api_key: boolean
  chunk_size: number
  chunk_overlap: number
  top_k: number
  similarity_threshold: number
  rerank_enabled: boolean
  document_count: number
  chunk_count: number
  created_at?: string | null
  updated_at?: string | null
}

export interface KnowledgeBasePayload {
  name: string
  description?: string | null
  embedding_provider: string
  embedding_model: string
  embedding_base_url?: string | null
  embedding_api_key?: string | null
  embedding_dimension: number
  chunk_size: number
  chunk_overlap: number
  top_k: number
  similarity_threshold: number
  rerank_enabled: boolean
}

export interface EmbeddingPreset {
  value: string
  label: string
  dimension: number
  requires_api_key?: boolean
}

export interface EmbeddingProviderInfo {
  value: string
  label: string
  default_base_url?: string | null
  presets: EmbeddingPreset[]
}

export type DocumentStatus = 'pending' | 'parsing' | 'splitting' | 'embedding' | 'completed' | 'failed'

export interface DocumentItem {
  id: number
  knowledge_base_id: number
  knowledge_base_name?: string
  filename: string
  file_type: string
  file_size: number
  status: DocumentStatus
  progress: number
  stage_message?: string | null
  chunk_count: number
  char_count: number
  error_message?: string | null
  doc_metadata?: Record<string, unknown> | null
  processed_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface DocumentChunkItem {
  id: number
  document_id: number
  chunk_index: number
  content: string
  token_count: number
  meta?: Record<string, unknown> | null
  score: number
}

export interface RetrievalTestResult {
  query: string
  latency_ms: number
  chunks: RagSource[]
  context_preview?: string
}

/* ------------------------------ Prompt --------------------------------- */
export type PromptScene = 'system' | 'rag' | 'chat'

export interface PromptItem {
  id: number
  user_id?: number | null
  name: string
  content: string
  description?: string | null
  variables?: string[] | null
  tags?: string[] | null
  scene: PromptScene
  enabled: boolean
  is_builtin: boolean
  usage_count: number
  created_at?: string | null
  updated_at?: string | null
}

export interface PromptPayload {
  name: string
  content: string
  description?: string | null
  variables?: string[] | null
  tags?: string[] | null
  scene: PromptScene
  enabled: boolean
}

/* ----------------------------- Dashboard ------------------------------- */
export interface DashboardStats {
  today_conversations: number
  today_messages: number
  today_tokens: number
  today_model_calls: number
  today_retrievals: number
  total_conversations: number
  total_messages: number
  total_tokens: number
  model_count: number
  enabled_model_count: number
  knowledge_base_count: number
  document_count: number
  chunk_count: number
  user_count: number
}

export interface TrendPoint {
  date: string
  conversations: number
  messages: number
  tokens: number
  model_calls: number
}

export interface DistributionItem {
  name: string
  value: number
}

export interface DashboardData {
  stats: DashboardStats
  trends: TrendPoint[]
  model_usage: DistributionItem[]
  knowledge_usage: DistributionItem[]
  recent_conversations: Array<{
    id: number
    title: string
    message_count: number
    total_tokens: number
    updated_at?: string | null
  }>
}

/* ------------------------------ MCP ------------------------------------ */
export type McpTransport = 'stdio' | 'sse' | 'http'

export interface McpTool {
  name: string
  description: string
  input_schema: Record<string, unknown>
}

export interface McpServerItem {
  id: number
  name: string
  slug: string
  transport: McpTransport
  transport_label: string
  description?: string | null
  command?: string | null
  args?: string[] | null
  env?: Record<string, string> | null
  cwd?: string | null
  url?: string | null
  headers?: Record<string, string> | null
  masked_keys?: string[]
  enabled: boolean
  visible_to_users: boolean
  timeout: number
  sort_order: number
  status: 'ok' | 'error' | 'unknown'
  status_message?: string | null
  last_connected_at?: string | null
  tool_count: number
  tools: McpTool[]
  usage_count: number
  last_used_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface McpServerPayload {
  name: string
  transport: McpTransport
  slug?: string | null
  description?: string | null
  command?: string | null
  args?: string[] | null
  env?: Record<string, string> | null
  cwd?: string | null
  url?: string | null
  headers?: Record<string, string> | null
  enabled: boolean
  visible_to_users: boolean
  timeout: number
  sort_order?: number
}

export interface McpServerOption {
  id: number
  name: string
  slug: string
  transport: McpTransport
  description?: string | null
  tool_count: number
  status: string
}

export interface McpTestResult {
  success: boolean
  message: string
  latency_ms: number
  tool_count: number
  tools: McpTool[]
}

export interface McpToolCallResult {
  success: boolean
  output: string
  error?: string | null
  latency_ms: number
  is_error: boolean
}

export interface McpImportItemResult {
  name: string
  slug: string
  server_id?: number | null
  transport: string
  action: 'created' | 'updated' | 'renamed' | 'skipped' | 'failed' | string
  success: boolean
  message: string
  tool_count: number
  tools: McpTool[]
}

export interface McpImportResult {
  total: number
  created: number
  updated: number
  skipped: number
  failed: number
  items: McpImportItemResult[]
  warnings: string[]
}

export interface McpExportResult {
  content: string
  count: number
  include_secrets: boolean
}

export interface McpImportPayload {
  payload: string
  strategy: 'skip' | 'overwrite' | 'rename'
  auto_test: boolean
  enabled: boolean
  visible_to_users: boolean
}

export interface McpTransportInfo {
  value: McpTransport
  label: string
  description: string
  fields: string[]
}

/* ------------------------------ SSE 事件 -------------------------------- */
export type StreamEventType =
  | 'start'
  | 'meta'
  | 'route'
  | 'sources'
  | 'skill'
  | 'token'
  | 'notice'
  | 'usage'
  | 'error'
  | 'done'

export interface StreamEvent {
  type: StreamEventType
  [key: string]: unknown
}
