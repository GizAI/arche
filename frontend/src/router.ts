import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: () => import('@/views/Dashboard.vue'),
    },
    {
      path: '/logs',
      name: 'logs',
      component: () => import('@/views/Logs.vue'),
    },
    {
      path: '/journals',
      name: 'journals',
      component: () => import('@/views/Journals.vue'),
    },
    {
      path: '/plans',
      name: 'plans',
      component: () => import('@/views/Plans.vue'),
    },
    {
      path: '/feedback',
      name: 'feedback',
      component: () => import('@/views/Feedback.vue'),
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/views/Settings.vue'),
    },
  ],
})

export default router
