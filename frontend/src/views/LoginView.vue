<template>
  <section class="card narrow">
    <h1>登录</h1>
    <p class="muted">仅管理员分配账号，用户不可注册。</p>

    <form @submit.prevent="onSubmit" class="form-grid">
      <label>
        <span>用户名</span>
        <input v-model="username" required />
      </label>

      <label>
        <span>密码</span>
        <input v-model="password" type="password" required />
      </label>

      <button class="btn" :disabled="loading">{{ loading ? '登录中...' : '登录' }}</button>
      <p v-if="error" class="error">{{ error }}</p>
    </form>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { login } from '../stores/auth'

const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')
const router = useRouter()

async function onSubmit() {
  loading.value = true
  error.value = ''
  try {
    const me = await login(username.value, password.value)
    if (me.role === 'admin') {
      router.push('/admin')
    } else {
      router.push('/')
    }
  } catch (err) {
    error.value = err.message || '登录失败'
  } finally {
    loading.value = false
  }
}
</script>
