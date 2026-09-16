<template>
  <div class="not-found">
    <EmptyState :icon="CompassOutlined" title="页面不存在" :description="`找不到路径：${route.fullPath}`">
      <a-space>
        <a-button @click="router.push('/')">返回首页</a-button>
        <a-button type="primary" @click="router.push('/chat')">去聊天</a-button>
      </a-space>
    </EmptyState>
  </div>
</template>

<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'

import EmptyState from '@/components/common/EmptyState.vue'
import { CompassOutlined } from '@ant-design/icons-vue'

const route = useRoute()
const router = useRouter()
</script>

<style scoped>
.not-found {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: var(--bg-page);
}
</style>
