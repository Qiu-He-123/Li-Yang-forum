<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

defineOptions({ name: 'PublishChoiceView' })

const router = useRouter()
const choice = ref<'sync' | 'manual' | null>(null)

function go() {
  if (!choice.value) return
  router.push(choice.value === 'sync' ? '/wechat/publish/sync' : '/wechat/publish/manual')
}
</script>

<template>
  <div class="page">
    <header class="page-header">
      <button type="button" class="back-btn" @click="router.back()">←</button>
      <h1>选择朋友圈发布</h1>
    </header>

    <section class="card">
      <p class="tip">选择一种朋友圈同步方式：</p>

      <label class="option" :class="{ active: choice === 'sync' }">
        <input v-model="choice" type="radio" value="sync" />
        <span class="option-body">
          <span class="option-title">同步发布</span>
          <span class="option-desc">绑定后，朋友圈新动态自动同步到社区</span>
        </span>
      </label>

      <label class="option" :class="{ active: choice === 'manual' }">
        <input v-model="choice" type="radio" value="manual" />
        <span class="option-body">
          <span class="option-title">手动发布</span>
          <span class="option-desc">自己挑选朋友圈内容，手动导入发布</span>
        </span>
      </label>

      <button type="button" class="btn-primary" :disabled="!choice" @click="go">下一步</button>
    </section>
  </div>
</template>

<style scoped>
.page {
  max-width: 720px;
  margin: 0 auto;
  padding: 0 14px 60px;
  min-height: 100vh;
}
.page-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 0;
}
.page-header h1 {
  font-size: 17px;
  margin: 0;
}
.back-btn {
  border: none;
  background: transparent;
  font-size: 20px;
  cursor: pointer;
  padding: 0 4px;
}
.card {
  background: #fff;
  border-radius: 12px;
  padding: 18px;
  margin-top: 10px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05);
}
.tip {
  font-size: 13px;
  color: var(--text-600, #555);
  margin: 0 0 12px;
}
.option {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid #e5e5e5;
  border-radius: 10px;
  padding: 14px;
  margin-bottom: 10px;
  cursor: pointer;
}
.option.active {
  border-color: #4f9cff;
  background: rgba(79, 156, 255, 0.06);
}
.option input {
  accent-color: #4f9cff;
}
.option-body {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.option-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-800, #222);
}
.option-desc {
  font-size: 12px;
  color: var(--text-400, #999);
}
.btn-primary {
  width: 100%;
  border: none;
  background: #4f9cff;
  color: #fff;
  border-radius: 8px;
  padding: 10px;
  font-size: 14px;
  cursor: pointer;
  margin-top: 8px;
}
.btn-primary:disabled {
  opacity: 0.5;
}
</style>
