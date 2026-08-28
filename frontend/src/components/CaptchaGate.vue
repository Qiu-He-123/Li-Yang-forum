<script setup lang="ts">
/**
 * 全局验证码弹窗：由 useCaptchaGate 单例控制，任何位置都能触发。
 * - challenge 模式：验证通过 → resolve({ok:true})，http 拦截器自动重试原请求
 * - download 模式：验证通过 → resolve({ok:true, downloadToken})，调用方跳转下载
 */
import { ref, watch } from 'vue'

import { fetchCaptcha, verifyCaptcha } from '../api/auth'
import { getDownloadToken } from '../api/appDownload'
import { resolveCaptchaGate, useCaptchaGate } from '../composables/useCaptchaGate'
import Dialog from './native/Dialog.vue'
import { toast } from './native/Toast'

const gate = useCaptchaGate()
const captchaImg = ref('')
const captchaId = ref('')
const captchaText = ref('')
const submitting = ref(false)

async function loadCaptcha() {
  captchaText.value = ''
  try {
    const { data } = await fetchCaptcha()
    captchaId.value = data.data.captcha_id
    captchaImg.value = data.data.image
  } catch (error) {
    toast.error((error as Error).message || '验证码加载失败，请稍后重试')
  }
}

watch(
  () => gate.visible,
  (visible) => {
    if (visible) void loadCaptcha()
  },
)

async function submit() {
  const text = captchaText.value.trim()
  if (!captchaId.value || !text) {
    toast.error('请输入验证码')
    return
  }
  submitting.value = true
  try {
    if (gate.mode === 'download') {
      const { data } = await getDownloadToken({ captcha_id: captchaId.value, captcha_text: text })
      resolveCaptchaGate({ ok: true, downloadToken: data.data.download_token })
    } else {
      await verifyCaptcha({ captcha_id: captchaId.value, captcha_text: text })
      resolveCaptchaGate({ ok: true })
    }
  } catch (error) {
    toast.error((error as Error).message || '验证失败，请重试')
    void loadCaptcha()
  } finally {
    submitting.value = false
  }
}

function onCloseRequested() {
  resolveCaptchaGate({ ok: false })
}
</script>

<template>
  <Dialog
    :model-value="gate.visible"
    :title="gate.title"
    width="360px"
    :close-on-overlay="false"
    @update:model-value="onCloseRequested"
  >
    <div class="captcha-gate">
      <p class="captcha-hint">
        {{ gate.mode === 'download' ? '为防刷下载，请先完成图形验证码' : '检测到访问过于频繁，请完成验证后继续' }}
      </p>
      <div class="captcha-row">
        <input
          v-model="captchaText"
          class="captcha-input"
          type="text"
          placeholder="输入图中字符"
          maxlength="8"
          autocomplete="off"
          @keyup.enter="submit"
        />
        <img
          v-if="captchaImg"
          :src="captchaImg"
          alt="验证码"
          class="captcha-img"
          title="点击刷新"
          @click="loadCaptcha"
        />
      </div>
      <p class="captcha-refresh-hint">看不清？点击图片刷新</p>
    </div>
    <template #footer>
      <button class="captcha-btn" :disabled="submitting" @click="submit">
        {{ submitting ? '验证中…' : '确认' }}
      </button>
    </template>
  </Dialog>
</template>

<style scoped>
.captcha-gate {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.captcha-hint {
  margin: 0;
  font-size: 13px;
  color: var(--text-500, #6e6e73);
  line-height: 1.5;
}
.captcha-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.captcha-input {
  flex: 1;
  height: 42px;
  padding: 0 12px;
  border: 1px solid var(--bg-300, #e5e5ea);
  border-radius: 10px;
  font-size: 15px;
  outline: none;
  background: var(--bg-50, #fff);
  color: var(--text-800, #1d1d1f);
}
.captcha-input:focus {
  border-color: var(--brand-400, #007aff);
}
.captcha-img {
  width: 160px;
  height: 48px;
  border-radius: 8px;
  border: 1px solid var(--bg-300, #e5e5ea);
  cursor: pointer;
  object-fit: cover;
  background: #f5f5f7;
}
.captcha-refresh-hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-400, #8e8e93);
}
.captcha-btn {
  min-width: 88px;
  height: 36px;
  padding: 0 18px;
  border: none;
  border-radius: 10px;
  background: var(--brand-500, #007aff);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}
.captcha-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
