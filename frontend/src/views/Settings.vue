<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'

import AppHeader from '../components/header/AppHeader.vue'
import { useThemeStore } from '../stores/theme'
import {
  changePassword,
  getMyInviteCode,
  getVerificationStatus,
  updateQQ,
  type MyInviteCodeInfo,
  type VerificationStatusInfo,
} from '../api/auth'
import {
  createAppeal,
  fetchBanStatus,
  fetchMe,
  fetchMyAppeals,
  updateMe,
  type BanStatus,
  type UserAppeal,
} from '../api/user'
import { uploadImage } from '../api/image'
import {
  getMessagePermission,
  updateMessagePermission,
  type MessagePermission,
} from '../api/friend'
import {
  listMyAnnouncements,
  markAnnouncementRead,
} from '../api/announcement'
import { isSilentRequestError } from '../api/http'
import { useUserStore } from '../stores/user'
import { useSessionStore } from '../stores/session'
import type { Announcement, Profile } from '../types/api'

const router = useRouter()
const userStore = useUserStore()
const session = useSessionStore()

const profile = ref<Profile | null>(null)
const form = ref({
  nickname: '',
  avatar_url: '',
  background_url: '',
  bio: '',
  gender: 'unknown' as 'male' | 'female' | 'unknown',
  /** 生日（YYYY-MM-DD），设置后动态计算年龄，替代年级 */
  birthday: '' as string,
})
const activeTab = ref<'profile' | 'security' | 'invite' | 'ban' | 'messages' | 'notifications' | 'announcements' | 'appearance'>('profile')
const themeStore = useThemeStore()
themeStore.init()
const saving = ref(false)

// ============ 年龄系统：生日设置 ============
/** 生日选择最大日期（今天），最小日期（100 年前） */
const birthdayMax = new Date().toISOString().slice(0, 10)
const birthdayMin = new Date(new Date().getFullYear() - 100, 0, 1).toISOString().slice(0, 10)

/** 从生日计算年龄（周岁） */
function calcAge(birthday: string | null | undefined): number | null {
  if (!birthday) return null
  const d = new Date(birthday)
  if (isNaN(d.getTime())) return null
  const now = new Date()
  let age = now.getFullYear() - d.getFullYear()
  const m = now.getMonth() - d.getMonth()
  if (m < 0 || (m === 0 && now.getDate() < d.getDate())) age--
  return age >= 0 ? age : null
}

/** 当前用户的年龄显示 */
const currentAge = computed(() => calcAge(form.value.birthday || profile.value?.birthday))

// ============ 性别选项 ============
const genderOptions: { value: 'male' | 'female' | 'unknown'; label: string }[] = [
  { value: 'male', label: '男生' },
  { value: 'female', label: '女生' },
  { value: 'unknown', label: '保密' },
]

// ============ 我的公告 ============
const myAnnouncements = ref<Announcement[]>([])
const announcementsLoading = ref(false)

async function loadMyAnnouncements() {
  announcementsLoading.value = true
  try {
    const { data } = await listMyAnnouncements({
      showGlobalLoading: false,
      showGlobalError: false,
    })
    myAnnouncements.value = data.data || []
  } catch (err) {
    if (isSilentRequestError(err)) return
    ElMessage.error((err as Error).message)
  } finally {
    announcementsLoading.value = false
  }
}

async function markRead(id: number) {
  try {
    await markAnnouncementRead(id)
    const item = myAnnouncements.value.find((x) => x.id === id)
    if (item) item.is_read = true
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}

function fmtAnnouncementTime(t: string | null | undefined): string {
  if (!t) return ''
  return t.replace('T', ' ').slice(0, 19)
}

// ============ 账号状态 / 申诉 ============
const banStatus = ref<BanStatus | null>(null)
const myAppeals = ref<UserAppeal[]>([])
const banLoading = ref(false)
const appealDialogVisible = ref(false)
const appealForm = reactive({
  reason: '',
})
const submittingAppeal = ref(false)

const appealStatusMeta: Record<string, { type: 'success' | 'warning' | 'danger' | 'info'; text: string }> = {
  pending: { type: 'warning', text: '待审核' },
  approved: { type: 'success', text: '已通过（已解封）' },
  rejected: { type: 'danger', text: '已驳回' },
}

async function loadBanStatus() {
  banLoading.value = true
  try {
    const [banRes, appealsRes] = await Promise.all([
      fetchBanStatus({
        showGlobalLoading: false,
        showGlobalError: false,
      }),
      fetchMyAppeals({
        showGlobalLoading: false,
        showGlobalError: false,
      }),
    ])
    banStatus.value = banRes.data.data
    myAppeals.value = appealsRes.data.data || []
  } catch (err) {
    if (isSilentRequestError(err)) return
    ElMessage.error((err as Error).message)
  } finally {
    banLoading.value = false
  }
}

function openAppealDialog() {
  appealForm.reason = ''
  appealDialogVisible.value = true
}

async function submitAppeal() {
  if (!appealForm.reason.trim()) {
    ElMessage.warning('请填写申诉理由')
    return
  }
  submittingAppeal.value = true
  try {
    await createAppeal(appealForm.reason.trim(), banStatus.value?.is_banned ? undefined : undefined)
    ElMessage.success('申诉已提交，请等待管理员审核')
    appealDialogVisible.value = false
    await loadBanStatus()
  } catch (err) {
    ElMessage.error((err as Error).message)
  } finally {
    submittingAppeal.value = false
  }
}

function fmtBanUntil(t: string | null): string {
  if (!t) return '永久封禁'
  return t.replace('T', ' ').slice(0, 19)
}

function fmtTime(t: string | null): string {
  if (!t) return ''
  return t.replace('T', ' ').slice(0, 19)
}

// ============ 私信权限 ============
const messagePerm = ref<MessagePermission>('stranger_once')
const permLoading = ref(false)

const permOptions: { value: MessagePermission; label: string; desc: string }[] = [
  { value: 'everyone', label: '所有人可发', desc: '任何用户都可以给你发送私信' },
  { value: 'mutual_only', label: '仅互关可发', desc: '只有互相关注的用户可以发送私信' },
  { value: 'stranger_once', label: '陌生人每天 1 条', desc: '陌生人每天只能发送 1 条私信（推荐）' },
  { value: 'no_stranger', label: '不接受陌生人消息', desc: '完全屏蔽非互关用户的消息' },
]

async function loadMessagePerm() {
  try {
    const { data } = await getMessagePermission({
      showGlobalLoading: false,
      showGlobalError: false,
    })
    messagePerm.value = data.data.message_permission
  } catch (err) {
    if (isSilentRequestError(err)) return
    ElMessage.error((err as Error).message)
  }
}

async function changeMessagePerm(value: string | number | boolean | undefined) {
  if (!permOptions.some((opt) => opt.value === value)) return
  const next = value as MessagePermission
  permLoading.value = true
  try {
    await updateMessagePermission(next)
    messagePerm.value = next
    ElMessage.success('已更新')
  } catch (err) {
    ElMessage.error((err as Error).message)
  } finally {
    permLoading.value = false
  }
}

// ============ T5-2 账号安全：修改密码 ============
const pwdFormRef = ref<FormInstance>()
const pwdForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: '',
})
const pwdRules: FormRules = {
  old_password: [{ required: true, message: '请输入旧密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, max: 72, message: '密码长度 8-72 位', trigger: 'blur' },
  ],
  confirm_password: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (_rule, value: string, callback: (e?: Error) => void) => {
        if (value !== pwdForm.new_password) callback(new Error('两次密码不一致'))
        else callback()
      },
      trigger: 'blur',
    },
  ],
}
const changingPwd = ref(false)
const newPasswordLen = computed(() => pwdForm.new_password.length)

// ============ 邀请码系统：QQ 号 + 邀请码展示 ============
const qqForm = reactive({
  qq: '',
})
const qqSaving = ref(false)
const verificationInfo = ref<VerificationStatusInfo | null>(null)
const inviteCodeInfo = ref<MyInviteCodeInfo | null>(null)
const inviteLoading = ref(false)

// ============ 学生认证（已移除照片上传，改为加管理员微信） ============

async function loadVerificationInfo() {
  try {
    const { data } = await getVerificationStatus({
      showGlobalLoading: false,
      showGlobalError: false,
    })
    verificationInfo.value = data.data
    qqForm.qq = data.data.qq || ''
  } catch (err) {
    if (isSilentRequestError(err)) return
    ElMessage.error((err as Error).message)
  }
}

async function loadInviteCodeInfo() {
  inviteLoading.value = true
  try {
    const { data } = await getMyInviteCode({
      showGlobalLoading: false,
      showGlobalError: false,
    })
    inviteCodeInfo.value = data.data
  } catch (err) {
    // 未认证用户可能没有邀请码，错误静默处理
    inviteCodeInfo.value = null
  } finally {
    inviteLoading.value = false
  }
}

async function saveQQ() {
  qqSaving.value = true
  try {
    await updateQQ(qqForm.qq.trim() || null)
    ElMessage.success('QQ 号已保存')
    await loadVerificationInfo()
  } catch (err) {
    ElMessage.error((err as Error).message)
  } finally {
    qqSaving.value = false
  }
}

async function copyInviteCode() {
  if (!inviteCodeInfo.value?.code) return
  try {
    await navigator.clipboard.writeText(inviteCodeInfo.value.code)
    ElMessage.success('邀请码已复制')
  } catch {
    ElMessage.info(`邀请码：${inviteCodeInfo.value.code}`)
  }
}

function copyAdminWechat() {
  navigator.clipboard.writeText('qhsqq2623655749').then(() => {
    ElMessage.success('管理员微信号已复制')
  }).catch(() => {
    ElMessage.info('管理员微信号：qhsqq2623655749')
  })
}

/** 格式化冷却/冻结剩余秒数为「x天 y小时 z分钟」 */
function formatSeconds(sec: number): string {
  if (sec <= 0) return '已结束'
  const d = Math.floor(sec / 86400)
  const h = Math.floor((sec % 86400) / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const parts: string[] = []
  if (d > 0) parts.push(`${d} 天`)
  if (h > 0) parts.push(`${h} 小时`)
  if (m > 0) parts.push(`${m} 分钟`)
  return parts.length ? parts.join(' ') : '不足 1 分钟'
}

async function load() {
  try {
    const { data } = await fetchMe()
    profile.value = data.data
    form.value = {
      nickname: data.data.nickname,
      avatar_url: data.data.avatar_url || '',
      background_url: data.data.background_url || '',
      bio: data.data.bio || '',
      gender: (data.data.gender as 'male' | 'female' | 'unknown') || 'unknown',
      birthday: data.data.birthday ? data.data.birthday.slice(0, 10) : '',
    }
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function uploadAvatar(file: File) {
  try {
    const { data } = await uploadImage(file, undefined, 'avatar')
    form.value.avatar_url = data.data.url
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function uploadBackground(file: File) {
  try {
    const { data } = await uploadImage(file)
    form.value.background_url = data.data.url
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function save() {
  saving.value = true
  try {
    await updateMe({
      ...form.value,
      // 未设置生日时后端要求 null，空字符串会导致整个保存失败（422）
      birthday: form.value.birthday || null,
    })
    ElMessage.success('已保存')
    await userStore.loadProfile()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    saving.value = false
  }
}

async function changePwd() {
  if (!pwdFormRef.value) return
  try {
    await pwdFormRef.value.validate()
  } catch {
    return
  }
  changingPwd.value = true
  try {
    await changePassword({ ...pwdForm })
    ElMessage.success('密码已修改，请使用新密码登录')
    pwdForm.old_password = ''
    pwdForm.new_password = ''
    pwdForm.confirm_password = ''
    // 后端已撤销其他设备的 refresh_token，本端也清登录态让用户重新登录
    session.clearSession()
    router.push('/')
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    changingPwd.value = false
  }
}

onMounted(async () => {
  if (!session.userId) {
    ElMessage.info('请先登录')
    router.push('/')
  } else {
    // 性能优化：validateSession 与 load 并行，不阻塞
    void session.validateSession()
    await load()
    void Promise.allSettled([
      loadMessagePerm(),
      loadBanStatus(),
      loadMyAnnouncements(),
      loadVerificationInfo(),
      session.isVerified() ? loadInviteCodeInfo() : Promise.resolve(),
    ])
    // 邀请码系统：加载 QQ 号 + 认证状态
    // 已认证用户才加载邀请码信息
  }
})
</script>

<template>
  <main class="min-h-screen pb-16 lg:pb-0">
    <AppHeader />
    <div class="mx-auto max-w-2xl px-4 py-5">
      <h2 class="mb-3 text-lg font-black">设置</h2>
      <el-tabs v-model="activeTab" tab-position="top" class="settings-tabs">
        <el-tab-pane label="基本资料" name="profile">
          <el-form v-if="profile" label-position="top">
            <el-form-item label="昵称">
              <el-input v-model="form.nickname" />
            </el-form-item>
            <el-form-item label="头像">
              <div class="flex items-center gap-3">
                <el-avatar :size="64" :src="form.avatar_url || undefined">
                  {{ form.nickname?.[0] || '?' }}
                </el-avatar>
                <el-upload
                  :show-file-list="false"
                  :http-request="(o: { file: File }) => uploadAvatar(o.file)"
                  accept="image/*"
                >
                  <el-button>上传头像</el-button>
                </el-upload>
              </div>
            </el-form-item>
            <el-form-item label="背景图">
              <div
                v-if="form.background_url"
                class="mb-2 overflow-hidden rounded-lg border border-slate-200 bg-slate-100"
                style="width: 100%; max-width: 320px; height: 120px"
              >
                <div
                  class="h-full w-full bg-cover bg-center"
                  :style="{ backgroundImage: `url(${form.background_url})` }"
                />
              </div>
              <div class="flex items-center gap-2">
                <el-upload
                  :show-file-list="false"
                  :http-request="(o: { file: File }) => uploadBackground(o.file)"
                  accept="image/*"
                >
                  <el-button>{{ form.background_url ? '更换背景图' : '上传背景图' }}</el-button>
                </el-upload>
                <el-button v-if="form.background_url" @click="form.background_url = ''">移除</el-button>
              </div>
              <p class="m-0 mt-1 text-xs text-slate-400">建议上传横向图片，将展示在个人主页顶部。</p>
            </el-form-item>
            <el-form-item label="简介">
              <el-input v-model="form.bio" type="textarea" :rows="3" />
            </el-form-item>
            <el-form-item label="性别">
              <el-radio-group v-model="form.gender">
                <el-radio
                  v-for="opt in genderOptions"
                  :key="opt.value"
                  :value="opt.value"
                >{{ opt.label }}</el-radio>
              </el-radio-group>
              <div class="text-xs text-slate-400">用于漂流瓶和实时匹配，未设置时按"不限"处理。</div>
            </el-form-item>
            <el-form-item label="生日">
              <el-date-picker
                v-model="form.birthday"
                type="date"
                placeholder="选择生日，系统会自动计算年龄"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                :disabled-date="(d: Date) => d > new Date() || d < new Date(new Date().getFullYear() - 100, 0, 1)"
                style="width: 100%; max-width: 280px"
              />
              <div class="mt-1 text-xs text-slate-400">
                设置生日后系统会自动计算年龄，用于漂流瓶和实时匹配。
                <span v-if="currentAge !== null" class="text-slate-600 font-medium">当前年龄：{{ currentAge }} 岁</span>
              </div>
            </el-form-item>
            <el-button type="primary" :loading="saving" @click="save">保存</el-button>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="外观" name="appearance">
          <h3 class="mb-3 text-base font-bold">主题模式</h3>
          <div class="theme-switch-card">
            <button
              class="theme-option"
              :class="{ 'is-active': themeStore.theme === 'light' }"
              type="button"
              @click="themeStore.apply('light')"
            >
              <span class="theme-icon" aria-hidden="true">☀️</span>
              <span class="theme-name">白天模式</span>
              <span class="theme-desc">明亮清爽</span>
              <span class="theme-check" aria-hidden="true">✓</span>
            </button>
            <button
              class="theme-option"
              :class="{ 'is-active': themeStore.theme === 'dark' }"
              type="button"
              @click="themeStore.apply('dark')"
            >
              <span class="theme-icon" aria-hidden="true">🌙</span>
              <span class="theme-name">暗色模式</span>
              <span class="theme-desc">夜间护眼</span>
              <span class="theme-check" aria-hidden="true">✓</span>
            </button>
          </div>
          <p class="theme-hint">主题选择会保存在本机，下次打开自动生效。</p>
        </el-tab-pane>
        <el-tab-pane label="账号安全" name="security">
          <h3 class="mb-3 text-base font-bold">修改密码</h3>
          <el-form
            ref="pwdFormRef"
            :model="pwdForm"
            :rules="pwdRules"
            label-position="top"
            style="max-width: 360px"
          >
            <el-form-item label="旧密码" prop="old_password">
              <el-input v-model="pwdForm.old_password" type="password" show-password />
            </el-form-item>
            <el-form-item label="新密码" prop="new_password">
              <el-input v-model="pwdForm.new_password" type="password" show-password />
              <div class="mt-1 text-xs text-slate-400">长度 {{ newPasswordLen }}/72，至少 8 位</div>
            </el-form-item>
            <el-form-item label="确认新密码" prop="confirm_password">
              <el-input v-model="pwdForm.confirm_password" type="password" show-password />
            </el-form-item>
            <el-button type="primary" :loading="changingPwd" @click="changePwd">提交修改</el-button>
            <p class="mt-3 text-xs text-slate-500">
              修改成功后其他设备的登录态将被撤销，本端也会退出登录。
            </p>
          </el-form>

          <el-divider />

          <h3 class="mb-3 text-base font-bold">QQ 号（账号找回）</h3>
          <el-form label-position="top" style="max-width: 360px">
            <el-form-item label="QQ 号">
              <el-input v-model="qqForm.qq" placeholder="选填，仅用于账号找回" maxlength="20" />
              <div class="mt-1 text-xs text-slate-400">
                不填写账号丢失将无法找回。可在设置中随时修改。
              </div>
            </el-form-item>
            <el-button type="primary" :loading="qqSaving" @click="saveQQ">保存 QQ 号</el-button>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="邀请码" name="invite">
          <div v-loading="inviteLoading">
            <!-- 已认证用户：展示邀请码 + 分享状态 -->
            <template v-if="session.isVerified() && inviteCodeInfo">
              <h3 class="mb-3 text-base font-bold">我的邀请码</h3>
              <div class="invite-code-card">
                <div class="text-center mb-3">
                  <div class="text-xs text-slate-500 mb-1">将此邀请码分享给同学，对方填入后即可解锁全部功能</div>
                  <div class="invite-code-display">{{ inviteCodeInfo.code }}</div>
                  <el-button
                    size="small"
                    type="primary"
                    plain
                    class="mt-2"
                    @click="copyInviteCode"
                  >复制邀请码</el-button>
                </div>
                <el-divider />
                <div class="invite-info-row">
                  <span class="invite-label">分享状态</span>
                  <el-tag
                    v-if="inviteCodeInfo.can_share"
                    type="success"
                    size="small"
                  >可分享</el-tag>
                  <el-tag
                    v-else-if="inviteCodeInfo.is_frozen"
                    type="danger"
                    size="small"
                  >已冻结</el-tag>
                  <el-tag v-else type="info" size="small">冷却中</el-tag>
                </div>
                <div v-if="!inviteCodeInfo.can_share" class="invite-info-row">
                  <span class="invite-label">{{ inviteCodeInfo.is_frozen ? '冻结剩余' : '冷却剩余' }}</span>
                  <span class="invite-value">
                    {{ formatSeconds(inviteCodeInfo.is_frozen ? inviteCodeInfo.frozen_remaining : inviteCodeInfo.cooldown_remaining) }}
                  </span>
                </div>
                <div v-if="inviteCodeInfo.is_frozen" class="invite-warning">
                  你的邀请资格已被冻结（被邀请人违规），冻结期内无法被他人邀请码验证。请遵守社区规范。
                </div>
              </div>

              <el-alert type="warning" :closable="false" show-icon class="mt-4">
                <template #title>邀请码连坐机制</template>
                <div class="text-xs mt-1">
                  每位用户每 3 天可分享 1 次邀请码。被邀请人若被核实非本校学生或违规，
                  你的邀请资格将被冻结 30 天。请勿将邀请码出售或分享给校外人员。
                </div>
              </el-alert>
            </template>

            <!-- 未认证用户：引导填写邀请码 -->
            <template v-else>
              <h3 class="mb-3 text-base font-bold">填写邀请码解锁全部功能</h3>
              <el-alert type="info" :closable="false" show-icon class="mb-4">
                <template #title>当前账号状态：未认证</template>
                <div class="text-sm mt-1">
                  你已注册成功，可以浏览帖子内容。但发帖 / 评论 / 随机匹配 / 漂流瓶 等功能需要填写邀请码解锁。
                </div>
              </el-alert>

              <div class="space-y-3 text-sm" style="max-width: 560px">
                <div class="p-3 bg-slate-50 rounded">
                  <div class="font-medium text-slate-700 mb-1">方式一：找已认证的同学</div>
                  <div class="text-slate-500">
                    请身边已认证的同学在他的「设置 → 邀请码」中查看邀请码并分享给你。
                    每位同学 3 天只能分享 1 次，请珍惜使用。
                  </div>
                </div>
                <div class="p-3 bg-slate-50 rounded">
                  <div class="font-medium text-slate-700 mb-1">方式二：添加管理员微信获取邀请码</div>
                  <div class="text-slate-500 mb-2">
                    添加管理员微信，说明身份后获取专属邀请码：
                  </div>
                  <div class="flex items-center gap-2">
                    <el-tag type="success" size="large">微信号：qhsqq2623655749</el-tag>
                    <el-button size="small" @click="copyAdminWechat">复制</el-button>
                  </div>
                </div>
              </div>

              <el-alert type="warning" :closable="false" show-icon class="mt-4">
                <template #title>邀请码连坐机制</template>
                <div class="text-xs mt-1">
                  邀请人需对被邀请人身份负责。若被邀请人被核实非本校学生，邀请人将
                  被冻结 30 天分享资格。请勿将邀请码出售或分享给校外人员。
                </div>
              </el-alert>
            </template>
          </div>
        </el-tab-pane>
        <el-tab-pane label="账号状态" name="ban">
          <div v-loading="banLoading">
            <h3 class="mb-3 text-base font-bold">账号封禁状态</h3>
            <div v-if="banStatus" class="ban-status-card" :class="{ banned: banStatus.is_banned }">
              <div class="ban-status-row">
                <span class="ban-label">当前状态</span>
                <el-tag
                  :type="banStatus.is_banned ? 'danger' : 'success'"
                  size="large"
                >
                  {{ banStatus.is_banned ? '已封禁' : '正常' }}
                </el-tag>
              </div>
              <template v-if="banStatus.is_banned">
                <div class="ban-status-row">
                  <span class="ban-label">封禁原因</span>
                  <span class="ban-value">{{ banStatus.ban_reason || '未填写' }}</span>
                </div>
                <div class="ban-status-row">
                  <span class="ban-label">封禁截止</span>
                  <span class="ban-value ban-until">{{ fmtBanUntil(banStatus.ban_until) }}</span>
                </div>
                <div class="ban-action-row">
                  <el-button type="primary" plain @click="openAppealDialog">提交申诉</el-button>
                  <span class="ban-tip">申诉后管理员会人工复查，请耐心等待</span>
                </div>
              </template>
              <div v-else class="ban-violation">
                <span class="ban-label">历史违规次数</span>
                <span class="ban-value">{{ banStatus.violation_count }} 次</span>
                <p v-if="banStatus.violation_count > 0" class="ban-warning">
                  累计违规 {{ banStatus.violation_count }} 次，请遵守社区规范，多次违规将导致封号。
                </p>
              </div>
            </div>

            <h3 class="mb-3 mt-6 text-base font-bold">我的申诉记录</h3>
            <el-table :data="myAppeals" border stripe style="width: 100%">
              <el-table-column prop="id" label="ID" width="80" />
              <el-table-column label="申诉理由" min-width="240">
                <template #default="{ row }">
                  <div class="appeal-reason">{{ row.reason }}</div>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="140">
                <template #default="{ row }">
                  <el-tag :type="appealStatusMeta[row.status]?.type || 'info'" size="small">
                    {{ appealStatusMeta[row.status]?.text || row.status }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="审核回复" min-width="200">
                <template #default="{ row }">
                  <span class="appeal-comment">{{ row.review_comment || '—' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="提交时间" width="160">
                <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
              </el-table-column>
              <el-table-column label="审核时间" width="160">
                <template #default="{ row }">{{ fmtTime(row.reviewed_at) }}</template>
              </el-table-column>
            </el-table>
            <p v-if="myAppeals.length === 0" class="mt-3 text-xs text-slate-400">暂无申诉记录</p>
          </div>
        </el-tab-pane>
        <el-tab-pane label="私信权限" name="messages">
          <h3 class="mb-2 text-base font-bold">谁可以给我发私信</h3>
          <p class="mb-4 text-xs text-slate-500">
            互相关注的用户始终可以给你发送私信，此设置仅对非互关用户生效。
          </p>
          <el-radio-group
            v-model="messagePerm"
            :disabled="permLoading"
            class="perm-radio-group"
            @change="changeMessagePerm"
          >
            <el-radio
              v-for="opt in permOptions"
              :key="opt.value"
              :value="opt.value"
              class="perm-radio-item"
            >
              <div class="perm-radio-body">
                <span class="perm-radio-label">{{ opt.label }}</span>
                <span class="perm-radio-desc">{{ opt.desc }}</span>
              </div>
            </el-radio>
          </el-radio-group>
          <p v-if="permLoading" class="mt-3 text-xs text-slate-400">保存中…</p>
        </el-tab-pane>
        <el-tab-pane label="通知设置" name="notifications">
          <p class="text-sm text-slate-600">通知设置功能尚未开放，敬请期待。</p>
        </el-tab-pane>
        <el-tab-pane label="我的公告" name="announcements">
          <div v-loading="announcementsLoading">
            <h3 class="mb-3 text-base font-bold">站点公告</h3>
            <p class="mb-4 text-xs text-slate-500">登录后未读公告会自动弹窗提示，已读的公告这里仍可查看。</p>
            <div v-if="myAnnouncements.length" class="announcement-list">
              <div
                v-for="item in myAnnouncements"
                :key="item.id"
                class="announcement-item"
                :class="{ 'is-unread': !item.is_read }"
              >
                <div class="announcement-head">
                  <span class="announcement-title">{{ item.title }}</span>
                  <el-tag v-if="!item.is_read" type="warning" size="small">未读</el-tag>
                  <el-tag v-else type="info" size="small">已读</el-tag>
                </div>
                <div class="announcement-content">{{ item.content }}</div>
                <div class="announcement-foot">
                  <span class="announcement-time">{{ fmtAnnouncementTime(item.created_at) }}</span>
                  <el-button
                    v-if="!item.is_read"
                    size="small"
                    type="primary"
                    plain
                    @click="markRead(item.id)"
                  >我知道了</el-button>
                </div>
              </div>
            </div>
            <p v-else class="text-xs text-slate-400">暂无公告</p>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 申诉对话框 -->
    <el-dialog v-model="appealDialogVisible" title="提交申诉" width="90%" style="max-width: 480px">
      <el-form label-position="top">
        <el-form-item label="申诉理由">
          <el-input
            v-model="appealForm.reason"
            type="textarea"
            :rows="5"
            maxlength="500"
            show-word-limit
            placeholder="请说明你认为应当解封的理由，管理员会人工复查"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="appealDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submittingAppeal" @click="submitAppeal">
          提交申诉
        </el-button>
      </template>
    </el-dialog>

  </main>
</template>

<style scoped>
/* 外观主题切换 */
.theme-switch-card {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  max-width: 420px;
}
.theme-option {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  padding: 18px 16px;
  border: 1.5px solid var(--bg-300);
  border-radius: 14px;
  background: var(--bg-50);
  cursor: pointer;
  text-align: left;
  transition: all 0.15s ease;
}
.theme-option:hover {
  border-color: var(--brand-300);
}
.theme-option.is-active {
  border-color: var(--brand-500);
  background: var(--brand-50);
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.12);
}
.theme-icon {
  font-size: 28px;
  line-height: 1;
}
.theme-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-800);
}
.theme-desc {
  font-size: 12px;
  color: var(--text-400);
}
.theme-check {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 20px;
  height: 20px;
  display: none;
  place-items: center;
  border-radius: 50%;
  background: var(--brand-500);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
}
.theme-option.is-active .theme-check {
  display: grid;
}
.theme-hint {
  margin-top: 12px;
  font-size: 12px;
  color: var(--text-400);
}
/* 设置页 Tab */
.settings-tabs :deep(.el-tabs__header) {
  margin: 0 0 16px;
}
.settings-tabs :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
}
.settings-tabs :deep(.el-tabs__item) {
  font-size: 14px;
  font-weight: 600;
  padding: 0 16px;
}
.settings-tabs :deep(.el-tabs__active-bar) {
  background-color: var(--brand-500, #007aff);
}
.settings-tabs :deep(.el-tabs__item.is-active) {
  color: var(--brand-500, #007aff);
}
.settings-tabs :deep(.el-tabs__item:hover) {
  color: var(--brand-500, #007aff);
}

/* 私信权限单选组 */
.perm-radio-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 480px;
}
.perm-radio-item {
  display: flex;
  align-items: flex-start;
  height: auto !important;
  padding: 12px 14px !important;
  margin-right: 0 !important;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  transition: border-color 0.15s, background 0.15s;
}
.perm-radio-item.is-checked {
  border-color: var(--el-color-primary, #007aff);
  background: rgba(0, 122, 255, 0.04);
}
.perm-radio-item :deep(.el-radio__label) {
  padding-left: 8px;
  width: 100%;
}
.perm-radio-body {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.perm-radio-label {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
}
.perm-radio-desc {
  font-size: 12px;
  color: #6b7280;
  line-height: 1.5;
}

/* 账号状态卡片 */
.ban-status-card {
  padding: 16px 18px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  max-width: 560px;
}
.ban-status-card.banned {
  border-color: #fecaca;
  background: #fef2f2;
}
.ban-status-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  font-size: 14px;
}
.ban-label {
  min-width: 96px;
  color: #6b7280;
  font-weight: 500;
}
.ban-value {
  color: #1f2937;
  flex: 1;
  word-break: break-all;
}
.ban-until {
  color: #dc2626;
  font-weight: 600;
}
.ban-action-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 0 4px;
}
.ban-tip {
  font-size: 12px;
  color: #6b7280;
}
.ban-violation {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  font-size: 14px;
}
.ban-warning {
  margin: 8px 0 0;
  font-size: 12px;
  color: #d97706;
}
.appeal-reason {
  font-size: 13px;
  color: #1f2937;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 96px;
  overflow: auto;
}
.appeal-comment {
  font-size: 12px;
  color: #6b7280;
  white-space: pre-wrap;
  word-break: break-all;
}

/* 公告列表 */
.announcement-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 560px;
}
.announcement-item {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  padding: 14px 16px;
}
.announcement-item.is-unread {
  border-color: #fbbf24;
  background: #fffbeb;
}
.announcement-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.announcement-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
  flex: 1;
  word-break: break-all;
}
.announcement-content {
  font-size: 13px;
  color: #374151;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  margin-bottom: 8px;
}
.announcement-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.announcement-time {
  font-size: 12px;
  color: #9ca3af;
}

/* 邀请码卡片 */
.invite-code-card {
  padding: 18px 20px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  max-width: 560px;
}
.invite-code-display {
  font-size: 28px;
  font-weight: 800;
  font-family: 'Courier New', 'Menlo', monospace;
  letter-spacing: 4px;
  color: var(--brand-500, #007aff);
  padding: 10px 0;
  user-select: all;
}
.invite-info-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 0;
  font-size: 14px;
}
.invite-label {
  min-width: 96px;
  color: #6b7280;
  font-weight: 500;
}
.invite-value {
  color: #1f2937;
  flex: 1;
}
.invite-warning {
  margin-top: 8px;
  padding: 10px 12px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 6px;
  font-size: 12px;
  color: #dc2626;
  line-height: 1.6;
}
</style>
