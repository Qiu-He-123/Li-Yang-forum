<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { adminGetUser, adminListSettings, adminUpdateSettings, type AdminUserBrief } from '../../api/admin'

const loading = ref(false)

// ============ 首页滚动字幕 ============
const marqueeText = ref('')
const marqueeSaving = ref(false)

// ============ 默认好友（可多人） ============
const friendIds = ref<number[]>([])
const friendOptions = ref<AdminUserBrief[]>([])
const friendSaving = ref(false)
let querySeq = 0
let resolveTimer: ReturnType<typeof setTimeout> | null = null

function parseIds(raw: string): number[] {
  const ids: number[] = []
  for (const part of raw.split(/[,，\n\r\s]+/)) {
    const id = Number(part.trim())
    if (Number.isInteger(id) && id > 0 && !ids.includes(id)) ids.push(id)
  }
  return ids
}

/** 解析用户 ID → 用户简要信息，用于下拉框展示用户名 */
async function resolveFriends(ids: number[]) {
  const seq = ++querySeq
  const infos: AdminUserBrief[] = []
  for (const id of ids) {
    try {
      const { data } = await adminGetUser(id)
      if (seq !== querySeq) return
      infos.push(data.data)
    } catch {
      if (seq !== querySeq) return
      ElMessage.error(`用户 #${id} 不存在或已删除，已从列表移除`)
      friendIds.value = friendIds.value.filter((x) => x !== id)
    }
  }
  if (seq !== querySeq) return
  friendOptions.value = infos
}

watch(
  friendIds,
  (ids) => {
    if (resolveTimer) clearTimeout(resolveTimer)
    resolveTimer = setTimeout(() => {
      resolveFriends(ids)
    }, 400)
  },
)

onMounted(async () => {
  loading.value = true
  try {
    const { data } = await adminListSettings()
    const list = data.data ?? []
    marqueeText.value = list.find((s) => s.key === 'home_marquee')?.value ?? ''
    const raw = list.find((s) => s.key === 'default_friend_user_ids')?.value ?? ''
    friendIds.value = parseIds(raw)
    await resolveFriends(friendIds.value)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
})

async function saveMarquee() {
  marqueeSaving.value = true
  try {
    await adminUpdateSettings({ home_marquee: marqueeText.value.trim() })
    ElMessage.success('滚动字幕已保存')
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    marqueeSaving.value = false
  }
}

async function saveFriends() {
  friendSaving.value = true
  try {
    await adminUpdateSettings({ default_friend_user_ids: friendIds.value.join(',') })
    ElMessage.success('默认好友已保存')
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    friendSaving.value = false
  }
}
</script>

<template>
  <div class="p-4">
    <div v-loading="loading" class="space-y-4">
      <!-- ====== 首页滚动字幕 ====== -->
      <div class="rounded border border-ly-line bg-white p-4">
        <h3 class="m-0 mb-1 text-base font-bold">首页滚动字幕</h3>
        <p class="mt-1 mb-3 text-sm text-slate-500">
          配置后显示在首页顶部的公告条中，每行一条、循环滚动；留空则关闭不显示。
        </p>
        <el-input
          v-model="marqueeText"
          type="textarea"
          :rows="3"
          placeholder="每行一条，例如：&#10;欢迎来到立洋校园社区！&#10;社区公约：友善发言、拒绝网暴"
        />
        <div class="mt-3">
          <el-button type="primary" :loading="marqueeSaving" @click="saveMarquee">保存</el-button>
        </div>
      </div>

      <!-- ====== 默认好友（多人） ====== -->
      <div class="rounded border border-ly-line bg-white p-4">
        <h3 class="m-0 mb-1 text-base font-bold">默认好友（可多人）</h3>
        <p class="mt-1 mb-3 text-sm text-slate-500">
          配置后，所有用户默认与这些用户互相关注、无法取消关注，并置顶显示在消息-好友/会话列表。
          输入用户 ID 回车即可添加多个；留空表示关闭。
        </p>
        <el-select
          v-model="friendIds"
          multiple
          filterable
          allow-create
          default-first-option
          :reserve-keyword="false"
          placeholder="输入用户 ID 后回车添加，可添加多人"
          style="width: 100%; max-width: 480px"
        >
          <el-option
            v-for="u in friendOptions"
            :key="u.id"
            :value="u.id"
            :label="`#${u.id} ${u.nickname}${u.username ? '（' + u.username + '）' : ''}${u.school ? ' · ' + u.school : ''}`"
          />
        </el-select>
        <div class="mt-3">
          <el-button type="primary" :loading="friendSaving" @click="saveFriends">保存</el-button>
        </div>
      </div>
    </div>
  </div>
</template>
