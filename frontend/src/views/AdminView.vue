<template>
  <section class="grid-2">
    <article class="card">
      <h2>创建用户</h2>
      <form class="form-grid" @submit.prevent="createUser">
        <label>
          <span>用户名</span>
          <input v-model="form.username" required minlength="3" />
        </label>

        <label>
          <span>密码</span>
          <input v-model="form.password" type="password" required minlength="6" />
        </label>

        <label>
          <span>角色</span>
          <select v-model="form.role">
            <option value="user">user</option>
            <option value="admin">admin</option>
          </select>
        </label>

        <button class="btn">创建</button>
      </form>
      <p v-if="message" class="ok">{{ message }}</p>
      <p v-if="error" class="error">{{ error }}</p>
    </article>

    <article class="card">
      <h2>用户列表</h2>
      <button class="btn secondary" @click="loadUsers">刷新</button>
      <table class="table">
        <thead>
          <tr>
            <th>ID</th>
            <th>用户名</th>
            <th>角色</th>
            <th>状态</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="user in users" :key="user.id">
            <td>{{ user.id }}</td>
            <td>{{ user.username }}</td>
            <td>{{ user.role }}</td>
            <td>{{ user.is_active ? 'active' : 'disabled' }}</td>
            <td>
              <button class="btn danger" @click="removeUser(user.id)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </article>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { apiRequest } from '../api/http'

const users = ref([])
const form = reactive({ username: '', password: '', role: 'user' })
const error = ref('')
const message = ref('')

async function loadUsers() {
  error.value = ''
  users.value = await apiRequest('/users')
}

async function createUser() {
  error.value = ''
  message.value = ''
  try {
    await apiRequest('/users', {
      method: 'POST',
      body: JSON.stringify(form),
    })
    message.value = '用户创建成功'
    form.username = ''
    form.password = ''
    form.role = 'user'
    await loadUsers()
  } catch (err) {
    error.value = err.message || '创建失败'
  }
}

async function removeUser(userId) {
  error.value = ''
  message.value = ''
  try {
    await apiRequest(`/users/${userId}`, { method: 'DELETE' })
    message.value = '用户删除成功'
    await loadUsers()
  } catch (err) {
    error.value = err.message || '删除失败'
  }
}

onMounted(loadUsers)
</script>
