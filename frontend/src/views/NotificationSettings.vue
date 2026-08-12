<script setup lang="ts">
/**
 * 消息通知中心设置
 * - 网页版：提示下载手机端 App 后才能接收推送通知
 * - App 内（LYCommunityApp WebView）：完整的通知偏好开关，保存到后端并同步给原生通知服务
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { Icon, Switch } from '../components/native'
import { toast } from '../components/native/Toast'
import {
  fetchNotificationSettings,
  updateNotificationSettings,
  type NotificationSettings,
} from '../api/notification'
import { isAppEnv } from '../utils/platform'
import { useNotificationStore } from '../stores/notification'

const router = useRouter()
const notificationStore = useNotificationStore()

const loading = ref(false)
const saving = ref(false)
const loaded = ref(false)

const form = reactive<NotificationSettings>({
  like: true,
  comment: true,
  mention: true,
  follow: true,
  system: true,
  dm: true,
})

/** 原生 App 桥接（MainActivity 注入的 LYCommunityApp） */
interface LYBridge {
  setNotificationPrefs?: (json: string) => void
  getNotificationPrefs?: () => string
  openNotifications?: () => void
  requestNotificationPermission?: () => void
}

function bridge(): LYBridge {
  return (window as unknown as { LYCommunityApp?: LYBridge }).LYCommunityApp || {}
}

const items = computed(() => [
  {
    key: 'like' as const,
    icon: 'heart',
    color: '#ff3b30',
    title: '点赞',
    desc: '有人点赞了你的作品或评论',
  },
  {
    key: 'comment' as const,
    icon: 'message-circle',
    color: '#007aff',
    title: '评论',
    desc: '有人评论了你的作品',
  },
  {
    key: 'mention' as const,
    icon: 'at',
    color: '#ff9500',
    title: '@我的',
    desc: '有人在作品或评论中提到了你',
  },
  {
    key: 'follow' as const,
    icon: 'user-plus',
    color: '#34c759',
    title: '新增粉丝',
    desc: '有新用户关注了你',
  },
  {
    key: 'dm' as const,
    icon: 'message-square',
    color: '#af52de',
    title: '私信',
    desc: '收到新的私信消息',
  },
  {
    key: 'system' as const,
    icon: 'bell',
    color: '#5856d6',
    title: '系统通知',
    desc: '审核结果、勋章奖励、封禁提醒等',
  },
])

async function loadSettings() {
  if (loading.value) return
  loading.value = true
  try {
    const { data } = await fetchNotificationSettings()
    const s = data.data
    // App 内：若原生端已保存过偏好（更早设置过），以原生为准并同步到云端，
    // 避免"设备端关掉了某项、云端还是默认全开"导致设置不一致。
    const b = bridge()
    if (isAppEnv() && b.getNotificationPrefs) {
      try {
        const native = JSON.parse(b.getNotificationPrefs() || '{}') as Partial<NotificationSettings>
        const nativeDirty = (Object.keys(native) as (keyof NotificationSettings)[])
          .some((k) => typeof native[k] === 'boolean' && native[k] !== s[k])
        if (nativeDirty) {
          const merged = { ...s }
          for (const k of Object.keys(native) as (keyof NotificationSettings)[]) {
            if (typeof native[k] === 'boolean') merged[k] = native[k] as boolean
          }
          await updateNotificationSettings(merged)
          Object.assign(s, merged)
        }
      } catch {
        /* 原生桥异常时以云端为准 */
      }
    }
    form.like = s.like
    form.comment = s.comment
    form.mention = s.mention
    form.follow = s.follow
    form.system = s.system
    form.dm = s.dm
    loaded.value = true
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    loading.value = false
  }
}

/** 开关变更：保存到后端 + 同步原生通知服务 */
async function onChange(key: keyof NotificationSettings, value: boolean) {
  saving.value = true
  try {
    await updateNotificationSettings({ [key]: value })
    if (isAppEnv() && bridge().setNotificationPrefs) {
      try {
        bridge().setNotificationPrefs!(JSON.stringify({ ...form }))
      } catch {
        /* 原生桥接异常不影响网页端保存 */
      }
    }
    toast.success('设置已保存')
  } catch (err) {
    form[key] = !value
    toast.error((err as Error).message)
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  // 偏好统一在 loadSettings 中处理：App 内会以原生已保存值为准并同步云端
  await loadSettings()
  // App 内请求系统通知权限（Android 13+ 会弹系统授权框），授权后原生推送服务才会启动
  const b = bridge()
  if (isAppEnv() && b.requestNotificationPermission) {
    try {
      b.requestNotificationPermission()
    } catch {
      /* 忽略 */
    }
  }
  notificationStore.refreshUnread()
})

function goBack() {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/settings')
  }
}

function downloadApp() {
  window.location.href = '/api/app-download'
}
</script>

<template>
  <main class="page-notif-settings">
    <!-- 顶栏 -->
    <div class="ns-topbar">
      <button class="icon-btn" type="button" aria-label="返回" @click="goBack">
        <Icon name="arrow-left" :size="20" />
      </button>
      <span class="ns-title">消息通知中心</span>
      <span class="icon-btn-placeholder" />
    </div>

    <template v-if="isAppEnv()">
      <!-- 状态卡 -->
      <div class="ns-status-card">
        <div class="ns-status-icon">
          <Icon name="bell" :size="22" color="#fff" />
        </div>
        <div class="ns-status-body">
          <strong>推送通知已开启</strong>
          <p>收到新消息时，App 会像抖音、快手一样弹出通知提醒你</p>
        </div>
      </div>

      <!-- 通知开关列表 -->
      <div class="ns-card">
        <div class="ns-card-title">消息提醒</div>
        <div
          v-for="(item, idx) in items"
          :key="item.key"
          class="ns-row"
          :class="{ 'no-border': idx === items.length - 1 }"
        >
          <span class="ns-row-icon" :style="{ background: item.color }">
            <Icon :name="item.icon" :size="15" color="#fff" />
          </span>
          <div class="ns-row-body">
            <span class="ns-row-title">{{ item.title }}</span>
            <span class="ns-row-desc">{{ item.desc }}</span>
          </div>
          <Switch
            :model-value="form[item.key]"
            :disabled="saving || !loaded"
            @update:model-value="onChange(item.key, $event)"
          />
        </div>
      </div>

      <!-- 通知记录入口 -->
      <div class="ns-card">
        <button class="ns-row ns-row--action" type="button" @click="router.push('/notifications')">
          <span class="ns-row-icon" style="background: #007aff">
            <Icon name="list" :size="15" color="#fff" />
          </span>
          <div class="ns-row-body">
            <span class="ns-row-title">查看消息记录</span>
            <span class="ns-row-desc">点赞、评论、粉丝、私信等历史消息</span>
          </div>
          <span v-if="notificationStore.unreadCount > 0" class="ns-unread-badge">
            {{ notificationStore.unreadCount > 99 ? '99+' : notificationStore.unreadCount }}
          </span>
          <Icon name="chevron-right" :size="16" color="#c7c7cc" />
        </button>
      </div>

      <p class="ns-footnote">设置会自动同步到云端，换设备登录后依然生效。</p>
    </template>

    <!-- 网页版：提示下载手机端 -->
    <template v-else>
      <div class="ns-web-card">
        <div class="ns-web-icon">
          <Icon name="phone" :size="36" color="#007aff" />
        </div>
        <h3>推送通知仅支持手机端</h3>
        <p>
          点赞、评论、新增粉丝、私信等消息提醒需要安装「立洋社区」手机端 App
          才能在锁屏或后台收到通知。
        </p>
        <button class="ns-download-btn" type="button" @click="downloadApp">
          <Icon name="arrow-down" :size="16" color="#fff" />
          下载手机端 App
        </button>
        <p class="ns-web-tip">安装后登录同一账号，即可在 App 内设置各类通知提醒。</p>
      </div>

      <!-- 网页端也能预览通知偏好（只读提示） -->
      <div class="ns-card">
        <div class="ns-card-title">可管理哪些提醒</div>
        <div v-for="item in items" :key="item.key" class="ns-row no-border">
          <span class="ns-row-icon" :style="{ background: item.color }">
            <Icon :name="item.icon" :size="15" color="#fff" />
          </span>
          <div class="ns-row-body">
            <span class="ns-row-title">{{ item.title }}</span>
            <span class="ns-row-desc">{{ item.desc }}</span>
          </div>
          <span class="ns-web-check">
            <Icon name="check" :size="12" color="#34c759" />
          </span>
        </div>
      </div>
    </template>
  </main>
</template>

<style scoped>
.page-notif-settings {
  min-height: 100vh;
  background: var(--bg-100, #f2f2f7);
  padding-bottom: 32px;
}

.ns-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 48px;
  padding: 0 12px;
  background: var(--bg-50, #fff);
  border-bottom: 1px solid var(--bg-300, #e5e5ea);
  position: sticky;
  top: 0;
  z-index: 10;
}

.icon-btn {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: transparent;
  border: none;
  color: var(--text-900, #1c1c1e);
}

.icon-btn-placeholder {
  width: 36px;
}

.ns-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-900, #1c1c1e);
}

.ns-status-card {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 16px 14px 12px;
  padding: 14px;
  border-radius: 14px;
  background: linear-gradient(135deg, #0a84ff, #007aff);
  color: #fff;
  box-shadow: 0 6px 18px -8px rgba(0, 122, 255, 0.55);
}

.ns-status-icon {
  flex: none;
  width: 42px;
  height: 42px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.22);
  display: grid;
  place-items: center;
}

.ns-status-body strong {
  font-size: 15px;
  display: block;
}

.ns-status-body p {
  margin: 3px 0 0;
  font-size: 12px;
  opacity: 0.9;
  line-height: 1.45;
}

.ns-card {
  margin: 12px 14px;
  background: var(--bg-50, #fff);
  border-radius: 14px;
  padding: 6px 14px;
  box-shadow: var(--shadow-sm, 0 1px 3px rgba(0, 0, 0, 0.06));
}

.ns-card-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-500, #8e8e93);
  padding: 10px 0 2px;
}

.ns-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 12px 0;
  border: none;
  border-bottom: 0.5px solid var(--bg-300, #e5e5ea);
  background: transparent;
  color: inherit;
  text-align: left;
}

.ns-row.no-border {
  border-bottom: none;
}

.ns-row--action {
  cursor: pointer;
}

.ns-row--action:active {
  opacity: 0.7;
}

.ns-row-icon {
  flex: none;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  display: grid;
  place-items: center;
}

.ns-row-body {
  flex: 1;
  min-width: 0;
}

.ns-row-title {
  display: block;
  font-size: 15px;
  color: var(--text-900, #1c1c1e);
}

.ns-row-desc {
  display: block;
  font-size: 12px;
  color: var(--text-500, #8e8e93);
  margin-top: 1px;
}

.ns-unread-badge {
  flex: none;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: #ff3b30;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  display: grid;
  place-items: center;
}

.ns-footnote {
  margin: 4px 18px;
  font-size: 12px;
  color: var(--text-500, #8e8e93);
  text-align: center;
}

.ns-web-card {
  margin: 24px 18px;
  padding: 32px 22px;
  background: var(--bg-50, #fff);
  border-radius: 18px;
  text-align: center;
  box-shadow: var(--shadow-md, 0 6px 20px -10px rgba(0, 0, 0, 0.14));
}

.ns-web-icon {
  width: 72px;
  height: 72px;
  margin: 0 auto 14px;
  border-radius: 22px;
  background: #eaf4ff;
  display: grid;
  place-items: center;
}

.ns-web-card h3 {
  margin: 0 0 8px;
  font-size: 17px;
  color: var(--text-900, #1c1c1e);
}

.ns-web-card p {
  margin: 0 0 18px;
  font-size: 13px;
  line-height: 1.65;
  color: var(--text-500, #8e8e93);
}

.ns-download-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 11px 26px;
  border: none;
  border-radius: 24px;
  background: #007aff;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 8px 20px -8px rgba(0, 122, 255, 0.6);
}

.ns-download-btn:active {
  transform: scale(0.98);
}

.ns-web-tip {
  margin: 16px 0 0 !important;
  font-size: 12px !important;
}

.ns-web-check {
  flex: none;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #e8f9ee;
  display: grid;
  place-items: center;
}
</style>
