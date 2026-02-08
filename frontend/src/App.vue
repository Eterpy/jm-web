<template>
  <div class="layout">
    <header class="header" v-if="showHeader">
      <div class="title">JM Web</div>
      <div class="header-right">
        <span class="user">{{ authState.me?.username }} ({{ authState.me?.role }})</span>
        <button class="btn" @click="handleLogout">Logout</button>
      </div>
    </header>
    <main class="main">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { authState, logout } from './stores/auth'

const route = useRoute()
const router = useRouter()

const showHeader = computed(() => route.path !== '/login')

function handleLogout() {
  logout()
  router.push('/login')
}
</script>
