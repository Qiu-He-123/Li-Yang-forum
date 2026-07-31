<script setup lang="ts">
/**
 * 发帖页（P1 改造后）
 * 对齐设计稿：发帖页.html
 * - 顶部固定栏：返回 + 标题"发帖" + 发布按钮
 * - 主区：PostEditor 组件（圈子选择 + 标题 + 正文 + 图片网格 + iOS 开关）
 *
 * 阶段二：新增 onBeforeRouteLeave 守卫，编辑中离开页面时弹窗确认是否保存草稿。
 */
import { onMounted, ref } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'

import { Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import PostEditor from '../components/post/PostEditor.vue'
import { useSessionStore } from '../stores/session'
import { useSchoolStore } from '../stores/school'
import { useUIStore } from '../stores/ui'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const schoolStore = useSchoolStore()
const uiStore = useUIStore()

// 从路由 query 读取圈子 slug（从圈子详情页点击「发布」时自动带入）
const initialCircle = ref<string | undefined>(
  typeof route.query.circle === 'string' ? route.query.circle : undefined,
)

// 通过 ref 调用 PostEditor 的 publish 方法
const editorRef = ref<InstanceType<typeof PostEditor> | null>(null)
const submitting = ref(false)

// 邀请码系统：未认证用户进入发帖页时直接弹邀请码框并返回
onMounted(() => {
  if (session.isLoggedIn() && !session.isVerified()) {
    // 先返回再弹窗，避免路由 watcher 立即关闭弹窗
    onBack()
    setTimeout(() => uiStore.openInviteCodeDialog(), 100)
  }
})

function onBack() {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/')
  }
}

async function onPublish() {
  if (!editorRef.value) return
  submitting.value = true
  try {
    await editorRef.value.publish()
  } finally {
    submitting.value = false
  }
}

function onPublished() {
  // 发布成功的 toast 已由 PostEditor.publish() 统一弹出（"发布成功，内容审核中"），
  // 此处仅负责跳转到首页最新 tab，避免重复弹窗。
  router.push('/?view=latest')
}

onMounted(() => {
  if (!session.userId) {
    toast.info('请先登录')
    router.push('/')
    return
  }
  // 确保校区数据已加载（PostEditor 依赖）
  if (!schoolStore.schools.length) {
    schoolStore.loadSchools()
  }
})

// ============ 阶段二：路由离开守卫 ============
// 编辑中（有内容且未发布）路由离开时弹窗确认：确定=保存草稿并离开，取消=留在页面
onBeforeRouteLeave(async (_to, _from, next) => {
  const editor = editorRef.value
  if (editor?.hasUnsavedContent) {
    // window.confirm 只有两个按钮：确定 / 取消
    const confirmed = window.confirm('有未保存的内容，是否保存为草稿？\n\n点击「确定」保存草稿并离开；点击「取消」留在页面继续编辑。')
    if (confirmed) {
      try {
        await editor.saveDraft()
        toast.success('草稿已保存')
      } catch (err) {
        toast.error((err as Error).message)
      }
      next()
    } else {
      // 取消：留在页面
      next(false)
    }
  } else {
    next()
  }
})
</script>


<template>
  <main class="page-create">
    <!-- 顶部固定栏：返回 + 发帖 + 发布 -->
    <header class="post-header" role="banner">
      <div class="header-inner">
        <button class="back-btn" type="button" aria-label="返回" @click="onBack">
          <Icon name="arrow-left" :size="21" />
        </button>
        <h1 class="header-title">发帖</h1>
        <button
          class="publish-btn"
          type="button"
          :disabled="submitting"
          @click="onPublish"
        >
          {{ submitting ? '发布中…' : '发布' }}
        </button>
      </div>
    </header>

    <!-- 主内容 -->
    <div class="post-container">
      <PostEditor ref="editorRef" :initial-category="initialCircle" @published="onPublished" />
    </div>

    <!-- 安全底部留白 -->
    <div class="safe-bottom" aria-hidden="true"></div>
  </main>
</template>

<style scoped>
.page-create {
  min-height: 100vh;
  background: var(--bg-100);
  padding-bottom: 80px;
}

/* 顶部固定栏 */
.post-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  height: 56px;
  background: var(--bg-50);
  border-bottom: 0.5px solid var(--color-border);
}
.header-inner {
  max-width: 640px;
  margin: 0 auto;
  height: 100%;
  padding: 0 16px;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 12px;
}
.back-btn {
  justify-self: start;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  color: var(--text-800);
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 0;
  transition: background 150ms var(--ease-apple), color 150ms var(--ease-apple);
}
.back-btn:hover {
  background: var(--bg-100);
}
.header-title {
  justify-self: center;
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  color: var(--text-800);
  letter-spacing: -0.01em;
}
.publish-btn {
  justify-self: end;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 34px;
  padding: 0 18px;
  border-radius: 999px;
  background: var(--brand-500);
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  font-family: inherit;
  border: none;
  cursor: pointer;
  letter-spacing: 0.02em;
  transition: background 150ms var(--ease-apple), transform 150ms var(--ease-apple),
    opacity 150ms var(--ease-apple);
}
.publish-btn:hover:not(:disabled) {
  background: var(--brand-600);
}
.publish-btn:active:not(:disabled) {
  transform: scale(0.96);
}
.publish-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* 主容器 */
.post-container {
  max-width: 640px;
  margin: 0 auto;
  padding: 76px 20px 0;
}

/* 安全底部 */
.safe-bottom {
  height: 24px;
}

/* 响应式 */
@media (max-width: 768px) {
  .post-container {
    padding: 72px 14px 0;
  }
  .header-inner {
    padding: 0 10px;
  }
  .header-title {
    font-size: 16px;
  }
  .publish-btn {
    padding: 0 15px;
    height: 32px;
    font-size: 14px;
  }
  .back-btn {
    width: 34px;
    height: 34px;
  }
}
</style>
