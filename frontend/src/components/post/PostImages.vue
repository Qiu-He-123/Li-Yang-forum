<script setup lang="ts">
/**
 * 帖子图片墙（原生组件，替代 el-image）
 * - 3 列网格，方形裁切
 * - 点击进入轻量图片预览（带左右切换、ESC 关闭）
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { Icon } from '../native'

const props = withDefaults(defineProps<{
  urls: string[]
  /** 列表场景用缩略图（400x400 JPEG ~30KB），详情页传 false 用原图 */
  thumb?: boolean
}>(), { thumb: true })

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

// 预览始终用原图（保证清晰度）
const previewVisible = ref(false)
const previewIndex = ref(0)
const previewUrl = computed(() => props.urls[previewIndex.value] || '')

function openPreview(idx: number) {
  previewIndex.value = idx
  previewVisible.value = true
}
function closePreview() {
  previewVisible.value = false
}
function prev() {
  if (!props.urls.length) return
  previewIndex.value = (previewIndex.value - 1 + props.urls.length) % props.urls.length
}
function next() {
  if (!props.urls.length) return
  previewIndex.value = (previewIndex.value + 1) % props.urls.length
}
function onKey(e: KeyboardEvent) {
  if (!previewVisible.value) return
  if (e.key === 'Escape') closePreview()
  else if (e.key === 'ArrowLeft') prev()
  else if (e.key === 'ArrowRight') next()
}
onMounted(() => document.addEventListener('keydown', onKey))
onUnmounted(() => document.removeEventListener('keydown', onKey))

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

  <!-- 轻量图片预览 -->
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="previewVisible" class="img-preview" role="dialog" aria-modal="true" @click.self="closePreview">
        <button class="preview-close" type="button" aria-label="关闭" @click="closePreview">
          <Icon name="x" :size="24" color="#fff" />
        </button>
        <button
          v-if="urls.length > 1"
          class="preview-nav preview-prev"
          type="button"
          aria-label="上一张"
          @click.stop="prev"
        >
          <Icon name="chevron-left" :size="28" color="#fff" />
        </button>
        <img :src="previewUrl" class="preview-img" :alt="`预览${previewIndex + 1}`" />
        <button
          v-if="urls.length > 1"
          class="preview-nav preview-next"
          type="button"
          aria-label="下一张"
          @click.stop="next"
        >
          <Icon name="chevron-right" :size="28" color="#fff" />
        </button>
        <div v-if="urls.length > 1" class="preview-counter">{{ previewIndex + 1 }} / {{ urls.length }}</div>
      </div>
    </Transition>
  </Teleport>
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
