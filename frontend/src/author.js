import { ref, watch } from 'vue'

const KEY = 'proposal-presenter:author'

function read() {
  try {
    return localStorage.getItem(KEY) || ''
  } catch {
    return ''
  }
}

// One name for the whole app: used for comments, replies and resolving.
export const author = ref(read())

watch(author, (name) => {
  try {
    localStorage.setItem(KEY, name.trim())
  } catch {
    // storage unavailable (private mode); the name just won't be remembered
  }
})
