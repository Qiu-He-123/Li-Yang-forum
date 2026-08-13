<script setup lang="ts">
import { useRouter } from 'vue-router'

defineOptions({ name: 'PublishHubView' })

const router = useRouter()

const options = [
  {
    key: 'post',
    title: '发帖子',
    desc: '文字/图片发到社区圈子',
    icon: '📝',
    to: '/post/create',
  },
  {
    key: 'video',
    title: '分享视频',
    desc: '抖音/快手链接一键转视频帖',
    icon: '🎬',
    to: '/video/share',
    hot: true,
  },
  {
    key: 'wechat',
    title: '同步微信朋友圈',
    desc: '绑定微信，同步/手动导入朋友圈',
    icon: '💬',
    to: '/wechat/publish',
  },
]
</script>

<template>
  <div class="page">
    <header class="page-header">
      <button type="button" class="back-btn" @click="router.back()">←</button>
      <h1>发布</h1>
    </header>

    <section class="hub">
      <button
        v-for="opt in options"
        :key="opt.key"
        type="button"
        class="hub-card"
        :class="{ 'hub-card--hot': opt.hot }"
        @click="router.push(opt.to)"
      >
        <span class="hub-icon">{{ opt.icon }}</span>
        <span class="hub-body">
          <span class="hub-title">
            {{ opt.title }}
            <span v-if="opt.hot" class="hub-hot">新</span>
          </span>
          <span class="hub-desc">{{ opt.desc }}</span>
        </span>
        <span class="hub-arrow">›</span>
      </button>
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
.hub {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 10px;
}
.hub-card {
  display: flex;
  align-items: center;
  gap: 14px;
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 14px;
  padding: 16px;
  cursor: pointer;
  text-align: left;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.hub-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.08);
}
.hub-card--hot {
  border-color: rgba(255, 45, 85, 0.35);
  background: linear-gradient(135deg, #fff 60%, rgba(255, 45, 85, 0.05));
}
.hub-icon {
  font-size: 26px;
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  background: #f5f7fa;
  border-radius: 12px;
  flex-shrink: 0;
}
.hub-card--hot .hub-icon {
  background: rgba(255, 45, 85, 0.1);
}
.hub-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.hub-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-800, #222);
}
.hub-hot {
  font-size: 10px;
  color: #fff;
  background: #ff2d55;
  border-radius: 999px;
  padding: 1px 6px;
  margin-left: 4px;
  vertical-align: 1px;
}
.hub-desc {
  font-size: 12px;
  color: var(--text-400, #999);
}
.hub-arrow {
  color: #c8cdd4;
  font-size: 22px;
}
</style>
