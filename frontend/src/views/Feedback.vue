<script setup lang="ts">
/**
 * 意见反馈页
 *
 * 功能：
 * - 列表展示当前用户提交的反馈（按时间倒序）
 * - 点击卡片展开详情与回复
 * - 底部固定「写反馈」按钮，弹出表单弹窗
 * - 表单：分类（标签）+ 标题 + 内容 + 联系方式（选填）
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import EmptyState from '../components/common/EmptyState.vue'
import { Dialog, Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import {
  closeFeedback,
  createFeedback,
  listMyFeedbacks,
  type Feedback,
} from '../api/feedback'

const router = useRouter()

const items = ref<Feedback[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = 20
const total = ref(0)
const hasMore = computed(() => items.value.length < total.value)

// 当前展开详情的反馈 id（同时只展开一个）
const expandedId = ref<number | null>(null)

// 写反馈弹窗
const formVisible = ref(false)
const submitting = ref(false)
const form = reactive({
  category: '建议' as string,
  title: '',
  content: '',
  contact: '',
})

const categories = [
  { value: 'bug', label: 'Bug' },
  { value: '建议', label: '建议' },
  { value: '疑问', label: '疑问' },
  { value: '其他', label: '其他' },
]

const statusMeta: Record<string, { text: string; cls: string }> = {
  pending: { text: '待处理', cls: 'status-pending' },
  replied: { text: '已回复', cls: 'status-replied' },
  closed: { text: '已关闭', cls: 'status-closed' },
}

async function loadList(reset = false) {
  if (reset) {
    page.value = 1
    items.value = []
  }
  if (loading.value) return
  loading.value = true
  try {
    const { data } = await listMyFeedbacks(page.value, pageSize)
    const next = data.data.items || []
    items.value = reset ? next : [...items.value, ...next]
    total.value = data.data.total || 0
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    loading.value = false
  }
}

async function onLoadMore() {
  if (loading.value || !hasMore.value) return
  page.value += 1
  await loadList(false)
}

function toggleExpand(item: Feedback) {
  if (item.status === 'closed') {
    expandedId.value = expandedId.value === item.id ? null : item.id
    return
  }
  expandedId.value = expandedId.value === item.id ? null : item.id
}

function openForm() {
  form.category = '建议'
  form.title = ''
  form.content = ''
  form.contact = ''
  formVisible.value = true
}

async function submitForm() {
  if (!form.title.trim()) {
    toast.error('请填写标题')
    return
  }
  if (!form.content.trim()) {
    toast.error('请填写反馈内容')
    return
  }
  if (submitting.value) return
  submitting.value = true
  try {
    await createFeedback({
      category: form.category,
      title: form.title.trim(),
      content: form.content.trim(),
      contact: form.contact.trim() || undefined,
    })
    toast.success('反馈已提交，感谢你的声音')
    formVisible.value = false
    await loadList(true)
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    submitting.value = false
  }
}

async function onClose(item: Feedback) {
  if (!window.confirm('确定要关闭这条反馈吗？关闭后将不再接受回复。')) return
  try {
    await closeFeedback(item.id)
    item.status = 'closed'
    toast.success('已关闭')
  } catch (err) {
    toast.error((err as Error).message)
  }
}

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push('/')
}

function fmtTime(t: string | null | undefined): string {
  if (!t) return ''
  return t.replace('T', ' ').slice(0, 16)
}

function timeAgo(dateStr?: string | null): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const now = new Date()
  const diff = (now.getTime() - d.getTime()) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
  if (diff < 604800) return `${Math.floor(diff / 86400)}天前`
  return d.toLocaleDateString()
}

const isEmpty = computed(() => !loading.value && items.value.length === 0)

onMounted(() => {
  loadList(true)
})
</script>

<template>
  <main class="page-feedback">
    <!-- 顶部栏 -->
    <header class="page-header">
      <button class="icon-btn" type="button" aria-label="返回" @click="goBack">
        <Icon name="arrow-left" :size="20" />
      </button>
      <h1 class="page-title">意见反馈</h1>
      <span class="icon-btn-placeholder" />
    </header>

    <div class="page-container">
      <!-- 统计条 -->
      <div v-if="items.length" class="stat-bar">
        <Icon name="message-square" :size="14" />
        <span>共 {{ total }} 条反馈</span>
      </div>

      <!-- 加载中（首次） -->
      <div v-if="loading && !items.length" class="loading-tip">
        <Icon name="refresh" :size="20" />
        <span>加载中…</span>
      </div>

      <!-- 反馈列表 -->
      <div v-else-if="items.length" class="feedback-list">
        <article
          v-for="item in items"
          :key="item.id"
          class="feedback-item"
          :class="{ expanded: expandedId === item.id }"
        >
          <div class="item-head" @click="toggleExpand(item)">
            <div class="item-head-main">
              <div class="item-title-row">
                <span class="item-cat">#{{ item.category || '其他' }}</span>
                <h3 class="item-title">{{ item.title }}</h3>
              </div>
              <div class="item-meta">
                <span class="meta-status" :class="statusMeta[item.status]?.cls || 'status-pending'">
                  {{ statusMeta[item.status]?.text || item.status }}
                </span>
                <span class="meta-dot">·</span>
                <span class="meta-time">{{ timeAgo(item.created_at) }}</span>
                <span class="meta-dot">·</span>
                <span class="meta-reply">
                  <Icon name="message-square" :size="12" />
                  {{ item.replies?.length || 0 }} 回复
                </span>
              </div>
            </div>
            <span class="expand-arrow" :class="{ rotated: expandedId === item.id }">
              <Icon name="chevron-down" :size="16" />
            </span>
          </div>

          <!-- 展开详情 -->
          <div v-if="expandedId === item.id" class="item-detail">
            <div class="detail-section">
              <div class="detail-label">反馈内容</div>
              <p class="detail-content">{{ item.content }}</p>
              <div v-if="item.contact" class="detail-contact">
                联系方式：<span>{{ item.contact }}</span>
              </div>
              <div class="detail-time">{{ fmtTime(item.created_at) }}</div>
            </div>

            <!-- 回复列表 -->
            <div v-if="item.replies?.length" class="reply-list">
              <div class="reply-list-title">官方回复（{{ item.replies.length }}）</div>
              <div v-for="r in item.replies" :key="r.id" class="reply-item">
                <div class="reply-head">
                  <span class="reply-name">{{ r.replier_name || '管理员' }}</span>
                  <span class="reply-time">{{ timeAgo(r.created_at) }}</span>
                </div>
                <p class="reply-content">{{ r.content }}</p>
              </div>
            </div>

            <!-- 关闭按钮 -->
            <div v-if="item.status !== 'closed'" class="detail-actions">
              <button class="close-action" type="button" @click="onClose(item)">
                关闭反馈
              </button>
            </div>
          </div>
        </article>

        <!-- 加载更多 -->
        <div v-if="hasMore" class="load-more">
          <button
            class="load-more-btn"
            type="button"
            :disabled="loading"
            @click="onLoadMore"
          >
            <Icon v-if="loading" name="refresh" :size="14" />
            {{ loading ? '加载中…' : '加载更多' }}
          </button>
        </div>
        <div v-else class="list-end">
          <span>没有更多了</span>
        </div>
      </div>

      <!-- 空状态 -->
      <EmptyState v-else-if="isEmpty" icon="message-square" text="还没有反馈记录，点击下方按钮写下你的声音" />
    </div>

    <!-- 底部固定按钮 -->
    <div class="footer-bar">
      <button class="write-btn" type="button" @click="openForm">
        <Icon name="edit" :size="18" />
        <span>写反馈</span>
      </button>
    </div>

    <!-- 写反馈弹窗 -->
    <Dialog v-model="formVisible" title="写反馈" width="460px">
      <div class="fb-form">
        <!-- 分类 -->
        <div class="form-row">
          <label class="form-label">分类</label>
          <div class="cat-tags">
            <button
              v-for="c in categories"
              :key="c.value"
              type="button"
              class="cat-tag"
              :class="{ active: form.category === c.value }"
              @click="form.category = c.value"
            >
              {{ c.label }}
            </button>
          </div>
        </div>

        <!-- 标题 -->
        <div class="form-row">
          <label class="form-label">
            标题 <span class="req">*</span>
          </label>
          <input
            v-model="form.title"
            class="form-input"
            type="text"
            maxlength="50"
            placeholder="一句话描述你的反馈"
          />
        </div>

        <!-- 内容 -->
        <div class="form-row">
          <label class="form-label">
            内容 <span class="req">*</span>
          </label>
          <textarea
            v-model="form.content"
            class="form-textarea"
            rows="5"
            maxlength="1000"
            placeholder="详细描述你遇到的问题或建议（最多 1000 字）"
          />
        </div>

        <!-- 联系方式 -->
        <div class="form-row">
          <label class="form-label">联系方式（选填）</label>
          <input
            v-model="form.contact"
            class="form-input"
            type="text"
            maxlength="50"
            placeholder="手机/邮箱/微信，方便我们联系你"
          />
        </div>
      </div>
      <template #footer>
        <button class="btn-cancel" type="button" @click="formVisible = false">取消</button>
        <button class="btn-submit" type="button" :disabled="submitting" @click="submitForm">
          {{ submitting ? '提交中…' : '提交反馈' }}
        </button>
      </template>
    </Dialog>
  </main>
</template>

<style scoped>
.page-feedback {
  min-height: 100vh;
  background: var(--bg-100);
  padding-bottom: calc(150px + env(safe-area-inset-bottom));
}

/* 顶部 */
.page-header {
  position: sticky;
  top: 0;
  z-index: 50;
  background: rgba(255, 255, 255, 0.95);
  -webkit-backdrop-filter: blur(20px);
  backdrop-filter: blur(20px);
  border-bottom: 0.5px solid var(--bg-300);
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  padding-top: env(safe-area-inset-top);
}
.page-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-800);
  margin: 0;
  flex: 1;
  text-align: center;
}
.icon-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: transparent;
  cursor: pointer;
  display: grid;
  place-items: center;
  color: var(--text-600);
  transition: background 0.15s;
}
.icon-btn:hover {
  background: var(--bg-100);
}
.icon-btn-placeholder {
  width: 36px;
  height: 36px;
  display: inline-block;
}

/* 内容区 */
.page-container {
  max-width: 720px;
  margin: 0 auto;
  padding: 8px 16px 0;
}

/* 统计条 */
.stat-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 4px 12px;
  font-size: 12px;
  color: var(--text-500);
}

/* 加载中 */
.loading-tip {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 48px 0;
  color: var(--text-500);
  font-size: 13px;
}

/* 列表 */
.feedback-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.feedback-item {
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  overflow: hidden;
  transition: box-shadow 0.15s;
}
.feedback-item:hover {
  box-shadow: var(--shadow-sm);
}
.feedback-item.expanded {
  box-shadow: var(--shadow-sm);
}

.item-head {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 14px;
  cursor: pointer;
}
.item-head-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.item-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.item-cat {
  font-size: 11px;
  font-weight: 600;
  color: var(--brand-500);
  background: rgba(0, 122, 255, 0.08);
  padding: 2px 8px;
  border-radius: 999px;
  flex-shrink: 0;
}
.item-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-800);
  line-height: 1.4;
  flex: 1;
  min-width: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.item-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-400);
  flex-wrap: wrap;
}
.meta-status {
  font-weight: 600;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 11px;
}
.status-pending {
  color: #ff9500;
  background: rgba(255, 149, 0, 0.1);
}
.status-replied {
  color: #34c759;
  background: rgba(52, 199, 89, 0.1);
}
.status-closed {
  color: var(--text-400);
  background: var(--bg-100);
}
.meta-dot {
  color: var(--bg-300);
}
.meta-reply {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}
.expand-arrow {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  color: var(--text-400);
  transition: transform 0.2s ease;
  flex-shrink: 0;
}
.expand-arrow.rotated {
  transform: rotate(180deg);
}

/* 展开详情 */
.item-detail {
  border-top: 0.5px solid var(--bg-200);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.detail-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.detail-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-500);
}
.detail-content {
  margin: 0;
  font-size: 14px;
  color: var(--text-800);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.detail-contact {
  font-size: 12px;
  color: var(--text-500);
  margin-top: 4px;
}
.detail-contact span {
  color: var(--text-700);
}
.detail-time {
  font-size: 11px;
  color: var(--text-300);
  margin-top: 4px;
}

/* 回复列表 */
.reply-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: var(--bg-100);
  border-radius: 12px;
  padding: 12px;
}
.reply-list-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-600);
}
.reply-item {
  background: var(--bg-50);
  border-radius: 10px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.reply-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.reply-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--brand-500);
}
.reply-time {
  font-size: 11px;
  color: var(--text-400);
}
.reply-content {
  margin: 0;
  font-size: 13px;
  color: var(--text-700);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.detail-actions {
  display: flex;
  justify-content: flex-end;
}
.close-action {
  font-size: 13px;
  color: var(--text-500);
  background: transparent;
  border: 1px solid var(--bg-300);
  padding: 6px 14px;
  border-radius: 999px;
  cursor: pointer;
  transition: all 0.15s;
}
.close-action:hover {
  color: #ff3b30;
  border-color: rgba(255, 59, 48, 0.4);
  background: rgba(255, 59, 48, 0.05);
}

/* 加载更多 */
.load-more {
  display: flex;
  justify-content: center;
  padding: 16px 0 8px;
}
.load-more-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 20px;
  border: 1px solid var(--bg-300);
  background: var(--bg-50);
  color: var(--text-600);
  font-size: 13px;
  border-radius: 999px;
  cursor: pointer;
  transition: all 0.15s;
}
.load-more-btn:hover:not(:disabled) {
  background: var(--bg-100);
  border-color: var(--brand-400);
  color: var(--brand-500);
}
.load-more-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.list-end {
  text-align: center;
  padding: 16px 12px 18px;
  font-size: 12px;
  color: var(--text-300);
}

/* 底部固定按钮（避开底部导航栏） */
.footer-bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 70px;
  z-index: 60;
  padding: 10px 16px calc(10px + env(safe-area-inset-bottom));
  background: rgba(255, 255, 255, 0.95);
  -webkit-backdrop-filter: blur(20px);
  backdrop-filter: blur(20px);
  border-top: 0.5px solid var(--bg-300);
  display: flex;
  justify-content: center;
}
.write-btn {
  max-width: 720px;
  width: 100%;
  height: 46px;
  border: none;
  border-radius: 999px;
  background: var(--brand-500);
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: transform 0.15s, background 0.15s;
}
.write-btn:hover {
  background: var(--brand-600, #0066d6);
}
.write-btn:active {
  transform: scale(0.98);
}

/* 弹窗表单 */
.fb-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.form-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.form-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-700, #3a3a3c);
}
.req {
  color: var(--state-error, #ff3b30);
  margin-left: 2px;
}
.form-input,
.form-textarea {
  width: 100%;
  padding: 9px 12px;
  font-size: 14px;
  font-family: inherit;
  color: var(--text-800);
  background: var(--bg-100, #f2f2f7);
  border: 1px solid transparent;
  border-radius: 10px;
  outline: none;
  transition: border-color 150ms cubic-bezier(0.32, 0.72, 0, 1),
    background 150ms cubic-bezier(0.32, 0.72, 0, 1);
  resize: none;
}
.form-input:focus,
.form-textarea:focus {
  border-color: var(--brand-500);
  background: var(--bg-50, #fff);
}
.cat-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.cat-tag {
  padding: 6px 14px;
  border-radius: 999px;
  border: 1px solid var(--bg-300);
  background: var(--bg-50);
  color: var(--text-600);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}
.cat-tag:hover {
  border-color: var(--brand-400);
  color: var(--brand-500);
}
.cat-tag.active {
  background: var(--brand-500);
  border-color: var(--brand-500);
  color: #fff;
}
.btn-cancel,
.btn-submit {
  height: 36px;
  padding: 0 18px;
  border-radius: 999px;
  border: none;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-cancel {
  background: var(--bg-100);
  color: var(--text-600);
}
.btn-cancel:hover {
  background: var(--bg-200);
}
.btn-submit {
  background: var(--brand-500);
  color: #fff;
}
.btn-submit:hover:not(:disabled) {
  background: var(--brand-600, #0066d6);
}
.btn-submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

@media (max-width: 768px) {
  .page-header {
    height: 48px;
    padding: 0 12px;
    padding-top: env(safe-area-inset-top);
  }
  .page-container {
    padding: 8px 12px 0;
  }
}
</style>
