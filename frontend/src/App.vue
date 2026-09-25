<script setup>
import { onMounted } from 'vue'
import { session } from './session'

onMounted(() => session.refresh())
</script>

<template>
  <header class="topbar">
    <div class="topbar-inner">
      <RouterLink to="/" class="brand">
        <svg viewBox="0 0 32 32" aria-hidden="true">
          <rect width="32" height="32" rx="7" />
          <path d="M10 8h8l5 5v11a1 1 0 0 1-1 1H10a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z" />
        </svg>
        Proposal Presenter
      </RouterLink>
      <div v-if="session.signedIn" class="session-pill">
        <span class="dot" aria-hidden="true" />
        Signed in as editor
        <button class="link-btn" @click="session.signOut()">Sign out</button>
      </div>
    </div>
  </header>
  <main>
    <RouterView />
  </main>
</template>
