<script setup lang="ts">
/**
 * 后台 - 全局推送管理
 * 管理员可控制每个通知类型：
 * - 红点开关（show_badge）：该类型未读是否计入 App / 网页红点
 * - 推送开关（notify_enabled）：是否允许向用户弹出推送通知（App 端）
 * 默认全开，保存后即时生效，无需重启。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  adminGetPushSettings,
  adminUpdatePushSettings,
  type AdminPushTypeConfig,
} from '../../api/admin'

const loading = ref(false)
const saving = ref(false)
const items = ref<Record<string, AdminPushTypeConfig>>({})

const rows = computed(() => Object.entries(items.value))

async function load() {
  if (loading.value) return
  loading.value = true
  try {
    const { data } = await adminGetPushSettings()
    items.value = data.data?.items || {}
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function toggle(ntype: string, key: 'show_badge' | 'notify_enabled', val: boolean) {
  saving.value = true
  try {
    await adminUpdatePushSettings({ [ntype]: { [key]: val } })
    if (items.value[ntype]) items.value[ntype][key] = val
    ElMessage.success('已保存')
  } catch (error) {
    // 还原
    if (items.value[ntype]) items.value[ntype][key] = !val
    ElMessage.error((error as Error).message)
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="push-manage">
    <div class="pm-header">
      <h2>全局推送管理</h2>
      <p>管理员控制每个通知类型是否计入红点、是否允许推送。关闭后对所有用户即时生效；用户仍可自行决定是否接收（登录端「消息通知中心」）。</p>
    </div>

    <el-card class="pm-card" v-loading="loading">
      <el-empty v-if="!rows.length && !loading" description="暂无可配置的通知类型" />
      <div v-else class="pm-list">
        <div v-for="[ntype, cfg] in rows" :key="ntype" class="pm-row">
          <div class="pm-info">
            <span class="pm-type">{{ cfg.label }}</span>
            <span class="pm-desc">{{ cfg.desc }}</span>
            <span class="pm-code">{{ ntype }}</span>
          </div>
          <div class="pm-switches">
            <div class="pm-switch-item">
              <span class="pm-switch-label">红点</span>
              <el-switch
                :model-value="cfg.show_badge"
                :disabled="saving"
                @update:model-value="(v: boolean) => toggle(ntype, 'show_badge', v)"
              />
            </div>
            <div class="pm-switch-item">
              <span class="pm-switch-label">推送</span>
              <el-switch
                :model-value="cfg.notify_enabled"
                :disabled="saving"
                @update:model-value="(v: boolean) => toggle(ntype, 'notify_enabled', v)"
              />
            </div>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.push-manage {
  padding: 16px;
}

.pm-header h2 {
  margin: 0 0 6px;
  font-size: 18px;
}

.pm-header p {
  margin: 0 0 14px;
  font-size: 13px;
  color: #666;
}

.pm-list {
  display: flex;
  flex-direction: column;
}

.pm-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 4px;
  border-bottom: 1px solid #f0f0f0;
}

.pm-row:last-child {
  border-bottom: none;
}

.pm-info {
  display: flex;
  flex-direction: column;
  line-height: 1.4;
}

.pm-type {
  font-size: 15px;
  font-weight: 600;
  color: #1f1f1f;
}

.pm-desc {
  font-size: 12px;
  color: #888;
}

.pm-code {
  font-size: 11px;
  color: #b0b0b0;
  margin-top: 2px;
}

.pm-switches {
  display: flex;
  align-items: center;
  gap: 18px;
  flex: none;
}

.pm-switch-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.pm-switch-label {
  font-size: 13px;
  color: #444;
}
</style>