import { reactive } from 'vue'
import { api } from './api'
import { author } from './author'

// Editor sign-in state. `enabled` is false when the server has no EDIT_PASSWORD_HASH.
// `username` is null when signed in with the shared editor password.
export const session = reactive({
  enabled: false,
  signedIn: false,
  username: null,

  async refresh() {
    try {
      this.apply(await api.authStatus())
    } catch {
      // leave editing hidden if the status can't be read
    }
  },

  async signIn(username, password) {
    this.apply(await api.signIn(username, password))
  },

  async register(username, password, code) {
    this.apply(await api.register(username, password, code))
  },

  async signOut() {
    this.apply(await api.signOut())
  },

  apply(s) {
    Object.assign(this, { enabled: s.enabled, signedIn: s.signed_in, username: s.username ?? null })
    // Comment as yourself by default.
    if (this.username && !author.value.trim()) author.value = this.username
  },
})
