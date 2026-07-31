<script setup lang="ts">
import { Warning } from '@element-plus/icons-vue'
</script>

<template>
  <div class="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-[12px] leading-5 text-amber-900">
    <el-icon class="mt-0.5 flex-none"><Warning /></el-icon>
    <span>AI 审核建议仅辅助判断，后台处置仍由管理员确认。</span>
  </div>
</template>
