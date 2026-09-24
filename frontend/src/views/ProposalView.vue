<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { renderMarkdown } from '../markdown'
import { fullDate, timeAgo } from '../format'
import { anchorFromSelection, quoteFound, stripWhitespace } from '../anchors'
import { useComments } from '../useComments'
import CommentPanel from '../components/CommentPanel.vue'
import DocRendered from '../components/DocRendered.vue'
import DocSource from '../components/DocSource.vue'

const route = useRoute()
const router = useRouter()

const proposal = ref(null)
const loading = ref(true)
const error = ref('')
const pending = ref(null) // anchor being commented on: { quote, line_start, line_end }
const selection = ref(null) // { anchor, top, left } for the floating "Comment" button
const docArea = ref(null)
const rendered = ref(null)
const source = ref(null)
const panel = ref(null)

const path = computed(() => route.params.path)
const store = useComments(path)
const html = computed(() => (proposal.value ? renderMarkdown(proposal.value.content, proposal.value.path) : ''))

// The URL holds the view and the active thread, so links to a thread can be shared.
const view = computed(() => (route.query.view === 'source' ? 'source' : 'rendered'))
const activeId = computed(() => Number(route.query.thread) || null)
const setQuery = (patch) => router.replace({ query: { ...route.query, ...patch } })
const currentDoc = () => (view.value === 'source' ? source.value : rendered.value)

// Waits for the URL (and so the active view) to update, then scrolls the target into view.
async function revealAfter(navigation, target) {
  await navigation
  await nextTick()
  if (target) currentDoc()?.reveal(target)
}

function activate(id, { scroll = false } = {}) {
  if (id) pending.value = null // clicking empty space clears the active thread, not a half-written comment
  revealAfter(setQuery({ thread: id ? String(id) : undefined }), scroll && id)
}

function setView(v) {
  revealAfter(setQuery({ view: v === 'source' ? 'source' : undefined }), pending.value ?? activeId.value)
}

// A thread is outdated when its line is past the end of the file, or its quoted
// text is in neither the rendered text nor the source any more.
const haystacks = computed(() => {
  if (!proposal.value) return []
  const t = document.createElement('template')
  t.innerHTML = html.value
  return [stripWhitespace(t.content.textContent), stripWhitespace(proposal.value.content)]
})
const outdatedIds = computed(() => {
  const lineCount = proposal.value?.content.split('\n').length ?? 0
  return new Set(
    store.threads
      .filter((t) => t.line_start && (t.line_start > lineCount || !quoteFound(haystacks.value, t.quote)))
      .map((t) => t.id),
  )
})

async function load() {
  loading.value = true
  error.value = ''
  proposal.value = null
  pending.value = null
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

// Deep link (?thread=12): once the document and comments are in, scroll to it.
watch(
  () => !loading.value && !store.loading && proposal.value,
  async (ready) => {
    if (!ready || !activeId.value) return
    await nextTick()
    currentDoc()?.reveal(activeId.value)
  },
)

function compose(anchor) {
  pending.value = anchor
  setQuery({ thread: undefined })
  panel.value?.focusComposer()
}

function onPosted(created) {
  pending.value = null
  setQuery({ thread: String(created.id) })
}

function captureSelection() {
  const sel = window.getSelection()
  const anchor = anchorFromSelection(docArea.value, sel)
  if (!anchor) {
    selection.value = null
    return
  }
  const rect = sel.getRangeAt(0).getBoundingClientRect()
  selection.value = {
    anchor,
    top: rect.top + window.scrollY - 44,
    left: Math.max(8, rect.left + window.scrollX + rect.width / 2 - 60),
  }
}

function commentOnSelection() {
  const { anchor } = selection.value
  selection.value = null
  window.getSelection()?.removeAllRanges()
  compose(anchor)
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
          <div class="doc-meta">
            <span class="doc-path">{{ proposal.path }}</span>
            <span class="muted" :title="fullDate(proposal.modified)">Updated {{ timeAgo(proposal.modified) }}</span>
          </div>
          <div class="segmented" role="tablist" aria-label="View">
            <button role="tab" :aria-selected="view === 'rendered'" :class="{ on: view === 'rendered' }" @click="setView('rendered')">
              Rendered
            </button>
            <button role="tab" :aria-selected="view === 'source'" :class="{ on: view === 'source' }" @click="setView('source')">
              Source
            </button>
          </div>
        </header>

        <div ref="docArea" @mouseup="captureSelection" @keyup="captureSelection">
          <DocRendered
            v-show="view === 'rendered'"
            ref="rendered"
            :html="html"
            :threads="store.sorted"
            :active-id="activeId"
            :pending="pending"
            @activate="activate"
            @compose="compose"
          />
          <DocSource
            v-if="view === 'source'"
            ref="source"
            :content="proposal.content"
            :threads="store.sorted"
            :active-id="activeId"
            :pending="pending"
            @activate="activate"
            @compose="compose"
          />
        </div>

        <p class="hint muted">
          Select text, or hover a block and click <strong>+</strong>, to comment inline.
          Switch to <strong>Source</strong> to see exact line numbers.
        </p>
      </article>

      <CommentPanel
        ref="panel"
        :store="store"
        :active-id="activeId"
        :pending="pending"
        :outdated-ids="outdatedIds"
        @activate="(id) => activate(id, { scroll: true })"
        @clear-pending="pending = null"
        @posted="onPosted"
      />
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
