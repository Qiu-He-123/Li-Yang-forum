<script setup lang="ts">
/**
 * 帖子图片墙（原生组件，替代 el-image）
 * - 3 列网格，方形裁切
 * - 点击进入轻量图片预览（带左右切换、ESC 关闭）
 */
import { computed, ref } from 'vue'

import ImageViewer from '../common/ImageViewer.vue'
import { Icon } from '../native'

const props = withDefaults(defineProps<{
  urls: string[]
  /** 视频 URL 列表（微信朋友圈视频等），渲染为 HTML5 video */
  videos?: string[]
  /** 列表场景用缩略图（400x400 JPEG ~30KB），详情页传 false 用原图 */
  thumb?: boolean
}>(), { thumb: true, videos: () => [] })

const errored = ref<Set<number>>(new Set())
const loaded = ref<Set<number>>(new Set())
// 缩略图加载失败的索引集合 → 回退到原图（旧图无缩略图时自动降级）
const useOriginal = ref<Set<number>>(new Set())

/**
 * 推导缩略图 URL。
 * 上传时（images.py）：原图 {uuid}.jpg/png/webp → 缩略图 {uuid}_thumb.jpg（统一 JPEG 80 质量 400x400）
 * GIF 无缩略图（上传时保留动效），直接用原图。
 * 缩略图体积约为原图 1/50~1/100，列表页 9 图传输量从 ~30MB 降到 ~300KB，提速显著。
 */
const thumbUrls = computed(() =>
  props.urls.map(url => {
    if (/\.gif$/i.test(url)) return url
    return url.replace(/\.(jpe?g|png|webp)$/i, '_thumb.jpg')
  })
)

function srcFor(idx: number): string {
  // 详情页(thumb=false) 或缩略图加载失败 → 用原图
  if (!props.thumb || useOriginal.value.has(idx)) return props.urls[idx]
  return thumbUrls.value[idx]
}

// 图片查看（使用公共 ImageViewer：左上角返回 + 双指/双击缩放）
const previewVisible = ref(false)
const previewIndex = ref(0)

function openPreview(idx: number) {
  previewIndex.value = idx
  previewVisible.value = true
}
function updateIndex(idx: number) {
  previewIndex.value = idx
}

function onImgError(idx: number) {
  if (props.thumb && !useOriginal.value.has(idx)) {
    // 缩略图加载失败（旧图无缩略图 / 存储故障）→ 回退原图，不算真错误
    useOriginal.value.add(idx)
    useOriginal.value = new Set(useOriginal.value)
    return
  }
  // 原图也失败 → 显示错误占位
  errored.value.add(idx)
  errored.value = new Set(errored.value)
}
function onLoad(idx: number) {
  loaded.value.add(idx)
  loaded.value = new Set(loaded.value)
}
</script>

<template>
  <div v-if="urls.length" class="post-images-grid">
    <div v-for="(url, idx) in urls" :key="url + idx" class="img-cell" @click="openPreview(idx)">
      <!-- 加载中 -->
      <div v-if="!loaded.has(idx) && !errored.has(idx)" class="img-placeholder">
        <span class="placeholder-text">加载中</span>
      </div>
      <!-- 加载失败 -->
      <div v-if="errored.has(idx)" class="img-placeholder img-error">
        <Icon name="image" :size="22" color="#aeaeb2" />
        <span class="placeholder-text">加载失败</span>
      </div>
      <img
        v-if="!errored.has(idx)"
        :src="srcFor(idx)"
        :alt="`图片${idx + 1}`"
        loading="lazy"
        decoding="async"
        @error="onImgError(idx)"
        @load="onLoad(idx)"
      />
    </div>
  </div>

  <!-- 视频：HTML5 播放器，列表页只取封面不预载（无控件，点卡片进详情播放） -->
  <div v-if="videos.length" class="post-videos">
    <video
      v-for="(vurl, vi) in videos"
      :key="'v' + vi + vurl"
      class="post-video"
      :controls="!thumb"
      :preload="thumb ? 'metadata' : 'auto'"
      :src="vurl"
    ></video>
  </div>

  <!-- 图片查看器：返回 + 双指/双击缩放 -->
  <ImageViewer
    :visible="previewVisible"
    :url="urls[previewIndex] || ''"
    :urls="urls"
    :initial-index="previewIndex"
    @update:visible="previewVisible = $event"
    @update:index="updateIndex"
  />
</template>

<style scoped>
.post-images-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}
.img-cell {
  position: relative;
  aspect-ratio: 1 / 1;
  border-radius: var(--radius-sm);
  overflow: hidden;
  background: var(--bg-100);
  cursor: zoom-in;
}
.img-cell img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  transition: transform 0.2s var(--ease-apple);
}
.post-videos {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}
.post-video {
  width: 100%;
  max-height: 420px;
  border-radius: var(--radius-sm);
  background: #000;
  display: block;
}
.img-cell:hover img {
  transform: scale(1.03);
}
.img-placeholder {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  gap: 4px;
  color: var(--text-500);
  background: var(--bg-100);
  z-index: 1;
}
.img-error {
  flex-direction: column;
}
.placeholder-text {
  font-size: 12px;
  color: var(--text-500);
}

/* 预览 */
.img-preview {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.92);
  display: flex;
  align-items: center;
  justify-content: center;
}
.preview-img {
  max-width: 92vw;
  max-height: 88vh;
  object-fit: contain;
  border-radius: 6px;
}
.preview-close {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.12);
  border: none;
  cursor: pointer;
  display: grid;
  place-items: center;
  transition: background 0.15s var(--ease-apple);
}
.preview-close:hover {
  background: rgba(255, 255, 255, 0.22);
}
.preview-nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
  border: none;
  cursor: pointer;
  display: grid;
  place-items: center;
  transition: background 0.15s var(--ease-apple);
}
.preview-nav:hover {
  background: rgba(255, 255, 255, 0.2);
}
.preview-prev {
  left: 16px;
}
.preview-next {
  right: 16px;
}
.preview-counter {
  position: absolute;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  padding: 4px 12px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.5);
  color: #fff;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s var(--ease-apple);
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
