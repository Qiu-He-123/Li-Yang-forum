<script setup lang="ts">
/**
 * 帖子详情弹窗（管理后台通用）
 *
 * 用于：举报处理、帖子审核管理、评论审核管理 等需要查看帖子完整详情的场景。
 * 调用 GET /admin/posts/{post_id} 获取详情并展示。
 */
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { adminGetPost, type AdminPost } from '../../api/admin'

const props = defineProps<{
  modelValue: boolean
  postId: number | null
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
}>()

const visible = ref(props.modelValue)
const loading = ref(false)
const post = ref<AdminPost | null>(null)

watch(() => props.modelValue, (v) => {
  visible.value = v
  if (v && props.postId) {
    load()
  } else if (!v) {
    post.value = null
  }
})
watch(visible, (v) => emit('update:modelValue', v))

async function load() {
  if (!props.postId) return
  loading.value = true
  post.value = null
  try {
    const { data } = await adminGetPost(props.postId)
    post.value = data.data
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

const statusMeta: Record<string, { type: 'success' | 'warning' | 'danger' | 'info'; text: string }> = {
  pending: { type: 'warning', text: '待审核' },
  approved: { type: 'success', text: '已通过' },
  rejected: { type: 'danger', text: '已驳回' },
  manual_review: { type: 'info', text: '人工复审' },
}

function fmtTime(t: string | null): string {
  if (!t) return ''
  return t.replace('T', ' ').slice(0, 19)
}

const imageBase = import.meta.env.VITE_API_BASE?.replace(/\/api\/?$/, '') || '/api'
function imageUrl(path: string): string {
  if (!path) return ''
  if (path.startsWith('http')) return path
  return `${imageBase}${path.startsWith('/') ? '' : '/'}${path}`
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="帖子详情"
    width="720px"
    :close-on-click-modal="false"
    align-center
  >
    <div v-loading="loading" class="post-detail">
      <div v-if="!post && !loading" class="empty">帖子不存在或已删除</div>
      <template v-else-if="post">
        <!-- 基础信息 -->
        <div class="meta-row">
          <span class="meta-label">帖子 ID：</span>
          <span class="meta-value">#{{ post.id }}</span>
          <span class="meta-label" style="margin-left: 24px">审核状态：</span>
          <el-tag :type="statusMeta[post.ai_status]?.type || 'info'" size="small">
            {{ statusMeta[post.ai_status]?.text || post.ai_status }}
          </el-tag>
        </div>

        <div class="meta-row">
          <span class="meta-label">作者：</span>
          <span class="meta-value">{{ post.author || '#' + post.author_id }}</span>
          <span v-if="post.is_anonymous" class="meta-tag">（匿名）</span>
          <span class="meta-label" style="margin-left: 24px">分类：</span>
          <span class="meta-value">{{ post.category || '-' }}</span>
          <span class="meta-label" style="margin-left: 24px">校区：</span>
          <span class="meta-value">{{ post.school || '-' }}</span>
        </div>

        <div class="meta-row">
          <span class="meta-label">发布时间：</span>
          <span class="meta-value">{{ fmtTime(post.created_at) }}</span>
          <span class="meta-label" style="margin-left: 24px">可见性：</span>
          <span class="meta-value">{{ post.is_public ? '公开' : '私密' }}</span>
        </div>

        <!-- 标题 -->
        <div v-if="post.title" class="post-title">{{ post.title }}</div>

        <!-- 正文 -->
        <div class="post-content">{{ post.content }}</div>

        <!-- 图片 -->
        <div v-if="post.image_urls && post.image_urls.length" class="post-images">
          <img
            v-for="(url, i) in post.image_urls"
            :key="i"
            :src="imageUrl(url)"
            alt="post image"
            class="post-img"
            loading="lazy"
          />
        </div>

        <!-- 标签 -->
        <div v-if="post.tags && post.tags.length" class="post-tags">
          <el-tag v-for="tag in post.tags" :key="tag" size="small" effect="plain" style="margin-right: 6px">
            #{{ tag }}
          </el-tag>
        </div>

        <!-- 互动数据 -->
        <div class="meta-row stats-row">
          <span class="stat-item">👍 {{ post.like_count }}</span>
          <span class="stat-item">💬 {{ post.comment_count }}</span>
          <span class="stat-item">👀 {{ post.view_count }}</span>
          <span class="stat-item">🔁 {{ post.share_count || 0 }}</span>
        </div>
      </template>
    </div>
  </el-dialog>
</template>

<style scoped>
.post-detail {
  min-height: 200px;
}
.empty {
  padding: 40px 0;
  text-align: center;
  color: #8c8c8c;
  font-size: 14px;
}
.meta-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  font-size: 13px;
  margin-bottom: 12px;
  color: #262626;
}
.meta-label {
  color: #8c8c8c;
  min-width: 70px;
}
.meta-value {
  color: #262626;
}
.meta-tag {
  font-size: 12px;
  color: #faad14;
}
.post-title {
  font-size: 16px;
  font-weight: 700;
  color: #1f1f1f;
  margin: 16px 0 8px;
  line-height: 1.5;
}
.post-content {
  font-size: 14px;
  line-height: 1.7;
  color: #262626;
  background: #fafafa;
  padding: 16px;
  border-radius: 6px;
  white-space: pre-wrap;
  word-break: break-word;
  margin-bottom: 12px;
  max-height: 320px;
  overflow-y: auto;
}
.post-images {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 8px;
  margin-bottom: 12px;
}
.post-img {
  width: 100%;
  height: 140px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid #f0f0f0;
  cursor: pointer;
}
.post-tags {
  margin-bottom: 12px;
}
.stats-row {
  gap: 16px;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
}
.stat-item {
  font-size: 13px;
  color: #595959;
}
</style>
