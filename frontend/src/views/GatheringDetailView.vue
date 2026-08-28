<script setup lang="ts">
/**
 * 组局详情页（真实后端）
 * - 顶部：返回 + 分享
 * - 封面图 / 头部信息（标题、状态、分类、时间、地点、人数）
 * - 发起人卡片 + 成员头像列表
 * - 详情描述 + 图片
 * - 底部操作栏：报名 / 退出报名 / 取消组局（发起人）/ 满员 / 已结束
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import { useSessionStore } from '../stores/session'
import { useUIStore } from '../stores/ui'
import {
  cancelGathering,
  fetchGathering,
  joinGathering,
  leaveGathering,
  type Gathering,
} from '../api/gathering'
import MessageBoard from '../components/comment/MessageBoard.vue'
import PostPetBox from '../components/post/PostPetBox.vue'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const uiStore = useUIStore()

const gatheringId = computed(() => Number(route.params.id))
const loading = ref(false)
const loadError = ref('')
const gathering = ref<Gathering | null>(null)
const acting = ref(false)

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const { data: resp } = await fetchGathering(gatheringId.value)
    gathering.value = resp.data
  } catch (err) {
    loadError.value = (err as Error).message || '组局不存在'
    gathering.value = null
  } finally {
    loading.value = false
  }
}

function onBack() {
  if (window.history.length > 1) router.back()
  else router.push('/gatherings')
}

// ====== 展示辅助 ======
function isImageUrl(url: string | null | undefined): boolean {
  return !!url && (url.startsWith('/') || url.startsWith('http'))
}

function fmtDateTime(iso: string | null): string {
  if (!iso) return '时间待定'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '时间待定'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const statusInfo = computed(() => {
  const g = gathering.value
  if (!g) return { text: '', cls: '' }
  if (g.status === 'cancelled') return { text: '已取消', cls: 'is-cancelled' }
  if (g.status === 'ended') return { text: '已结束', cls: 'is-ended' }
  if (g.joined_people >= g.max_people) return { text: '已满员', cls: 'is-full' }
  return { text: '招募中', cls: 'is-recruiting' }
})

/** 是否可报名 */
const canJoin = computed(() => {
  const g = gathering.value
  if (!g) return false
  return (
    g.status === 'recruiting' &&
    !g.is_host &&
    !g.is_joined &&
    g.joined_people < g.max_people
  )
})

// ====== 操作 ======
async function onJoin() {
  if (!session.isLoggedIn()) {
    uiStore.openAuthDialog()
    return
  }
  acting.value = true
  try {
    const { data: resp } = await joinGathering(gatheringId.value)
    gathering.value = resp.data as any
    toast.success('报名成功')
  } catch {
    // 错误提示由 http 拦截器统一处理
  } finally {
    acting.value = false
  }
}

async function onLeave() {
  if (!session.isLoggedIn()) {
    uiStore.openAuthDialog()
    return
  }
  acting.value = true
  try {
    const { data: resp } = await leaveGathering(gatheringId.value)
    gathering.value = resp.data as any
    toast.success('已退出组局')
  } catch {
    // 错误提示由 http 拦截器统一处理
  } finally {
    acting.value = false
  }
}

async function onCancel() {
  if (!gathering.value) return
  if (!window.confirm(`确定取消组局「${gathering.value.title}」吗？取消后无法恢复。`)) return
  acting.value = true
  try {
    const { data: resp } = await cancelGathering(gatheringId.value)
    gathering.value = resp.data as any
    toast.success('组局已取消')
  } catch {
    // 错误提示由 http 拦截器统一处理
  } finally {
    acting.value = false
  }
}

function onShare() {
  // 复制链接到剪贴板
  const url = window.location.href
  if (navigator.clipboard) {
    navigator.clipboard.writeText(url).then(() => toast.success('链接已复制'))
  } else {
    toast.success(url)
  }
}

onMounted(() => {
  load()
})
</script>

<template>
  <div class="gathering-detail-page">
    <!-- 顶部导航 -->
    <header class="gd-header">
      <button class="gd-header__btn" type="button" @click="onBack">
        <Icon name="chevron-left" :size="22" />
      </button>
      <button class="gd-header__btn" type="button" @click="onShare">
        <Icon name="share" :size="20" />
      </button>
    </header>

    <!-- 加载中 -->
    <div v-if="loading" class="gd-state">
      <div class="gd-state__spinner"></div>
      <p class="gd-state__text">加载中...</p>
    </div>

    <!-- 加载失败 -->
    <div v-else-if="!gathering" class="gd-state">
      <span class="gd-state__emoji">🎉</span>
      <p class="gd-state__text">{{ loadError || '组局不存在' }}</p>
      <button class="gd-state__btn" type="button" @click="onBack">返回组局广场</button>
    </div>

    <template v-else>
      <!-- 封面图 -->
      <div v-if="gathering.images.length && isImageUrl(gathering.images[0])" class="gd-cover">
        <img :src="gathering.images[0]" :alt="gathering.title" />
      </div>
      <div v-else class="gd-no-cover-spacer"></div>

      <!-- 头部信息卡 -->
      <section class="gd-info-card" :class="{ 'gd-info-card--no-cover': !(gathering.images.length && isImageUrl(gathering.images[0])) }">
        <div class="gd-info-card__tags">
          <span class="gd-type-tag" :class="gathering.type === 'online' ? 'is-online' : 'is-offline'">
            {{ gathering.type === 'online' ? '🎮 线上组局' : '📍 线下组局' }}
          </span>
          <span class="gd-status" :class="statusInfo.cls">{{ statusInfo.text }}</span>
          <span class="gd-cat">{{ gathering.category }}</span>
        </div>
        <h1 class="gd-title">{{ gathering.title }}</h1>

        <div class="gd-rows">
          <div class="gd-row">
            <Icon name="clock" :size="16" class="gd-row__icon" />
            <div class="gd-row__body">
              <div class="gd-row__label">开始时间</div>
              <div class="gd-row__value">{{ fmtDateTime(gathering.start_time) }}</div>
            </div>
          </div>
          <div v-if="gathering.end_time" class="gd-row">
            <Icon name="clock" :size="16" class="gd-row__icon" />
            <div class="gd-row__body">
              <div class="gd-row__label">结束时间</div>
              <div class="gd-row__value">{{ fmtDateTime(gathering.end_time) }}</div>
            </div>
          </div>
          <div v-if="gathering.location" class="gd-row">
            <Icon name="map-pin" :size="16" class="gd-row__icon" />
            <div class="gd-row__body">
              <div class="gd-row__label">活动地点</div>
              <div class="gd-row__value">{{ gathering.location }}</div>
            </div>
          </div>
          <div class="gd-row">
            <Icon name="users" :size="16" class="gd-row__icon" />
            <div class="gd-row__body">
              <div class="gd-row__label">参与人数</div>
              <div class="gd-row__value">
                {{ gathering.joined_people }} / {{ gathering.max_people }} 人
                <span v-if="gathering.is_joined" class="gd-joined-badge">已报名</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 人数进度条 -->
        <div class="gd-progress">
          <div
            class="gd-progress__fill"
            :style="{ width: Math.min(100, (gathering.joined_people / gathering.max_people) * 100) + '%' }"
          ></div>
        </div>
      </section>

      <!-- 发起人 -->
      <section class="gd-section gd-section--host">
        <div class="gd-section__title">发起人</div>
        <div
          class="gd-host"
          @click="gathering.host.id && router.push(`/user/${gathering.host.id}`)"
        >
          <img v-if="gathering.host.avatar" class="gd-host__avatar" :src="gathering.host.avatar" alt="" />
          <span v-else class="gd-host__avatar gd-host__avatar--fallback">
            {{ gathering.host.nickname.slice(0, 1) }}
          </span>
          <div class="gd-host__info">
            <div class="gd-host__name">{{ gathering.host.nickname }}</div>
            <div class="gd-host__sub">发布于 {{ fmtDateTime(gathering.created_at) }}</div>
          </div>
          <Icon name="chevron-right" :size="18" class="gd-host__arrow" />
        </div>
        <!-- 发起人的可互动宠物（悬浮在发起人区域内，可拖动、随机小动作，不挡文字） -->
        <PostPetBox
          v-if="gathering.host?.id"
          :user-id="gathering.host.id"
          :size="50"
          class="gd-host-pet"
        />
      </section>

      <!-- 成员列表 -->
      <section v-if="gathering.members && gathering.members.length" class="gd-section">
        <div class="gd-section__title">
          成员（{{ gathering.members.length }}）
        </div>
        <div class="gd-members">
          <div
            v-for="m in gathering.members"
            :key="m.user_id"
            class="gd-member"
            @click="router.push(`/user/${m.user_id}`)"
          >
            <div class="gd-member__avatar-wrap">
              <img v-if="m.avatar" class="gd-member__avatar" :src="m.avatar" alt="" />
              <span v-else class="gd-member__avatar gd-member__avatar--fallback">
                {{ m.nickname.slice(0, 1) }}
              </span>
              <span v-if="m.is_host" class="gd-member__host-badge">主</span>
            </div>
            <span class="gd-member__name">{{ m.nickname }}</span>
          </div>
        </div>
      </section>

      <!-- 详情描述 -->
      <section class="gd-section">
        <div class="gd-section__title">组局详情</div>
        <p class="gd-desc">
          {{ gathering.description || '暂无详情介绍，可私信发起人了解更多。' }}
        </p>
        <!-- 附加图片 -->
        <div v-if="gathering.images.length > 1" class="gd-images">
          <img
            v-for="(img, i) in gathering.images.slice(1)"
            :key="i"
            v-show="isImageUrl(img)"
            :src="img"
            class="gd-images__item"
            alt="组局图片"
            loading="lazy"
          />
        </div>
      </section>

      <!-- 留言板 -->
      <section class="gd-section">
        <MessageBoard target-type="gathering" :target-id="gatheringId" title="留言板" />
      </section>

      <div class="gd-bottom-space"></div>

      <!-- 底部操作栏 -->
      <footer class="gd-bottom-bar">
        <template v-if="gathering.status === 'recruiting'">
          <!-- 发起人：取消组局 -->
          <button
            v-if="gathering.is_host"
            class="gd-btn gd-btn--cancel"
            type="button"
            :disabled="acting"
            @click="onCancel"
          >
            取消组局
          </button>
          <!-- 已报名：退出 -->
          <button
            v-else-if="gathering.is_joined"
            class="gd-btn gd-btn--leave"
            type="button"
            :disabled="acting"
            @click="onLeave"
          >
            退出报名
          </button>
          <!-- 满员 -->
          <button
            v-else-if="gathering.joined_people >= gathering.max_people"
            class="gd-btn gd-btn--disabled"
            type="button"
            disabled
          >
            已满员
          </button>
          <!-- 报名 -->
          <button
            v-else
            class="gd-btn gd-btn--join"
            type="button"
            :disabled="acting"
            @click="onJoin"
          >
            {{ acting ? '处理中...' : '立即报名' }}
          </button>
        </template>
        <template v-else>
          <button class="gd-btn gd-btn--disabled" type="button" disabled>
            {{ gathering.status === 'cancelled' ? '组局已取消' : '组局已结束' }}
          </button>
        </template>
      </footer>
    </template>
  </div>
</template>

<style scoped>
.gathering-detail-page {
  min-height: 100vh;
  background: var(--bg-100, #f2f3f7);
  padding-bottom: calc(76px + env(safe-area-inset-bottom));
}

/* ====== 顶部导航 ====== */
.gd-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 60;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  max-width: 720px;
  margin: 0 auto;
}
.gd-header__btn {
  width: 36px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.4);
  color: #fff;
  border: none;
  border-radius: 50%;
  cursor: pointer;
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
}
.gd-header__btn:hover { background: rgba(0, 0, 0, 0.55); }
.gd-header__btn :deep(svg) { width: 22px; height: 22px; }

/* ====== 状态页 ====== */
.gd-state {
  min-height: 60vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px 24px;
  text-align: center;
}
.gd-state__spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--bg-200);
  border-top-color: var(--brand-500);
  border-radius: 50%;
  animation: gd-spin 0.8s linear infinite;
}
@keyframes gd-spin {
  to { transform: rotate(360deg); }
}
.gd-state__emoji { font-size: 48px; line-height: 1; }
.gd-state__text { font-size: 14px; color: #505464; margin: 0; }
.gd-state__btn {
  margin-top: 8px;
  padding: 8px 24px;
  background: var(--brand-500);
  color: #fff;
  border: none;
  border-radius: 18px;
  font-size: 14px;
  cursor: pointer;
}

/* ====== 封面 ====== */
.gd-cover {
  width: 100%;
  aspect-ratio: 16 / 8;
  max-width: 720px;
  margin: 0 auto;
  overflow: hidden;
}
.gd-no-cover-spacer {
  height: calc(56px + env(safe-area-inset-top));
  background: var(--bg-100, #f2f3f7);
}
.gd-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

/* ====== 信息卡 ====== */
.gd-info-card {
  margin: -20px 12px 10px;
  padding: 16px;
  background: var(--bg-50, #fff);
  border-radius: 14px;
  border: 0.5px solid var(--bg-200);
  position: relative;
  z-index: 1;
  max-width: 720px;
  margin-left: auto;
  margin-right: auto;
  width: calc(100% - 24px);
}
.gd-info-card--no-cover {
  margin-top: 12px;
}
.gd-info-card__tags {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.gd-type-tag {
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
}
.gd-type-tag.is-online { background: rgba(25, 66, 194, 0.1); color: #1942c2; }
.gd-type-tag.is-offline { background: rgba(255, 138, 0, 0.12); color: #e07800; }
.gd-status {
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  background: rgba(52, 199, 89, 0.12);
  color: #28a745;
}
.gd-status.is-cancelled,
.gd-status.is-ended { background: rgba(142, 142, 147, 0.15); color: #8e8e93; }
.gd-status.is-full { background: rgba(255, 59, 48, 0.1); color: #ff3b30; }
.gd-cat {
  padding: 4px 10px;
  background: var(--bg-100);
  border-radius: 6px;
  font-size: 11px;
  color: var(--text-500);
}
.gd-title {
  font-size: 19px;
  font-weight: 700;
  color: var(--text-900, #111);
  line-height: 1.4;
  margin: 0 0 14px;
}

.gd-rows {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 14px;
}
.gd-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.gd-row__icon {
  color: var(--brand-500);
  margin-top: 2px;
  flex-shrink: 0;
}
.gd-row__icon :deep(svg) { width: 16px; height: 16px; }
.gd-row__body { flex: 1; min-width: 0; }
.gd-row__label { font-size: 12px; color: var(--text-400); margin-bottom: 2px; }
.gd-row__value { font-size: 14px; color: var(--text-800); font-weight: 500; }
.gd-joined-badge {
  display: inline-block;
  margin-left: 8px;
  padding: 1px 8px;
  background: rgba(52, 199, 89, 0.12);
  color: #28a745;
  font-size: 11px;
  font-weight: 600;
  border-radius: 8px;
}

.gd-progress {
  height: 6px;
  background: var(--bg-200);
  border-radius: 3px;
  overflow: hidden;
}
.gd-progress__fill {
  height: 100%;
  background: linear-gradient(90deg, var(--brand-500), #4d7cff);
  border-radius: 3px;
  transition: width 300ms ease;
}

/* ====== 通用 section ====== */
.gd-section {
  margin: 10px 12px;
  padding: 16px;
  background: var(--bg-50, #fff);
  border-radius: 14px;
  border: 0.5px solid var(--bg-200);
  max-width: 720px;
  margin-left: auto;
  margin-right: auto;
  width: calc(100% - 24px);
}
/* 发起人区域作为宠物悬浮的定位容器 */
.gd-section--host {
  position: relative;
}
.gd-section__title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-900);
  margin-bottom: 12px;
}

/* ====== 发起人 ====== */
.gd-host {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px;
  background: var(--bg-100, #f7f8fa);
  border-radius: 12px;
  cursor: pointer;
}
.gd-host__avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
}
.gd-host__avatar--fallback {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--brand-500) 15%, transparent);
  color: var(--brand-500);
  font-size: 18px;
  font-weight: 600;
}
.gd-host__info { flex: 1; min-width: 0; }
.gd-host__name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-900);
}
.gd-host__sub {
  font-size: 12px;
  color: var(--text-400);
  margin-top: 2px;
}
.gd-host__arrow { color: var(--text-400); flex-shrink: 0; }
.gd-host__arrow :deep(svg) { width: 18px; height: 18px; }

/* ====== 成员 ====== */
.gd-members {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(64px, 1fr));
  gap: 14px 8px;
}
.gd-member {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}
.gd-member__avatar-wrap { position: relative; }
.gd-member__avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  object-fit: cover;
}
.gd-member__avatar--fallback {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--brand-500) 15%, transparent);
  color: var(--brand-500);
  font-size: 18px;
  font-weight: 600;
}
.gd-member__host-badge {
  position: absolute;
  bottom: -2px;
  right: -2px;
  padding: 1px 5px;
  background: #e07800;
  color: #fff;
  font-size: 10px;
  font-weight: 600;
  border-radius: 6px;
}
.gd-member__name {
  font-size: 11px;
  color: var(--text-600);
  max-width: 64px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ====== 详情描述 ====== */
.gd-desc {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-600);
  margin: 0;
  white-space: pre-wrap;
}
.gd-images {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
}
.gd-images__item {
  width: 100%;
  border-radius: 10px;
  display: block;
}

.gd-bottom-space { height: 12px; }

/* ====== 底部操作栏 ====== */
.gd-bottom-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 50;
  padding: 10px 16px calc(10px + env(safe-area-inset-bottom));
  background: var(--bg-50, #fff);
  border-top: 0.5px solid var(--bg-200);
  max-width: 720px;
  margin: 0 auto;
}
.gd-btn {
  width: 100%;
  height: 46px;
  border: none;
  border-radius: 23px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 150ms ease;
}
.gd-btn:active { opacity: 0.85; }
.gd-btn--join {
  background: linear-gradient(135deg, #2b5ae0, #1942c2);
  color: #fff;
}
.gd-btn--leave {
  background: var(--bg-100);
  color: var(--text-700);
  border: 1px solid var(--bg-300);
}
.gd-btn--cancel {
  background: #ffe5e5;
  color: #ff3b30;
}
.gd-btn--disabled {
  background: var(--bg-200);
  color: var(--text-400);
  cursor: not-allowed;
}
</style>
