import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  { path: '/login', component: () => import('@/views/Login.vue'), meta: { public: true } },
  { path: '/screen', component: () => import('@/views/Screen.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('@/views/Layout.vue'),
    redirect: '/dashboard',
    children: [
      { path: 'dashboard',  name: 'dashboard',  component: () => import('@/views/Dashboard.vue'), meta: { role: 'admin' } },
      { path: 'knowledge',  name: 'knowledge',  component: () => import('@/views/Knowledge.vue'), meta: { role: 'viewer' } },
      { path: 'reviews',    name: 'reviews',    component: () => import('@/views/ReviewWorkbench.vue'), meta: { role: 'admin' } },
      { path: 'changelog',  name: 'changelog',  component: () => import('@/views/ChangeLog.vue'), meta: { role: 'admin' } },
      { path: 'tasks',      name: 'tasks',      component: () => import('@/views/Tasks.vue'), meta: { role: 'admin' } },
      { path: 'alerts',     name: 'alerts',     component: () => import('@/views/Alerts.vue'), meta: { role: 'admin' } },
      { path: 'settings',   name: 'settings',   component: () => import('@/views/Settings.vue'), meta: { role: 'admin' } },
      { path: 'documents',  name: 'documents',  component: () => import('@/views/Documents.vue'), meta: { role: 'viewer' } },
      { path: 'official-sources', name: 'official-sources', component: () => import('@/views/OfficialSources.vue'), meta: { role: 'admin' } },
      { path: 'research',   name: 'research',   component: () => import('@/views/Research.vue'), meta: { role: 'viewer' } },
      { path: 'llm-channels', name: 'llm-channels', component: () => import('@/views/LlmChannels.vue'), meta: { role: 'admin' } },
      { path: 'models',     name: 'models',     component: () => import('@/views/Models.vue'), meta: { role: 'admin' } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.token) return '/login'
  if (to.meta.role === 'admin' && auth.role !== 'admin') return '/knowledge'
})

export default router
