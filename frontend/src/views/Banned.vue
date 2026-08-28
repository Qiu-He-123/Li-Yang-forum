<script setup lang="ts">
/**
 * 封号提示页
 *
 * - 展示用户头像、昵称（加载个人资料）
 * - 展示封号原因、截止时间、当前警告值
 * - 提供「提交申诉」入口（原生 Dialog 填写申诉理由）
 * - 提供「我已知情」按钮：仅查看提示后退出登录
 *
 * 警告值机制：
 * - 文案采用警告值表述，不再说"违规 X 次"
 * - 显示当前警告值 / 永久封号阈值，便于用户理解封号原因
 * - 临时封号用户提示"解封后保持良好行为可减少警告值"
 *
 * 样式对齐主页面：使用全局 CSS 变量（--bg-*, --text-*, --error, --radius-*, --shadow-*）
 *
 * 触发时机：
 * 1. 登录返回 ban_info.is_banned=true → 跳转本页
 * 2. 应用启动时检测 ban_status.is_banned=true → 跳转本页
 * 3. 写操作返回 -301 USER_BANNED → HTTP 拦截器自动跳转本页
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { Icon, Dialog as NativeDialog } from '../components/native'
import { toast } from '../components/native/Toast'
import { fetchBanStatus, fetchMyWarningStatus, createAppeal, type BanStatus, type WarningStatus } from '../api/user'
import { useSessionStore } from '../stores/session'

const router = useRouter()
const session = useSessionStore()

const banStatus = ref<BanStatus | null>(null)
const warningStatus = ref<WarningStatus | null>(null)
const loading = ref(true)

const appealDialogVisible = ref(false)
const appealForm = reactive({ reason: '' })
const submittingAppeal = ref(false)

const isPermanent = computed(() => !banStatus.value?.ban_until)
const banUntilText = computed(() => {
  const t = banStatus.value?.ban_until
  if (!t) return '永久封禁'
  return t.replace('T', ' ').slice(0, 19)
})

// 警告值展示：优先用 warningStatus（警告值系统权威源），其次 banStatus（含阈值兜底）
const warningScore = computed(() => warningStatus.value?.score ?? banStatus.value?.warning_score ?? 0)
const permBanThreshold = computed(() => warningStatus.value?.perm_ban_threshold ?? banStatus.value?.perm_ban_threshold ?? 100)
const warningPercent = computed(() => {
  if (permBanThreshold.value <= 0) return 0
  return Math.min(100, Math.round((warningScore.value / permBanThreshold.value) * 100))
})

// 是否真的达到对应阈值（避免管理员强制封号但分数未到阈值时显示误导标签）
const reachedThreshold = computed(() => {
  if (!banStatus.value) return false
  if (isPermanent.value) return warningScore.value >= permBanThreshold.value
  const tempTh = warningStatus.value?.temp_ban_threshold ?? banStatus.value?.temp_ban_threshold ?? 60
  return warningScore.value >= tempTh
})

// 头像渐变（与 PostCard 一致）
const avatarPalettes = [
  'linear-gradient(135deg, #66abff, #007aff)',
  'linear-gradient(135deg, #34c759, #2e8dff)',
  'linear-gradient(135deg, #ff9500, #007aff)',
  'linear-gradient(135deg, #5856d6, #af52de)',
  'linear-gradient(135deg, #d1d1d6, #8e8e93)',
]
const avatarGradient = computed(() => {
  const id = session.userId
  if (!id) return avatarPalettes[4]
  return avatarPalettes[id % 5]
})
const authorInitial = computed(() => (session.nickname || '?').trim().charAt(0).toUpperCase())
const avatarUrl = computed(() => null)
const nickname = computed(() => session.nickname || '用户')

async function loadBanStatus() {
  loading.value = true
  try {
    // 仅加载封号状态 + 警告值状态（均使用 current_user_allow_banned，封号用户可访问）
    // 不再调用 userStore.loadProfile()：/users/me 用 current_user 会对封号用户返回 -301，
    // 触发 handleBannedRedirect 副作用，在并发场景下引发"系统开小差了"。
    // 头像/昵称用 session.nickname 兜底（登录时已存入）。
    const [banRes] = await Promise.all([
      fetchBanStatus(),
      fetchMyWarningStatus({
        showGlobalLoading: false,
        showGlobalError: false,
      })
        .then((res) => {
          warningStatus.value = res.data.data
        })
        .catch(() => {
          // 警告值加载失败不阻塞主流程，banStatus 已含阈值兜底
        }),
    ])
    banStatus.value = banRes.data.data
    // 未封号（管理员已解封 / 已到期）：清除本地封号标记再跳转
    // 必须在 router.replace 前调用 setBanned(false)清除 localStorage，
    // 否则路由守卫（router.beforeEach）会因 localStorage banned=1 再次拦回本页，形成死循环。
    if (!banRes.data.data.is_banned) {
      session.setBanned(false)
      router.replace('/')
    }
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    loading.value = false
  }
}

function openAppealDialog() {
  appealForm.reason = ''
  appealDialogVisible.value = true
}

async function submitAppeal() {
  if (!appealForm.reason.trim()) {
    toast.warning('请填写申诉理由')
    return
  }
  submittingAppeal.value = true
  try {
    await createAppeal(appealForm.reason.trim())
    toast.success('申诉已提交，请耐心等待管理员复查')
    appealDialogVisible.value = false
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    submittingAppeal.value = false
  }
}

async function onAcknowledge() {
  // 我已知情：退出登录回到首页
  try {
    await session.clearSession()
  } catch {
    /* ignore */
  }
  router.replace('/')
}

onMounted(loadBanStatus)
</script>

<template>
  <main class="page-banned">
    <div class="banned-container">
      <div v-if="loading" class="loading-tip">
        <Icon name="refresh" :size="24" />
        <span>加载中…</span>
      </div>

      <template v-else-if="banStatus && banStatus.is_banned">
        <!-- 用户头像 + 昵称（与主页面风格一致） -->
        <div class="banned-user">
          <div class="banned-avatar">
            <img v-if="avatarUrl" :src="avatarUrl" :alt="nickname" />
            <div v-else class="avatar-fallback" :style="{ background: avatarGradient }">
              {{ authorInitial }}
            </div>
          </div>
          <div class="banned-nickname">{{ nickname }}</div>
        </div>

        <div class="banned-icon-wrap">
          <div class="banned-icon">
            <Icon name="alert-octagon" :size="40" />
          </div>
        </div>

        <h1 class="banned-title">账号已被封禁</h1>
        <p class="banned-subtitle">
          {{ isPermanent ? '您的账号已被永久封禁' : '您的账号已被临时封禁' }}
        </p>

        <div class="banned-info-card">
          <div class="info-row">
            <span class="info-label">封禁原因</span>
            <span class="info-value">{{ banStatus.ban_reason || '违反社区规范' }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">封禁截止</span>
            <span class="info-value info-until">{{ banUntilText }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">当前警告值</span>
            <span class="info-value info-until">
              {{ warningScore }} / {{ permBanThreshold }}
              <span v-if="reachedThreshold" class="warn-score-tag">
                {{ isPermanent ? '已达永久封号阈值' : '已达临时封号阈值' }}
              </span>
            </span>
          </div>
        </div>

        <!-- 警告值进度条 -->
        <div class="warn-progress-wrap">
          <div class="warn-progress">
            <div class="warn-progress-bar" :style="{ width: `${warningPercent}%` }" />
          </div>
          <div class="warn-progress-tip">
            <Icon name="triangle-alert" :size="12" />
            <span>
              {{ isPermanent
                ? '警告值已达永久封号阈值，账号已被永久封禁'
                : `解封后保持良好社区行为（签到、发帖等）可减少警告值，避免再次封号`
              }}
            </span>
          </div>
        </div>

        <div class="banned-actions">
          <button
            class="btn btn-primary btn-pill"
            type="button"
            @click="openAppealDialog"
          >
            <Icon name="edit" :size="14" />
            提交申诉
          </button>
          <button
            class="btn btn-ghost btn-pill"
            type="button"
            @click="onAcknowledge"
          >
            我已知情
          </button>
        </div>

        <p class="banned-tip">
          申诉后管理员会人工复查，请耐心等待审核结果。
        </p>
      </template>
    </div>

    <!-- 申诉对话框（原生 Dialog，对齐主页面风格） -->
    <NativeDialog v-model="appealDialogVisible" title="提交申诉" width="480px">
      <div class="appeal-form">
        <label class="appeal-label">申诉理由</label>
        <textarea
          v-model="appealForm.reason"
          class="appeal-textarea"
          rows="5"
          maxlength="500"
          placeholder="请说明你认为应当解封的理由，管理员会人工复查"
        />
        <div class="appeal-count">{{ appealForm.reason.length }}/500</div>
      </div>
      <template #footer>
        <button class="btn btn-ghost btn-pill" @click="appealDialogVisible = false">取消</button>
        <button class="btn btn-primary btn-pill" :disabled="submittingAppeal" @click="submitAppeal">
          {{ submittingAppeal ? '提交中…' : '提交申诉' }}
        </button>
      </template>
    </NativeDialog>
  </main>
</template>

<style scoped>
.page-banned {
  min-height: 100vh;
  background: var(--bg-100);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.banned-container {
  width: 100%;
  max-width: 480px;
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  padding: 40px 28px;
  text-align: center;
}

.loading-tip {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 60px 0;
  color: var(--text-400);
  font-size: 14px;
}

/* 用户头像区域 */
.banned-user {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  margin-bottom: 20px;
}
.banned-avatar {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}
.banned-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.avatar-fallback {
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
  color: #fff;
  font-size: 24px;
  font-weight: 700;
}
.banned-nickname {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-800);
}

.banned-icon-wrap {
  display: flex;
  justify-content: center;
  margin-bottom: 16px;
}
.banned-icon {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: var(--state-error-surface);
  color: var(--state-error);
  display: grid;
  place-items: center;
  animation: banned-pulse 2s ease-in-out infinite;
}
@keyframes banned-pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.05); }
}

.banned-title {
  margin: 0 0 8px;
  font-size: 22px;
  font-weight: 800;
  color: var(--text-800);
}
.banned-subtitle {
  margin: 0 0 24px;
  font-size: 14px;
  color: var(--text-500);
}

.banned-info-card {
  background: var(--bg-100);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 16px 20px;
  margin-bottom: 16px;
  text-align: left;
}
.info-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 8px 0;
  font-size: 14px;
}
.info-row + .info-row {
  border-top: 1px dashed var(--color-border);
}
.info-label {
  min-width: 80px;
  color: var(--text-500);
  font-weight: 500;
  flex-shrink: 0;
}
.info-value {
  color: var(--text-800);
  flex: 1;
  word-break: break-all;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.info-until {
  color: var(--state-error);
  font-weight: 700;
}
.warn-score-tag {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
  background: #ffe5e3;
  color: #ff3b30;
}

/* 警告值进度条 */
.warn-progress-wrap {
  margin-bottom: 24px;
  text-align: left;
}
.warn-progress {
  width: 100%;
  height: 6px;
  background: var(--bg-200);
  border-radius: 999px;
  overflow: hidden;
  margin-bottom: 8px;
}
.warn-progress-bar {
  height: 100%;
  background: var(--state-error);
  border-radius: 999px;
  transition: width 0.3s ease;
}
.warn-progress-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-600);
  line-height: 1.5;
}

.banned-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  margin-bottom: 16px;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  padding: 10px 24px;
  border-radius: 999px;
  border: none;
  cursor: pointer;
  transition: opacity 0.15s, transform 0.15s;
}
.btn:hover { opacity: 0.9; }
.btn:active { transform: scale(0.97); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary {
  background: var(--state-error);
  color: #fff;
}
.btn-ghost {
  background: transparent;
  color: var(--text-500);
  border: 1px solid var(--color-border);
}
.btn-ghost:hover {
  background: var(--bg-100);
}

.banned-tip {
  margin: 0;
  font-size: 12px;
  color: var(--text-400);
}

/* 申诉表单 */
.appeal-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.appeal-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-800);
}
.appeal-textarea {
  width: 100%;
  padding: 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: 14px;
  font-family: inherit;
  resize: vertical;
  outline: none;
  transition: border-color 0.15s;
}
.appeal-textarea:focus {
  border-color: var(--brand-500);
}
.appeal-count {
  text-align: right;
  font-size: 12px;
  color: var(--text-400);
}

@media (max-width: 480px) {
  .banned-container {
    padding: 32px 20px;
  }
  .banned-title {
    font-size: 20px;
  }
  .banned-actions {
    flex-direction: column;
  }
  .btn {
    width: 100%;
    justify-content: center;
  }
}
</style>
