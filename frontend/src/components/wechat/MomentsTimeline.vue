<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import { createComment, listComments } from '../../api/comment'
import { likeTarget, unlikeTarget } from '../../api/interaction'
import { useInteractionStore } from '../../stores/interaction'
import type { WechatFeedItem } from '../../api/wechat'
import type { CommentItem } from '../../types/api'
import { toast } from '../native/Toast'

interface Props {
  items: WechatFeedItem[]
  loading?: boolean
}

const props = defineProps<Props>()
const store = useInteractionStore()

// 点赞态：用全局 interaction store（登录时从 /users/me/likes/posts 回填），
// 刷新/翻页后仍保持"已点赞"；后端点赞幂等，一人一帖只能赞一次
function isLiked(postId: number): boolean {
  return store.likedPostIds.has(postId)
}

// 微信式内联评论：默认展示前 10 条，点"查看更多"再 +10
const COMMENTS_PAGE_SIZE = 10
const commentsMap = ref<Record<number, CommentItem[]>>({})
const commentsTotal = ref<Record<number, number>>({})
const commentsPage = ref<Record<number, number>>({})
const commentsLoading = ref<Set<number>>(new Set())
const commentText = ref('')

function fmtCount(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, '') + 'w'
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k'
  return String(n)
}

function timeText(t: string | null): string {
  if (!t) return ''
  const d = new Date(t)
  if (Number.isNaN(d.getTime())) return t
  const now = Date.now()
  const diff = Math.floor((now - d.getTime()) / 1000)
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
  if (diff < 7 * 86400) return `${Math.floor(diff / 86400)}天前`
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function avatarLetter(item: WechatFeedItem): string {
  return (item.author || 'U').charAt(0).toUpperCase()
}

async function toggleLike(post: WechatFeedItem) {
  const liked = isLiked(post.id)
  store.toggleLikedPost(post.id, !liked) // 乐观更新
  post.like_count += liked ? -1 : 1
  try {
    const res = liked ? await unlikeTarget('post', post.id) : await likeTarget('post', post.id)
    post.like_count = res.data.data.like_count // 以服务端返回为准
  } catch {
    store.toggleLikedPost(post.id, liked) // 失败回滚
    post.like_count += liked ? 1 : -1
    toast.error('操作失败，请先登录')
  }
}

// 评论：每条动态默认加载前 10 条；查看更多再翻一页
async function loadComments(post: WechatFeedItem, page: number) {
  const id = post.id
  if (commentsLoading.value.has(id)) return
  commentsLoading.value.add(id)
  try {
    const data = (await listComments(id, page, COMMENTS_PAGE_SIZE)).data.data
    const existing = commentsMap.value[id] || []
    commentsMap.value[id] = page === 1 ? data.items || [] : [...existing, ...(data.items || [])]
    commentsTotal.value[id] = data.total
    commentsPage.value[id] = page
  } catch {
    if (page === 1) commentsMap.value[id] = commentsMap.value[id] || []
  } finally {
    commentsLoading.value.delete(id)
  }
}

function loadAllComments() {
  for (const post of props.items) {
    if (commentsMap.value[post.id] === undefined && !commentsLoading.value.has(post.id)) {
      loadComments(post, 1)
    }
  }
}

function showMoreComments(post: WechatFeedItem) {
  loadComments(post, (commentsPage.value[post.id] || 1) + 1)
}

async function submitComment(post: WechatFeedItem) {
  const content = commentText.value.trim()
  if (!content) return
  try {
    const data = (await createComment(post.id, { content })).data.data
    commentsMap.value[post.id] = [...(commentsMap.value[post.id] || []), data]
    commentsTotal.value[post.id] = (commentsTotal.value[post.id] || 0) + 1
    post.comment_count += 1
    commentText.value = ''
    toast.success('评论成功')
  } catch (e: unknown) {
    const err = e as { response?: { data?: { msg?: string } } }
    toast.error(err.response?.data?.msg || '评论失败')
  }
}

onMounted(() => {
  store.loadAll()
  loadAllComments()
})

// 翻页/刷新后新出现的动态也要自动加载评论
watch(
  () => props.items,
  () => loadAllComments(),
)
</script>

<template>
  <div class="moments-timeline">
    <div v-if="loading" class="moments-empty">加载中…</div>
    <div v-else-if="!items.length" class="moments-empty">
      还没有同步的朋友圈，大家绑定微信并开启自动同步后，这里会展示所有人的朋友圈
    </div>
    <article
      v-for="post in items"
      :key="post.id"
      class="moment-item"
      :class="{ 'moment-item--pinned': post.is_pinned }"
    >
      <div class="moment-avatar">
        <img v-if="post.author_avatar_url" :src="post.author_avatar_url" :alt="post.author" class="avatar-img" />
        <span v-else class="avatar-letter">{{ avatarLetter(post) }}</span>
      </div>
      <div class="moment-main">
        <div class="moment-head">
          <span class="moment-nick">{{ post.author }}</span>
          <span v-if="post.is_pinned" class="moment-pin" title="置顶帖：付费置顶展示在频道顶部，持续一段时间">置顶</span>
          <span v-if="post.ai_status === 'pending'" class="moment-status">审核中</span>
          <span v-else-if="post.ai_status === 'rejected'" class="moment-status moment-status--rejected">未通过</span>
          <span class="moment-time">{{ timeText(post.wechat_created_at || post.created_at) }}</span>
        </div>
        <p class="moment-content">{{ post.content }}</p>
        <div v-if="post.image_urls.length && !post.video_urls?.length" class="moment-grid" :class="`grid-${Math.min(post.image_urls.length, 3)}`">
          <!-- 点图看大图（Element Plus 预览），绝不跳转帖子详情页 -->
          <el-image
            v-for="(url, i) in post.image_urls"
            :key="i"
            :src="url"
            :preview-src-list="post.image_urls"
            :initial-index="i"
            preview-teleported
            fit="cover"
            class="moment-img"
            :alt="`图片${i + 1}`"
          />
        </div>
        <!-- 视频：HTML5 播放器 -->
        <div v-if="post.video_urls?.length" class="moment-videos">
          <video
            v-for="(vurl, vi) in post.video_urls"
            :key="vi"
            class="moment-video"
            controls
            preload="metadata"
            :src="vurl"
          ></video>
        </div>
        <div class="moment-foot">
          <button type="button" class="moment-action" :class="{ liked: isLiked(post.id) }" @click="toggleLike(post)">
            <span>{{ isLiked(post.id) ? '❤' : '🤍' }}</span>
            <span>{{ fmtCount(post.like_count) }}</span>
          </button>
          <span class="moment-action"><span>💬</span><span>{{ fmtCount(post.comment_count) }}</span></span>
          <span class="moment-source">来自微信朋友圈</span>
        </div>

        <!-- 微信式内联评论：默认展示前 10 条，更多点"查看更多"再 +10；不进入帖子页 -->
        <div class="moment-comments">
          <div v-if="commentsLoading.has(post.id) && !commentsMap[post.id]?.length" class="moment-comment-empty">加载评论…</div>
          <template v-else>
            <div v-if="commentsMap[post.id]?.length" class="moment-comment-list">
              <div v-for="c in commentsMap[post.id]" :key="c.id" class="moment-comment-line">
                <span class="moment-comment-author">{{ c.author }}</span>
                <span class="moment-comment-body">{{ c.content }}</span>
              </div>
              <button
                v-if="(commentsMap[post.id]?.length || 0) < (commentsTotal[post.id] || 0)"
                type="button"
                class="moment-comment-more"
                @click="showMoreComments(post)"
              >
                查看更多评论（还剩 {{ (commentsTotal[post.id] || 0) - (commentsMap[post.id]?.length || 0) }} 条）
              </button>
            </div>
            <div v-else-if="!commentsLoading.has(post.id)" class="moment-comment-empty">还没有评论，来抢沙发～</div>
            <div class="moment-comment-input-row">
              <input
                v-model="commentText"
                class="moment-comment-input"
                type="text"
                maxlength="200"
                placeholder="评论…"
                @keyup.enter="submitComment(post)"
              />
              <button
                type="button"
                class="moment-comment-send"
                :disabled="!commentText.trim()"
                @click="submitComment(post)"
              >
                发送
              </button>
            </div>
          </template>
        </div>
      </div>
    </article>
  </div>
</template>

<style scoped>
.moments-timeline {
  padding: 4px 12px 24px;
}
.moments-empty {
  text-align: center;
  color: var(--text-400, #999);
  padding: 48px 16px;
  font-size: 13px;
  line-height: 1.7;
}
.moment-item {
  display: flex;
  gap: 10px;
  padding: 14px 0;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
}
.moment-item--pinned {
  background: linear-gradient(90deg, rgba(255, 193, 7, 0.08), transparent);
}
.moment-avatar {
  flex: 0 0 40px;
}
.avatar-img,
.avatar-letter {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  object-fit: cover;
}
.avatar-letter {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #4f9cff, #7b5cff);
  color: #fff;
  font-weight: 600;
}
.moment-main {
  flex: 1;
  min-width: 0;
}
.moment-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.moment-nick {
  font-weight: 600;
  font-size: 14px;
  color: #576b95;
}
.moment-pin {
  font-size: 10px;
  color: #fff;
  background: #ff9800;
  border-radius: 4px;
  padding: 1px 5px;
}
.moment-status {
  font-size: 10px;
  color: #b26a00;
  background: #fff7e0;
  border: 1px solid #f0dc9c;
  border-radius: 4px;
  padding: 1px 5px;
}
.moment-status--rejected {
  color: #c62828;
  background: #fdecea;
  border-color: #f2b8b5;
}
.moment-time {
  font-size: 11px;
  color: var(--text-400, #999);
  margin-left: auto;
}
.moment-content {
  margin: 6px 0 8px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-800, #222);
  word-break: break-word;
  cursor: pointer;
  white-space: pre-wrap;
}
.moment-grid {
  display: grid;
  gap: 4px;
  border-radius: 8px;
  overflow: hidden;
  max-width: 320px;
}
.moment-grid.grid-1 img {
  max-width: 220px;
  max-height: 220px;
  object-fit: cover;
  border-radius: 8px;
}
.moment-grid.grid-2 {
  grid-template-columns: repeat(2, 1fr);
}
.moment-grid.grid-3 {
  grid-template-columns: repeat(3, 1fr);
}
.moment-grid img,
.moment-img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  cursor: pointer;
  display: block;
}
.moment-img :deep(img) {
  object-fit: cover;
}
.moment-videos {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-width: 320px;
  margin-top: 6px;
}
.moment-video {
  width: 100%;
  max-height: 360px;
  border-radius: 8px;
  background: #000;
  display: block;
}
.moment-foot {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 8px;
}
.moment-action {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: none;
  background: transparent;
  color: var(--text-500, #666);
  font-size: 12px;
  cursor: pointer;
  padding: 2px 0;
}
.moment-action.liked {
  color: #e0245e;
}
.moment-source {
  margin-left: auto;
  font-size: 10px;
  color: var(--text-300, #bbb);
}

/* 微信式内联评论 */
.moment-comments {
  margin: 8px 0 0;
  padding: 8px 10px;
  background: rgba(0, 0, 0, 0.045);
  border-radius: 8px;
  font-size: 13px;
  max-width: 320px;
}
.moment-comment-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
}
.moment-comment-line {
  line-height: 1.5;
  word-break: break-word;
}
.moment-comment-author {
  color: #576b95;
  font-weight: 500;
  margin-right: 6px;
}
.moment-comment-body {
  color: var(--text-800, #222);
  white-space: pre-wrap;
  word-break: break-word;
}
.moment-comment-more {
  border: none;
  background: transparent;
  color: #576b95;
  font-size: 12px;
  cursor: pointer;
  padding: 2px 0;
  align-self: flex-start;
}
.moment-comment-empty {
  color: var(--text-400, #999);
  font-size: 12px;
  padding: 4px 0 8px;
}
.moment-comment-input-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.moment-comment-input {
  flex: 1;
  min-width: 0;
  border: 1px solid rgba(0, 0, 0, 0.12);
  background: #fff;
  border-radius: 999px;
  padding: 5px 12px;
  font-size: 13px;
  outline: none;
}
.moment-comment-send {
  border: none;
  background: #576b95;
  color: #fff;
  border-radius: 999px;
  padding: 5px 14px;
  font-size: 12px;
  cursor: pointer;
  flex-shrink: 0;
}
.moment-comment-send:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
