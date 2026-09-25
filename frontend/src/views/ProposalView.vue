<script setup>
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { renderMarkdown } from '../markdown'
import { fullDate, timeAgo } from '../format'
import { anchorFromSelection, quoteFound, stripWhitespace } from '../anchors'
import { session } from '../session'
import { useComments } from '../useComments'
import CommentPanel from '../components/CommentPanel.vue'
import DocRendered from '../components/DocRendered.vue'
import DocSource from '../components/DocSource.vue'
import LoginDialog from '../components/LoginDialog.vue'

// The editor (CodeMirror) is loaded only when someone actually edits.
const ProposalEditor = defineAsyncComponent(() => import('../components/ProposalEditor.vue'))

const route = useRoute()
const router = useRouter()

const proposal = ref(null)
const loading = ref(true)
const error = ref('')
const pending = ref(null) // anchor being commented on: { quote, line_start, line_end, version }
const selection = ref(null) // { anchor, top, left } for the floating "Comment" button
const docArea = ref(null)
const rendered = ref(null)
const source = ref(null)
const editor = ref(null)
const panel = ref(null)
const login = ref(null)

// Edit mode
const editing = ref(false)
const dirty = ref(false)
const saving = ref(false)
const saveError = ref('')
const conflict = ref(false)
const notice = ref('')
const liveLines = ref(null) // thread id -> lines in the unsaved text, while editing
let afterSignIn = null

const path = computed(() => route.params.path)
const store = useComments(path)
const html = computed(() => (proposal.value ? renderMarkdown(proposal.value.content, proposal.value.path) : ''))

// The URL holds the view and the active thread, so links to a thread can be shared.
const view = computed(() => (route.query.view === 'source' ? 'source' : 'rendered'))
const activeId = computed(() => Number(route.query.thread) || null)
const setQuery = (patch) => router.replace({ query: { ...route.query, ...patch } })
const currentDoc = () => (editing.value ? editor.value : view.value === 'source' ? source.value : rendered.value)

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
  editing.value = false
  dirty.value = false
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
  pending.value = { ...anchor, version: proposal.value.version }
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

// ---- Editing ------------------------------------------------------------------------

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

function startEdit() {
  requireSignIn(() => {
    pending.value = null
    selection.value = null
    notice.value = ''
    saveError.value = ''
    conflict.value = false
    dirty.value = false
    liveLines.value = null
    editing.value = true
  })
}

function cancelEdit() {
  if (dirty.value && !confirm('Discard your changes?')) return
  editing.value = false
  dirty.value = false
  conflict.value = false
  saveError.value = ''
}

function describeSave({ moved, touched }) {
  const parts = ['Saved.']
  if (moved) parts.push(`${moved} comment ${moved === 1 ? 'thread' : 'threads'} moved with their text.`)
  if (touched) parts.push(`${touched} ${touched === 1 ? 'thread is' : 'threads are'} on lines you changed and may be outdated.`)
  return parts.join(' ')
}

async function save({ force = false } = {}) {
  if (saving.value || !editor.value) return
  saving.value = true
  saveError.value = ''
  try {
    const result = await api.saveProposal(proposal.value.path, editor.value.getContent(), proposal.value.version, force)
    proposal.value = result.proposal
    editing.value = false
    dirty.value = false
    conflict.value = false
    notice.value = describeSave(result.remap)
    await store.load() // line numbers were moved on the server
  } catch (e) {
    if (e.status === 401) {
      session.signedIn = false
      requireSignIn(() => save({ force }), 'Your session expired. Sign in again to save your changes.')
    } else if (e.status === 409) {
      conflict.value = true
    } else {
      saveError.value = e.message
    }
  } finally {
    saving.value = false
  }
}

async function discardAndReload() {
  dirty.value = false
  await load()
  await store.load()
}

const confirmLeave = () => !dirty.value || confirm('You have unsaved changes. Leave without saving?')
onBeforeRouteLeave(confirmLeave)
onBeforeRouteUpdate((to, from) => (to.path === from.path ? true : confirmLeave()))

function onBeforeUnload(event) {
  if (!dirty.value) return
  event.preventDefault()
  event.returnValue = ''
}

watch(path, load)
onMounted(() => {
  load()
  document.addEventListener('selectionchange', clearSelectionIfEmpty)
  window.addEventListener('beforeunload', onBeforeUnload)
})
onBeforeUnmount(() => {
  document.removeEventListener('selectionchange', clearSelectionIfEmpty)
  window.removeEventListener('beforeunload', onBeforeUnload)
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
      <article class="doc" :class="{ editing }">
        <header v-if="!editing" class="doc-header">
          <div class="doc-meta">
            <span class="doc-path">{{ proposal.path }}</span>
            <span class="muted" :title="fullDate(proposal.modified)">Updated {{ timeAgo(proposal.modified) }}</span>
          </div>
          <div class="doc-actions">
            <button
              v-if="session.enabled"
              class="btn btn-sm"
              :disabled="!proposal.writable"
              :title="proposal.writable ? 'Edit this proposal' : 'The proposals folder is read-only for the app (see README: Editing)'"
              @click="startEdit"
            >
              <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M11 2.5l2.5 2.5L6 12.5H3.5V10z" /></svg>
              Edit
            </button>
            <div class="segmented" role="tablist" aria-label="View">
              <button role="tab" :aria-selected="view === 'rendered'" :class="{ on: view === 'rendered' }" @click="setView('rendered')">
                Rendered
              </button>
              <button role="tab" :aria-selected="view === 'source'" :class="{ on: view === 'source' }" @click="setView('source')">
                Source
              </button>
            </div>
          </div>
        </header>

        <header v-else class="doc-header edit-toolbar">
          <div class="doc-meta">
            <strong>Editing</strong>
            <span class="doc-path">{{ proposal.path }}</span>
            <span v-if="dirty" class="badge unsaved">Unsaved changes</span>
          </div>
          <div class="doc-actions">
            <button class="btn btn-sm" :disabled="saving" @click="cancelEdit">Cancel</button>
            <button class="btn btn-sm btn-primary" :disabled="saving || !dirty" @click="save()">
              {{ saving ? 'Saving...' : 'Save' }}
            </button>
          </div>
        </header>

        <div v-if="notice && !editing" class="notice success small save-notice">
          {{ notice }}
          <button class="link-btn" aria-label="Dismiss" @click="notice = ''">Dismiss</button>
        </div>

        <template v-if="editing">
          <div v-if="conflict" class="notice error small conflict">
            <strong>Someone else changed this proposal since you started editing.</strong>
            Saving now would overwrite their version.
            <div class="conflict-actions">
              <button class="btn btn-sm" @click="discardAndReload">Discard mine, load theirs</button>
              <button class="btn btn-sm btn-danger" @click="save({ force: true })">Overwrite with mine</button>
            </div>
          </div>
          <p v-if="saveError" class="notice error small">Could not save: {{ saveError }}</p>
          <ProposalEditor
            ref="editor"
            :content="proposal.content"
            :threads="store.sorted"
            :active-id="activeId"
            @activate="activate"
            @dirty="dirty = $event"
            @lines="liveLines = $event"
            @save="dirty && save()"
          />
          <p class="hint muted">
            Highlighted lines have open comments. Hover a bubble to read it, click it to open the thread.
            An orange bubble means you changed a commented line. <strong>Ctrl/⌘ + S</strong> saves.
          </p>
        </template>

        <template v-else>
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
        </template>
      </article>

      <CommentPanel
        ref="panel"
        :store="store"
        :active-id="activeId"
        :pending="pending"
        :outdated-ids="outdatedIds"
        :live-lines="editing ? liveLines : null"
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

    <LoginDialog ref="login" @signed-in="onSignedIn" />
  </div>
</template>
