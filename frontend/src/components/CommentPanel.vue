<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { author } from '../author'
import { lineLabel } from '../anchors'
import CommentThread from './CommentThread.vue'

const props = defineProps({
  store: { type: Object, required: true },
  activeId: { type: Number, default: null },
  pending: { type: Object, default: null },
  outdatedIds: { type: Set, required: true },
  liveLines: { type: Map, default: null },
})
const emit = defineEmits(['activate', 'clear-pending', 'posted'])

const tab = ref('open')
const body = ref('')
const submitting = ref(false)
const error = ref('')
const nameError = ref(false)
const textarea = ref(null)
const nameInput = ref(null)
const list = ref(null)

const visible = computed(() => (tab.value === 'open' ? props.store.open : props.store.resolved))
const total = computed(() => props.store.threads.reduce((n, t) => n + 1 + t.replies.length, 0))

function needName() {
  nameError.value = true
  nameInput.value?.focus()
}

async function submit() {
  if (!body.value.trim()) return
  if (!author.value.trim()) return needName()
  submitting.value = true
  error.value = ''
  try {
    const created = await props.store.addThread({ author: author.value, body: body.value, anchor: props.pending })
    body.value = ''
    tab.value = 'open'
    emit('posted', created)
  } catch (e) {
    error.value = e.message
  } finally {
    submitting.value = false
  }
}

function onKeydown(event) {
  if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) submit()
}

async function focusComposer() {
  await nextTick()
  textarea.value?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  textarea.value?.focus({ preventScroll: true })
}

// Bring a thread into view, switching to the tab it's on.
async function showThread(id) {
  const thread = id && props.store.find(id)
  if (!thread) return
  tab.value = thread.resolved ? 'resolved' : 'open'
  await nextTick()
  list.value?.querySelector(`[data-thread="${id}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
}

watch(() => props.activeId, showThread)
watch(author, (name) => name.trim() && (nameError.value = false))

defineExpose({ focusComposer })
</script>

<template>
  <aside class="comments">
    <div class="panel-head">
      <h2>Comments <span class="count">{{ total }}</span></h2>
      <div class="tabs" role="tablist">
        <button role="tab" :aria-selected="tab === 'open'" :class="{ on: tab === 'open' }" @click="tab = 'open'">
          Open <span class="count">{{ store.open.length }}</span>
        </button>
        <button role="tab" :aria-selected="tab === 'resolved'" :class="{ on: tab === 'resolved' }" @click="tab = 'resolved'">
          Resolved <span class="count">{{ store.resolved.length }}</span>
        </button>
      </div>
    </div>

    <label class="name-field" :class="{ invalid: nameError }">
      <span>Your name</span>
      <input ref="nameInput" v-model="author" maxlength="100" placeholder="Required to comment" />
    </label>
    <p v-if="nameError" class="notice error small">Enter your name first.</p>

    <form class="comment-form" @submit.prevent="submit">
      <div v-if="pending" class="quote-preview">
        <div class="quote-label">
          Commenting on {{ lineLabel(pending).toLowerCase() }}
          <button type="button" class="link-btn" @click="emit('clear-pending')">Cancel</button>
        </div>
        <blockquote v-if="pending.quote" class="comment-quote">{{ pending.quote }}</blockquote>
      </div>
      <textarea
        ref="textarea"
        v-model="body"
        rows="3"
        maxlength="5000"
        :placeholder="pending ? 'Comment on this passage...' : 'Leave a general comment...'"
        aria-label="Comment"
        @keydown="onKeydown"
      />
      <p v-if="error" class="notice error small">{{ error }}</p>
      <div class="form-actions">
        <span class="muted small">Ctrl/⌘ + Enter to post</span>
        <button class="btn btn-primary" :disabled="submitting || !body.trim()">
          {{ submitting ? 'Posting...' : 'Post comment' }}
        </button>
      </div>
    </form>

    <p v-if="store.error" class="notice error small">Could not load comments: {{ store.error }}</p>
    <p v-else-if="store.loading" class="muted">Loading comments...</p>
    <p v-else-if="!visible.length" class="muted empty-list">
      {{ tab === 'open' ? 'No open comments.' : 'No resolved comments.' }}
    </p>

    <div ref="list" class="thread-list">
      <CommentThread
        v-for="t in visible"
        :key="t.id"
        :thread="t"
        :store="store"
        :active="t.id === activeId"
        :outdated="outdatedIds.has(t.id)"
        :live="liveLines?.get(t.id) ?? null"
        @activate="emit('activate', $event)"
        @need-name="needName"
        @reopened="showThread"
      />
    </div>
  </aside>
</template>
