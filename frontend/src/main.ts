import { createPinia } from 'pinia'
import { createApp } from 'vue'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'

import App from './App.vue'
import router from './router'
import { applyThemeEarly } from './stores/theme'
import { useUserStore } from './stores/user'
import './styles/index.css'

async function bootstrap() {
  const app = createApp(App)

  app.use(createPinia())
  app.use(router)
  app.use(Antd)

  // 挂载前先把亮/暗主题写到 <html>，避免首屏闪白
  applyThemeEarly()

  // 启动时恢复登录态（有 token 才请求 /auth/me）
  const userStore = useUserStore()
  await userStore.bootstrap()

  app.mount('#app')
}

bootstrap()
