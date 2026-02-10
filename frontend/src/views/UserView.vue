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
          <span>{{ downloadForm.target_type === 'photo' ? '章节ID' : '本子ID' }}</span>
          <input v-model="downloadForm.id_value" :placeholder="singleIdPlaceholder" required />
          <small class="muted">
            {{ downloadForm.target_type === 'photo' ? '单章节请直接填数字ID，或粘贴 /photo/ 链接' : '单本子请填数字ID，或粘贴 /album/ 链接' }}
          </small>
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
      <form class="row search-row" @submit.prevent="search">
        <input v-model="searchForm.keyword" placeholder="名称或ID" required />
        <button class="btn">搜索</button>
        <button type="button" class="btn secondary" :disabled="searchResults.length === 0" @click="clearSearchResults">
          清除结果
        </button>
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
        <button class="btn secondary" @click="toggleRanking">{{ auxMode === 'ranking' ? '收起周排行' : '周排行' }}</button>
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
            <th>目标ID</th>
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
            <td>{{ formatTargetId(job.payload_json, job.job_type) }}</td>
            <td>{{ job.job_type }}</td>
            <td>{{ job.status }}</td>
            <td>{{ formatBeijingTime(job.expires_at) }}</td>
            <td>{{ job.error_message || '-' }}</td>
            <td>
              <div class="row">
                <button class="btn" :disabled="job.status !== 'done'" @click="downloadJob(job.id)">下载</button>
                <button class="btn danger" :disabled="!canCancel(job.status)" @click="cancelJob(job.id)">中止</button>
                <button class="btn secondary" @click="deleteJob(job.id)">删除</button>
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
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { apiRequest, buildApiPath } from '../api/http'
import { authState, refreshMe } from '../stores/auth'

const jm = reactive({ username: '', password: '' })
const downloadForm = reactive({ target_type: 'album', id_value: '', album_ids_text: '' })
const searchForm = reactive({ keyword: '' })

const jobs = ref([])
const searchResults = ref([])
const auxList = ref([])
const auxMode = ref(null)
const jobsLoading = ref(false)

const message = ref('')
const error = ref('')
const editingJmAccount = ref(false)
const JOB_POLL_INTERVAL_MS = 5000
const ACTIVE_POLL_STATUSES = new Set(['queued', 'running', 'merging'])
let jobsPollTimer = null

const jmBound = computed(() => Boolean(authState.me?.jm_credential_bound))
const currentJmUsername = computed(() => authState.me?.jm_username || '')
const singleIdPlaceholder = computed(() => {
  if (downloadForm.target_type === 'photo') {
    return '例如 413446 或 https://18comic.vip/photo/413446'
  }
  return '例如 350234 或 https://18comic.vip/album/350234'
})

const ALBUM_PATH_RE = /\/album\/(\d+)/i
const PHOTO_PATH_RE = /\/photo\/(\d+)/i

function normalizeSingleIdInput(targetType, rawValue) {
  const text = String(rawValue || '').trim()
  if (!text) {
    throw new Error('请输入 ID')
  }

  const albumMatch = text.match(ALBUM_PATH_RE)
  const photoMatch = text.match(PHOTO_PATH_RE)

  if (targetType === 'album') {
    if (photoMatch || /^p\d+$/i.test(text)) {
      throw new Error('检测到章节ID，请将类型切换为「单章节 photo」后重试')
    }
    if (albumMatch) {
      return albumMatch[1]
    }
    if (/^jm\d+$/i.test(text)) {
      return text.slice(2)
    }
    if (/^\d+$/.test(text)) {
      return text
    }
    throw new Error('本子ID格式不正确，请输入数字ID或 /album/ 链接')
  }

  if (targetType === 'photo') {
    if (albumMatch || /^jm\d+$/i.test(text)) {
      throw new Error('检测到本子ID，请将类型切换为「单本子 album」后重试')
    }
    if (photoMatch) {
      return photoMatch[1]
    }
    if (/^p\d+$/i.test(text)) {
      return text.slice(1)
    }
    if (/^\d+$/.test(text)) {
      return text
    }
    throw new Error('章节ID格式不正确，请输入数字ID或 /photo/ 链接')
  }

  return text
}

function normalizeMultiAlbumInput(rawText) {
  const values = String(rawText || '')
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean)
  if (values.length === 0) {
    throw new Error('请输入至少一个本子ID')
  }
  return values.map((value) => normalizeSingleIdInput('album', value))
}

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
    const existingIds = new Set(jobs.value.map((job) => job.id))
    const body = {
      target_type: downloadForm.target_type,
      id_value: downloadForm.id_value || null,
      album_ids: null,
    }

    if (downloadForm.target_type === 'multi_album') {
      body.album_ids = normalizeMultiAlbumInput(downloadForm.album_ids_text)
      body.id_value = null
    } else {
      body.id_value = normalizeSingleIdInput(downloadForm.target_type, downloadForm.id_value)
    }

    const createdOrReused = await apiRequest('/jobs/download-by-id', {
      method: 'POST',
      body: JSON.stringify(body),
    })

    message.value = existingIds.has(createdOrReused.id) ? `任务已存在，已复用（#${createdOrReused.id}）` : '下载任务已创建'
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

function clearSearchResults() {
  searchResults.value = []
}

async function downloadFromSearch(albumId) {
  error.value = ''
  message.value = ''
  try {
    const existingIds = new Set(jobs.value.map((job) => job.id))
    const createdOrReused = await apiRequest(`/jobs/download-from-search/${albumId}`, { method: 'POST' })
    message.value = existingIds.has(createdOrReused.id) ? `任务已存在，已复用（#${createdOrReused.id}）` : `已创建下载任务 album ${albumId}`
    await loadJobs()
  } catch (err) {
    error.value = err.message || '创建任务失败'
  }
}

async function loadJobs(options = {}) {
  const { silent = false } = options
  if (jobsLoading.value) {
    return
  }
  jobsLoading.value = true
  try {
    jobs.value = await apiRequest('/jobs')
  } catch (err) {
    if (!silent) {
      error.value = err.message || '加载任务列表失败'
    }
  } finally {
    jobsLoading.value = false
    syncJobsPolling()
  }
}

function hasActiveJobs() {
  return jobs.value.some((job) => ACTIVE_POLL_STATUSES.has(String(job.status || '').toLowerCase()))
}

function stopJobsPolling() {
  if (jobsPollTimer) {
    window.clearInterval(jobsPollTimer)
    jobsPollTimer = null
  }
}

function syncJobsPolling() {
  if (hasActiveJobs()) {
    if (!jobsPollTimer) {
      jobsPollTimer = window.setInterval(() => {
        loadJobs({ silent: true })
      }, JOB_POLL_INTERVAL_MS)
    }
    return
  }
  stopJobsPolling()
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
  try {
    auxList.value = await apiRequest('/jobs/ranking/week?page=1')
    auxMode.value = 'ranking'
  } catch (err) {
    error.value = err.message || '加载排行失败'
  }
}

async function toggleRanking() {
  if (auxMode.value === 'ranking') {
    auxList.value = []
    auxMode.value = null
    return
  }
  await loadRanking()
}

async function loadFavorites() {
  error.value = ''
  auxList.value = []
  try {
    auxList.value = await apiRequest('/jobs/favorites?page=1')
    auxMode.value = 'favorites'
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

function formatTargetId(payloadJson, jobType) {
  try {
    const payload = JSON.parse(payloadJson || '{}')
    if (jobType === 'multi_album') {
      const ids = Array.isArray(payload.album_ids) ? payload.album_ids.map((x) => String(x).trim()).filter(Boolean) : []
      return ids.length ? ids.join(', ') : '-'
    }
    const value = String(payload.id_value || '').trim()
    return value || '-'
  } catch (err) {
    return '-'
  }
}

function formatBeijingTime(value) {
  if (!value) {
    return '-'
  }
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) {
    return value
  }
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(dt)
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

async function deleteJob(jobId) {
  error.value = ''
  message.value = ''
  if (!window.confirm(`确认删除任务 ${jobId} 吗？已下载文件也会被清理。`)) {
    return
  }
  try {
    await apiRequest(`/jobs/${jobId}`, { method: 'DELETE' })
    message.value = `任务 ${jobId} 已删除`
    await loadJobs()
  } catch (err) {
    error.value = err.message || '删除任务失败'
  }
}

onMounted(async () => {
  await loadJobs()
  syncJmFormWithState()
})

onUnmounted(() => {
  stopJobsPolling()
})
</script>
