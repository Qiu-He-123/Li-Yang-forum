<script setup lang="ts">
/**
 * 首页「排行」子页：全部 / 金币 / 宠物亲密度 / 游戏 四个子排行。
 * - 子 Tab 动态样式：未选中 18px/400/#666，选中 20px/700/#111 + 2px 饱和蓝下划线跟随文字
 * - 榜单行：前三名奖牌 + 头像 + 昵称/徽章/学校 + 分值
 * - 登录用户顶部展示"我的排名"，榜单内高亮本人
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '../native'
import EmptyState from '../common/EmptyState.vue'
import BadgeIcon from '../common/BadgeIcon.vue'
import PostPetBox from '../post/PostPetBox.vue'
import { useSessionStore } from '../../stores/session'
import {
  fetchAllRanking,
  fetchCoinRanking,
  fetchGameRanking,
  fetchPetAffinityRanking,
  type RankingItem,
  type RankingResp,
} from '../../api/rankings'
import { fetchGratitudeList, type GratitudeItem } from '../../api/gratitude'
import type { LoadingAxiosRequestConfig } from '../../api/http'

type RankTabKey = 'all' | 'coins' | 'affinity' | 'game' | 'gratitude'

interface RankTabMeta {
  key: RankTabKey
  label: string
  emoji: string
  desc: string
  /** 分值后缀/单位 */
  unit: string
  /** 排行为 undefined：感谢名单走独立分支 */
  load?: (config?: LoadingAxiosRequestConfig) => Promise<{ data: { data: RankingResp } }>
}

const session = useSessionStore()
/** 排行页漂浮宠物体积：与首页组局/广场一致（120px） */
const PET_SIZE = 120

const tabs: RankTabMeta[] = [
  {
    key: 'all',
    label: '全部排行',
    emoji: '🏆',
    desc: '金币 + 亲密度 + 游戏 三项总分',
    unit: '分',
    load: fetchAllRanking,
  },
  {
    key: 'coins',
    label: '金币排行',
    emoji: '🪙',
    desc: '谁的腰包最鼓，一眼见分晓',
    unit: '币',
    load: fetchCoinRanking,
  },
  {
    key: 'affinity',
    label: '宠物亲密度排行',
    emoji: '🐾',
    desc: '谁家萌宠最黏人',
    unit: '❤',
    load: fetchPetAffinityRanking,
  },
  {
    key: 'game',
    label: '游戏排行',
    emoji: '🎮',
    desc: '小游戏巅峰对决',
    unit: '分',
    load: fetchGameRanking,
  },
  {
    key: 'gratitude',
    label: '感谢名单',
    emoji: '🎁',
    desc: '感谢每一位种下星光的人',
    unit: '',
    load: undefined,
  },
]

const activeTab = ref<RankTabKey>('all')
const meta = computed(() => tabs.find((t) => t.key === activeTab.value) || tabs[0])
const router = useRouter()

const items = ref<RankingItem[]>([])
const total = ref(0)
const me = ref<RankingResp['me']>(null)
const loading = ref(false)
const error = ref('')
/** 感谢名单：独立于排行的数据 */
const gratList = ref<GratitudeItem[]>([])

async function load(resetScroll = true) {
  loading.value = true
  error.value = ''
  if (resetScroll) {
    items.value = []
    total.value = 0
    me.value = null
    gratList.value = []
  }
  try {
    // 感谢名单：直接取后端上架名单
    if (activeTab.value === 'gratitude') {
      const { data: gr } = await fetchGratitudeList()
      gratList.value = gr.data ?? []
    } else {
      const { data } = await meta.value.load!({ showGlobalLoading: false, showGlobalError: false })
      const payload = data.data
      items.value = payload.items || []
      total.value = payload.total || 0
      me.value = payload.me || null
    }
  } catch (err) {
    error.value = (err as Error).message || '加载失败'
  } finally {
    loading.value = false
  }
}

watch(activeTab, () => load())

function switchTab(key: RankTabKey) {
  if (activeTab.value === key) return
  activeTab.value = key
}

function fmtScore(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, '') + 'w'
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k'
  return String(n)
}

/** 前三名奖牌样式（金/银/铜） */
const MEDAL: Record<number, { bg: string; color: string; label: string }> = {
  1: { bg: 'linear-gradient(135deg,#ffd86f,#ffb02e)', color: '#7a4a00', label: '1' },
  2: { bg: 'linear-gradient(135deg,#e8eef6,#b8c4d6)', color: '#4a5a70', label: '2' },
  3: { bg: 'linear-gradient(135deg,#f0c39a,#d89a63)', color: '#6b3d16', label: '3' },
}

function rankStyle(rank: number) {
  return MEDAL[rank] ? { background: MEDAL[rank].bg, color: MEDAL[rank].color } : {}
}

function rankClass(rank: number): string {
  return rank <= 3 ? 'rk-rank rk-rank--medal' : 'rk-rank'
}

function isMe(userId: number): boolean {
  return !!session.userId && session.userId === userId
}

/* ===== 感谢名单辅助 ===== */
function gratAvatar(item: GratitudeItem): string {
  return item.avatar_url && item.avatar_url.trim() ? item.avatar_url : ''
}
function gratInitial(name: string): string {
  return (name || '?').trim().charAt(0).toUpperCase()
}
function gratHue(name: string): number {
  let h = 0
  for (const ch of name || '') h = (h * 31 + ch.charCodeAt(0)) % 360
  return h
}

onMounted(() => load())
</script>

<template>
  <div class="ranking">
    <!-- ===== 子 Tab ===== -->
    <div class="rk-tabs" role="tablist" aria-label="排行分类">
      <button
        v-for="t in tabs"
        :key="t.key"
        class="rk-tab"
        :class="{ 'is-active': activeTab === t.key }"
        type="button"
        role="tab"
        :aria-selected="activeTab === t.key"
        @click="switchTab(t.key)"
      >
        {{ t.label }}
      </button>
    </div>

    <!-- ===== 榜单主题卡 ===== -->
    <div class="rk-hero" :class="`rk-hero--${activeTab}`">
      <span class="rk-hero__emoji" aria-hidden="true">{{ meta.emoji }}</span>
      <div class="rk-hero__body">
        <h3 class="rk-hero__title">{{ meta.label }}</h3>
        <p class="rk-hero__desc">
          {{ meta.desc }}
          <template v-if="activeTab !== 'gratitude'"> · 共 {{ total }} 人上榜</template>
          <template v-else> · 共 {{ gratList.length }} 位</template>
        </p>
      </div>
      <span class="rk-hero__badge" aria-hidden="true">
        <Icon name="award" :size="18" />
      </span>
    </div>

    <!-- ===== 我的排名 ===== -->
    <div v-if="me" class="rk-me">
      <span class="rk-me__label">我的排名</span>
      <div class="rk-me__value">
        <span class="rk-me__rank" :class="{ 'rk-me__rank--medal': me.rank <= 3 }">
          {{ me.rank <= 3 ? ['🏆', '🥈', '🥉'][me.rank - 1] : `No.${me.rank}` }}
        </span>
        <span class="rk-me__score">{{ fmtScore(me.score) }} <em>{{ meta.unit }}</em></span>
      </div>
    </div>

    <!-- ===== 加载骨架 ===== -->
    <div v-if="loading" class="rk-list">
      <div v-for="i in 8" :key="i" class="rk-skeleton">
        <span class="rk-skeleton__rank"></span>
        <span class="rk-skeleton__avatar"></span>
        <span class="rk-skeleton__line"></span>
        <span class="rk-skeleton__score"></span>
      </div>
    </div>

    <!-- ===== 加载失败 ===== -->
    <div v-else-if="error" class="rk-error">
      <p class="rk-error__text">加载失败，请稍后重试</p>
      <button class="rk-error__btn" type="button" @click="load()">重新加载</button>
    </div>

    <!-- ===== 感谢名单 ===== -->
    <template v-else-if="activeTab === 'gratitude'">
      <EmptyState v-if="!gratList.length" icon="gift" text="感谢名单正在筹备中，敬请期待" />
      <div v-else class="grat-list">
        <button
          v-for="(item, idx) in gratList"
          :key="item.id"
          class="grat-row"
          type="button"
          @click="router.push(`/gratitude/${item.id}`)"
        >
          <span class="grat-row__rank">{{ idx + 1 }}</span>
          <img v-if="gratAvatar(item)" class="grat-row__avatar" :src="gratAvatar(item)" :alt="item.name" loading="lazy" />
          <span
            v-else
            class="grat-row__avatar grat-row__avatar--char"
            :style="{ background: `linear-gradient(135deg, hsl(${gratHue(item.name)},70%,58%), hsl(${(gratHue(item.name) + 50) % 360},70%,46%))` }"
          >{{ gratInitial(item.name) }}</span>
          <span class="grat-row__body">
            <span class="grat-row__name">{{ item.name }}</span>
            <span class="grat-row__bio">{{ item.bio || '感谢支持 ♥' }}</span>
          </span>
          <Icon name="chevron-right" :size="17" color="#c7c7cc" />
        </button>
        <p class="rk-tip">点击查看每位朋友的感谢详情</p>
      </div>
    </template>

    <!-- ===== 空榜（排行） ===== -->
    <EmptyState v-else-if="!items.length" icon="award" :text="`${meta.label}暂无人上榜`" />

    <!-- ===== 榜单 ===== -->
    <div v-else class="rk-list">
      <div
        v-for="row in items"
        :key="row.user_id"
        class="rk-row"
        :class="{ 'rk-row--me': isMe(row.user_id) }"
      >
        <span class="rk-rank" :class="rankClass(row.rank)" :style="rankStyle(row.rank)">{{ row.rank }}</span>

        <img class="rk-avatar" :src="row.avatar_url" :alt="row.nickname" loading="lazy" />

        <div class="rk-user">
          <div class="rk-name">
            <BadgeIcon :badge="row.badge" :size="14" />
            <span class="rk-nickname">{{ row.nickname }}</span>
            <span v-if="isMe(row.user_id)" class="rk-tag-me">我</span>
          </div>
          <p class="rk-school">
            <Icon name="graduation" :size="12" />
            {{ row.school || '未知学校' }}
          </p>
        </div>

        <div class="rk-score">
          <span class="rk-score__num">{{ fmtScore(row.score) }}</span>
          <span class="rk-score__unit">{{ meta.unit }}</span>
          <!-- 全部排行：三项明细 -->
          <span v-if="activeTab === 'all' && row.extra" class="rk-breakdown">
            <span class="rk-bd rk-bd--coins">🪙{{ fmtScore(row.extra.coins || 0) }}</span>
            <span class="rk-bd rk-bd--aff">🐾{{ fmtScore(row.extra.affinity || 0) }}</span>
            <span class="rk-bd rk-bd--game">🎮{{ fmtScore(row.extra.game || 0) }}</span>
          </span>
          <!-- 亲密度/游戏：附加数量 -->
          <span v-else-if="row.extra?.pet_count != null" class="rk-extra">{{ row.extra.pet_count }} 只宠物</span>
          <span v-else-if="row.extra?.game_count != null" class="rk-extra">{{ row.extra.game_count }} 款游戏</span>
        </div>
      </div>

      <p class="rk-tip">仅展示前 {{ items.length }} 名，快去冲榜吧～</p>
    </div>

    <!-- 登录用户的漂浮宠物：与组局/广场一致，悬浮在排行页右下角，可拖动可移动、随机动作、可飞行 -->
    <PostPetBox
      v-if="session.userId"
      :user-id="session.userId"
      :size="PET_SIZE"
      class="post-pet-rank"
    />
  </div>
</template>

<style scoped>
*, *::before, *::after { box-sizing: border-box; }

.ranking {
  position: relative; /* 作为其内漂浮宠物 PostPetBox 的定位上下文 */
  padding-bottom: 140px; /* 底部留出宠物悬浮空间，避免遮挡最后一行榜单 */
}

/* ===== 子 Tab：未选中 18px/400/#666，选中 20px/700/#111 + 饱和蓝下划线 ===== */
.rk-tabs {
  display: flex;
  align-items: center;
  gap: 22px;
  margin-bottom: 16px;
  padding: 0 2px;
  border-bottom: 0.5px solid rgba(0, 0, 0, 0.06);
  overflow-x: auto;
  scrollbar-width: none;
}
.rk-tabs::-webkit-scrollbar { display: none; }
.rk-tab {
  position: relative;
  flex: 0 0 auto;
  padding: 6px 2px 12px;
  font-size: 18px;
  font-weight: 400;
  color: #666;
  background: transparent;
  border: none;
  cursor: pointer;
  font-family: inherit;
  white-space: nowrap;
  transition: color 180ms cubic-bezier(0.32, 0.72, 0, 1), font-weight 180ms cubic-bezier(0.32, 0.72, 0, 1);
}
.rk-tab.is-active {
  font-size: 20px;
  font-weight: 700;
  color: #111;
}
.rk-tab.is-active::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 2px;
  border-radius: 2px;
  background: #2f6bff;
}

/* ===== 主题卡 ===== */
.rk-hero {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 16px;
  color: #fff;
  margin-bottom: 12px;
  background: linear-gradient(135deg, #4f6df5, #8a5cf6);
  box-shadow: 0 6px 18px rgba(79, 109, 245, 0.28);
  position: relative;
  overflow: hidden;
}
.rk-hero--coins { background: linear-gradient(135deg, #f5a623, #ff7b2e); box-shadow: 0 6px 18px rgba(245, 166, 35, 0.3); }
.rk-hero--affinity { background: linear-gradient(135deg, #ff7eb3, #ff5f9e); box-shadow: 0 6px 18px rgba(255, 95, 158, 0.3); }
.rk-hero--game { background: linear-gradient(135deg, #36c99b, #2aa9e0); box-shadow: 0 6px 18px rgba(42, 169, 224, 0.3); }
.rk-hero--gratitude { background: linear-gradient(135deg, #ff9a56, #ff6b9d); box-shadow: 0 6px 18px rgba(255, 107, 157, 0.3); }
.rk-hero__emoji {
  font-size: 34px;
  line-height: 1;
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.2));
}
.rk-hero__body { flex: 1; min-width: 0; }
.rk-hero__title { margin: 0; font-size: 19px; font-weight: 700; letter-spacing: 0.01em; }
.rk-hero__desc { margin: 2px 0 0; font-size: 12px; opacity: 0.85; }
.rk-hero__badge {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.2);
  backdrop-filter: blur(4px);
}

/* ===== 我的排名 ===== */
.rk-me {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  margin-bottom: 12px;
  border-radius: 14px;
  background: #fff;
  border: 1px solid #eceef4;
  box-shadow: 0 3px 14px rgba(23, 32, 64, 0.08);
}
.rk-me__label { font-size: 13px; color: #666; }
.rk-me__value { display: flex; align-items: center; gap: 8px; }
.rk-me__rank {
  font-size: 17px;
  font-weight: 800;
  color: #2f6bff;
}
.rk-me__rank--medal { font-size: 20px; }
.rk-me__score { font-size: 16px; font-weight: 800; color: #111; }
.rk-me__score em { font-style: normal; font-size: 11px; font-weight: 500; color: #999; margin-left: 1px; }

/* ===== 榜单 ===== */
.rk-list { display: flex; flex-direction: column; gap: 10px; }
.rk-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 14px;
  background: #fff;
  border: 1px solid #eceef4;
  box-shadow: 0 3px 14px rgba(23, 32, 64, 0.08);
}
.rk-row--me {
  border-color: #2f6bff;
  box-shadow: 0 0 0 1.5px #2f6bff, 0 4px 16px rgba(47, 107, 255, 0.16);
}
.rk-rank {
  flex: 0 0 auto;
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  font-size: 14px;
  font-weight: 800;
  color: #999;
}
.rk-rank--medal {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  color: #fff;
  font-size: 14px;
  box-shadow: inset 0 -2px 3px rgba(0, 0, 0, 0.12);
}
.rk-avatar {
  flex: 0 0 auto;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  object-fit: cover;
  background: #eef0f5;
  border: 1px solid #e4e7ef;
}
.rk-user { flex: 1; min-width: 0; }
.rk-name {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}
.rk-nickname {
  font-size: 15px;
  font-weight: 600;
  color: #17181d;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.rk-tag-me {
  flex: 0 0 auto;
  font-size: 10px;
  font-weight: 700;
  color: #fff;
  background: #2f6bff;
  border-radius: 5px;
  padding: 1px 5px;
  line-height: 1.4;
}
.rk-school {
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 3px 0 0;
  font-size: 12px;
  color: #9093a3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.rk-score {
  flex: 0 0 auto;
  text-align: right;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}
.rk-score__num { font-size: 17px; font-weight: 800; color: #17181d; }
.rk-score__unit { font-size: 11px; color: #999; margin-left: 1px; }
.rk-breakdown { display: flex; gap: 6px; }
.rk-bd {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 8px;
  background: #f4f5f9;
  color: #666;
  white-space: nowrap;
}
.rk-bd--coins { background: #fff5e0; color: #b9761a; }
.rk-bd--aff { background: #ffeef4; color: #d4497e; }
.rk-bd--game { background: #e8f7f2; color: #1f9a75; }
.rk-extra { font-size: 11px; color: #999; }

/* ===== 感谢名单卡片 ===== */
.grat-list { display: flex; flex-direction: column; gap: 10px; }
.grat-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 14px;
  background: #fff;
  border: 1px solid #eceef4;
  box-shadow: 0 3px 14px rgba(23, 32, 64, 0.08);
  cursor: pointer;
  font-family: inherit;
}
.grat-row:active { transform: scale(0.99); }
.grat-row__rank {
  width: 22px;
  flex: none;
  font-size: 14px;
  font-weight: 800;
  color: #ff9a56;
  text-align: center;
}
.grat-row__avatar {
  flex: none;
  width: 46px;
  height: 46px;
  border-radius: 50%;
  object-fit: cover;
  background: #eef0f5;
  border: 1px solid #e4e7ef;
}
.grat-row__avatar--char {
  display: grid;
  place-items: center;
  color: #fff;
  font-size: 18px;
  font-weight: 800;
  border: none;
}
.grat-row__body { flex: 1; min-width: 0; text-align: left; }
.grat-row__name { display: block; font-size: 15px; font-weight: 700; color: #1a1a2e; }
.grat-row__bio {
  display: block;
  margin-top: 3px;
  font-size: 12px;
  color: #888;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rk-tip {
  text-align: center;
  font-size: 12px;
  color: #a0a3b1;
  padding: 6px 0 2px;
  margin: 0;
}

/* ===== 骨架 ===== */
.rk-skeleton {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 14px;
  background: #fff;
  border: 1px solid #eceef4;
}
.rk-skeleton__rank { width: 28px; height: 28px; border-radius: 50%; background: #eef0f5; }
.rk-skeleton__avatar { width: 44px; height: 44px; border-radius: 50%; background: #eef0f5; }
.rk-skeleton__line { flex: 1; height: 14px; border-radius: 7px; background: #eef0f5; }
.rk-skeleton__score { width: 48px; height: 14px; border-radius: 7px; background: #eef0f5; }
.rk-skeleton__rank, .rk-skeleton__avatar, .rk-skeleton__line, .rk-skeleton__score {
  animation: rk-pulse 1.3s ease-in-out infinite;
}
@keyframes rk-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.55; }
}

/* ===== 错误 ===== */
.rk-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 48px 16px;
}
.rk-error__text { margin: 0; font-size: 14px; color: #666; }
.rk-error__btn {
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  background: #2f6bff;
  border: none;
  border-radius: 10px;
  padding: 8px 22px;
  cursor: pointer;
  font-family: inherit;
}
</style>
