<template>
  <div class="app-logo" :class="{ compact }">
    <span class="app-logo__mark">
      <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
        <path
          d="M12 2.6l1.9 4.9 4.9 1.9-4.9 1.9L12 16.2l-1.9-4.9-4.9-1.9 4.9-1.9L12 2.6z"
          fill="currentColor"
        />
        <circle cx="18.4" cy="18.2" r="2.6" fill="currentColor" opacity="0.55" />
      </svg>
    </span>
    <span v-if="!compact" class="app-logo__text">
      <strong>AI Assistant</strong>
      <small>Chat  RAG  Agent</small>
    </span>
  </div>
</template>

<script setup lang="ts">
defineProps<{ compact?: boolean }>()
</script>

<style scoped>
.app-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  user-select: none;
}

.app-logo__mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: var(--brand);
  color: var(--brand-contrast);
  flex-shrink: 0;
}

.app-logo__text {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}

.app-logo__text strong {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.app-logo__text small {
  font-size: 11px;
  color: var(--text-secondary);
}
</style>
