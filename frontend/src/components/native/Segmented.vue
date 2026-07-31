<script setup lang="ts">
/**
 * Segmented Control 分段控制器（替代 el-segmented / el-tabs）
 * Apple 风格
 */
interface Option {
  label: string
  value: string | number
}

interface Props {
  modelValue: string | number
  options: Option[]
}
defineProps<Props>()
const emit = defineEmits<{ (e: 'update:modelValue', v: string | number): void; (e: 'change', v: string | number): void }>()

function onSelect(v: string | number) {
  emit('update:modelValue', v)
  emit('change', v)
}
</script>

<template>
  <div class="segmented">
    <button
      v-for="opt in options"
      :key="opt.value"
      type="button"
      class="segmented-item"
      :class="{ active: opt.value === modelValue }"
      @click="onSelect(opt.value)"
    >
      {{ opt.label }}
    </button>
  </div>
</template>
