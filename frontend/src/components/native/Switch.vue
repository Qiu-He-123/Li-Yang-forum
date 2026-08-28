<script setup lang="ts">
/**
 * iOS 风格 Toggle 开关（替代 el-switch）
 */
interface Props {
  modelValue: boolean
  disabled?: boolean
}
const props = defineProps<Props>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void; (e: 'change', v: boolean): void }>()

function toggle() {
  if (props.disabled) return
  const v = !props.modelValue
  emit('update:modelValue', v)
  emit('change', v)
}
</script>

<template>
  <label class="ios-toggle" :class="{ 'opacity-50 cursor-not-allowed': disabled }">
    <input type="checkbox" :checked="modelValue" :disabled="disabled" @change="toggle" />
    <span class="ios-toggle-slider"></span>
  </label>
</template>
