<template>
  <div class="login-wrap">
    <div class="login-box">
      <div class="login-logo">CYBERSEC · COMPLIANCE</div>
      <div class="login-title">管理后台</div>
      <div class="login-sub">网络安全合规助手 · 内部系统</div>
      <div class="form-group">
        <label class="form-label">用户名</label>
        <input class="input" v-model="form.username" @keyup.enter="submit" placeholder="Username" />
      </div>
      <div class="form-group">
        <label class="form-label">密码</label>
        <input class="input" type="password" v-model="form.password" @keyup.enter="submit" placeholder="Password" />
      </div>
      <div class="error-msg" v-if="error">{{ error }}</div>
      <button class="btn btn-primary" style="width:100%;margin-top:8px" :disabled="loading" @click="submit">
        {{ loading ? '登录中...' : '登 录' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const form = ref({ username: '', password: '' })
const error = ref('')
const loading = ref(false)

async function submit() {
  if (!form.value.username || !form.value.password) { error.value = '请填写用户名和密码'; return }
  loading.value = true; error.value = ''
  try {
    await auth.login(form.value.username, form.value.password)
    router.push('/')
  } catch(e) { error.value = typeof e === 'string' ? e : '用户名或密码错误' }
  loading.value = false
}
</script>

<style scoped>
.login-wrap {
  width: 100vw; height: 100vh; display: flex;
  align-items: center; justify-content: center; background: var(--bg);
  background-image: radial-gradient(ellipse at 20% 50%, rgba(0,204,255,.06) 0%, transparent 60%),
                    radial-gradient(ellipse at 80% 20%, rgba(0,229,160,.04) 0%, transparent 50%);
}
.login-box { width: 380px; padding: 48px 40px; background: var(--bg2); border: 1px solid var(--border); border-radius: 4px; }
.login-logo { font-family: var(--mono); font-size: 10px; color: var(--accent); letter-spacing: 3px; margin-bottom: 8px; }
.login-title { font-size: 22px; font-weight: 600; margin-bottom: 4px; }
.login-sub { font-size: 12px; color: var(--text3); margin-bottom: 36px; }
.error-msg { color: var(--red); font-size: 12px; margin-top: 10px; text-align: center; }
</style>
