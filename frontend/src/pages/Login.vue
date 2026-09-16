<template>
  <div class="login-page">
    <!-- 左侧品牌区 -->
    <section class="login-page__brand">
      <div class="login-page__brand-inner">
        <AppLogo />
        <h1 class="login-page__headline">企业级 AI 问答平台</h1>
        <p class="login-page__sub">
          多模型配置 · RAG 知识库 · 文档解析与向量检索 · LangGraph 工作流
        </p>

        <ul class="login-page__features">
          <li v-for="item in features" :key="item.title">
            <span class="login-page__feature-icon"><component :is="item.icon" /></span>
            <div>
              <strong>{{ item.title }}</strong>
              <p>{{ item.desc }}</p>
            </div>
          </li>
        </ul>

      </div>
    </section>

    <!-- 右侧表单区 -->
    <section class="login-page__form">
      <div class="login-page__card">
        <h2 class="login-page__title">{{ mode === 'login' ? '欢迎回来' : '创建账号' }}</h2>
        <p class="login-page__desc">
          {{ mode === 'login' ? '登录后即可开始与 AI 对话' : '系统首个注册用户将自动成为管理员' }}
        </p>

        <a-form ref="formRef" :model="form" :rules="rules" layout="vertical" @finish="submit">
          <a-form-item label="用户名" name="username">
            <a-input v-model:value="form.username" size="large" placeholder="请输入用户名" autocomplete="username">
              <template #prefix><UserOutlined /></template>
            </a-input>
          </a-form-item>

          <a-form-item v-if="mode === 'register'" label="邮箱（可选）" name="email">
            <a-input v-model:value="form.email" size="large" placeholder="name@example.com">
              <template #prefix><MailOutlined /></template>
            </a-input>
          </a-form-item>

          <a-form-item label="密码" name="password">
            <a-input-password
              v-model:value="form.password"
              size="large"
              placeholder="请输入密码"
              autocomplete="current-password"
            >
              <template #prefix><LockOutlined /></template>
            </a-input-password>
          </a-form-item>

          <a-button type="primary" size="large" block html-type="submit" :loading="userStore.loading">
            {{ mode === 'login' ? '登录' : '注册并进入' }}
          </a-button>
        </a-form>

        <div class="login-page__switch">
          <span>{{ mode === 'login' ? '还没有账号？' : '已有账号？' }}</span>
          <a-button type="link" @click="toggleMode">
            {{ mode === 'login' ? '立即注册' : '返回登录' }}
          </a-button>
        </div>

        <a-alert v-if="errorText" type="error" show-icon :message="errorText" class="login-page__error" />
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
/** 登录 / 注册页 */
import { computed, reactive, ref } from 'vue'
import type { Rule } from 'ant-design-vue/es/form'
import { message } from 'ant-design-vue'
import {
  ApiOutlined,
  DatabaseOutlined,
  LockOutlined,
  MailOutlined,
  NodeIndexOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import { useRoute, useRouter } from 'vue-router'

import AppLogo from '@/components/common/AppLogo.vue'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const mode = ref<'login' | 'register'>('login')
const errorText = ref('')
const formRef = ref()

const form = reactive({ username: '', password: '', email: '' })

const rules: Record<string, Rule[]> = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
}


const features = [
  { icon: NodeIndexOutlined, title: '多模型统一接入', desc: 'OpenAI / DeepSeek / 通义 / Ollama / Claude / Gemini，配置即用' },
  { icon: DatabaseOutlined, title: 'RAG 知识库', desc: '上传 PDF、DOCX、Excel，自动解析、切分、向量化并带引用回答' },
  { icon: ApiOutlined, title: '真实流式输出', desc: 'SSE 逐字返回，支持停止生成、重新生成与多轮上下文' },
]

function toggleMode() {
  mode.value = mode.value === 'login' ? 'register' : 'login'
  errorText.value = ''
}

async function submit() {
  errorText.value = ''
  try {
    if (mode.value === 'login') {
      await userStore.login({ username: form.username, password: form.password })
      message.success('登录成功')
    } else {
      await userStore.register({
        username: form.username,
        password: form.password,
        email: form.email || null,
      })
      message.success('注册成功，已自动登录')
    }
    const redirect = (route.query.redirect as string) || '/chat'
    await router.replace(redirect)
  } catch (error) {
    errorText.value = (error as Error)?.message || '操作失败，请稍后重试'
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  min-height: 100vh;
  background: var(--bg-page);
}

.login-page__brand {
  flex: 1.1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px;
  background: var(--bg-sunken);
  border-right: 1px solid var(--border-color);
}

.login-page__brand-inner {
  max-width: 460px;
}

.login-page__headline {
  margin: 28px 0 10px;
  font-size: 30px;
  font-weight: 700;
  line-height: 1.3;
  color: var(--text-primary);
}

.login-page__sub {
  margin: 0 0 28px;
  font-size: 14px;
  color: var(--text-secondary);
}

.login-page__features {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.login-page__features li {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.login-page__feature-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 9px;
  background: var(--bg-card);
  color: var(--brand);
  border: 1px solid var(--border-color);
  flex-shrink: 0;
}

.login-page__features strong {
  display: block;
  font-size: 14px;
  color: var(--text-primary);
}

.login-page__features p {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}


.login-page__form {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 24px;
}

.login-page__card {
  width: 100%;
  max-width: 380px;
}

.login-page__title {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 600;
}

.login-page__desc {
  margin: 0 0 24px;
  font-size: 13px;
  color: var(--text-secondary);
}

.login-page__switch {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 2px;
  margin-top: 14px;
  font-size: 13px;
  color: var(--text-secondary);
}

.login-page__error {
  margin-top: 14px;
}

@media (max-width: 900px) {
  .login-page__brand {
    display: none;
  }
  .login-page__form {
    flex: 1;
  }
}
</style>
