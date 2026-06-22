import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '@/api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const username = ref(localStorage.getItem('username') || '')
  const role = ref(localStorage.getItem('role') || 'viewer')
  const isAdmin = computed(() => role.value === 'admin')

  async function login(user, pass) {
    const form = new URLSearchParams()
    form.append('username', user)
    form.append('password', pass)
    const data = await api.post('/auth/login', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    })
    token.value = data.access_token
    username.value = data.username || user
    role.value = data.role || 'viewer'
    localStorage.setItem('token', data.access_token)
    localStorage.setItem('username', username.value)
    localStorage.setItem('role', role.value)
  }

  function logout() {
    token.value = ''
    username.value = ''
    role.value = 'viewer'
    localStorage.removeItem('token')
    localStorage.removeItem('username')
    localStorage.removeItem('role')
  }

  return { token, username, role, isAdmin, login, logout }
})
