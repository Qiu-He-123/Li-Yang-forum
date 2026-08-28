<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  importMoments,
  listMyMoments,
  refreshWechatMoments,
  type WechatMomentItem,
} from '../api/wechat'
import { toast } from '../components/native/Toast'

defineOptions({ name: 'ManualPublishView' })

const router = useRouter()
const moments = ref<WechatMomentItem[]>([])
const selectedTids = ref<Set<string>>(new Set())
const pinnedTids = ref<string[]>([])
const pinDays = ref(1)
const loading = ref(true)
const refreshing = ref(false)
const importing = ref(false)

async function loadMoments() {
  loading.value = true
  try {
    const data = (await listMyMoments(1, 100)).data.data
    moments.value = data.items
    // 有图片还在后台下载时，轮询刷新把图补上
    if (data.items.some((it) => it.media_pending)) {
      window.clearTimeout(loadMomentsTimer)
      loadMomentsTimer = window.setTimeout(loadMoments, 4000)
    }
  } catch {
    moments.value = []
  } finally {
    loading.value = false
  }
}

let loadMomentsTimer: number | undefined

function toggleSelect(item: WechatMomentItem) {
  const set = new Set(selectedTids.value)
  if (set.has(item.tid)) {
    set.delete(item.tid)
    pinnedTids.value = pinnedTids.value.filter((t) => t !== item.tid)
  } else {
    set.add(item.tid)
  }
  selectedTids.value = set
}

function togglePin(item: WechatMomentItem) {
  if (!selectedTids.value.has(item.tid)) return
  if (pinnedTids.value.includes(item.tid)) {
    pinnedTids.value = pinnedTids.value.filter((t) => t !== item.tid)
  } else {
    if (pinnedTids.value.length >= 3) {
      toast.info('同一批最多置顶 3 条')
      return
    }
    pinnedTids.value = [...pinnedTids.value, item.tid]
  }
}

const pinPrice = computed(() => {
  if (!pinnedTids.value.length) return 0
  const unit = pinnedTids.value.reduce((sum, _t, i) => sum + Math.min(i + 1, 3), 0)
  return unit * pinDays.value
})

async function doImport() {
  if (!selectedTids.value.size) {
    toast.info('请先勾选要导入的朋友圈')
    return
  }
  importing.value = true
  try {
    const data = (await importMoments({
      tids: [...selectedTids.value],
      pinned_tids: pinnedTids.value,
      pin_days: pinDays.value,
    })).data.data
    toast.success(pinnedTids.value.length ? `发布成功，置顶共花费 ${data.cost} 金币` : '发布成功')
    selectedTids.value = new Set()
    pinnedTids.value = []
    await loadMoments()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { msg?: string } } }
    toast.error(err.response?.data?.msg || '发布失败')
  } finally {
    importing.value = false
  }
}

async function refreshNow(opts: { silent?: boolean } = {}) {
  refreshing.value = true
  try {
    const res = (await refreshWechatMoments()) as { data?: { data?: { added?: number } } }
    const added = res?.data?.data?.added ?? 0
    if (!opts.silent) toast.success(added ? `已刷新，新增 ${added} 条朋友圈` : '已刷新，暂无新动态')
    await loadMoments()
    // 媒体在后台下载，稍后再拉一次把图片补上
    window.setTimeout(loadMoments, 6000)
  } catch {
    if (!opts.silent) toast.error('刷新太频繁，请稍后再试')
    await loadMoments()
  } finally {
    refreshing.value = false
  }
}

function fmtTime(t: string | null): string {
  if (!t) return ''
  const d = new Date(t)
  if (Number.isNaN(d.getTime())) return t
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function thumbUrl(url: string): string {
  if (!url) return ''
  // 图片走后端压缩缩略图：最长边 800px + JPEG 压缩
  return `/api/wechat/thumb?url=${encodeURIComponent(url)}`
}

function mediaImages(item: WechatMomentItem) {
  return (item.media || []).filter((m) => m.type === 2 && m.url)
}

function mediaVideos(item: WechatMomentItem) {
  return (item.media || []).filter((m) => m.type !== 2)
}

function videoThumbStyle(item: WechatMomentItem): Record<string, string> {
  const v = (item.media || []).find((m) => m.type !== 2 && m.thumb_url)
  if (!v?.thumb_url) return {}
  return { backgroundImage: `url(${v.thumb_url})`, backgroundSize: 'cover', backgroundPosition: 'center' }
}

const gridClass = (n: number) => {
  if (n === 1) return 'media-grid media-grid--one'
  if (n === 2) return 'media-grid media-grid--two'
  if (n === 3) return 'media-grid media-grid--three'
  return 'media-grid media-grid--many'
}

onMounted(() => {
  // 进入页面先自动刷新一次，扫描最新朋友圈（静默，不弹提示）
  refreshNow({ silent: true })
  loadMoments()
})
</script>

<template>
  <div class="page">
    <header class="page-header">
      <button type="button" class="back-btn" @click="router.back()">←</button>
      <h1>手动发布</h1>
    </header>

    <section class="card">
      <div class="head">
        <h2>选择要发布的朋友圈</h2>
        <button type="button" class="refresh-btn" :disabled="refreshing" @click="refreshNow()">
          {{ refreshing ? '刷新中…' : '手动刷新' }}
        </button>
      </div>
      <p class="tip">手动刷新会立即扫描你的朋友圈。只能扫描能看到且近期的朋友圈。</p>

      <div v-if="loading" class="empty-tip">加载中…</div>
      <div v-else-if="!moments.length" class="empty-tip">暂无可导入的朋友圈，点上方「手动刷新」试试</div>

      <!-- 微信朋友圈卡片：图片九宫格 + 文字 + 选择/置顶 -->
      <div
        v-for="item in moments"
        :key="item.tid"
        class="moment-card"
        :class="{ 'is-selected': selectedTids.has(item.tid), imported: item.imported }"
        @click="!item.imported && toggleSelect(item)"
      >
        <!-- 卡片头：勾选 + 时间 + 已导入标识 -->
        <div class="moment-card-head">
          <label class="check-wrap" @click.stop>
            <input
              type="checkbox"
              :checked="selectedTids.has(item.tid)"
              :disabled="item.imported"
              @change="toggleSelect(item)"
            />
            <span class="check-box" :class="{ checked: selectedTids.has(item.tid) }">
              <span v-if="selectedTids.has(item.tid)" class="check-mark">✓</span>
            </span>
          </label>
          <span class="moment-time">{{ fmtTime(item.create_time) }}</span>
          <span v-if="item.imported" class="imported-tag">已导入</span>
        </div>

        <!-- 图片九宫格 -->
        <div v-if="mediaImages(item).length" :class="gridClass(mediaImages(item).length)">
          <div
            v-for="(m, i) in mediaImages(item)"
            :key="i"
            class="media-cell"
            :class="{ 'media-cell--first': i === 0 && mediaImages(item).length > 1 }"
          >
            <img
              :src="thumbUrl(m.url || '')"
              :alt="item.content || '朋友圈图片'"
              loading="lazy"
            />
            <span v-if="i === 0 && mediaImages(item).length > 1" class="media-count-badge">
              {{ mediaImages(item).length }} 图
            </span>
          </div>
        </div>
        <!-- 图片后台下载中：占位提示 -->
        <div v-else-if="item.media_pending" class="media-loading">
          <span class="media-loading-spinner"></span>
          <span>图片加载中…</span>
        </div>

        <!-- 视频占位：有封面时显示封面 -->
        <div v-if="mediaVideos(item).length" class="video-cell" :style="videoThumbStyle(item)">
          <span class="video-play">▶</span>
          <span class="video-label">视频 × {{ mediaVideos(item).length }}</span>
        </div>

        <!-- 文字内容 -->
        <p v-if="item.content" class="moment-text">{{ item.content }}</p>

        <!-- 选中后的操作：置顶 -->
        <div v-if="selectedTids.has(item.tid) && !item.imported" class="moment-actions" @click.stop>
          <label class="pin-btn" :class="{ active: pinnedTids.includes(item.tid) }" title="发布后置顶展示在朋友圈频道顶部">
            <input type="checkbox" :checked="pinnedTids.includes(item.tid)" @change="togglePin(item)" />
            <span>📌 {{ pinnedTids.includes(item.tid) ? '已置顶' : '置顶' }}</span>
          </label>
        </div>
      </div>

      <div v-if="selectedTids.size" class="import-bar">
        <div class="pin-opts">
          <span>已选 {{ selectedTids.size }} 条</span>
          <template v-if="pinnedTids.length">
            <span>置顶 {{ pinnedTids.length }} 条 ×</span>
            <select v-model.number="pinDays">
              <option :value="1">1天</option>
              <option :value="3">3天</option>
              <option :value="7">7天</option>
            </select>
          </template>
          <span v-if="pinnedTids.length" class="price">费用 {{ pinPrice }} 金币</span>
        </div>
        <button type="button" class="publish-btn" :disabled="importing" @click="doImport">
          {{ importing ? '发布中…' : '发布到论坛' }}
        </button>
      </div>
      <p class="pin-rule">
        置顶说明：勾选朋友圈后点「📌 置顶」，发布时这条帖子会固定在「朋友圈频道」顶部展示，持续所选天数，其他人一进频道就能最先看到它。同一批第 1/2/3 条置顶分别收 1/2/3 金币/天。
      </p>
    </section>
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
  padding: 16px;
  margin-top: 10px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05);
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.head h2 {
  font-size: 15px;
  margin: 0;
}
.refresh-btn {
  border: 1px solid #4f9cff;
  color: #4f9cff;
  background: #fff;
  border-radius: 999px;
  padding: 4px 14px;
  font-size: 13px;
  cursor: pointer;
}
.tip,
.pin-rule {
  font-size: 12px;
  color: var(--text-400, #999);
  line-height: 1.6;
  margin: 8px 0;
}
.moment-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid #f5f5f5;
  display: none; /* 旧版行样式已废弃，保留占位 */
}
.moment-row.imported {
  opacity: 0.55;
}
.moment-info {
  flex: 1;
  min-width: 0;
  cursor: pointer;
}
.moment-text {
  font-size: 13px;
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.moment-meta {
  font-size: 11px;
  color: var(--text-400, #999);
  margin: 3px 0 0;
  display: flex;
  gap: 8px;
}
.imported-tag {
  color: #2e7d32;
}
.pin-box {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #b26a00;
  white-space: nowrap;
}
.import-bar {
  position: fixed;
  left: 50%;
  bottom: calc(84px + env(safe-area-inset-bottom));
  transform: translateX(-50%);
  width: min(720px, calc(100% - 28px));
  z-index: 50;
  background: #fff;
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 4px 18px rgba(15, 23, 42, 0.14);
  padding: 10px 14px;
  margin-top: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.pin-opts {
  font-size: 12px;
  color: var(--text-500, #666);
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.pin-opts select {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 3px 6px;
  font-size: 12px;
}
.price {
  color: #b26a00;
  font-weight: 600;
}
.publish-btn {
  border: none;
  background: #4f9cff;
  color: #fff;
  border-radius: 999px;
  padding: 8px 18px;
  font-size: 13px;
  cursor: pointer;
}
.empty-tip {
  text-align: center;
  color: var(--text-400, #999);
  padding: 30px 0;
  font-size: 13px;
}

/* ====== 朋友圈卡片（微信风格） ====== */
.moment-card {
  background: #fafafa;
  border: 1.5px solid #f0f0f0;
  border-radius: 14px;
  padding: 12px 14px;
  margin-bottom: 12px;
  cursor: pointer;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
}
.moment-card:hover {
  border-color: #dbe7ff;
}
.moment-card.is-selected {
  border-color: #4f9cff;
  background: #f5f9ff;
  box-shadow: 0 0 0 1px rgba(79, 156, 255, 0.35), 0 4px 14px rgba(79, 156, 255, 0.12);
}
.moment-card.imported {
  opacity: 0.55;
  cursor: default;
}
.moment-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.check-wrap {
  position: relative;
  display: inline-flex;
  cursor: pointer;
}
.check-wrap input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}
.check-box {
  width: 20px;
  height: 20px;
  border-radius: 6px;
  border: 1.5px solid #c8cdd4;
  background: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s ease;
}
.check-box.checked {
  background: #4f9cff;
  border-color: #4f9cff;
}
.check-mark {
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  line-height: 1;
}
.moment-time {
  font-size: 12px;
  color: var(--text-400, #999);
}
.imported-tag {
  margin-left: auto;
  color: #2e7d32;
  font-size: 12px;
  background: #e8f5e9;
  border-radius: 999px;
  padding: 2px 10px;
}

/* 图片九宫格 */
.media-grid {
  display: grid;
  gap: 3px;
  border-radius: 10px;
  overflow: hidden;
  margin-bottom: 10px;
  background: #efefef;
}
.media-grid--one {
  grid-template-columns: 1fr;
}
.media-grid--two {
  grid-template-columns: 1fr 1fr;
}
.media-grid--three {
  grid-template-columns: repeat(3, 1fr);
}
.media-grid--many {
  grid-template-columns: repeat(3, 1fr);
}
.media-cell {
  position: relative;
  aspect-ratio: 1 / 1;
  overflow: hidden;
  background: #e5e5e5;
}
.media-grid--one .media-cell {
  aspect-ratio: 16 / 10;
}
.media-cell img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.media-count-badge {
  position: absolute;
  right: 6px;
  bottom: 6px;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  font-size: 11px;
  border-radius: 999px;
  padding: 2px 8px;
  backdrop-filter: blur(4px);
}

/* 图片后台下载中占位 */
.media-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 140px;
  border-radius: 10px;
  background: #f4f4f5;
  color: #999;
  font-size: 13px;
  margin-bottom: 10px;
}
.media-loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid #ddd;
  border-top-color: #999;
  border-radius: 50%;
  animation: media-spin 0.8s linear infinite;
}
@keyframes media-spin {
  to {
    transform: rotate(360deg);
  }
}

/* 视频占位 */
.video-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #000;
  color: #fff;
  border-radius: 10px;
  padding: 14px;
  margin-bottom: 10px;
}
.video-play {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.22);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  padding-left: 2px;
}
.video-label {
  font-size: 13px;
}

/* 文字内容 */
.moment-text {
  font-size: 14px;
  color: var(--text-700, #333);
  line-height: 1.65;
  margin: 0;
  white-space: pre-line;
}

/* 选中后操作 */
.moment-actions {
  margin-top: 10px;
  display: flex;
  justify-content: flex-end;
  border-top: 1px dashed #e3e8f0;
  padding-top: 8px;
}
.pin-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #8a6d1a;
  cursor: pointer;
  border: 1px solid #f0e0b0;
  background: #fffdf3;
  border-radius: 999px;
  padding: 4px 12px;
  transition: all 0.15s ease;
}
.pin-btn.active {
  background: #fff3c4;
  border-color: #e6c35c;
}
.pin-btn input {
  display: none;
}
</style>
