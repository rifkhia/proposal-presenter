<script setup>
import { nextTick, ref, watch } from 'vue'
import { api } from '../api'
import { fullDate, timeAgo } from '../format'

const props = defineProps({ path: { type: String, required: true } })
const quote = defineModel('quote', { type: String, default: '' })

const AUTHOR_KEY = 'proposal-presenter:author'
const readAuthor = () => {
  try {
    return localStorage.getItem(AUTHOR_KEY) || ''
  } catch {
    return ''
  }
}

const comments = ref([])
const loading = ref(true)
const error = ref('')
const author = ref(readAuthor())
const body = ref('')
const submitting = ref(false)
const textarea = ref(null)

async function load() {
  loading.value = true
  error.value = ''
  try {
    comments.value = await api.listComments(props.path)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (!author.value.trim() || !body.value.trim()) return
  submitting.value = true
  error.value = ''
  try {
    const created = await api.addComment({
      proposal: props.path,
      author: author.value,
      body: body.value,
      quote: quote.value || null,
    })
    comments.value.push(created)
    body.value = ''
    quote.value = ''
    try {
      localStorage.setItem(AUTHOR_KEY, author.value.trim())
    } catch {
      // storage unavailable (private mode); the name just won't be remembered
    }
  } catch (e) {
    error.value = e.message
  } finally {
    submitting.value = false
  }
}

async function remove(comment) {
  if (!confirm(`Delete this comment by ${comment.author}?`)) return
  try {
    await api.deleteComment(comment.id)
    comments.value = comments.value.filter((c) => c.id !== comment.id)
  } catch (e) {
    error.value = e.message
  }
}

function onKeydown(event) {
  if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) submit()
}

async function focus() {
  await nextTick()
  textarea.value?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  textarea.value?.focus({ preventScroll: true })
}

defineExpose({ focus })
watch(() => props.path, load, { immediate: true })
</script>

<template>
  <aside class="comments">
    <h2>
      Comments <span class="count">{{ comments.length }}</span>
    </h2>

    <p v-if="loading" class="muted">Loading comments...</p>
    <p v-else-if="comments.length === 0" class="muted">No comments yet. Be the first.</p>

    <ol v-else class="comment-list">
      <li v-for="c in comments" :key="c.id" class="comment">
        <div class="comment-head">
          <span class="avatar" aria-hidden="true">{{ c.author.charAt(0).toUpperCase() }}</span>
          <strong>{{ c.author }}</strong>
          <span class="muted" :title="fullDate(c.created_at)">{{ timeAgo(c.created_at) }}</span>
          <button class="link-btn" @click="remove(c)" title="Delete comment">Delete</button>
        </div>
        <blockquote v-if="c.quote" class="comment-quote">{{ c.quote }}</blockquote>
        <p class="comment-body">{{ c.body }}</p>
      </li>
    </ol>

    <form class="comment-form" @submit.prevent="submit">
      <div v-if="quote" class="quote-preview">
        <div class="quote-label">
          Commenting on
          <button type="button" class="link-btn" @click="quote = ''">Remove</button>
        </div>
        <blockquote class="comment-quote">{{ quote }}</blockquote>
      </div>
      <input v-model="author" placeholder="Your name" maxlength="100" required aria-label="Your name" />
      <textarea
        ref="textarea"
        v-model="body"
        rows="4"
        maxlength="5000"
        placeholder="Write a comment..."
        required
        aria-label="Comment"
        @keydown="onKeydown"
      />
      <p v-if="error" class="notice error">{{ error }}</p>
      <div class="form-actions">
        <span class="muted small">Ctrl/⌘ + Enter to post</span>
        <button class="btn btn-primary" :disabled="submitting || !author.trim() || !body.trim()">
          {{ submitting ? 'Posting...' : 'Post comment' }}
        </button>
      </div>
    </form>
  </aside>
</template>
