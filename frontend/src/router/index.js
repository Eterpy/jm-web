import { createRouter, createWebHistory } from 'vue-router'
import AdminView from '../views/AdminView.vue'
import LoginView from '../views/LoginView.vue'
import UserView from '../views/UserView.vue'
import { authState, refreshMe } from '../stores/auth'

const routes = [
  { path: '/login', component: LoginView },
  { path: '/admin', component: AdminView },
  { path: '/', component: UserView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  if (to.path === '/login') {
    return true
  }

  if (!authState.token) {
    return '/login'
  }

  if (!authState.me) {
    try {
      await refreshMe()
    } catch {
      return '/login'
    }
  }

  if (to.path === '/admin' && authState.me?.role !== 'admin') {
    return '/'
  }

  if (to.path === '/' && authState.me?.role === 'admin') {
    return '/admin'
  }

  return true
})

export default router
