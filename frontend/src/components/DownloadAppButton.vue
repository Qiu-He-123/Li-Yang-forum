<script setup lang="ts">
/**
 * 网页版左上角「下载手机端」按钮。
 * 点击 → 选择安卓/苹果 → 选安卓直接从服务器下载 APK（不依赖第三方网盘）。
 * 按钮本体继承全局 .download-app-btn 样式（App 内自动隐藏）。
 */
import { ref } from 'vue'

import Icon from './native/Icon.vue'
import Dialog from './native/Dialog.vue'
import { toast } from './native/Toast'
import { openCaptchaGate } from '../composables/useCaptchaGate'

const visible = ref(false)

async function choose(platform: 'android' | 'ios') {
  visible.value = false
  if (platform === 'android') {
    // 防刷下载：先过图形验证码，换取一次性下载令牌后再跳转
    const result = await openCaptchaGate('download')
    if (result.ok && result.downloadToken) {
      window.location.href = `/api/app-download?token=${result.downloadToken}`
    }
  } else {
    toast.info('iOS 版暂未开放下载，敬请期待')
  }
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

  <!-- 选择安卓 / 苹果 -->
  <Dialog v-model="visible" title="下载手机端" width="360px">
    <div class="download-options">
      <button class="download-option" type="button" @click="choose('android')">
        <span class="download-option-text">
          <b>安卓版</b>
          <small>从服务器直接下载安装包</small>
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
</style>
