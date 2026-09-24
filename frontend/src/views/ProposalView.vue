<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { renderMarkdown } from '../markdown'
import { fullDate, timeAgo } from '../format'
import CommentPanel from '../components/CommentPanel.vue'

const route = useRoute()
const router = useRouter()

const proposal = ref(null)
const loading = ref(true)
const error = ref('')
const quote = ref('')
const article = ref(null)
const panel = ref(null)
const selection = ref(null) // { text, top, left } for the floating "Comment" button

const path = computed(() => route.params.path)
const html = computed(() => (proposal.value ? renderMarkdown(proposal.value.content, proposal.value.path) : ''))

async function load() {
  loading.value = true
  error.value = ''
  proposal.value = null
  quote.value = ''
  selection.value = null
  try {
    proposal.value = await api.getProposal(path.value)
    document.title = `${proposal.value.title} · Proposal Presenter`
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function captureSelection() {
  const sel = window.getSelection()
  const text = sel?.toString().trim()
  if (!text || !article.value || !article.value.contains(sel.anchorNode)) {
    selection.value = null
    return
  }
  const rect = sel.getRangeAt(0).getBoundingClientRect()
  selection.value = {
    text: text.slice(0, 2000),
    top: rect.top + window.scrollY - 44,
    left: Math.max(8, rect.left + window.scrollX + rect.width / 2 - 60),
  }
}

function commentOnSelection() {
  quote.value = selection.value.text
  selection.value = null
  window.getSelection()?.removeAllRanges()
  panel.value?.focus()
}

// Links to other proposals are rendered as plain <a href="/p/...">; route them in-app.
function onArticleClick(event) {
  const link = event.target.closest('a')
  const href = link?.getAttribute('href')
  if (href?.startsWith('/p/') && !event.metaKey && !event.ctrlKey && event.button === 0) {
    event.preventDefault()
    router.push(href)
  }
}

function clearSelectionIfEmpty() {
  if (!window.getSelection()?.toString().trim()) selection.value = null
}

watch(path, load)
onMounted(() => {
  load()
  document.addEventListener('selectionchange', clearSelectionIfEmpty)
})
onBeforeUnmount(() => {
  document.removeEventListener('selectionchange', clearSelectionIfEmpty)
  document.title = 'Proposal Presenter'
})
</script>

<template>
  <div class="page">
    <RouterLink to="/" class="back">&larr; All proposals</RouterLink>

    <p v-if="loading" class="muted">Loading...</p>
    <div v-else-if="error" class="notice error">
      <strong>Could not open this proposal.</strong> {{ error }}
    </div>

    <div v-else class="proposal-layout">
      <article class="doc">
        <header class="doc-header">
          <div class="muted doc-path">{{ proposal.path }}</div>
          <div class="muted" :title="fullDate(proposal.modified)">Updated {{ timeAgo(proposal.modified) }}</div>
        </header>
        <div
          ref="article"
          class="markdown-body"
          v-html="html"
          @mouseup="captureSelection"
          @keyup="captureSelection"
          @click="onArticleClick"
        />
        <p class="hint muted">Tip: select any text in the proposal to comment on that part.</p>
      </article>

      <CommentPanel ref="panel" :path="proposal.path" v-model:quote="quote" />
    </div>

    <button
      v-if="selection"
      class="btn btn-primary floating-comment"
      :style="{ top: `${selection.top}px`, left: `${selection.left}px` }"
      @mousedown.prevent
      @click="commentOnSelection"
    >
      Comment
    </button>
  </div>
</template>
