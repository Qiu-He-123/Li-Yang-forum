<script setup lang="ts">
/**
 * 原生 Select 下拉选择（替代 el-select）
 * Apple 风格，支持自定义触发器
 */
import { onMounted, onUnmounted, ref } from 'vue'
import Icon from './Icon.vue'

interface Option {
  label: string
  value: string | number
  [k: string]: any
}

interface Props {
  modelValue: string | number
  options: Option[]
  placeholder?: string
  disabled?: boolean
  width?: string
}

const props = withDefaults(defineProps<Props>(), {
  placeholder: '请选择',
  width: '100%',
})

const emit = defineEmits<{ (e: 'update:modelValue', v: string | number): void; (e: 'change', v: string | number): void }>()

const open = ref(false)
const rootRef = ref<HTMLElement | null>(null)

const selectedLabel = ref(props.options.find((o) => o.value === props.modelValue)?.label || props.placeholder)

function onToggle() {
  if (props.disabled) return
  open.value = !open.value
}

function onSelect(opt: Option) {
  emit('update:modelValue', opt.value)
  emit('change', opt.value)
  selectedLabel.value = opt.label
  open.value = false
}

function onDocClick(e: MouseEvent) {
  if (rootRef.value && !rootRef.value.contains(e.target as Node)) {
    open.value = false
  }
}

onMounted(() => document.addEventListener('click', onDocClick))
onUnmounted(() => document.removeEventListener('click', onDocClick))
</script>

<template>
  <div ref="rootRef" class="native-select" :style="{ width }" :class="{ disabled }">
    <button type="button" class="select-trigger" :disabled="disabled" @click="onToggle">
      <span class="select-value" :class="{ placeholder: !modelValue && modelValue !== 0 }">{{ selectedLabel }}</span>
      <Icon name="chevron-down" :size="16" :class="{ 'rotate-180': open }" />
    </button>
    <Transition name="dropdown">
      <div v-if="open" class="select-dropdown">
        <button
          v-for="opt in options"
          :key="opt.value"
          type="button"
          class="select-option"
          :class="{ active: opt.value === modelValue }"
          @click="onSelect(opt)"
        >
          <span>{{ opt.label }}</span>
          <Icon v-if="opt.value === modelValue" name="check" :size="16" color="#007aff" />
        </button>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.native-select {
  position: relative;
  display: inline-block;
}
.native-select.disabled {
  opacity: 0.5;
}
.select-trigger {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 12px;
  border: 1px solid #e5e5ea;
  background: white;
  font-size: 14px;
  color: #1d1d1f;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.32, 0.72, 0, 1);
}
.select-trigger:hover:not(:disabled) {
  border-color: #c7c7cc;
}
.select-trigger:focus {
  outline: none;
  border-color: #007aff;
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.15);
}
.select-value.placeholder {
  color: #8e8e93;
}
.select-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  background: white;
  border-radius: 12px;
  box-shadow: 0 8px 16px -4px rgba(0, 0, 0, 0.1), 0 4px 8px -2px rgba(0, 0, 0, 0.05);
  z-index: 50;
  padding: 4px;
  max-height: 240px;
  overflow-y: auto;
}
.select-option {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 12px;
  border-radius: 8px;
  font-size: 14px;
  color: #1d1d1f;
  cursor: pointer;
  border: none;
  background: transparent;
  transition: background 0.15s;
  text-align: left;
}
.select-option:hover {
  background: #f2f2f7;
}
.select-option.active {
  color: #007aff;
  font-weight: 600;
}

.dropdown-enter-active,
.dropdown-leave-active {
  transition: opacity 0.2s cubic-bezier(0.32, 0.72, 0, 1), transform 0.2s;
}
.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
