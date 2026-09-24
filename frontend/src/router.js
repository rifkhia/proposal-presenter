import { createRouter, createWebHistory } from 'vue-router'
import ProposalList from './views/ProposalList.vue'
import ProposalView from './views/ProposalView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'list', component: ProposalList },
    { path: '/p/:path(.*)', name: 'proposal', component: ProposalView },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior(to, from, saved) {
    if (saved) return saved
    if (to.hash) return { el: decodeURIComponent(to.hash), top: 80, behavior: 'smooth' }
    if (to.path !== from.path) return { top: 0 }
  },
})
