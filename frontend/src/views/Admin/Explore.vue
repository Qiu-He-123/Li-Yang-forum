<script setup lang="ts">
/**
 * 推荐探索（Explore-Exploit）配置与效果看板
 *
 * 大厂风格推荐闭环：
 * - 热门流每页按 ε 比例插入「探索池」冷启动内容（低互动新帖随机曝光）
 * - Thompson / 加权 / 均匀随机三种采样算法可切换
 * - MMR 类别多样性：防止热门页被单一圈子刷屏
 * - 曝光 → 点击 → 点赞/评论 全链路埋点，实时查看 CTR 与互动率
 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  adminExploreStats,
  adminListSettings,
  adminUpdateSettings,
  type ExploreStats,
} from '../../api/admin'

const loading = ref(false)
const saving = ref(false)
const stats = ref<ExploreStats | null>(null)

// ============ 配置项 ============
const config = ref({
  feed_explore_enabled: true,
  feed_explore_rate: 0.15,
  feed_explore_hours: 48,
  feed_explore_max_likes: 10,
  feed_explore_mode: 'thompson',
  feed_mmr_enabled: true,
  feed_mmr_max_per_category: 6,
  comment_explore_enabled: true,
  comment_explore_rate: 0.15,
})

const modeOptions = [
  { label: 'Thompson 采样（推荐）', value: 'thompson', hint: 'Beta 分布建模帖子质量：曝光无互动自动降温，互动好自动升权' },
  { label: '加权随机', value: 'weighted', hint: '越新、点赞越少的帖子权重越高，更容易被抽中' },
  { label: '均匀随机', value: 'uniform', hint: '探索池内完全随机，最朴素' },
]

async function load() {
  loading.value = true
  try {
    const [cfgResp, statsResp] = await Promise.all([adminListSettings(), adminExploreStats()])
    const list = cfgResp.data.data ?? []
    const get = (key: string, fallback: string) => list.find((s) => s.key === key)?.value ?? fallback
    config.value = {
      feed_explore_enabled: get('feed_explore_enabled', 'true') !== 'false',
      feed_explore_rate: Number(get('feed_explore_rate', '0.15')) || 0.15,
      feed_explore_hours: Number(get('feed_explore_hours', '48')) || 48,
      feed_explore_max_likes: Number(get('feed_explore_max_likes', '10')) || 10,
      feed_explore_mode: get('feed_explore_mode', 'thompson'),
      feed_mmr_enabled: get('feed_mmr_enabled', 'true') !== 'false',
      feed_mmr_max_per_category: Number(get('feed_mmr_max_per_category', '6')) || 6,
      comment_explore_enabled: get('comment_explore_enabled', 'true') !== 'false',
      comment_explore_rate: Number(get('comment_explore_rate', '0.15')) || 0.15,
    }
    stats.value = statsResp.data.data
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    await adminUpdateSettings({
      feed_explore_enabled: config.value.feed_explore_enabled ? 'true' : 'false',
      feed_explore_rate: String(Math.min(0.5, Math.max(0, config.value.feed_explore_rate))),
      feed_explore_hours: String(Math.max(1, Math.floor(config.value.feed_explore_hours))),
      feed_explore_max_likes: String(Math.max(0, Math.floor(config.value.feed_explore_max_likes))),
      feed_explore_mode: config.value.feed_explore_mode,
      feed_mmr_enabled: config.value.feed_mmr_enabled ? 'true' : 'false',
      feed_mmr_max_per_category: String(Math.max(1, Math.floor(config.value.feed_mmr_max_per_category))),
      comment_explore_enabled: config.value.comment_explore_enabled ? 'true' : 'false',
      comment_explore_rate: String(Math.min(0.5, Math.max(0, config.value.comment_explore_rate))),
    })
    ElMessage.success('已保存，探索策略即时生效')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    saving.value = false
  }
}

function pct(v: number | undefined): string {
  if (v == null) return '-'
  return (v * 100).toFixed(1) + '%'
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="p-4">
    <!-- 配置区 -->
    <div class="mb-4 rounded border border-ly-line bg-white p-4">
      <h3 class="m-0 mb-1 text-base font-bold">探索推荐配置（Explore-Exploit）</h3>
      <p class="mt-1 mb-4 text-sm text-slate-500">
        热门页每页按 ε 比例插入「探索池」冷启动帖子（低互动 + 新鲜 + 已过审），
        打破热门霸榜的马太效应。探索曝光会记录点击 / 点赞 / 评论反馈，Thompson 模式会自动调节下次曝光概率。
      </p>

      <div class="grid max-w-3xl gap-4 sm:grid-cols-2">
        <div class="flex items-center justify-between rounded border border-ly-line px-3 py-2">
          <div>
            <div class="text-sm font-medium">帖子探索开关</div>
            <div class="text-xs text-slate-400">关闭后热门页回归纯热门排序</div>
          </div>
          <el-switch v-model="config.feed_explore_enabled" />
        </div>

        <div class="flex items-center justify-between rounded border border-ly-line px-3 py-2">
          <div>
            <div class="text-sm font-medium">帖子探索比例 ε</div>
            <div class="text-xs text-slate-400">每页约 ε×20 条给冷启动内容（0-0.5，建议 0.15）</div>
          </div>
          <el-input-number v-model="config.feed_explore_rate" :min="0" :max="0.5" :step="0.05" :precision="2" size="small" />
        </div>

        <div class="flex items-center justify-between rounded border border-ly-line px-3 py-2">
          <div>
            <div class="text-sm font-medium">探索窗口（小时）</div>
            <div class="text-xs text-slate-400">只探索最近 N 小时内发布的帖子</div>
          </div>
          <el-input-number v-model="config.feed_explore_hours" :min="1" :max="720" :step="6" size="small" />
        </div>

        <div class="flex items-center justify-between rounded border border-ly-line px-3 py-2">
          <div>
            <div class="text-sm font-medium">冷启动点赞上限</div>
            <div class="text-xs text-slate-400">点赞数超过该值的帖子不再进入探索池</div>
          </div>
          <el-input-number v-model="config.feed_explore_max_likes" :min="0" :max="1000" size="small" />
        </div>

        <div class="flex items-center justify-between rounded border border-ly-line px-3 py-2">
          <div>
            <div class="text-sm font-medium">采样算法</div>
            <div class="text-xs text-slate-400">{{ modeOptions.find((m) => m.value === config.feed_explore_mode)?.hint }}</div>
          </div>
          <el-select v-model="config.feed_explore_mode" size="small" class="w-44">
            <el-option v-for="m in modeOptions" :key="m.value" :label="m.label" :value="m.value" />
          </el-select>
        </div>

        <div class="flex items-center justify-between rounded border border-ly-line px-3 py-2">
          <div>
            <div class="text-sm font-medium">MMR 类别多样性</div>
            <div class="text-xs text-slate-400">同圈子内容超上限时自动穿插其他圈子</div>
          </div>
          <div class="flex items-center gap-2">
            <el-input-number v-model="config.feed_mmr_max_per_category" :min="1" :max="20" size="small" :disabled="!config.feed_mmr_enabled" />
            <el-switch v-model="config.feed_mmr_enabled" />
          </div>
        </div>

        <div class="flex items-center justify-between rounded border border-ly-line px-3 py-2">
          <div>
            <div class="text-sm font-medium">评论探索开关</div>
            <div class="text-xs text-slate-400">帖子「最热」评论页插入低赞新评论</div>
          </div>
          <el-switch v-model="config.comment_explore_enabled" />
        </div>

        <div class="flex items-center justify-between rounded border border-ly-line px-3 py-2">
          <div>
            <div class="text-sm font-medium">评论探索比例 ε</div>
            <div class="text-xs text-slate-400">0-0.5，建议 0.15</div>
          </div>
          <el-input-number v-model="config.comment_explore_rate" :min="0" :max="0.5" :step="0.05" :precision="2" size="small" />
        </div>
      </div>

      <div class="mt-4">
        <el-button type="primary" :loading="saving" @click="save">保存配置</el-button>
      </div>
    </div>

    <!-- 效果统计区 -->
    <div class="mb-4 rounded border border-ly-line bg-white p-4">
      <h3 class="m-0 mb-1 text-base font-bold">探索效果统计</h3>
      <p class="mt-1 mb-4 text-sm text-slate-500">
        探索曝光 → 点击进入详情 → 点赞/评论 的全链路数据。CTR 与互动率越高，说明探索池内容质量越好。
      </p>
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div class="rounded border border-ly-line p-3">
          <div class="text-xs text-slate-400">探索曝光</div>
          <div class="mt-1 text-2xl font-bold">{{ stats?.summary.impressions ?? 0 }}</div>
        </div>
        <div class="rounded border border-ly-line p-3">
          <div class="text-xs text-slate-400">点击进详情</div>
          <div class="mt-1 text-2xl font-bold">{{ stats?.summary.click_count ?? 0 }}</div>
        </div>
        <div class="rounded border border-ly-line p-3">
          <div class="text-xs text-slate-400">CTR（点击率）</div>
          <div class="mt-1 text-2xl font-bold">{{ pct(stats?.summary.ctr) }}</div>
        </div>
        <div class="rounded border border-ly-line p-3">
          <div class="text-xs text-slate-400">互动（赞+评）</div>
          <div class="mt-1 text-2xl font-bold">{{ stats?.summary.interaction_count ?? 0 }}</div>
          <div class="text-xs text-slate-400">互动率 {{ pct(stats?.summary.interaction_rate) }}</div>
        </div>
      </div>
    </div>

    <!-- Top 探索帖 -->
    <div class="mb-4 rounded border border-ly-line bg-white p-4">
      <h3 class="m-0 mb-3 text-base font-bold">Top 探索帖（按曝光量）</h3>
      <el-table :data="stats?.top_posts ?? []" size="small" stripe>
        <el-table-column prop="post_id" label="帖子 ID" width="90" />
        <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
        <el-table-column prop="category" label="圈子" width="110" />
        <el-table-column prop="impressions" label="曝光" width="90" />
        <el-table-column prop="click_count" label="点击" width="80" />
        <el-table-column label="CTR" width="90">
          <template #default="{ row }">{{ pct(row.ctr) }}</template>
        </el-table-column>
        <el-table-column prop="like_count" label="获赞" width="80" />
        <el-table-column prop="comment_count" label="获评" width="80" />
      </el-table>
      <div v-if="!stats?.top_posts?.length" class="py-6 text-center text-sm text-slate-400">
        暂无探索数据，开启探索后用户刷新热门页即开始积累
      </div>
    </div>

    <!-- 最近曝光日志 -->
    <div class="rounded border border-ly-line bg-white p-4">
      <h3 class="m-0 mb-3 text-base font-bold">最近探索曝光日志</h3>
      <el-table :data="stats?.recent_logs ?? []" size="small" stripe>
        <el-table-column prop="id" label="日志 ID" width="80" />
        <el-table-column prop="created_at" label="时间" width="170" />
        <el-table-column prop="post_id" label="帖子 ID" width="90" />
        <el-table-column label="场景目标" width="90">
          <template #default="{ row }">
            <span v-if="row.target_id">评论 #{{ row.target_id }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="帖子标题" min-width="180" show-overflow-tooltip />
        <el-table-column label="曝光对象" width="120">
          <template #default="{ row }">{{ row.nickname || (row.user_id ? `#${row.user_id}` : '匿名') }}</template>
        </el-table-column>
        <el-table-column label="场景" width="100">
          <template #default="{ row }">
            <el-tag :type="row.scene === 'post_feed' ? 'primary' : 'success'" size="small">
              {{ row.scene === 'post_feed' ? '帖子热门流' : '评论最热' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="page" label="页码" width="70" />
      </el-table>
    </div>
  </div>
</template>
