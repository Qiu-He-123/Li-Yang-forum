<script setup lang="ts">
import { onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { parseVideoShare, publishVideoShare, type VideoParseResult } from '../api/video'
import { toast } from '../components/native/Toast'

defineOptions({ name: 'ShareVideoView' })

const router = useRouter()
const text = ref('')
const parsing = ref(false)
const publishing = ref(false)
const anonymous = ref(false)
const preview = ref<VideoParseResult | null>(null)
const error = ref('')

// 底部"解析中..."：点号不断变化，让用户知道在动
const dotCount = ref(1)
let dotTimer: ReturnType<typeof setInterval> | null = null

function startDots() {
  stopDots()
  dotTimer = setInterval(() => {
    dotCount.value = (dotCount.value % 3) + 1
  }, 400)
}
function stopDots() {
  if (dotTimer) {
    clearInterval(dotTimer)
    dotTimer = null
  }
}
onUnmounted(stopDots)

async function doParse() {
  if (!text.value.trim()) {
    toast.info('请粘贴抖音/快手分享链接')
    return
  }
  parsing.value = true
  error.value = ''
  preview.value = null
  startDots()
  try {
    preview.value = (await parseVideoShare(text.value.trim())).data.data
  } catch (e: unknown) {
    // 注意：业务错误被 http 拦截器转成普通 Error，真实原因在 e.message
    const err = e as { response?: { data?: { msg?: string } }; message?: string }
    error.value = err.response?.data?.msg || err.message || '解析失败，请确认链接'
  } finally {
    parsing.value = false
    if (!publishing.value) stopDots()
  }
}

async function doPublish() {
  if (!preview.value) return
  publishing.value = true
  error.value = ''
  startDots()
  try {
    const data = (await publishVideoShare(text.value.trim(), anonymous.value)).data.data
    const post = data.post as { id?: number }
    toast.success(anonymous.value ? '匿名发布成功' : '发布成功')
    router.replace(post.id ? `/post/${post.id}` : '/')
  } catch (e: unknown) {
    const err = e as { response?: { data?: { msg?: string } }; message?: string }
    error.value = err.response?.data?.msg || err.message || '发布失败，请重试'
  } finally {
    publishing.value = false
    stopDots()
  }
}
</script>

<template>
  <div class="page">
    <header class="page-header">
      <button type="button" class="back-btn" @click="router.back()">←</button>
      <h1>分享视频</h1>
    </header>

    <section class="card">
      <p class="tip">粘贴抖音/B站/快手的分享链接或口令，解析后发布为视频帖（直链播放，不占服务器存储，原画质）。</p>
      <textarea
        v-model="text"
        class="input-area"
        rows="3"
        maxlength="1000"
        placeholder="例如：https://v.douyin.com/xxx/ 或 https://b23.tv/xxx 或 https://v.kuaishou.com/xxx"
      ></textarea>

      <button type="button" class="btn-primary" :disabled="parsing" @click="doParse">
        {{ parsing ? '解析中…' : '解析预览' }}
      </button>

      <p v-if="error" class="error">{{ error }}</p>

      <!-- 解析结果预览 -->
      <div v-if="preview" class="preview">
        <img v-if="preview.cover" :src="preview.cover" :alt="preview.title" class="preview-cover" />
        <div class="preview-info">
          <span class="preview-platform">{{ preview.platform === 'douyin' ? '抖音' : preview.platform === 'bilibili' ? 'B站' : '快手' }}</span>
          <p class="preview-title">{{ preview.title || '未命名视频' }}</p>
          <p v-if="preview.author" class="preview-author">作者：{{ preview.author }}</p>
        </div>
      </div>

      <!-- 匿名发布开关 -->
      <label v-if="preview" class="anon-toggle">
        <input v-model="anonymous" type="checkbox" class="anon-checkbox" />
        <span class="anon-label">匿名发布</span>
        <span class="anon-hint">发布后不显示昵称和头像，展示为"匿名同学"</span>
      </label>

      <button
        v-if="preview"
        type="button"
        class="btn-primary btn-publish"
        :disabled="publishing"
        @click="doPublish"
      >
        {{ publishing ? '发布中…' : '发布到「视频」圈子' }}
      </button>
      <p class="mini">发布后视频会出现在推荐/最新流和「视频」圈子，点进去直接播放（原平台直链）；直链偶尔失效时可点"刷新链接"换新</p>
    </section>

    <!-- 底部解析中提示（非全屏遮罩）：点号动态变化 -->
    <div v-if="parsing || publishing" class="parsing-bar">
      <span class="parsing-dot"></span>
      <span>{{ publishing ? '发布中' : '解析中' }}<span class="parsing-ellipsis">{{ '.'.repeat(dotCount) }}</span></span>
    </div>
  </div>
</template>

<style scoped>
.page {
  max-width: 720px;
  margin: 0 auto;
  padding: 0 14px 60px;
  min-height: 100vh;
}
.page-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 0;
}
.page-header h1 {
  font-size: 17px;
  margin: 0;
}
.back-btn {
  border: none;
  background: transparent;
  font-size: 20px;
  cursor: pointer;
  padding: 0 4px;
}
.card {
  background: #fff;
  border-radius: 12px;
  padding: 18px;
  margin-top: 10px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05);
}
.tip {
  font-size: 13px;
  color: var(--text-600, #555);
  line-height: 1.7;
  margin: 0 0 12px;
}
.input-area {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #e5e5e5;
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 13px;
  resize: vertical;
  outline: none;
}
.btn-primary {
  width: 100%;
  border: none;
  background: #4f9cff;
  color: #fff;
  border-radius: 8px;
  padding: 10px;
  font-size: 14px;
  cursor: pointer;
  margin-top: 10px;
}
.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-publish {
  background: #ff2d55;
}
.error {
  color: #e5484d;
  font-size: 13px;
  margin: 10px 0 0;
}
.preview {
  display: flex;
  gap: 12px;
  margin-top: 12px;
  border: 1px solid #f0f0f0;
  border-radius: 10px;
  padding: 10px;
  background: #fafafa;
}
.preview-cover {
  width: 96px;
  height: 96px;
  object-fit: cover;
  border-radius: 8px;
  background: #000;
  flex-shrink: 0;
}
.preview-info {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.preview-platform {
  align-self: flex-start;
  font-size: 11px;
  color: #ff2d55;
  background: rgba(255, 45, 85, 0.1);
  border-radius: 999px;
  padding: 1px 8px;
}
.preview-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-800, #222);
  margin: 0;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.preview-author {
  font-size: 12px;
  color: var(--text-400, #999);
  margin: 0;
}
.mini {
  font-size: 12px;
  color: var(--text-400, #999);
  margin: 10px 0 0;
  line-height: 1.6;
}
.anon-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding: 10px 12px;
  background: #f7f8fa;
  border-radius: 10px;
  cursor: pointer;
}
.anon-checkbox {
  width: 17px;
  height: 17px;
  accent-color: #4f9cff;
  cursor: pointer;
  flex-shrink: 0;
}
.anon-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-800, #222);
}
.anon-hint {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-400, #999);
}
/* 底部"解析中..."：小胶囊，不遮全屏 */
.parsing-bar {
  position: fixed;
  left: 50%;
  bottom: calc(28px + env(safe-area-inset-bottom));
  transform: translateX(-50%);
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.82);
  color: #fff;
  font-size: 13px;
  z-index: 200;
  white-space: nowrap;
}
.parsing-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #4f9cff;
  animation: parsing-pulse 1s ease-in-out infinite;
}
.parsing-ellipsis {
  min-width: 1.2em;
  display: inline-block;
  text-align: left;
}
@keyframes parsing-pulse {
  0%,
  100% {
    opacity: 0.35;
    transform: scale(0.85);
  }
  50% {
    opacity: 1;
    transform: scale(1.15);
  }
}
</style>
