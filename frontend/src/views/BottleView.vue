<script setup lang="ts">
/**
 * 漂流瓶页面（独立功能页，非帖子流）
 *
 * 核心玩法：
 * - 投放：设置校区（必选）+ 兴趣标签（可选）+ 文本/图片（至少一项）；年龄由生日自动计算
 * - 拾取：设置期望年龄范围/校区/兴趣标签/性别，系统按优先级匹配
 * - 我的瓶子：查看我投放的 + 我拾取过的
 *
 * 透明展示：在线人数 / 匹配中人数 / 已投放数 / 今日拾取数
 *
 * 动效：
 * - 投放：瓶子向海面飞出的轻量动效
 * - 拾取：瓶子从海面浮起的轻量动效
 */
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import BottleSkeleton from '../components/common/BottleSkeleton.vue'
import BadgeIcon from '../components/common/BadgeIcon.vue'
import { Dialog as NativeDialog, Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import { useSessionStore } from '../stores/session'
import { useUserStore } from '../stores/user'
import { useUIStore } from '../stores/ui'
import {
  createBottle,
  fetchBottleStats,
  getPickStatus,
  listBottleTags,
  listMyBottles,
  listMyPicks,
  pickBottle,
  recallBottle,
  type Bottle,
  type BottleStats,
  type PickStatus,
} from '../api/bottle'
import { uploadImage } from '../api/image'
import { formatRelative } from '../utils/time'
import { isAppEnv } from '../utils/platform'

const router = useRouter()
const session = useSessionStore()
const userStore = useUserStore()
const uiStore = useUIStore()

// ============ 顶部统计 ============
const stats = ref<BottleStats>({ online_count: 0, matching_count: 0, total_bottles: 0, today_picks: 0 })
let statsTimer: ReturnType<typeof setInterval> | null = null
// 首页骨架屏：初始数据加载完成前显示
const pageLoading = ref(true)

async function loadStats() {
  try {
    const { data } = await fetchBottleStats({
      showGlobalLoading: false,
      showGlobalError: false,
    })
    stats.value = data.data
  } catch {
    /* 静默 */
  }
}

// ============ Tab 切换 ============
type TabKey = 'throw' | 'pick' | 'mine'
const activeTab = ref<TabKey>('throw')

// ============ 年龄/校区/性别选项 ============
// 年龄范围：13-18 岁（中学阶段），替代原年级
const AGE_OPTIONS = [13, 14, 15, 16, 17, 18]
const SCHOOLS = [
  { id: 1, name: '本部校区' },
  { id: 2, name: '未来校区' },
  { id: 3, name: '香山校区' },
  { id: 4, name: '东校校区' },
]
const GENDERS = [
  { value: 'male', label: '男' },
  { value: 'female', label: '女' },
  { value: 'any', label: '不限' },
] as const

// ============ 兴趣标签 ============
const interestTags = ref<string[]>([])
async function loadTags() {
  try {
    const { data } = await listBottleTags({
      showGlobalLoading: false,
      showGlobalError: false,
    })
    interestTags.value = data.data || []
  } catch {
    /* 静默 */
  }
}

// ============ 投放表单 ============
const throwForm = ref({
  content: '',
  image_urls: [] as string[],
  school_id: 0,
  tags: [] as string[],
  customTag: '',
  contact: '',
})
const throwLoading = ref(false)

// 漂流瓶人工审核提示（AI 不可用时不直接放行）
const auditDialogVisible = ref(false)
const auditDialogMessage = ref('')

function showAuditNotice(status: string | undefined) {
  if (status === 'manual_review') {
    auditDialogMessage.value = '瓶子已投出，AI 审核服务暂不可用（未开启/无余额/调用失败），已转人工审核。审核可能较慢，通过后才会进入大海等待拾取。'
    auditDialogVisible.value = true
  }
}
const throwAnim = ref(false) // 投放动效

function ensureLogin(): boolean {
  if (!session.userId) {
    uiStore.openAuthDialog()
    return false
  }
  return true
}

function toggleThrowTag(t: string) {
  const idx = throwForm.value.tags.indexOf(t)
  if (idx >= 0) throwForm.value.tags.splice(idx, 1)
  else if (throwForm.value.tags.length < 5) throwForm.value.tags.push(t)
  else toast.info('最多选择 5 个标签')
}

function addCustomTag() {
  const t = throwForm.value.customTag.trim()
  if (!t) return
  if (throwForm.value.tags.includes(t)) {
    throwForm.value.customTag = ''
    return
  }
  if (throwForm.value.tags.length >= 5) {
    toast.info('最多选择 5 个标签')
    return
  }
  throwForm.value.tags.push(t)
  throwForm.value.customTag = ''
}

async function onUploadImage(e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files || !input.files.length) return
  for (const file of Array.from(input.files)) {
    if (file.size > 8 * 1024 * 1024) {
      toast.error('单张图片不能超过 8MB')
      continue
    }
    try {
      const { data } = await uploadImage(file)
      throwForm.value.image_urls.push(data.data.url)
    } catch (err) {
      toast.error((err as Error).message)
    }
  }
  input.value = ''
}

function removeImage(idx: number) {
  throwForm.value.image_urls.splice(idx, 1)
}

async function onThrow() {
  if (!ensureLogin()) return
  const f = throwForm.value
  // 年龄由后端从用户生日自动计算，无需用户选择；只需提示用户先在设置中填写生日
  if (!userStore.profile?.birthday) {
    toast.error('请先在「我的-设置」中填写生日（系统会自动计算年龄）')
    return
  }
  if (!f.school_id) {
    toast.error('请选择校区')
    return
  }
  const content = f.content.trim()
  if (!content && f.image_urls.length === 0) {
    toast.error('请输入文本或上传图片')
    return
  }
  // 校验用户校区与所选一致（后端也会校验）
  if (userStore.profile?.school_id && f.school_id !== userStore.profile.school_id) {
    toast.error('校区必须与你的资料校区一致')
    return
  }
  throwLoading.value = true
  try {
    const contact = f.contact.trim()
    const { data } = await createBottle({
      content: content || null,
      image_urls: f.image_urls,
      school_id: f.school_id,
      tags: f.tags,
      contact: contact || null,
    })
    // 投放动效
    throwAnim.value = true
    setTimeout(() => { throwAnim.value = false }, 1200)
    const auditStatus = data.data.audit_status
    if (auditStatus === 'pending') {
      toast.success('瓶子已投出，内容审核中，通过后等待有缘人拾取')
    } else if (auditStatus === 'manual_review') {
      toast.success('瓶子已投出，进入人工审核')
      showAuditNotice(auditStatus)
    } else {
      toast.success('瓶子已投出，等待有缘人拾取')
    }
    // 重置表单（保留校区）
    f.content = ''
    f.image_urls = []
    f.tags = []
    f.customTag = ''
    f.contact = ''
    await loadStats()
    await loadPickStatus()
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    throwLoading.value = false
  }
}

// ============ 拾取 ============
const pickForm = ref({
  /** 期望作者年龄下限（13-18，null=不限） */
  age_min: null as number | null,
  /** 期望作者年龄上限（13-18，null=不限） */
  age_max: null as number | null,
  school_ids: [] as number[],
  target_gender: 'any' as 'male' | 'female' | 'any',
})
/**
 * 拾取标签三态点击机制：
 * - 0：无所谓（默认，点三下回到此态）
 * - 1：尽量有（点一下，候选中按重叠度排序优先）
 * - 2：必须有（点两下，瓶子必须包含此标签才能匹配到）
 */
const tagStates = ref<Record<string, 0 | 1 | 2>>({})
const pickLoading = ref(false)
const pickResult = ref<Bottle | null>(null)
const pickAnim = ref(false) // 拾取动效
const pickStatus = ref<PickStatus>({ today_count: 0, daily_limit: 3, remaining: 3 })

async function loadPickStatus() {
  if (!session.userId) return
  try {
    const { data } = await getPickStatus({
      showGlobalLoading: false,
      showGlobalError: false,
    })
    pickStatus.value = data.data
  } catch {
    /* 静默 */
  }
}

function togglePickAgeMin(a: number) {
  // 点击已选中的最小年龄再次点击 → 取消
  if (pickForm.value.age_min === a) {
    pickForm.value.age_min = null
    return
  }
  pickForm.value.age_min = a
  // 自动校验：min 不能大于 max
  if (pickForm.value.age_max !== null && a > pickForm.value.age_max) {
    pickForm.value.age_max = a
  }
}
function togglePickAgeMax(a: number) {
  if (pickForm.value.age_max === a) {
    pickForm.value.age_max = null
    return
  }
  pickForm.value.age_max = a
  if (pickForm.value.age_min !== null && a < pickForm.value.age_min) {
    pickForm.value.age_min = a
  }
}
function clearPickAgeRange() {
  pickForm.value.age_min = null
  pickForm.value.age_max = null
}

function togglePickSchool(id: number) {
  const idx = pickForm.value.school_ids.indexOf(id)
  if (idx >= 0) pickForm.value.school_ids.splice(idx, 1)
  else pickForm.value.school_ids.push(id)
}

/**
 * 三态标签点击：0 → 1 → 2 → 0
 * - 0 默认（无所谓）
 * - 1 点一下：尽量有（候选中优先排序）
 * - 2 点两下：必须有（硬过滤条件）
 * - 点三下回到 0
 */
function toggleTagState(tag: string) {
  const current = tagStates.value[tag] || 0
  const next = current === 2 ? 0 : (current + 1) as 0 | 1 | 2
  tagStates.value = { ...tagStates.value, [tag]: next }
}

function getTagState(tag: string): 0 | 1 | 2 {
  return tagStates.value[tag] || 0
}

function getTagStateClass(tag: string) {
  const state = getTagState(tag)
  return {
    'tag-state-default': state === 0,
    'tag-state-prefer': state === 1,
    'tag-state-required': state === 2,
  }
}

function getTagStateLabel(tag: string): string {
  const state = getTagState(tag)
  if (state === 1) return '尽量'
  if (state === 2) return '必须'
  return ''
}

function setTargetGender(g: 'male' | 'female' | 'any') {
  pickForm.value.target_gender = g
}

async function onPick() {
  if (!ensureLogin()) return
  if (pickStatus.value.remaining <= 0) {
    toast.error('今日拾取次数已达上限，明天再来吧')
    return
  }
  // 性别筛选需用户已设置性别
  if (userStore.profile?.gender === 'unknown' || !userStore.profile?.gender) {
    toast.error('请先在「我的-设置」中完善性别信息后再拾取')
    return
  }
  // 把三态标签拆分为 tag_required 和 tag_preferred
  const tagRequired: string[] = []
  const tagPreferred: string[] = []
  for (const [tag, state] of Object.entries(tagStates.value)) {
    if (state === 2) tagRequired.push(tag)
    else if (state === 1) tagPreferred.push(tag)
  }
  pickLoading.value = true
  pickResult.value = null
  try {
    // 拾取动效：先播放「捞瓶子」动画
    pickAnim.value = true
    await new Promise((r) => setTimeout(r, 800))
    const { data } = await pickBottle({
      school_ids: pickForm.value.school_ids,
      tag_required: tagRequired,
      tag_preferred: tagPreferred,
      target_gender: pickForm.value.target_gender,
      age_min: pickForm.value.age_min,
      age_max: pickForm.value.age_max,
    })
    pickResult.value = data.data
    pickAnim.value = false
    if (data.data.remaining_picks_today !== undefined) {
      pickStatus.value.remaining = data.data.remaining_picks_today
      pickStatus.value.today_count = pickStatus.value.daily_limit - data.data.remaining_picks_today
    }
    await loadStats()
  } catch (err) {
    pickAnim.value = false
    toast.error((err as Error).message)
  } finally {
    pickLoading.value = false
  }
}

function closePickResult() {
  pickResult.value = null
}

// ============ 我的瓶子 ============
const mineSubTab = ref<'thrown' | 'picked'>('thrown')
const myBottles = ref<Bottle[]>([])
const myPicks = ref<Bottle[]>([])
const myPickedCount = ref(0)
const mineLoading = ref(false)
const recallingId = ref<number | null>(null)

async function loadMine() {
  if (!session.userId) return
  mineLoading.value = true
  try {
    const [mineRes, picksRes] = await Promise.all([
      listMyBottles({
        showGlobalLoading: false,
        showGlobalError: false,
      }),
      listMyPicks({
        showGlobalLoading: false,
        showGlobalError: false,
      }),
    ])
    myBottles.value = mineRes.data.data.bottles || []
    myPickedCount.value = mineRes.data.data.picked_count || 0
    myPicks.value = picksRes.data.data || []
  } catch {
    /* 静默 */
  } finally {
    mineLoading.value = false
  }
}

/** 作者收回瓶子 */
async function onRecall(bottleId: number) {
  if (!ensureLogin()) return
  if (!window.confirm('收回后瓶子将不再可被拾取，确定要收回吗？')) return
  recallingId.value = bottleId
  try {
    const { data } = await recallBottle(bottleId)
    // 更新本地列表中的状态
    const idx = myBottles.value.findIndex((b) => b.id === bottleId)
    if (idx >= 0) {
      myBottles.value[idx] = { ...myBottles.value[idx], status: 'recalled' }
    }
    toast.success('瓶子已收回，不再可被拾取')
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    recallingId.value = null
  }
}

// ============ 跳转实时匹配 ============
function goMatch() {
  router.push('/match')
}

function formatStatsNum(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, '') + 'w'
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k'
  return String(n)
}

function genderLabel(g: string): string {
  if (g === 'male') return '男'
  if (g === 'female') return '女'
  return '未知'
}

/** 年龄显示：null → '未知年龄'；其他 → 'X 岁' */
function ageLabel(age: number | null | undefined): string {
  if (age === null || age === undefined) return '未知年龄'
  return `${age} 岁`
}

// ============ 生命周期 ============
onMounted(async () => {
  // 性能优化：validateSession 后台并行，不阻塞（邀请码检查基于 localStorage 缓存的 verificationStatus）
  void session.validateSession()
  // 邀请码系统：未认证用户进入漂流瓶页时直接弹邀请码框并返回
  if (session.isLoggedIn() && !session.isVerified()) {
    // 先返回再弹窗，避免路由 watcher 立即关闭弹窗
    router.back()
    setTimeout(() => uiStore.openInviteCodeDialog(), 100)
    return
  }
  // 同步加载用户资料（用于校验 school_id 和 gender）
  if (session.userId) {
    await userStore.loadProfile()
    // 自动填充用户的校区到投放表单
    if (userStore.profile?.school_id) {
      throwForm.value.school_id = userStore.profile.school_id
    }
  }
  // 最小骨架显示 200ms，避免本地加载太快骨架屏一闪而过
  const minDelay = new Promise(resolve => setTimeout(resolve, 200))
  await Promise.all([loadStats(), loadTags(), loadPickStatus(), loadMine(), minDelay])
  pageLoading.value = false
  // 统计数据每 30 秒刷新一次
  statsTimer = setInterval(loadStats, 60_000)
})

onUnmounted(() => {
  if (statsTimer) {
    clearInterval(statsTimer)
    statsTimer = null
  }
})
</script>

<template>
  <!-- 骨架屏：初始数据加载完成前显示 -->
  <BottleSkeleton v-if="pageLoading" />
  <main v-else class="page-bottle">
    <!-- ====== 顶部固定栏 ====== -->
    <header class="site-header" role="banner">
      <div class="header-inner">
        <div class="header-side header-side--left">
          <button class="icon-btn" type="button" aria-label="返回" @click="router.back()">
            <Icon name="arrow-left" :size="20" />
          </button>
        </div>
        <h1 class="header-title">漂流瓶</h1>
        <div class="header-side header-side--right">
          <button class="icon-btn" type="button" aria-label="在线匹配" @click="goMatch">
            <Icon name="shuffle" :size="20" />
          </button>
        </div>
      </div>
    </header>

    <div class="page-container">
      <!-- ====== 透明统计 ====== -->
      <section class="bottle-stats" aria-label="实时统计">
        <div class="stats-item">
          <span class="stats-dot stats-dot--green" aria-hidden="true"></span>
          <span class="stats-num">{{ formatStatsNum(stats.online_count) }}</span>
          <span class="stats-label">在线</span>
        </div>
        <span class="stats-divider" aria-hidden="true"></span>
        <div class="stats-item">
          <Icon name="shuffle" :size="14" />
          <span class="stats-num">{{ formatStatsNum(stats.matching_count) }}</span>
          <span class="stats-label">匹配中</span>
        </div>
        <span class="stats-divider" aria-hidden="true"></span>
        <div class="stats-item">
          <Icon name="box" :size="14" />
          <span class="stats-num">{{ formatStatsNum(stats.total_bottles) }}</span>
          <span class="stats-label">已投放</span>
        </div>
        <span class="stats-divider" aria-hidden="true"></span>
        <div class="stats-item">
          <Icon name="gift" :size="14" />
          <span class="stats-num">{{ formatStatsNum(stats.today_picks) }}</span>
          <span class="stats-label">今日拾取</span>
        </div>
      </section>

      <!-- ====== 入口提示：在线匹配 ====== -->
      <button class="match-entry" type="button" @click="goMatch">
        <span class="match-entry-ic" aria-hidden="true">
          <Icon name="shuffle" :size="20" />
        </span>
        <span class="match-entry-text">
          <span class="match-entry-title">在线实时匹配</span>
          <span class="match-entry-desc">180 秒临时聊天，互关成为好友</span>
        </span>
        <Icon name="arrow-right" :size="16" class="match-entry-arrow" />
      </button>

      <!-- ====== Tab 切换 ====== -->
      <div class="tab-bar" role="tablist" aria-label="漂流瓶操作">
        <button
          class="tab-item"
          type="button"
          :class="{ 'is-active': activeTab === 'throw' }"
          role="tab"
          @click="activeTab = 'throw'"
        >投放</button>
        <button
          class="tab-item"
          type="button"
          :class="{ 'is-active': activeTab === 'pick' }"
          role="tab"
          @click="activeTab = 'pick'"
        >拾取 <span v-if="pickStatus.remaining > 0" class="tab-badge">{{ pickStatus.remaining }}</span></button>
        <button
          class="tab-item"
          type="button"
          :class="{ 'is-active': activeTab === 'mine' }"
          role="tab"
          @click="activeTab = 'mine'; loadMine()"
        >我的瓶子</button>
      </div>

      <!-- ====== 投放表单 ====== -->
      <section v-if="activeTab === 'throw'" class="tab-panel">
        <div class="form-card" :class="{ 'is-throwing': throwAnim }">
          <!-- 投放动效层 -->
          <div v-if="throwAnim" class="throw-anim" aria-hidden="true">
            <div class="throw-bottle">
              <Icon name="box" :size="48" />
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">校区 <span class="required">*</span></label>
            <div class="option-row">
              <button
                v-for="s in SCHOOLS"
                :key="s.id"
                type="button"
                class="option-chip"
                :class="{ 'is-active': throwForm.school_id === s.id, 'is-disabled': !!userStore.profile?.school_id && userStore.profile.school_id !== s.id }"
                :disabled="!!userStore.profile?.school_id && userStore.profile.school_id !== s.id"
                @click="throwForm.school_id = s.id"
              >{{ s.name }}</button>
            </div>
            <p v-if="userStore.profile?.school_id" class="form-hint">校区需与你的资料一致（{{ SCHOOLS.find(s => s.id === userStore.profile?.school_id)?.name }}）</p>
          </div>

          <div class="form-group">
            <label class="form-label">年龄 <span class="form-hint-inline">由生日自动计算</span></label>
            <div class="age-display-box">
              <Icon name="calendar-check" :size="16" />
              <span v-if="userStore.profile?.age !== null && userStore.profile?.age !== undefined">
                当前 <strong>{{ userStore.profile.age }}</strong> 岁
              </span>
              <span v-else class="age-missing">
                未设置生日
                <button type="button" class="link-inline" @click="router.push('/settings')">去设置</button>
              </span>
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">兴趣标签 <span class="form-hint-inline">最多 5 个</span></label>
            <div class="option-row">
              <button
                v-for="t in interestTags"
                :key="t"
                type="button"
                class="option-chip"
                :class="{ 'is-active': throwForm.tags.includes(t) }"
                @click="toggleThrowTag(t)"
              >{{ t }}</button>
            </div>
            <div class="custom-tag-row">
              <input
                v-model="throwForm.customTag"
                type="text"
                class="custom-tag-input"
                placeholder="自定义标签"
                maxlength="10"
                @keyup.enter="addCustomTag"
              />
              <button type="button" class="custom-tag-btn" @click="addCustomTag">添加</button>
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">内容 <span class="form-hint-inline">文本和图片至少一项</span></label>
            <textarea
              v-model="throwForm.content"
              class="form-textarea"
              placeholder="写点什么，让拾到瓶子的人感受你的心意..."
              maxlength="2000"
              rows="4"
            ></textarea>
            <div class="image-uploader">
              <div v-for="(url, idx) in throwForm.image_urls" :key="idx" class="image-item">
                <img :src="url" alt="瓶子图片" />
                <button type="button" class="image-remove" @click="removeImage(idx)" aria-label="删除">
                  <Icon name="x" :size="14" />
                </button>
              </div>
              <label v-if="throwForm.image_urls.length < 3" class="image-upload-btn">
                <Icon name="image-plus" :size="20" />
                <!-- App 内 Android WebView 不支持 multiple（change 不触发），强制单选 -->
                <input
                  type="file"
                  accept="image/*"
                  :multiple="!isAppEnv()"
                  hidden
                  @change="onUploadImage"
                />
              </label>
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">联系方式 <span class="form-hint-inline">选填，拾取者可见</span></label>
            <input
              v-model="throwForm.contact"
              type="text"
              class="form-input"
              placeholder="QQ / 微信 / 手机号，方便拾取者联系你"
              maxlength="100"
            />
          </div>

          <button
            type="button"
            class="primary-btn"
            :disabled="throwLoading"
            @click="onThrow"
          >
            <Icon name="send" :size="16" />
            <span>{{ throwLoading ? '投放中...' : '投出瓶子' }}</span>
          </button>
        </div>
      </section>

      <!-- ====== 拾取面板 ====== -->
      <section v-else-if="activeTab === 'pick'" class="tab-panel">
        <div class="form-card" :class="{ 'is-picking': pickAnim }">
          <!-- 拾取动效层 -->
          <div v-if="pickAnim" class="pick-anim" aria-hidden="true">
            <div class="pick-wave"></div>
            <div class="pick-bottle">
              <Icon name="gift" :size="48" />
            </div>
            <p class="pick-anim-text">正在捞取瓶子...</p>
          </div>

          <div class="pick-status-bar">
            <Icon name="gift" :size="14" />
            <span>今日剩余拾取次数：<strong>{{ pickStatus.remaining }}</strong> / {{ pickStatus.daily_limit }}</span>
          </div>

          <div class="form-group">
            <label class="form-label">
              期望作者年龄
              <span class="form-hint-inline">点击下限/上限，可只设一边；不选则不限</span>
            </label>
            <div class="age-range-row">
              <div class="age-range-col">
                <span class="age-range-label">下限</span>
                <div class="option-row">
                  <button
                    v-for="a in AGE_OPTIONS"
                    :key="`min-${a}`"
                    type="button"
                    class="option-chip"
                    :class="{ 'is-active': pickForm.age_min === a }"
                    @click="togglePickAgeMin(a)"
                  >{{ a }}</button>
                </div>
              </div>
              <div class="age-range-col">
                <span class="age-range-label">上限</span>
                <div class="option-row">
                  <button
                    v-for="a in AGE_OPTIONS"
                    :key="`max-${a}`"
                    type="button"
                    class="option-chip"
                    :class="{ 'is-active': pickForm.age_max === a }"
                    @click="togglePickAgeMax(a)"
                  >{{ a }}</button>
                </div>
              </div>
            </div>
            <p v-if="pickForm.age_min || pickForm.age_max" class="form-hint">
              当前筛选：
              <strong>
                {{ pickForm.age_min ? pickForm.age_min + ' 岁' : '不限' }}
                ~
                {{ pickForm.age_max ? pickForm.age_max + ' 岁' : '不限' }}
              </strong>
              <button type="button" class="link-inline" @click="clearPickAgeRange">清除</button>
            </p>
          </div>

          <div class="form-group">
            <label class="form-label">期望校区 <span class="form-hint-inline">可多选</span></label>
            <div class="option-row">
              <button
                v-for="s in SCHOOLS"
                :key="s.id"
                type="button"
                class="option-chip"
                :class="{ 'is-active': pickForm.school_ids.includes(s.id) }"
                @click="togglePickSchool(s.id)"
              >{{ s.name }}</button>
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">对方性别 <span class="required">*</span></label>
            <div class="option-row">
              <button
                v-for="g in GENDERS"
                :key="g.value"
                type="button"
                class="option-chip"
                :class="{ 'is-active': pickForm.target_gender === g.value }"
                @click="setTargetGender(g.value)"
              >{{ g.label }}</button>
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">
              兴趣标签
              <span class="form-hint-inline">点一下=尽量有 · 点两下=必须有 · 点三下=无所谓</span>
            </label>
            <div class="tag-state-legend">
              <span class="legend-item"><span class="legend-dot legend-default"></span>无所谓</span>
              <span class="legend-item"><span class="legend-dot legend-prefer"></span>尽量有</span>
              <span class="legend-item"><span class="legend-dot legend-required"></span>必须有</span>
            </div>
            <div class="option-row">
              <button
                v-for="t in interestTags"
                :key="t"
                type="button"
                class="option-chip tag-chip"
                :class="getTagStateClass(t)"
                @click="toggleTagState(t)"
              >
                <span class="tag-name">{{ t }}</span>
                <span v-if="getTagState(t) === 1" class="tag-state-badge tag-state-badge--prefer">尽量</span>
                <span v-if="getTagState(t) === 2" class="tag-state-badge tag-state-badge--required">必须</span>
              </button>
            </div>
          </div>

          <button
            type="button"
            class="primary-btn"
            :disabled="pickLoading || pickStatus.remaining <= 0"
            @click="onPick"
          >
            <Icon name="gift" :size="16" />
            <span>{{ pickLoading ? '捞取中...' : '拾取一个瓶子' }}</span>
          </button>
          <p v-if="pickStatus.remaining <= 0" class="form-hint-center">今日拾取次数已用完，明天再来吧</p>
        </div>

        <!-- 拾取结果（居中模态弹窗，参考选择圈子写法） -->
        <Teleport to="body">
          <Transition name="pick-modal">
            <div v-if="pickResult" class="pick-modal-overlay" @click.self="closePickResult">
              <div class="pick-modal" role="dialog" aria-modal="true" aria-label="拾取结果">
                <div class="pick-modal-head">
                  <span class="pick-modal-title">拾到一个瓶子</span>
                  <button type="button" class="icon-btn-sm" @click="closePickResult" aria-label="关闭">
                    <Icon name="x" :size="16" />
                  </button>
                </div>
                <div class="pick-modal-body">
                  <div class="pick-result-author">
                    <img
                      v-if="pickResult.author_avatar_url"
                      :src="pickResult.author_avatar_url"
                      :alt="pickResult.author_nickname || '作者'"
                      class="avatar avatar-md"
                    />
                    <span v-else class="avatar avatar-md" aria-hidden="true">{{ (pickResult.author_nickname || 'U').charAt(0) }}</span>
                    <div class="author-info">
                      <span class="author-name">
                        <BadgeIcon :badge="pickResult.author_badge" :size="14" />
                        {{ pickResult.author_nickname || '匿名同学' }}
                      </span>
                      <span class="author-meta">
                        <span>{{ ageLabel(pickResult.author_age) }}</span>
                        <span class="meta-dot">·</span>
                        <span>{{ pickResult.school_name || '未知校区' }}</span>
                        <span class="meta-dot">·</span>
                        <span>{{ genderLabel(pickResult.author_gender) }}</span>
                      </span>
                    </div>
                  </div>
                  <p v-if="pickResult.content" class="pick-result-content">{{ pickResult.content }}</p>
                  <div v-if="pickResult.image_urls?.length" class="pick-result-images">
                    <img
                      v-for="(url, idx) in pickResult.image_urls"
                      :key="idx"
                      :src="url"
                      alt="瓶子图片"
                      class="result-image"
                      loading="lazy"
                    />
                  </div>
                  <div v-if="pickResult.tags?.length" class="pick-result-tags">
                    <span v-for="t in pickResult.tags" :key="t" class="result-tag">{{ t }}</span>
                  </div>
                  <div v-if="pickResult.contact" class="pick-result-contact">
                    <Icon name="phone" :size="14" />
                    <div>
                      <span class="contact-label">联系方式</span>
                      <span class="contact-value">{{ pickResult.contact }}</span>
                    </div>
                  </div>
                  <p class="pick-result-time">投放于 {{ formatRelative(pickResult.created_at || '') }}</p>
                </div>
                <div class="pick-modal-foot">
                  <button type="button" class="pick-modal-btn" @click="closePickResult">
                    收下瓶子
                  </button>
                </div>
              </div>
            </div>
          </Transition>
        </Teleport>
      </section>

      <!-- ====== 我的瓶子 ====== -->
      <section v-else class="tab-panel">
        <div class="mine-subtabs">
          <button
            type="button"
            class="mine-subtab"
            :class="{ 'is-active': mineSubTab === 'thrown' }"
            @click="mineSubTab = 'thrown'"
          >我投放的（{{ myBottles.length }}）</button>
          <button
            type="button"
            class="mine-subtab"
            :class="{ 'is-active': mineSubTab === 'picked' }"
            @click="mineSubTab = 'picked'"
          >我拾取的（{{ myPicks.length }}）</button>
        </div>

        <div v-if="mineLoading" class="mine-loading">
          <Icon name="refresh" :size="20" />
          <span>加载中...</span>
        </div>

        <template v-else>
          <div v-if="mineSubTab === 'thrown'">
            <div v-if="myBottles.length" class="mine-list">
              <div v-for="b in myBottles" :key="b.id" class="mine-item">
                <div class="mine-item-head">
                  <span class="mine-item-status" :class="`status-${b.status}`">
                    {{ b.status === 'active' ? '漂流中' : b.status === 'recalled' ? '已收回' : b.status === 'picked' ? '已拾取' : '已过期' }}
                  </span>
                  <span
                    v-if="b.audit_status && b.audit_status !== 'approved'"
                    class="mine-item-audit"
                    :class="`audit-${b.audit_status}`"
                  >
                    {{ b.audit_status === 'pending' ? '审核中' : b.audit_status === 'manual_review' ? '人工审核中' : '未通过' }}
                  </span>
                  <span class="mine-item-time">{{ formatRelative(b.created_at || '') }}</span>
                </div>
                <p v-if="b.audit_status === 'rejected' && b.reject_reason" class="mine-item-reject">
                  <Icon name="circle-alert" :size="12" />
                  未通过原因：{{ b.reject_reason }}
                </p>
                <p v-if="b.content" class="mine-item-content">{{ b.content }}</p>
                <div v-if="b.image_urls?.length" class="mine-item-images">
                  <img
                    v-for="(url, idx) in b.image_urls"
                    :key="idx"
                    :src="url"
                    alt="瓶子图片"
                    class="mine-image"
                    loading="lazy"
                  />
                </div>
                <div v-if="b.tags?.length" class="mine-item-tags">
                  <span v-for="t in b.tags" :key="t" class="mine-tag">{{ t }}</span>
                </div>
                <div class="mine-item-meta">
                  <span>{{ ageLabel(b.author_age) }}</span>
                  <span class="meta-dot">·</span>
                  <span>{{ b.school_name }}</span>
                  <span class="meta-dot">·</span>
                  <span>被拾取 {{ b.picked_count || 0 }} 次</span>
                </div>
                <div v-if="b.contact" class="mine-item-contact">
                  <Icon name="phone" :size="12" />
                  <span>联系方式：{{ b.contact }}</span>
                </div>
                <div v-if="b.status === 'active' && (!b.audit_status || b.audit_status === 'approved')" class="mine-item-actions">
                  <button
                    type="button"
                    class="recall-btn"
                    :disabled="recallingId === b.id"
                    @click="onRecall(b.id)"
                  >
                    {{ recallingId === b.id ? '收回中...' : '收回瓶子' }}
                  </button>
                </div>
              </div>
            </div>
            <div v-else class="empty-state">
              <Icon name="box" :size="40" />
              <p>还没有投放过瓶子</p>
              <button type="button" class="link-btn" @click="activeTab = 'throw'">去投放</button>
            </div>
            <div v-if="myBottles.length" class="mine-summary">
              <Icon name="gift" :size="14" />
              <span>你的瓶子被拾取 {{ myPickedCount }} 次</span>
            </div>
          </div>

          <div v-else>
            <div v-if="myPicks.length" class="mine-list">
              <div v-for="b in myPicks" :key="b.id" class="mine-item">
                <div class="mine-item-head">
                  <div class="mine-item-author">
                    <img
                      v-if="b.author_avatar_url"
                      :src="b.author_avatar_url"
                      :alt="b.author_nickname || '作者'"
                      class="avatar avatar-sm"
                    />
                    <span v-else class="avatar avatar-sm" aria-hidden="true">{{ (b.author_nickname || 'U').charAt(0) }}</span>
                    <span class="author-name">
                      <BadgeIcon :badge="b.author_badge" :size="14" />
                      {{ b.author_nickname || '匿名同学' }}
                    </span>
                  </div>
                  <span class="mine-item-time">{{ formatRelative(b.picked_at || b.created_at || '') }}</span>
                </div>
                <p v-if="b.content" class="mine-item-content">{{ b.content }}</p>
                <div v-if="b.image_urls?.length" class="mine-item-images">
                  <img
                    v-for="(url, idx) in b.image_urls"
                    :key="idx"
                    :src="url"
                    alt="瓶子图片"
                    class="mine-image"
                    loading="lazy"
                  />
                </div>
                <div v-if="b.tags?.length" class="mine-item-tags">
                  <span v-for="t in b.tags" :key="t" class="mine-tag">{{ t }}</span>
                </div>
                <div class="mine-item-meta">
                  <span>{{ ageLabel(b.author_age) }}</span>
                  <span class="meta-dot">·</span>
                  <span>{{ b.school_name }}</span>
                  <span class="meta-dot">·</span>
                  <span>{{ genderLabel(b.author_gender) }}</span>
                </div>
                <div v-if="b.contact" class="mine-item-contact">
                  <Icon name="phone" :size="12" />
                  <span>联系方式：{{ b.contact }}</span>
                </div>
              </div>
            </div>
            <div v-else class="empty-state">
              <Icon name="gift" :size="40" />
              <p>还没有拾取过瓶子</p>
              <button type="button" class="link-btn" @click="activeTab = 'pick'">去拾取</button>
            </div>
          </div>
        </template>
      </section>
    </div>

    <!-- 漂流瓶人工审核提示 -->
    <NativeDialog v-model="auditDialogVisible" title="已进入人工审核" width="420px">
      <p class="audit-dialog-text">{{ auditDialogMessage }}</p>
      <template #footer>
        <button class="btn btn-primary" type="button" @click="auditDialogVisible = false">我知道了</button>
      </template>
    </NativeDialog>
  </main>
</template>

<style scoped>
*, *::before, *::after { box-sizing: border-box; }

.page-bottle {
  min-height: 100vh;
  background: linear-gradient(180deg, #e8f4fd 0%, #f5f7fa 30%);
  padding-top: 56px;
  padding-bottom: calc(56px + 28px + env(safe-area-inset-bottom));
  color: var(--text-800);
  font-family: var(--font-sans, inherit);
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

/* 顶部固定栏 */
.site-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  height: 56px;
  background: var(--bg-50);
  border-bottom: 0.5px solid var(--bg-300);
}
.header-inner {
  max-width: 640px;
  margin: 0 auto;
  height: 100%;
  padding: 0 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.header-side {
  flex: 1;
  display: flex;
  align-items: center;
}
.header-side--left { justify-content: flex-start; }
.header-side--right { justify-content: flex-end; }
.header-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-800);
  margin: 0;
}
.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  color: var(--text-600);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: background 150ms;
}
.icon-btn:hover { background: var(--bg-100); }

/* 内容区 */
.page-container {
  max-width: 640px;
  margin: 0 auto;
  padding: 16px 16px calc(56px + env(safe-area-inset-bottom));
}

/* 透明统计 */
.bottle-stats {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  margin-bottom: 14px;
  background: var(--bg-50);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-xs);
  font-size: 12px;
  flex-wrap: wrap;
}
.stats-item {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--text-500);
}
.stats-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  display: inline-block;
}
.stats-dot--green {
  background: #34c759;
  box-shadow: 0 0 0 3px rgba(52, 199, 89, 0.18);
  animation: pulse-online 1.6s ease-in-out infinite;
}
@keyframes pulse-online {
  0%, 100% { box-shadow: 0 0 0 3px rgba(52, 199, 89, 0.18); }
  50% { box-shadow: 0 0 0 5px rgba(52, 199, 89, 0.08); }
}
.stats-num {
  font-weight: 700;
  color: var(--text-800);
  font-size: 13px;
}
.stats-label {
  color: var(--text-400);
  font-size: 12px;
}
.stats-divider {
  width: 1px;
  height: 12px;
  background: var(--bg-300);
}

/* 在线匹配入口 */
.match-entry {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 14px 16px;
  margin-bottom: 16px;
  background: linear-gradient(135deg, #ff9500, #ff6b35);
  border: none;
  border-radius: var(--radius-lg);
  cursor: pointer;
  text-align: left;
  color: #fff;
  transition: transform 150ms, box-shadow 150ms;
}
.match-entry:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}
.match-entry-ic {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.25);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.match-entry-text {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.match-entry-title {
  font-size: 15px;
  font-weight: 700;
}
.match-entry-desc {
  font-size: 12px;
  opacity: 0.9;
}
.match-entry-arrow {
  flex-shrink: 0;
  opacity: 0.8;
}

/* Tab 栏 */
.tab-bar {
  display: flex;
  background: var(--bg-200);
  border-radius: var(--radius-md);
  padding: 3px;
  margin-bottom: 16px;
}
.tab-item {
  flex: 1;
  padding: 8px 12px;
  border: none;
  background: transparent;
  color: var(--text-500);
  font-size: 13px;
  font-weight: 500;
  border-radius: calc(var(--radius-md) - 2px);
  cursor: pointer;
  transition: all 150ms;
  position: relative;
}
.tab-item.is-active {
  background: var(--bg-50);
  color: var(--brand-600);
  font-weight: 600;
  box-shadow: var(--shadow-xs);
}
.tab-badge {
  display: inline-block;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  background: #ff9500;
  color: #fff;
  font-size: 11px;
  line-height: 18px;
  border-radius: 9px;
  margin-left: 4px;
}

/* 表单卡片 */
.form-card {
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  padding: 18px 16px;
  box-shadow: var(--shadow-xs);
  position: relative;
  overflow: hidden;
}
.form-card.is-throwing {
  animation: card-shake 0.6s ease-out;
}
@keyframes card-shake {
  0%, 100% { transform: translateY(0); }
  30% { transform: translateY(-4px); }
  60% { transform: translateY(2px); }
}

/* 投放动效 */
.throw-anim {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.85);
  z-index: 10;
  animation: fade-in 0.2s ease;
}
@keyframes fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}
.throw-bottle {
  color: var(--brand-500);
  animation: throw-fly 1.2s ease-out forwards;
}
@keyframes throw-fly {
  0% { transform: translateY(0) rotate(0); opacity: 1; }
  60% { transform: translateY(-80px) rotate(-25deg); opacity: 1; }
  100% { transform: translateY(-200px) rotate(-90deg); opacity: 0; }
}

/* 拾取动效 */
.pick-anim {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: rgba(255, 255, 255, 0.92);
  z-index: 10;
  animation: fade-in 0.2s ease;
}
.pick-wave {
  position: absolute;
  width: 100px;
  height: 100px;
  border: 2px solid #007aff;
  border-radius: 50%;
  opacity: 0.4;
  animation: wave-spread 1.5s ease-out infinite;
}
@keyframes wave-spread {
  0% { transform: scale(0.5); opacity: 0.6; }
  100% { transform: scale(1.5); opacity: 0; }
}
.pick-bottle {
  color: #ff9500;
  animation: pick-float 0.8s ease-out;
}
@keyframes pick-float {
  0% { transform: translateY(40px); opacity: 0; }
  60% { transform: translateY(-8px); opacity: 1; }
  100% { transform: translateY(0); opacity: 1; }
}
.pick-anim-text {
  font-size: 13px;
  color: var(--text-500);
  margin: 0;
}

/* 表单字段 */
.form-group {
  margin-bottom: 16px;
}
.form-label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-700);
  margin-bottom: 8px;
}
.required {
  color: #ff3b30;
  margin-left: 2px;
}
.form-hint-inline {
  font-size: 11px;
  color: var(--text-400);
  font-weight: 400;
  margin-left: 6px;
}
.form-hint {
  font-size: 11px;
  color: var(--text-400);
  margin: 6px 0 0;
}
.form-hint-center {
  font-size: 12px;
  color: var(--text-400);
  text-align: center;
  margin: 10px 0 0;
}

/* 年龄展示框（投放表单） */
.age-display-box {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 12px;
  background: var(--bg-100);
  border-radius: var(--radius-md);
  font-size: 13px;
  color: var(--text-600);
}
.age-display-box strong {
  color: var(--brand-600);
  font-size: 15px;
  margin: 0 2px;
}
.age-missing {
  color: #ff6b35;
}
.link-inline {
  background: none;
  border: none;
  color: var(--brand-600);
  font-size: 12px;
  cursor: pointer;
  padding: 0 4px;
  text-decoration: underline;
}
.link-inline:hover {
  color: var(--brand-700);
}

/* 年龄范围选择（拾取表单） */
.age-range-row {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 10px 12px;
  background: var(--bg-100);
  border-radius: var(--radius-md);
}
.age-range-col {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.age-range-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-500);
  letter-spacing: 0.2px;
}

.option-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.option-chip {
  padding: 6px 14px;
  border-radius: 999px;
  font-size: 13px;
  color: var(--text-600);
  background: var(--bg-100);
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 150ms;
}
.option-chip:hover:not(.is-disabled) {
  background: var(--bg-200);
}
.option-chip.is-active {
  color: var(--brand-600);
  background: var(--brand-50);
  border-color: var(--brand-500);
  font-weight: 600;
}
.option-chip.is-disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ============ 拾取标签三态样式 ============ */
.tag-state-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 8px;
  padding: 6px 10px;
  background: var(--bg-100);
  border-radius: var(--radius-sm);
  font-size: 11px;
  color: var(--text-500);
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
  border: 1.5px solid var(--bg-300);
}
.legend-default { background: transparent; }
.legend-prefer { background: #ffd60a; border-color: #ffd60a; }
.legend-required { background: #ff3b30; border-color: #ff3b30; }

/* 三态标签 chip */
.tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  transition: all 150ms;
}
.tag-chip .tag-name {
  font-size: 13px;
}
.tag-chip.tag-state-default {
  /* 默认态：保持原 option-chip 样式 */
}
.tag-chip.tag-state-prefer {
  background: #fff8e6;
  color: #b8860b;
  border-color: #ffd60a;
  font-weight: 600;
}
.tag-chip.tag-state-required {
  background: #ffedef;
  color: #ff3b30;
  border-color: #ff3b30;
  font-weight: 700;
}
.tag-state-badge {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 4px;
  font-weight: 600;
  line-height: 1.3;
}
.tag-state-badge--prefer {
  background: #ffd60a;
  color: #fff;
}
.tag-state-badge--required {
  background: #ff3b30;
  color: #fff;
}

.custom-tag-row {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}
.custom-tag-input {
  flex: 1;
  padding: 6px 10px;
  border: 1px solid var(--bg-300);
  border-radius: var(--radius-sm);
  font-size: 13px;
  background: var(--bg-50);
  color: var(--text-800);
  outline: none;
  transition: border-color 150ms;
}
.custom-tag-input:focus {
  border-color: var(--brand-500);
}
.custom-tag-btn {
  padding: 6px 12px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--brand-500);
  color: #fff;
  font-size: 12px;
  cursor: pointer;
}
.custom-tag-btn:hover { background: var(--brand-600); }

.form-textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--bg-300);
  border-radius: var(--radius-md);
  font-size: 14px;
  font-family: inherit;
  background: var(--bg-50);
  color: var(--text-800);
  outline: none;
  resize: vertical;
  min-height: 80px;
  transition: border-color 150ms;
}
.form-textarea:focus {
  border-color: var(--brand-500);
}

/* 图片上传 */
.image-uploader {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}
.image-item {
  position: relative;
  width: 80px;
  height: 80px;
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--bg-100);
}
.image-item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.image-remove {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
.image-upload-btn {
  width: 80px;
  height: 80px;
  border: 1.5px dashed var(--bg-300);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-400);
  cursor: pointer;
  transition: all 150ms;
}
.image-upload-btn:hover {
  border-color: var(--brand-500);
  color: var(--brand-500);
}

/* 主按钮 */
.primary-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  padding: 12px;
  border: none;
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, #007aff, #0064d6);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 150ms;
  margin-top: 8px;
}
.primary-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}
.primary-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.link-btn {
  background: none;
  border: none;
  color: var(--brand-600);
  font-size: 13px;
  cursor: pointer;
  margin-top: 8px;
}

/* 拾取状态条 */
.pick-status-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 12px;
  background: #fff8e6;
  border-radius: var(--radius-md);
  margin-bottom: 14px;
  font-size: 12px;
  color: #d26510;
}
.pick-status-bar strong {
  color: #ff6b35;
  font-size: 14px;
}

/* 拾取结果居中模态弹窗（参考选择圈子写法） */
.pick-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 9998;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}
.pick-modal {
  width: 100%;
  max-width: 420px;
  max-height: 85vh;
  background: var(--bg-50);
  border-radius: 20px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: var(--shadow-lg, 0 10px 40px rgba(0, 0, 0, 0.2));
}
.pick-modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 18px 12px;
  border-bottom: 0.5px solid var(--bg-300);
  flex-shrink: 0;
}
.pick-modal-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-900);
}
.pick-modal-body {
  padding: 16px 18px;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}
.pick-modal-foot {
  padding: 12px 18px 16px;
  border-top: 0.5px solid var(--bg-300);
  flex-shrink: 0;
}
.pick-modal-btn {
  width: 100%;
  padding: 11px;
  border: none;
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, #4a9eff, #2575fc);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 150ms;
}
.pick-modal-btn:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}
/* 进入/离开动画 */
.pick-modal-enter-active,
.pick-modal-leave-active {
  transition: opacity 200ms ease;
}
.pick-modal-enter-active .pick-modal,
.pick-modal-leave-active .pick-modal {
  transition: transform 250ms cubic-bezier(0.34, 1.56, 0.64, 1), opacity 200ms ease;
}
.pick-modal-enter-from,
.pick-modal-leave-to {
  opacity: 0;
}
.pick-modal-enter-from .pick-modal,
.pick-modal-leave-to .pick-modal {
  transform: scale(0.85);
  opacity: 0;
}
.icon-btn-sm {
  width: 28px;
  height: 28px;
  border: none;
  background: var(--bg-100);
  border-radius: 50%;
  color: var(--text-500);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 150ms;
}
.icon-btn-sm:hover {
  background: var(--bg-200);
}
.pick-result-author {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--bg-200);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}
.avatar-sm { width: 28px; height: 28px; }
.avatar-md { width: 40px; height: 40px; }
.avatar img { object-fit: cover; width: 100%; height: 100%; border-radius: 50%; }
.author-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.author-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-800);
}
.author-meta {
  font-size: 12px;
  color: var(--text-400);
  display: flex;
  align-items: center;
  gap: 4px;
}
.meta-dot {
  color: var(--text-300);
}
.pick-result-content {
  font-size: 14px;
  color: var(--text-700);
  line-height: 1.6;
  margin: 0 0 12px;
  white-space: pre-wrap;
  word-break: break-word;
}
.pick-result-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.result-image {
  width: 120px;
  height: 120px;
  object-fit: cover;
  border-radius: var(--radius-md);
  background: var(--bg-100);
}
.pick-result-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}
.result-tag {
  font-size: 11px;
  color: var(--brand-600);
  background: var(--brand-50);
  padding: 2px 8px;
  border-radius: 999px;
}
.pick-result-time {
  font-size: 11px;
  color: var(--text-400);
  margin: 0;
}

/* 我的瓶子 */
.mine-subtabs {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}
.mine-subtab {
  flex: 1;
  padding: 8px;
  border: 1px solid var(--bg-300);
  background: var(--bg-50);
  color: var(--text-500);
  font-size: 13px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 150ms;
}
.mine-subtab.is-active {
  color: var(--brand-600);
  border-color: var(--brand-500);
  background: var(--brand-50);
  font-weight: 600;
}
.mine-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 0;
  color: var(--text-500);
  font-size: 13px;
}
.mine-loading :deep(svg) {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0); }
  to { transform: rotate(360deg); }
}
.mine-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.mine-item {
  background: var(--bg-50);
  border-radius: var(--radius-md);
  padding: 14px;
  box-shadow: var(--shadow-xs);
}
.mine-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.mine-item-status {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 600;
}
.mine-item-audit {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 600;
}
.audit-pending {
  color: #b45309;
  background: #fff4e0;
}
.audit-manual_review {
  color: #1d4ed8;
  background: #e8f2ff;
}
.audit-rejected {
  color: #dc2626;
  background: #ffece8;
}
.mine-item-reject {
  display: flex;
  align-items: center;
  gap: 5px;
  margin: 4px 0 0;
  font-size: 12px;
  color: #dc2626;
  background: #fff5f4;
  border: 1px solid #ffd6d2;
  border-radius: 8px;
  padding: 6px 10px;
}
.audit-dialog-text {
  margin: 0;
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-700);
}
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 8px 16px;
  border-radius: var(--radius-sm);
  border: none;
  font-family: inherit;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}
.btn-primary {
  background: var(--brand-500);
  color: #fff;
}
.btn-primary:hover:not(:disabled) {
  background: var(--brand-600);
}
.status-active {
  color: #34c759;
  background: #e9f9ee;
}
.status-picked {
  color: #ff9500;
  background: #fff3e6;
}
.status-recalled {
  color: #8e8e93;
  background: #f0f0f2;
}
.status-expired {
  color: var(--text-400);
  background: var(--bg-100);
}
.mine-item-time {
  font-size: 11px;
  color: var(--text-400);
}
.mine-item-content {
  font-size: 14px;
  color: var(--text-700);
  line-height: 1.5;
  margin: 0 0 10px;
  white-space: pre-wrap;
  word-break: break-word;
}
.mine-item-images {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}
.mine-image {
  width: 80px;
  height: 80px;
  object-fit: cover;
  border-radius: var(--radius-sm);
  background: var(--bg-100);
}
.mine-item-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 8px;
}
.mine-tag {
  font-size: 11px;
  color: var(--brand-600);
  background: var(--brand-50);
  padding: 2px 8px;
  border-radius: 999px;
}
.mine-item-meta {
  font-size: 11px;
  color: var(--text-400);
  display: flex;
  align-items: center;
  gap: 4px;
}
.mine-item-author {
  display: flex;
  align-items: center;
  gap: 6px;
}
.mine-summary {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 16px;
  padding: 10px;
  background: #fff8e6;
  border-radius: var(--radius-md);
  font-size: 12px;
  color: #d26510;
}
/* 联系方式展示（我的瓶子/我的拾取） */
.mine-item-contact {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  padding: 6px 10px;
  background: #f0f7ff;
  border-radius: var(--radius-sm);
  font-size: 12px;
  color: var(--brand-600);
}
/* 收回按钮 */
.mine-item-actions {
  margin-top: 10px;
  display: flex;
  justify-content: flex-end;
}
.recall-btn {
  padding: 5px 12px;
  font-size: 12px;
  font-family: inherit;
  border: 1px solid var(--bg-300);
  border-radius: var(--radius-sm);
  background: var(--bg-50);
  color: var(--text-600);
  cursor: pointer;
  transition: all 0.15s var(--ease-apple);
}
.recall-btn:hover:not(:disabled) {
  border-color: #ff9500;
  color: #ff9500;
  background: #fff3e6;
}
.recall-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
/* 拾取结果中的联系方式高亮卡片 */
.pick-result-contact {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 10px 0;
  padding: 12px 14px;
  background: linear-gradient(135deg, #f0f7ff, #fff8e6);
  border: 1px solid #b8d9ff;
  border-radius: var(--radius-md);
}
.pick-result-contact .contact-label {
  display: block;
  font-size: 11px;
  color: var(--text-400);
  margin-bottom: 2px;
}
.pick-result-contact .contact-value {
  display: block;
  font-size: 15px;
  font-weight: 600;
  color: var(--brand-600);
  word-break: break-all;
}
/* 投放表单的 input 样式 */
.form-input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--bg-300);
  border-radius: var(--radius-sm);
  background: var(--bg-50);
  font-size: 14px;
  font-family: inherit;
  color: var(--text-800);
  outline: none;
  transition: border-color 0.15s var(--ease-apple), box-shadow 0.15s var(--ease-apple);
}
.form-input:focus {
  border-color: var(--brand-500);
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.12);
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 20px;
  color: var(--text-400);
  font-size: 13px;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .page-bottle {
    padding-top: 48px;
  }
  .site-header { height: 48px; }
  .header-title { font-size: 16px; }
  .page-container { padding: 12px 12px 24px; }
  .bottle-stats { gap: 8px; padding: 8px 12px; }
  .form-card { padding: 14px 12px; }
  .option-chip { padding: 5px 12px; font-size: 12px; }
  .result-image { width: 100px; height: 100px; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
  }
}
</style>
