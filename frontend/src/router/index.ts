import { createRouter, createWebHashHistory } from 'vue-router'

const router = createRouter({
  // Hash history so routes work under any subpath or reverse proxy without extra config.
  history: createWebHashHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      redirect: '/library',
    },
    {
      path: '/library',
      name: 'library',
      component: () => import('../views/LibraryView.vue'),
    },
    {
      path: '/downloads',
      name: 'downloads',
      component: () => import('../views/DownloadsView.vue'),
    },
    {
      path: '/accounts',
      name: 'accounts',
      component: () => import('../views/AccountsView.vue'),
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('../views/SettingsView.vue'),
    },
  ],
})

export default router
