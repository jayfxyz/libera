import './assets/main.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import { applyTheme, followSystemTheme } from './lib/theme'
import router from './router'

applyTheme()
followSystemTheme()

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')
