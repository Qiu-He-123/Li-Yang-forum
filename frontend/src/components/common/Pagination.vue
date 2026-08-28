<script setup lang="ts">
defineProps<{
  total: number
  page: number
  pageSize: number
}>()

const emit = defineEmits<{
  (e: 'update:page', v: number): void
  (e: 'change', page: number): void
}>()

function onChange(page: number) {
  emit('update:page', page)
  emit('change', page)
}
</script>

<template>
  <div v-if="total > pageSize" class="mt-4 flex justify-center">
    <el-pagination
      :current-page="page"
      :page-size="pageSize"
      :total="total"
      layout="prev, pager, next"
      background
      @current-change="onChange"
    />
  </div>
</template>
