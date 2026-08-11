<script setup lang="ts">
/**
 * 网页版左上角「下载手机端」按钮。
 * 点击 → 选择安卓/苹果 → 选安卓后弹出密码窗（普通下载 / 复制密码并跳转）→ 跳蓝奏云。
 * 按钮本体继承全局 .download-app-btn 样式（App 内自动隐藏）。
 */
import { ref } from 'vue'

import Icon from './native/Icon.vue'
import Dialog from './native/Dialog.vue'
import { toast } from './native/Toast'
import { http, type LoadingAxiosRequestConfig } from '../api/http'

const visible = ref(false)
const androidVisible = ref(false)
const password = ref('')
const loading = ref(false)

async function chooseAndroid() {
  visible.value = false
  androidVisible.value = true
  loading.value = true
  try {
    const config: LoadingAxiosRequestConfig = {
      showGlobalLoading: false,
      showGlobalError: false,
    }
    const { data } = await http.get<unknown, { data: { code: number; msg: string; data: { url?: string; password?: string } } }>(
      '/api/app-download/info',
      config,
    )
    password.value = data.data.password || ''
  } catch {
    password.value = ''
  } finally {
    loading.value = false
  }
}

function choose(platform: 'android' | 'ios') {
  if (platform === 'android') {
    chooseAndroid()
  } else {
    visible.value = false
    toast.info('iOS 版暂未开放下载，敬请期待')
  }
}

function goDownload() {
  window.location.href = '/api/app-download'
}

async function copyAndGo() {
  const text = password.value || ''
  if (!text) {
    toast.info('暂未获取到密码，请稍后重试')
    return
  }
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const ta = document.createElement('textarea')
      ta.value = text
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    toast.success('密码已复制')
  } catch {
    toast.info('复制失败，请手动复制密码')
    return
  }
  toast.info('跳转中…')
  // 等待 1 秒让用户看到提示，再跳转蓝奏云
  setTimeout(() => {
    window.location.href = '/api/app-download'
  }, 1000)
}
</script>

<template>
  <a
    class="download-app-btn"
    href="javascript:void(0)"
    title="下载手机端 App"
    aria-label="下载手机端 App"
    @click.prevent="visible = true"
  >
    <Icon name="arrow-down" :size="14" />
    <span>下载手机端</span>
  </a>

  <!-- 第一步：选择安卓 / 苹果 -->
  <Dialog v-model="visible" title="下载手机端" width="360px">
    <div class="download-options">
      <button class="download-option" type="button" @click="choose('android')">
        <span class="download-option-text">
          <b>安卓版</b>
          <small>Android 安装包</small>
        </span>
        <span class="download-option-arrow" aria-hidden="true">›</span>
      </button>
      <button class="download-option" type="button" @click="choose('ios')">
        <span class="download-option-text">
          <b>苹果版</b>
          <small>iOS 安装包</small>
        </span>
        <span class="download-option-arrow" aria-hidden="true">›</span>
      </button>
    </div>
  </Dialog>

  <!-- 第二步：安卓密码窗 -->
  <Dialog v-model="androidVisible" title="安卓版下载" width="360px">
    <div class="android-download">
      <p class="android-tip android-tip--warn">
        💡 如果使用微信浏览器，请点击右上角「···」选择「在浏览器打开」后再下载
      </p>
      <p class="android-tip">打开下载页面后，输入以下密码即可下载：</p>
      <div class="android-password">
        <Icon name="lock" :size="14" />
        <span>{{ loading ? '获取中…' : (password || '暂无密码') }}</span>
      </div>

      <button class="dl-btn dl-btn--primary" type="button" @click="goDownload">
        直接跳转
      </button>
      <button class="dl-btn dl-btn--copy" type="button" @click="copyAndGo">
        复制密码并跳转
      </button>
    </div>
  </Dialog>
</template>

<style scoped>
.download-options {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.download-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding: 16px;
  border: 1px solid var(--bg-300);
  border-radius: 12px;
  background: var(--bg-50);
  cursor: pointer;
  text-align: left;
  transition: all 0.15s ease;
}
.download-option:hover {
  border-color: var(--brand-400);
  background: var(--brand-50);
}
.download-option:active {
  transform: scale(0.98);
}
.download-option-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.download-option-text b {
  font-size: 15px;
  color: var(--text-800);
}
.download-option-text small {
  font-size: 12px;
  color: var(--text-400);
}
.download-option-arrow {
  font-size: 22px;
  color: var(--text-300);
}

/* 安卓密码窗 */
.android-download {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.android-tip {
  margin: 0;
  font-size: 13px;
  color: var(--text-500);
}
.android-tip--warn {
  color: var(--warning, #ff9500);
  font-size: 12px;
  line-height: 1.5;
}
.android-password {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
  border: 1px dashed var(--brand-300);
  border-radius: 10px;
  background: var(--brand-50);
  color: var(--text-800);
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 1px;
}
.dl-btn {
  width: 100%;
  height: 44px;
  border-radius: 10px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}
.dl-btn:active {
  transform: scale(0.98);
}
.dl-btn--copy {
  border: 1px solid var(--brand-400);
  background: var(--bg-50);
  color: var(--brand-600);
}
.dl-btn--copy:hover {
  background: var(--brand-50);
}
.dl-btn--primary {
  border: none;
  background: var(--brand-500);
  color: #fff;
}
.dl-btn--primary:hover {
  background: var(--brand-600);
}
</style>
