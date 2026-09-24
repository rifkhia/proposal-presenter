<script setup>
import { fullDate, timeAgo } from '../format'

defineProps({ comment: { type: Object, required: true } })
defineEmits(['delete'])
</script>

<template>
  <div class="comment">
    <div class="comment-head">
      <span class="avatar" aria-hidden="true">{{ comment.author.charAt(0).toUpperCase() }}</span>
      <strong>{{ comment.author }}</strong>
      <span class="muted" :title="fullDate(comment.created_at)">{{ timeAgo(comment.created_at) }}</span>
      <button class="link-btn danger" title="Delete" @click="$emit('delete')">Delete</button>
    </div>
    <p class="comment-body">{{ comment.body }}</p>
  </div>
</template>
