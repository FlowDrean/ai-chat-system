<template>
  <AdminLayout>
    <div class="page-container">
      <div class="page-header">
        <div>
          <h1 class="page-title">Dashboard</h1>
          <p class="page-subtitle">
            {{ userStore.isAdmin ? '全站运行概况' : '我的使用概况' }} · 最近 {{ days }} 天趋势
          </p>
        </div>
        <a-space>
          <a-segmented v-model:value="days" :options="dayOptions" @change="load" />
          <a-button @click="load">
            <template #icon><ReloadOutlined /></template>
          </a-button>
        </a-space>
      </div>

      <a-spin :spinning="loading">
        <!-- 核心指标 -->
        <div class="dash-stats">
          <StatCard label="今日对话" :value="formatNumber(stats?.today_conversations)" :icon="MessageOutlined" />
          <StatCard label="今日消息" :value="formatNumber(stats?.today_messages)" :icon="CommentOutlined" />
          <StatCard label="今日 Token" :value="formatNumber(stats?.today_tokens)" :icon="ThunderboltOutlined" />
          <StatCard label="模型调用" :value="formatNumber(stats?.today_model_calls)" :icon="ApiOutlined" />
          <StatCard label="知识库" :value="formatNumber(stats?.knowledge_base_count)" :icon="DatabaseOutlined" />
          <StatCard label="文档" :value="formatNumber(stats?.document_count)" :icon="FileTextOutlined" />
        </div>

        <!-- 趋势图 -->
        <a-row :gutter="16" class="dash-row">
          <a-col :xs="24" :lg="16">
            <a-card title="AI 调用趋势" size="small" :bordered="true">
              <div ref="trendRef" class="dash-chart"></div>
            </a-card>
          </a-col>
          <a-col :xs="24" :lg="8">
            <a-card title="模型使用比例" size="small" :bordered="true">
              <div v-if="modelUsage.length" ref="modelChartRef" class="dash-chart"></div>
              <EmptyState v-else :icon="BarChartOutlined" title="暂无调用数据" description="发起一次对话后即可看到统计。" />
            </a-card>
          </a-col>
        </a-row>

        <a-row :gutter="16" class="dash-row">
          <a-col :xs="24" :lg="12">
            <a-card title="知识库检索次数" size="small" :bordered="true">
              <div v-if="knowledgeUsage.length" ref="kbChartRef" class="dash-chart dash-chart--sm"></div>
              <EmptyState v-else :icon="SearchOutlined" title="暂无检索数据" description="使用知识库问答后即可看到统计。" />
            </a-card>
          </a-col>
          <a-col :xs="24" :lg="12">
            <a-card title="累计数据" size="small" :bordered="true">
              <a-descriptions :column="2" size="small">
                <a-descriptions-item label="累计会话">{{ formatNumber(stats?.total_conversations) }}</a-descriptions-item>
                <a-descriptions-item label="累计消息">{{ formatNumber(stats?.total_messages) }}</a-descriptions-item>
                <a-descriptions-item label="累计 Token">{{ formatNumber(stats?.total_tokens) }}</a-descriptions-item>
                <a-descriptions-item label="向量分块">{{ formatNumber(stats?.chunk_count) }}</a-descriptions-item>
                <a-descriptions-item label="模型总数">{{ formatNumber(stats?.model_count) }}</a-descriptions-item>
                <a-descriptions-item label="启用模型">{{ formatNumber(stats?.enabled_model_count) }}</a-descriptions-item>
                <a-descriptions-item v-if="userStore.isAdmin" label="用户数">
                  {{ formatNumber(stats?.user_count) }}
                </a-descriptions-item>
                <a-descriptions-item label="今日检索片段">
                  {{ formatNumber(stats?.today_retrievals) }}
                </a-descriptions-item>
              </a-descriptions>
            </a-card>
          </a-col>
        </a-row>

        <!-- 最近会话 -->
        <a-card title="最近会话" size="small" :bordered="true" class="dash-row">
          <EmptyState
            v-if="!recent.length"
            :icon="MessageOutlined"
            title="暂无会话"
            description="去聊天页开始第一次对话吧。"
          />
          <a-table
            v-else
            :data-source="recent"
            :columns="recentColumns"
            :pagination="false"
            row-key="id"
            size="small"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'title'">
                <a-button type="link" size="small" @click="openConversation(record.id)">{{ record.title }}</a-button>
              </template>
              <template v-else-if="column.key === 'updated_at'">
                {{ formatDateTime(record.updated_at) }}
              </template>
            </template>
          </a-table>
        </a-card>
      </a-spin>
    </div>
  </AdminLayout>
</template>

<script setup lang="ts">
/** Dashboard：核心指标 / 趋势图 / 分布图（ECharts） */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  SearchOutlined,
  BarChartOutlined,
  ApiOutlined,
  CommentOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  MessageOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons-vue'
import * as echarts from 'echarts'
import { useRouter } from 'vue-router'

import EmptyState from '@/components/common/EmptyState.vue'
import StatCard from '@/components/common/StatCard.vue'
import AdminLayout from '@/layouts/AdminLayout.vue'
import { dashboardApi } from '@/api/dashboard'
import { useThemeStore } from '@/stores/theme'
import { useUserStore } from '@/stores/user'
import type { DashboardData } from '@/types'
import { formatDateTime, formatNumber } from '@/utils/format'

const router = useRouter()
const userStore = useUserStore()
const themeStore = useThemeStore()

const loading = ref(false)
const days = ref(14)
const data = ref<DashboardData | null>(null)
const trendRef = ref<HTMLElement | null>(null)
const modelChartRef = ref<HTMLElement | null>(null)
const kbChartRef = ref<HTMLElement | null>(null)

let trendChart: echarts.ECharts | null = null
let modelChart: echarts.ECharts | null = null
let kbChart: echarts.ECharts | null = null

const stats = computed(() => data.value?.stats)
const recent = computed(() => data.value?.recent_conversations || [])
const modelUsage = computed(() => data.value?.model_usage || [])
const knowledgeUsage = computed(() => data.value?.knowledge_usage || [])

const dayOptions = [
  { label: '7 天', value: 7 },
  { label: '14 天', value: 14 },
  { label: '30 天', value: 30 },
]

const recentColumns = [
  { title: '会话标题', key: 'title', dataIndex: 'title', ellipsis: true },
  { title: '消息数', key: 'message_count', dataIndex: 'message_count', width: 100 },
  { title: 'Token', key: 'total_tokens', dataIndex: 'total_tokens', width: 110 },
  { title: '更新时间', key: 'updated_at', width: 180 },
]

async function load() {
  loading.value = true
  try {
    data.value = await dashboardApi.overview(days.value)
    await nextTick()
    renderCharts()
  } finally {
    loading.value = false
  }
}

/** 读取主题变量（ECharts 只有 canvas，拿不到 CSS 变量，只能运行时取值） */
function cssVar(name: string, fallback: string): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}

/** 工具框 / 图例等跟随主题的通用样式 */
function chartPalette() {
  return {
    line1: cssVar('--chart-line-1', '#111114'),
    line2: cssVar('--chart-line-2', '#71717a'),
    bar: cssVar('--chart-bar', '#d4d4d8'),
    area: cssVar('--chart-area', 'rgba(17, 17, 20, 0.06)'),
    grid: cssVar('--chart-grid', '#f4f4f5'),
    axis: cssVar('--chart-axis', '#e6e6e9'),
    label: cssVar('--chart-label', '#a1a1aa'),
    text: cssVar('--text-primary', '#16161a'),
    card: cssVar('--bg-card', '#ffffff'),
    pie: [1, 2, 3, 4, 5, 6].map((i) => cssVar(`--chart-pie-${i}`, '#111114')),
  }
}

function renderCharts() {
  const c = chartPalette()
  const trends = data.value?.trends || []

  if (trendRef.value) {
    trendChart = trendChart || echarts.init(trendRef.value)
    trendChart.setOption({
      grid: { left: 44, right: 20, top: 36, bottom: 28 },
      tooltip: {
        trigger: 'axis',
        backgroundColor: c.card,
        borderColor: c.axis,
        textStyle: { color: c.text },
      },
      legend: { data: ['模型调用', 'Token', '消息数'], right: 0, top: 0, icon: 'circle', itemWidth: 8, textStyle: { color: c.label } },
      xAxis: {
        type: 'category',
        data: trends.map((item) => item.date.slice(5)),
        axisLine: { lineStyle: { color: c.axis } },
        axisLabel: { color: c.label, fontSize: 11 },
      },
      yAxis: [
        {
          type: 'value',
          axisLabel: { color: c.label, fontSize: 11 },
          splitLine: { lineStyle: { color: c.grid } },
        },
      ],
      series: [
        {
          name: '模型调用',
          type: 'line',
          smooth: true,
          symbolSize: 5,
          data: trends.map((item) => item.model_calls),
          itemStyle: { color: c.line1 },
          areaStyle: { color: c.area },
        },
        {
          name: 'Token',
          type: 'line',
          smooth: true,
          symbolSize: 5,
          data: trends.map((item) => item.tokens),
          itemStyle: { color: c.line2 },
        },
        {
          name: '消息数',
          type: 'bar',
          barWidth: 8,
          data: trends.map((item) => item.messages),
          itemStyle: { color: c.bar, borderRadius: [4, 4, 0, 0] },
        },
      ],
    })
  }

  if (modelChartRef.value && modelUsage.value.length) {
    modelChart = modelChart || echarts.init(modelChartRef.value)
    modelChart.setOption({
      tooltip: { trigger: 'item', backgroundColor: c.card, borderColor: c.axis, textStyle: { color: c.text } },
      legend: { bottom: 0, icon: 'circle', itemWidth: 8, textStyle: { fontSize: 11, color: c.label } },
      series: [
        {
          type: 'pie',
          radius: ['46%', '70%'],
          center: ['50%', '44%'],
          avoidLabelOverlap: true,
          itemStyle: { borderColor: c.card, borderWidth: 2 },
          label: { show: false },
          data: modelUsage.value.map((item) => ({ name: item.name, value: item.value })),
          color: c.pie,
        },
      ],
    })
  }

  if (kbChartRef.value && knowledgeUsage.value.length) {
    kbChart = kbChart || echarts.init(kbChartRef.value)
    kbChart.setOption({
      grid: { left: 110, right: 30, top: 20, bottom: 24 },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: c.card, borderColor: c.axis, textStyle: { color: c.text } },
      xAxis: { type: 'value', splitLine: { lineStyle: { color: c.grid } }, axisLabel: { color: c.label, fontSize: 11 } },
      yAxis: {
        type: 'category',
        data: knowledgeUsage.value.map((item) => item.name),
        axisLine: { lineStyle: { color: c.axis } },
        axisLabel: { color: c.label, fontSize: 11 },
      },
      series: [
        {
          type: 'bar',
          barWidth: 14,
          data: knowledgeUsage.value.map((item) => item.value),
          itemStyle: { color: c.line1, borderRadius: [0, 4, 4, 0] },
        },
      ],
    })
  }
}

function handleResize() {
  trendChart?.resize()
  modelChart?.resize()
  kbChart?.resize()
}

async function openConversation(id: number) {
  await router.push('/chat')
  const { useChatStore } = await import('@/stores/chat')
  useChatStore().selectConversation(id).catch(() => undefined)
}

// 明暗切换后重绘（ECharts 不会自动跟随 CSS 变量）
watch(
  () => themeStore.resolved,
  async () => {
    await nextTick()
    renderCharts()
  },
)

onMounted(async () => {
  if (!userStore.user) await userStore.refresh().catch(() => undefined)
  await load()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  trendChart?.dispose()
  modelChart?.dispose()
  kbChart?.dispose()
})
</script>

<style scoped>
.dash-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 14px;
}

.dash-row {
  margin-top: 16px;
}

.dash-chart {
  height: 300px;
}

.dash-chart--sm {
  height: 240px;
}
</style>
