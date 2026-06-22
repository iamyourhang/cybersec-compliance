<template>
  <div class="layout">
    <!-- 侧边栏 -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <div class="brand-tag">CYBERSEC</div>
        <div class="brand-name">合规助手</div>
      </div>
      <nav class="nav">
        <router-link v-for="item in navItems" :key="item.path"
          :to="item.path" class="nav-item" active-class="nav-active">
          <span class="nav-icon">{{ item.icon }}</span>
          <span>{{ item.label }}</span>
        </router-link>
      </nav>
      <div class="sidebar-footer">
        <div class="user-info">
          <span class="user-dot"></span>
          <span class="user-name">{{ auth.username }}</span>
          <span class="role-badge" :title="auth.role">{{ roleLabel(auth.role) }}</span>
        </div>
        <button class="logout-btn" @click="logout">退出</button>
      </div>
    </aside>

    <!-- 主内容 -->
    <main class="main">
      <div class="page-header">
        <h1 class="page-title">{{ currentTitle }}</h1>
        <div class="page-time">{{ now }}</div>
      </div>
      <div class="page-body">
        <router-view />
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { roleLabel } from '@/utils/labels'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const allNavItems = [
  { path: '/dashboard', icon: '◈', label: '数据看板', adminOnly: true },
  { path: '/knowledge', icon: '◎', label: '合规知识库' },
  { path: '/reviews',   icon: '◩', label: '审核工作台', adminOnly: true },
  { path: '/changelog', icon: '◷', label: '变更日志', adminOnly: true },
  { path: '/tasks',     icon: '◆', label: '任务管理', adminOnly: true },
  { path: '/alerts',    icon: '◉', label: '预警规则', adminOnly: true },
  { path: '/settings',  icon: '◐', label: '系统设置', adminOnly: true },
  { path: '/documents', icon: '◧', label: '法规原文' },
  { path: '/official-sources', icon: '◮', label: '官方源', adminOnly: true },
  { path: '/research',  icon: '◬', label: '法规问答' },
  { path: '/llm-channels', icon: '◭', label: 'AI 通道', adminOnly: true },
  { path: '/models',    icon: '◫', label: '产品型号', adminOnly: true },
]
const navItems = computed(() => allNavItems.filter(item => !item.adminOnly || auth.isAdmin))

const titleMap = {
  dashboard: '数据看板', knowledge: '合规知识库',
  reviews: '审核工作台',
  changelog: '变更日志', tasks: '任务管理',
  alerts: '预警规则', settings: '系统设置',
  documents: '法规原文', 'official-sources': '官方源', research: '法规问答', 'llm-channels': 'AI 通道', models: '产品型号',
}
const currentTitle = computed(() => titleMap[route.name] || '管理后台')

const now = ref('')
let timer
onMounted(() => {
  const update = () => { now.value = new Date().toLocaleString('zh-CN') }
  update(); timer = setInterval(update, 1000)
})
onUnmounted(() => clearInterval(timer))

function logout() { auth.logout(); router.push('/login') }
</script>

<style scoped>
.layout { display: flex; min-height: 100vh; }
.sidebar {
  width: 200px; flex-shrink: 0; background: var(--bg2);
  border-right: 1px solid var(--border); display: flex; flex-direction: column;
}
.sidebar-header { padding: 24px 20px; border-bottom: 1px solid var(--border); }
.brand-tag { font-family: var(--mono); font-size: 9px; color: var(--accent); letter-spacing: 3px; margin-bottom: 4px; }
.brand-name { font-size: 15px; font-weight: 600; }
.nav { flex: 1; padding: 12px 0; }
.nav-item {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 20px; font-size: 13px; color: var(--text2);
  text-decoration: none; transition: all .15s; border-left: 2px solid transparent;
}
.nav-item:hover { color: var(--text); background: rgba(255,255,255,.03); }
.nav-active { color: var(--accent) !important; border-left-color: var(--accent); background: rgba(0,204,255,.05) !important; }
.nav-icon { font-size: 14px; width: 18px; }
.sidebar-footer { padding: 16px 20px; border-top: 1px solid var(--border); }
.user-info { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.user-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--green); }
.user-name { font-size: 12px; color: var(--text2); }
.role-badge { font-family: var(--mono); font-size: 9px; color: var(--accent); border:1px solid var(--border2); border-radius: 999px; padding: 1px 6px; }
.logout-btn { background: none; border: 1px solid var(--border2); color: var(--text3); font-size: 12px; padding: 5px 12px; border-radius: 2px; cursor: pointer; width: 100%; transition: all .15s; }
.logout-btn:hover { border-color: var(--red); color: var(--red); }
.main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.page-header { padding: 20px 28px 0; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 16px; }
.page-title { font-size: 18px; font-weight: 600; }
.page-time { font-family: var(--mono); font-size: 11px; color: var(--text3); }
.page-body { flex: 1; overflow-y: auto; padding: 24px 28px; }
</style>
