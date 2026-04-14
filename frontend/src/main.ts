import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { nanocatZhCN, setNanocatLocale } from 'nanocat-ui'
import router from './router'
import App from './App.vue'
import './style.css'
import './styles/features.css'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'

setNanocatLocale(nanocatZhCN)

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)

app.mount('#app')
