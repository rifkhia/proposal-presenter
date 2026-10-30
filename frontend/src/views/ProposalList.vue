<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, encodePath } from '../api'
import { fullDate, timeAgo } from '../format'
import { session } from '../session'
import LoginDialog from '../components/LoginDialog.vue'
import UploadDialog from '../components/UploadDialog.vue'

const proposals = ref([])
const loading = ref(true)
const error = ref('')
const query = ref('')
const sort = ref('recent')
const login = ref(null)
const uploader = ref(null)
let afterSignIn = null

async function load() {
  loading.value = true
  error.value = ''
  try {
    proposals.value = await api.listProposals()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  const list = q
    ? proposals.value.filter((p) =>
        [p.title, p.path, p.excerpt].some((field) => field.toLowerCase().includes(q)),
      )
    : [...proposals.value]
  if (sort.value === 'title') list.sort((a, b) => a.title.localeCompare(b.title))
  else if (sort.value === 'comments') list.sort((a, b) => b.open_threads - a.open_threads || b.comment_count - a.comment_count)
  return list
})

// Suggestions for the upload dialog's folder field.
const folders = computed(() => [...new Set(proposals.value.map((p) => p.folder).filter(Boolean))].sort())

function requireSignIn(then, reason) {
  if (session.signedIn) return then()
  afterSignIn = then
  login.value.open(reason)
}

function onSignedIn() {
  const next = afterSignIn
  afterSignIn = null
  next?.()
}

// Set by ProposalView after deleting a proposal.
const deleted = ref(history.state?.deleted || '')
if (deleted.value) history.replaceState({ ...history.state, deleted: undefined }, '') // not again on reload

const startUpload = () => requireSignIn(() => uploader.value.open(), 'Uploading proposals requires signing in.')
const retryUpload = () => requireSignIn(() => uploader.value.submit(), 'Your session expired. Sign in again to upload.')

onMounted(load)
</script>

<template>
  <div class="page">
    <div class="list-header">
      <div>
        <h1>Proposals</h1>
        <p class="muted" v-if="!loading && !error">
          {{ proposals.length }} {{ proposals.length === 1 ? 'proposal' : 'proposals' }}
        </p>
      </div>
      <div class="list-controls">
        <input v-model="query" type="search" placeholder="Search proposals" aria-label="Search proposals" />
        <select v-model="sort" aria-label="Sort by">
          <option value="recent">Recently updated</option>
          <option value="title">Title</option>
          <option value="comments">Most open comments</option>
        </select>
        <button class="btn" @click="load" :disabled="loading" title="Reload list">Refresh</button>
        <button v-if="session.enabled" class="btn" @click="startUpload">Upload</button>
      </div>
    </div>

    <div v-if="deleted" class="notice success small save-notice">
      Deleted "{{ deleted }}". It was moved to the trash folder on the server, with its comments.
      <button class="link-btn" aria-label="Dismiss" @click="deleted = ''">Dismiss</button>
    </div>

    <p v-if="error" class="notice error">Could not load proposals: {{ error }}</p>
    <p v-else-if="loading" class="muted">Loading...</p>

    <div v-else-if="proposals.length === 0" class="empty">
      <h2>No proposals yet</h2>
      <p>
        Drop <code>.md</code> or <code>.html</code> files into the <code>proposals/</code> folder on the server and hit Refresh.
        Subfolders are supported.
      </p>
    </div>

    <p v-else-if="filtered.length === 0" class="muted">No proposals match "{{ query }}".</p>

    <ul v-else class="proposal-grid">
      <li v-for="p in filtered" :key="p.path">
        <RouterLink :to="`/p/${encodePath(p.path)}`" class="card">
          <div class="card-top">
            <span v-if="p.folder" class="tag">{{ p.folder }}</span>
            <span v-if="p.kind === 'html'" class="tag">HTML</span>
            <span class="file muted">{{ p.path.split('/').pop() }}</span>
          </div>
          <h2>{{ p.title }}</h2>
          <p v-if="p.excerpt" class="excerpt">{{ p.excerpt }}</p>
          <div class="card-meta muted">
            <span :title="fullDate(p.modified)">Updated {{ timeAgo(p.modified) }}</span>
            <span class="comment-count" :title="`${p.comment_count} comments, ${p.open_threads} open threads`">
              <span v-if="p.open_threads" class="open-pill">{{ p.open_threads }} open</span>
              <svg viewBox="0 0 20 20" aria-hidden="true">
                <path d="M3 4.5A1.5 1.5 0 0 1 4.5 3h11A1.5 1.5 0 0 1 17 4.5v8a1.5 1.5 0 0 1-1.5 1.5H8l-4 3v-3h0A1.5 1.5 0 0 1 3 12.5z" />
              </svg>
              {{ p.comment_count }}
            </span>
          </div>
        </RouterLink>
      </li>
    </ul>

    <LoginDialog ref="login" @signed-in="onSignedIn" />
    <UploadDialog ref="uploader" :folders="folders" @need-sign-in="retryUpload" />
  </div>
</template>
