<script setup lang="ts">
/**
 * 原生 Dialog 组件（替代 el-dialog）
 * Apple 风格模态框，支持标题、内容插槽、底部按钮
 */
import { onMounted, onUnmounted, watch } from 'vue'
import Icon from './Icon.vue'

interface Props {
  modelValue: boolean
  title?: string
  width?: string
  closeOnOverlay?: boolean
  showClose?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  width: '480px',
  closeOnOverlay: true,
  showClose: true,
})

const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void; (e: 'close'): void }>()

function close() {
  emit('update:modelValue', false)
  emit('close')
}

function onOverlay() {
  if (props.closeOnOverlay) close()
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.modelValue) close()
}

watch(
  () => props.modelValue,
  (v) => {
    if (v) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
  },
)

onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog">
      <div v-if="modelValue" class="dialog-overlay" @click.self="onOverlay">
        <div class="dialog-panel" :style="{ maxWidth: width }" role="dialog" aria-modal="true">
          <div v-if="title || showClose" class="dialog-header">
            <h3 class="dialog-title">{{ title }}</h3>
            <button v-if="showClose" class="dialog-close" aria-label="关闭" @click="close">
              <Icon name="x" :size="18" />
            </button>
          </div>
          <div class="dialog-body">
            <slot />
          </div>
          <div v-if="$slots.footer" class="dialog-footer">
            <slot name="footer" />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  z-index: 9000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}
.dialog-panel {
  width: 100%;
  background: white;
  border-radius: 16px;
  box-shadow: 0 24px 64px -12px rgba(0, 0, 0, 0.2);
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px;
  border-bottom: 1px solid #e5e5ea;
}
.dialog-title {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  color: #1d1d1f;
}
.dialog-close {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  border: none;
  background: #f2f2f7;
  color: #6e6e73;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}
.dialog-close:hover {
  background: #e5e5ea;
  color: #1d1d1f;
}
.dialog-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}
.dialog-footer {
  padding: 14px 20px;
  border-top: 1px solid #e5e5ea;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.dialog-enter-active,
.dialog-leave-active {
  transition: opacity 0.25s cubic-bezier(0.32, 0.72, 0, 1);
}
.dialog-enter-active .dialog-panel,
.dialog-leave-active .dialog-panel {
  transition: transform 0.25s cubic-bezier(0.32, 0.72, 0, 1), opacity 0.25s;
}
.dialog-enter-from,
.dialog-leave-to {
  opacity: 0;
}
.dialog-enter-from .dialog-panel,
.dialog-leave-to .dialog-panel {
  transform: scale(0.92) translateY(8px);
  opacity: 0;
}
</style>
