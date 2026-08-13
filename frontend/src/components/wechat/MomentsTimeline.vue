<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { createComment, listComments } from '../../api/comment'
import { likeTarget, unlikeTarget } from '../../api/interaction'
import type { WechatFeedItem } from '../../api/wechat'
import type { CommentItem } from '../../types/api'
import { toast } from '../native/Toast'

interface Props {
  items: WechatFeedItem[]
  loading?: boolean
}

const props = defineProps<Props>()
const router = useRouter()
const likedSet = ref<Set<number>>(new Set())

// 微信式内联评论：懒加载 + 内联输入
const commentsMap = ref<Record<number, CommentItem[]>>({})
const commentsLoaded = ref<Set<number>>(new Set())
const commentsLoading = ref<Set<number>>(new Set())
const commentOpenId = ref<number | null>(null)
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
  const liked = likedSet.value.has(post.id)
  likedSet.value.add(post.id)
  post.like_count += 1
  try {
    if (liked) {
      await unlikeTarget('post', post.id)
      likedSet.value.delete(post.id)
      post.like_count -= 1
    } else {
      await likeTarget('post', post.id)
    }
  } catch {
    if (liked) {
      post.like_count += 1
      likedSet.value.add(post.id)
    } else {
      post.like_count -= 1
      likedSet.value.delete(post.id)
    }
    toast.error('操作失败，请先登录')
  }
}

async function toggleComments(post: WechatFeedItem) {
  if (commentOpenId.value === post.id) {
    commentOpenId.value = null
    return
  }
  commentOpenId.value = post.id
  if (commentsLoaded.value.has(post.id)) return
  commentsLoading.value.add(post.id)
  try {
    const data = (await listComments(post.id, 1, 50)).data.data
    commentsMap.value[post.id] = data.items || []
  } catch {
    commentsMap.value[post.id] = []
  } finally {
    commentsLoaded.value.add(post.id)
    commentsLoading.value.delete(post.id)
  }
}

async function submitComment(post: WechatFeedItem) {
  const content = commentText.value.trim()
  if (!content) return
  try {
    const data = (await createComment(post.id, { content })).data.data
    commentsMap.value[post.id] = [...(commentsMap.value[post.id] || []), data]
    post.comment_count += 1
    commentText.value = ''
    toast.success('评论成功')
  } catch (e: unknown) {
    const err = e as { response?: { data?: { msg?: string } } }
    toast.error(err.response?.data?.msg || '评论失败')
  }
}

function openPost(post: WechatFeedItem) {
  router.push(`/post/${post.id}`)
}
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
        <p class="moment-content" @click="openPost(post)">{{ post.content }}</p>
        <div v-if="post.image_urls.length && !post.video_urls?.length" class="moment-grid" :class="`grid-${Math.min(post.image_urls.length, 3)}`">
          <img
            v-for="(url, i) in post.image_urls"
            :key="i"
            :src="url"
            :alt="`图片${i + 1}`"
            loading="lazy"
            @click="openPost(post)"
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
          <button type="button" class="moment-action" :class="{ liked: likedSet.has(post.id) }" @click="toggleLike(post)">
            <span>{{ likedSet.has(post.id) ? '❤' : '🤍' }}</span>
            <span>{{ fmtCount(post.like_count) }}</span>
          </button>
          <button type="button" class="moment-action" :class="{ active: commentOpenId === post.id }" @click="toggleComments(post)">
            <span>💬</span>
            <span>{{ fmtCount(post.comment_count) }}</span>
          </button>
          <span class="moment-source">来自微信朋友圈</span>
        </div>

        <!-- 微信式内联评论：不进入帖子，直接在此查看/发表 -->
        <div v-if="commentOpenId === post.id" class="moment-comments">
          <div v-if="commentsLoading.has(post.id)" class="moment-comment-empty">加载评论…</div>
          <template v-else>
            <div v-if="commentsMap[post.id]?.length" class="moment-comment-list">
              <div v-for="c in commentsMap[post.id]" :key="c.id" class="moment-comment-line">
                <span class="moment-comment-author">{{ c.author }}</span>
                <span class="moment-comment-body">{{ c.content }}</span>
              </div>
            </div>
            <div v-else class="moment-comment-empty">还没有评论，来抢沙发～</div>
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
.moment-grid img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  cursor: pointer;
  display: block;
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
