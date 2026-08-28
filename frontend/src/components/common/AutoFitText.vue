<script setup lang="ts">
/**
 * 自动缩放文字：容器放不下时逐级缩小字号，保证不换行、不溢出。
 */
import { onMounted, ref, watch } from 'vue'

const props = defineProps<{ text: string }>()
const el = ref<HTMLElement | null>(null)

function fit() {
  const node = el.value
  if (!node) return
  let size = 18
  node.style.fontSize = `${size}px`
  while (size > 9 && node.scrollWidth > node.clientWidth + 1) {
    size -= 0.5
    node.style.fontSize = `${size}px`
  }
}

onMounted(() => fit())
watch(
  () => props.text,
  () => requestAnimationFrame(fit),
)
</script>

<template>
  <span ref="el" class="auto-fit-text">{{ text }}</span>
</template>

<style scoped>
.auto-fit-text {
  display: inline-block;
  min-width: 0;
  max-width: 100%;
  white-space: nowrap;
  overflow: hidden;
  font-weight: 700;
  color: var(--text-800);
  line-height: 1.2;
}
</style>
