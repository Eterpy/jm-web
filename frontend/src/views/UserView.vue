<template>
  <section class="grid-2">
    <article class="card">
      <h2>禁漫账号登录</h2>
      <div v-if="jmBound && !editingJmAccount" class="status-card">
        <p class="ok">已登录账号：{{ currentJmUsername }}</p>
        <button class="btn secondary" @click="editingJmAccount = true">更换账号</button>
      </div>
      <form v-else class="form-grid" @submit.prevent="saveJmAccount">
        <label>
          <span>JM 用户名</span>
          <input v-model="jm.username" required />
        </label>
        <label>
          <span>JM 密码</span>
          <input v-model="jm.password" type="password" required />
        </label>
        <div class="row">
          <button class="btn">{{ jmBound ? '更新并保存' : '验证并保存' }}</button>
          <button v-if="jmBound" type="button" class="btn secondary" @click="cancelEditJm">取消</button>
        </div>
      </form>

      <h2>通过 ID 下载</h2>
      <form class="form-grid" @submit.prevent="createDownloadJob">
        <label>
          <span>类型</span>
          <select v-model="downloadForm.target_type">
            <option value="album">单本子 album</option>
            <option value="photo">单章节 photo</option>
            <option value="multi_album">多个本子 multi_album</option>
          </select>
        </label>

        <label v-if="downloadForm.target_type !== 'multi_album'">
          <span>ID（photo可填 p123）</span>
          <input v-model="downloadForm.id_value" required />
        </label>

        <label v-else>
          <span>多个本子ID（逗号分隔）</span>
          <input v-model="downloadForm.album_ids_text" placeholder="123,456,789" required />
        </label>

        <button class="btn">创建下载任务</button>
      </form>
    </article>

    <article class="card">
      <h2>搜索本子并下载</h2>
      <form class="row" @submit.prevent="search">
        <input v-model="searchForm.keyword" placeholder="名称或ID" required />
        <button class="btn">搜索</button>
      </form>
      <ul class="list">
        <li v-for="item in searchResults" :key="item.album_id" class="list-item">
          <div>
            <strong>{{ item.album_id }}</strong> - {{ item.title }}
          </div>
          <button class="btn secondary" @click="downloadFromSearch(item.album_id)">下载</button>
        </li>
      </ul>

      <h2>可选功能</h2>
      <div class="row">
        <button class="btn secondary" @click="loadRanking">周排行</button>
        <button class="btn secondary" @click="loadFavorites">收藏夹</button>
      </div>
      <ul class="list">
        <li v-for="item in auxList" :key="`aux-${item.album_id}-${item.title}`">{{ item.album_id }} - {{ item.title }}</li>
      </ul>
    </article>

    <article class="card full">
      <h2>任务列表</h2>
      <div class="row">
        <button class="btn secondary" @click="loadJobs">刷新任务</button>
        <button class="btn secondary" @click="clearFailedExpiredJobs">清除失败/失效任务</button>
      </div>
      <table class="table">
        <thead>
          <tr>
            <th>ID</th>
            <th>类型</th>
            <th>状态</th>
            <th>过期时间</th>
            <th>错误</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="job in jobs" :key="job.id">
            <td>{{ job.id }}</td>
            <td>{{ job.job_type }}</td>
            <td>{{ job.status }}</td>
            <td>{{ job.expires_at || '-' }}</td>
            <td>{{ job.error_message || '-' }}</td>
            <td>
              <div class="row">
                <button class="btn" :disabled="job.status !== 'done'" @click="downloadJob(job.id)">下载</button>
                <button class="btn danger" :disabled="!canCancel(job.status)" @click="cancelJob(job.id)">中止</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="message" class="ok">{{ message }}</p>
      <p v-if="error" class="error">{{ error }}</p>
    </article>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { apiRequest, buildApiPath } from '../api/http'
import { authState, refreshMe } from '../stores/auth'

const jm = reactive({ username: '', password: '' })
const downloadForm = reactive({ target_type: 'album', id_value: '', album_ids_text: '' })
const searchForm = reactive({ keyword: '' })

const jobs = ref([])
const searchResults = ref([])
const auxList = ref([])

const message = ref('')
const error = ref('')
const editingJmAccount = ref(false)

const jmBound = computed(() => Boolean(authState.me?.jm_credential_bound))
const currentJmUsername = computed(() => authState.me?.jm_username || '')

function syncJmFormWithState() {
  jm.username = currentJmUsername.value || ''
  jm.password = ''
}

function cancelEditJm() {
  editingJmAccount.value = false
  syncJmFormWithState()
}

async function saveJmAccount() {
  error.value = ''
  message.value = ''
  try {
    await apiRequest('/jobs/jm-login', {
      method: 'POST',
      body: JSON.stringify({
        username: jm.username,
        password: jm.password,
        save_to_user: true,
      }),
    })
    await refreshMe()
    syncJmFormWithState()
    editingJmAccount.value = false
    message.value = 'JM 账号验证成功并已保存'
  } catch (err) {
    error.value = err.message || 'JM 登录失败'
  }
}

async function createDownloadJob() {
  error.value = ''
  message.value = ''
  try {
    const body = {
      target_type: downloadForm.target_type,
      id_value: downloadForm.id_value || null,
      album_ids: null,
    }

    if (downloadForm.target_type === 'multi_album') {
      body.album_ids = downloadForm.album_ids_text.split(',').map((x) => x.trim()).filter(Boolean)
      body.id_value = null
    }

    await apiRequest('/jobs/download-by-id', {
      method: 'POST',
      body: JSON.stringify(body),
    })

    message.value = '下载任务已创建'
    await loadJobs()
  } catch (err) {
    error.value = err.message || '创建下载任务失败'
  }
}

async function search() {
  error.value = ''
  message.value = ''
  try {
    searchResults.value = await apiRequest('/jobs/search', {
      method: 'POST',
      body: JSON.stringify({ keyword: searchForm.keyword, page: 1 }),
    })
  } catch (err) {
    error.value = err.message || '搜索失败'
  }
}

async function downloadFromSearch(albumId) {
  error.value = ''
  message.value = ''
  try {
    await apiRequest(`/jobs/download-from-search/${albumId}`, { method: 'POST' })
    message.value = `已创建下载任务 album ${albumId}`
    await loadJobs()
  } catch (err) {
    error.value = err.message || '创建任务失败'
  }
}

async function loadJobs() {
  jobs.value = await apiRequest('/jobs')
}

async function clearFailedExpiredJobs() {
  error.value = ''
  message.value = ''
  try {
    const result = await apiRequest('/jobs/clear-failed-expired', { method: 'DELETE' })
    message.value = `已清除 ${result.deleted_count} 条失败/失效任务`
    await loadJobs()
  } catch (err) {
    error.value = err.message || '清除任务失败'
  }
}

async function loadRanking() {
  error.value = ''
  auxList.value = []
  try {
    auxList.value = await apiRequest('/jobs/ranking/week?page=1')
  } catch (err) {
    error.value = err.message || '加载排行失败'
  }
}

async function loadFavorites() {
  error.value = ''
  auxList.value = []
  try {
    auxList.value = await apiRequest('/jobs/favorites?page=1')
  } catch (err) {
    error.value = err.message || '加载收藏夹失败'
  }
}

async function downloadJob(jobId) {
  error.value = ''
  message.value = ''
  try {
    const link = await apiRequest(`/jobs/${jobId}/download-link`)
    const cleanPath = link.download_url.startsWith('/api/v1')
      ? link.download_url.slice('/api/v1'.length)
      : link.download_url
    window.open(buildApiPath(cleanPath), '_blank')
  } catch (err) {
    error.value = err.message || '获取下载链接失败'
  }
}

function canCancel(status) {
  return ['queued', 'running', 'merging'].includes(status)
}

async function cancelJob(jobId) {
  error.value = ''
  message.value = ''
  try {
    await apiRequest(`/jobs/${jobId}/cancel`, { method: 'POST' })
    message.value = `任务 ${jobId} 已中止并清理`
    await loadJobs()
  } catch (err) {
    error.value = err.message || '中止任务失败'
  }
}

onMounted(async () => {
  await loadJobs()
  syncJmFormWithState()
})
</script>
