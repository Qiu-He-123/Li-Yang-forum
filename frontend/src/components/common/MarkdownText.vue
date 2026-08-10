<script setup lang="ts">
/**
 * 通用 Markdown 渲染（marked + DOMPurify）：
 * - 帖子正文统一走这里渲染，替换原先的纯文本分段逻辑；
 * - 编辑器里的 #话题 蓝色高亮是 textarea overlay，与此渲染互不影响；
 * - v-html 前必须过 DOMPurify 防 XSS。
 */
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const props = withDefaults(
  defineProps<{
    content?: string | null
    /** >0 时按行数截断显示（CSS line-clamp，用于卡片摘要） */
    clamp?: number
  }>(),
  { content: '', clamp: 0 },
)

const rootRef = ref<HTMLElement | null>(null)

// GFM + 单换行转 <br>：旧帖子是“一行一段”，这样渲染出来不会挤成一团
marked.setOptions({ gfm: true, breaks: true })

const html = computed(() => {
  const raw = props.content ?? ''
  if (!raw.trim()) return ''
  const rendered = marked.parse(raw, { async: false }) as string
  return DOMPurify.sanitize(rendered, { USE_PROFILES: { html: true } })
})

/** 渲染后高亮 #话题 / @用户（与发帖编辑器蓝色一致），跳过代码块避免误伤 */
function applyHighlight() {
  const root = rootRef.value
  if (!root) return
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  const nodes: Text[] = []
  while (walker.nextNode()) nodes.push(walker.currentNode as Text)
  for (const node of nodes) {
    if (node.parentElement?.closest('pre, code')) continue
    const text = node.nodeValue ?? ''
    if (!text) continue
    const parts = text.split(/(#[^\s#@]+|@[^\s#@]+)/g)
    if (parts.length <= 1) continue
    const frag = document.createDocumentFragment()
    for (const part of parts) {
      if (!part) continue
      const span = document.createElement('span')
      if (/^#[^\s#@]+$/.test(part)) {
        span.className = 'md-hl-topic'
      } else if (/^@[^\s#@]+$/.test(part)) {
        span.className = 'md-hl-mention'
      } else {
        frag.appendChild(document.createTextNode(part))
        continue
      }
      span.textContent = part
      frag.appendChild(span)
    }
    node.parentNode?.replaceChild(frag, node)
  }
}

onMounted(applyHighlight)
watch(html, () => nextTick(applyHighlight))
</script>

<template>
  <div
    ref="rootRef"
    class="markdown-body"
    :class="{ 'is-clamped': clamp > 0 }"
    :style="clamp > 0 ? { WebkitLineClamp: String(clamp) } : undefined"
    v-html="html"
  />
</template>

<style scoped>
/* 字体/颜色全部继承父级：卡片（13px）与详情（15px）各按自己的样式走 */
.markdown-body {
  word-break: break-word;
  width: 100%;
  box-sizing: border-box;
}
.markdown-body :deep(p) {
  margin: 0.5em 0;
  line-height: 1.7;
}
.markdown-body :deep(p:first-child) {
  margin-top: 0;
}
.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) {
  font-weight: 700;
  margin: 0.8em 0 0.4em;
  line-height: 1.4;
}
.markdown-body :deep(h1) {
  font-size: 1.35em;
}
.markdown-body :deep(h2) {
  font-size: 1.25em;
}
.markdown-body :deep(h3) {
  font-size: 1.15em;
}
.markdown-body :deep(h4) {
  font-size: 1.05em;
}
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 1.5em;
  margin: 0.5em 0;
}
.markdown-body :deep(li) {
  margin: 0.25em 0;
}
.markdown-body :deep(a) {
  color: var(--brand-500, #007aff);
  text-decoration: none;
}
.markdown-body :deep(a):hover {
  text-decoration: underline;
}
.markdown-body :deep(.md-hl-topic),
.markdown-body :deep(.md-hl-mention) {
  color: var(--brand-500);
}
.markdown-body :deep(img) {
  max-width: 100%;
  border-radius: 8px;
}
.markdown-body :deep(blockquote) {
  margin: 0.6em 0;
  padding: 0.3em 0.9em;
  border-left: 3px solid var(--bg-300, #e5e7eb);
  color: var(--text-500, #6b7280);
  background: var(--bg-100, #f9fafb);
  border-radius: 0 6px 6px 0;
}
.markdown-body :deep(code) {
  padding: 0.15em 0.4em;
  border-radius: 4px;
  font-size: 0.9em;
  background: var(--bg-200, #f3f4f6);
}
.markdown-body :deep(pre) {
  padding: 12px;
  border-radius: 8px;
  overflow-x: auto;
  background: var(--bg-100, #f3f4f6);
}
.markdown-body :deep(pre code) {
  padding: 0;
  background: none;
}
.markdown-body :deep(hr) {
  border: none;
  border-top: 1px solid var(--bg-300, #e5e7eb);
  margin: 1em 0;
}
.markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0.6em 0;
}
.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid var(--bg-300, #e5e7eb);
  padding: 6px 10px;
  text-align: left;
}
.markdown-body :deep(del) {
  color: var(--text-400, #9ca3af);
}
.markdown-body.is-clamped {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
