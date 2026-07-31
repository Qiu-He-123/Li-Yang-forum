<script setup lang="ts">
/**
 * 数据看板（大厂风格）
 *
 * 参考：Ant Design Pro / 腾讯内部仪表盘
 * - 顶部 4 张核心指标卡（带今日新增）
 * - 中部 7 天趋势折线图（SVG 实现）+ 圈子分布柱状图
 * - 待办事项卡 + 举报状态分布
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'

import { adminStats, type AdminStats } from '../../api/admin'

const router = useRouter()
const stats = ref<AdminStats | null>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const { data } = await adminStats()
    stats.value = data.data
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

// 核心指标卡
const overviewCards = computed(() => {
  if (!stats.value) return []
  const o = stats.value.overview
  const t = stats.value.today
  return [
    {
      key: 'users',
      label: '用户总数',
      value: o.user_count,
      today: t.new_users,
      todayLabel: '今日新增',
      icon: '👥',
      color: '#1890ff',
      bg: '#e6f7ff',
      route: '/admin/users',
    },
    {
      key: 'posts',
      label: '帖子总数',
      value: o.post_count,
      today: t.new_posts,
      todayLabel: '今日新增',
      icon: '📝',
      color: '#52c41a',
      bg: '#f6ffed',
      route: '/admin/posts',
    },
    {
      key: 'comments',
      label: '评论总数',
      value: o.comment_count,
      today: t.new_comments,
      todayLabel: '今日新增',
      icon: '💬',
      color: '#faad14',
      bg: '#fffbe6',
      route: '/admin/comments',
    },
    {
      key: 'reports',
      label: '举报总数',
      value: o.report_count,
      today: stats.value.pending.reports,
      todayLabel: '待处理',
      icon: '🚩',
      color: '#ff4d4f',
      bg: '#fff2f0',
      route: '/admin/reports',
    },
  ]
})

// 待办事项
const pendingItems = computed(() => {
  if (!stats.value) return []
  const p = stats.value.pending
  return [
    { label: '待审核帖子', count: p.posts, route: '/admin/posts', color: '#faad14' },
    { label: '待审核评论', count: p.comments, route: '/admin/comments', color: '#faad14' },
    { label: '待处理举报', count: p.reports, route: '/admin/reports', color: '#ff4d4f' },
  ]
})

// 7 天趋势图数据
const trendData = computed(() => stats.value?.trend_7d || [])
const trendMaxPosts = computed(() => Math.max(1, ...trendData.value.map((d) => d.posts)))
const trendMaxUsers = computed(() => Math.max(1, ...trendData.value.map((d) => d.users)))

// 圈子分布数据
const circleData = computed(() => stats.value?.circle_distribution || [])
const circleMaxCount = computed(() => Math.max(1, ...circleData.value.map((d) => d.count)))

// 举报状态分布
const reportStatusList = computed(() => {
  if (!stats.value) return []
  const rs = stats.value.report_status
  const map: Record<string, { label: string; color: string }> = {
    pending: { label: '待处理', color: '#faad14' },
    resolved: { label: '已处理', color: '#52c41a' },
    dismissed: { label: '已驳回', color: '#8c8c8c' },
    rejected: { label: '已驳回', color: '#8c8c8c' },
  }
  return Object.entries(rs).map(([k, v]) => ({
    key: k,
    label: map[k]?.label || k,
    color: map[k]?.color || '#8c8c8c',
    count: v,
  }))
})

// SVG 折线图坐标点（posts）
const postsPoints = computed(() => {
  const w = 560
  const h = 180
  const pad = 30
  if (!trendData.value.length) return ''
  const step = (w - pad * 2) / (trendData.value.length - 1 || 1)
  return trendData.value
    .map((d, i) => {
      const x = pad + i * step
      const y = h - pad - (d.posts / trendMaxPosts.value) * (h - pad * 2)
      return `${x},${y}`
    })
    .join(' ')
})

// SVG 折线图坐标点（users）
const usersPoints = computed(() => {
  const w = 560
  const h = 180
  const pad = 30
  if (!trendData.value.length) return ''
  const step = (w - pad * 2) / (trendData.value.length - 1 || 1)
  return trendData.value
    .map((d, i) => {
      const x = pad + i * step
      const y = h - pad - (d.users / trendMaxUsers.value) * (h - pad * 2)
      return `${x},${y}`
    })
    .join(' ')
})

function fmtNumber(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  return String(n)
}

onMounted(() => load())
</script>

<template>
  <div v-loading="loading" class="dashboard">
    <!-- 顶部标题 -->
    <div class="page-header">
      <div>
        <h2 class="page-title">数据看板</h2>
        <p class="page-subtitle">实时监控社区运营核心指标</p>
      </div>
      <el-button :icon="'Refresh'" @click="load">刷新</el-button>
    </div>

    <!-- 核心指标卡 -->
    <div class="stat-cards">
      <div
        v-for="card in overviewCards"
        :key="card.key"
        class="stat-card"
        @click="router.push(card.route)"
      >
        <div class="stat-card-icon" :style="{ background: card.bg, color: card.color }">
          {{ card.icon }}
        </div>
        <div class="stat-card-body">
          <div class="stat-card-label">{{ card.label }}</div>
          <div class="stat-card-value" :style="{ color: card.color }">{{ fmtNumber(card.value) }}</div>
          <div class="stat-card-today">
            <span class="today-label">{{ card.todayLabel }}</span>
            <span class="today-value" :style="{ color: card.today > 0 ? card.color : '#8c8c8c' }">
              {{ card.today }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- 中部：趋势图 + 圈子分布 -->
    <div class="chart-row">
      <!-- 7 天趋势图 -->
      <div class="chart-card chart-card--large">
        <div class="chart-header">
          <h3 class="chart-title">近 7 天趋势</h3>
          <div class="chart-legend">
            <span class="legend-item"><i class="legend-dot" style="background: #1890ff"></i>发帖数</span>
            <span class="legend-item"><i class="legend-dot" style="background: #52c41a"></i>注册数</span>
          </div>
        </div>
        <div class="chart-body">
          <svg v-if="trendData.length" viewBox="0 0 560 220" class="trend-svg" preserveAspectRatio="xMidYMid meet">
            <!-- 网格线 -->
            <g class="grid-lines">
              <line v-for="i in 4" :key="i" :x1="30" :x2="530" :y1="30 + (i - 1) * 40" :y2="30 + (i - 1) * 40"
                stroke="#f0f0f0" stroke-width="1" />
            </g>
            <!-- Y 轴标签 -->
            <text x="6" y="34" class="axis-label">{{ trendMaxPosts }}</text>
            <text x="6" y="194" class="axis-label">0</text>
            <!-- 帖子折线 -->
            <polyline :points="postsPoints" fill="none" stroke="#1890ff" stroke-width="2.5"
              stroke-linecap="round" stroke-linejoin="round" />
            <!-- 帖子数据点 -->
            <g v-for="(d, i) in trendData" :key="`p-${i}`">
              <circle :cx="30 + (i * (500 / (trendData.length - 1 || 1)))" :cy="190 - (d.posts / trendMaxPosts) * 160"
                r="3.5" fill="#1890ff" />
              <text :x="30 + (i * (500 / (trendData.length - 1 || 1)))" y="210" text-anchor="middle" class="axis-label">
                {{ d.date }}
              </text>
            </g>
            <!-- 用户折线 -->
            <polyline :points="usersPoints" fill="none" stroke="#52c41a" stroke-width="2.5"
              stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="4 2" />
            <!-- 用户数据点 -->
            <g v-for="(d, i) in trendData" :key="`u-${i}`">
              <circle :cx="30 + (i * (500 / (trendData.length - 1 || 1)))" :cy="190 - (d.users / trendMaxUsers) * 160"
                r="3.5" fill="#52c41a" />
            </g>
          </svg>
          <div v-else class="chart-empty">暂无趋势数据</div>
        </div>
      </div>

      <!-- 圈子分布 -->
      <div class="chart-card">
        <div class="chart-header">
          <h3 class="chart-title">圈子帖子分布（Top 8）</h3>
        </div>
        <div class="chart-body">
          <div v-if="circleData.length" class="bar-chart">
            <div v-for="item in circleData" :key="item.name" class="bar-row">
              <span class="bar-label" :title="item.name">{{ item.name }}</span>
              <div class="bar-track">
                <div class="bar-fill" :style="{ width: (item.count / circleMaxCount * 100) + '%' }">
                  <span class="bar-value">{{ item.count }}</span>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="chart-empty">暂无分布数据</div>
        </div>
      </div>
    </div>

    <!-- 底部：待办 + 举报状态 -->
    <div class="chart-row">
      <!-- 待办事项 -->
      <div class="chart-card">
        <div class="chart-header">
          <h3 class="chart-title">待办事项</h3>
        </div>
        <div class="chart-body">
          <div class="todo-list">
            <div
              v-for="item in pendingItems"
              :key="item.label"
              class="todo-item"
              @click="router.push(item.route)"
            >
              <div class="todo-info">
                <span class="todo-label">{{ item.label }}</span>
                <span class="todo-count" :style="{ color: item.color }">{{ item.count }}</span>
              </div>
              <span class="todo-arrow">›</span>
            </div>
            <div v-if="!pendingItems.some((i) => i.count > 0)" class="chart-empty">
              暂无待办事项
            </div>
          </div>
        </div>
      </div>

      <!-- 举报状态分布 -->
      <div class="chart-card">
        <div class="chart-header">
          <h3 class="chart-title">举报状态分布</h3>
        </div>
        <div class="chart-body">
          <div v-if="reportStatusList.length" class="status-list">
            <div v-for="item in reportStatusList" :key="item.key" class="status-row">
              <span class="status-dot" :style="{ background: item.color }"></span>
              <span class="status-label">{{ item.label }}</span>
              <span class="status-count">{{ item.count }}</span>
            </div>
          </div>
          <div v-else class="chart-empty">暂无举报数据</div>
        </div>
      </div>

      <!-- 快捷入口 -->
      <div class="chart-card">
        <div class="chart-header">
          <h3 class="chart-title">快捷入口</h3>
        </div>
        <div class="chart-body">
          <div class="shortcut-grid">
            <button class="shortcut-btn" @click="router.push('/admin/posts')">
              <span class="shortcut-icon">📝</span>
              <span>帖子管理</span>
            </button>
            <button class="shortcut-btn" @click="router.push('/admin/users')">
              <span class="shortcut-icon">👤</span>
              <span>用户管理</span>
            </button>
            <button class="shortcut-btn" @click="router.push('/admin/announcements')">
              <span class="shortcut-icon">📢</span>
              <span>发布公告</span>
            </button>
            <button class="shortcut-btn" @click="router.push('/admin/logs')">
              <span class="shortcut-icon">📋</span>
              <span>操作日志</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboard {
  min-height: 100%;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}
.page-title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: #1f1f1f;
}
.page-subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: #8c8c8c;
}

/* 核心指标卡 */
.stat-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}
.stat-card {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03), 0 1px 6px -1px rgba(0, 0, 0, 0.02);
  border: 1px solid #f0f0f0;
  cursor: pointer;
  transition: all 0.2s;
}
.stat-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  transform: translateY(-2px);
}
.stat-card-icon {
  width: 48px;
  height: 48px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  font-size: 24px;
  flex-shrink: 0;
}
.stat-card-body {
  flex: 1;
  min-width: 0;
}
.stat-card-label {
  font-size: 13px;
  color: #8c8c8c;
  margin-bottom: 4px;
}
.stat-card-value {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.2;
  margin-bottom: 4px;
}
.stat-card-today {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}
.today-label {
  color: #8c8c8c;
}
.today-value {
  font-weight: 600;
}

/* 图表行 */
.chart-row {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}
.chart-row:last-child {
  grid-template-columns: 1fr 1fr 1fr;
}
.chart-card {
  background: #fff;
  border-radius: 8px;
  border: 1px solid #f0f0f0;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
  overflow: hidden;
}
.chart-card--large {
  grid-column: span 1;
}
.chart-header {
  padding: 16px 20px;
  border-bottom: 1px solid #f0f0f0;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.chart-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #1f1f1f;
}
.chart-legend {
  display: flex;
  gap: 16px;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #595959;
}
.legend-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.chart-body {
  padding: 20px;
}

/* 趋势图 SVG */
.trend-svg {
  width: 100%;
  height: auto;
  max-height: 240px;
}
.axis-label {
  font-size: 11px;
  fill: #8c8c8c;
}

/* 柱状图 */
.bar-chart {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.bar-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.bar-label {
  width: 70px;
  font-size: 12px;
  color: #595959;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex-shrink: 0;
}
.bar-track {
  flex: 1;
  height: 20px;
  background: #f5f5f5;
  border-radius: 4px;
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #1890ff, #69c0ff);
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding-right: 6px;
  transition: width 0.3s ease;
}
.bar-value {
  font-size: 11px;
  color: #fff;
  font-weight: 600;
}

/* 待办 */
.todo-list {
  display: flex;
  flex-direction: column;
}
.todo-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
  border-bottom: 1px solid #f5f5f5;
  cursor: pointer;
  transition: background 0.15s;
}
.todo-item:last-child {
  border-bottom: none;
}
.todo-item:hover {
  background: #fafafa;
}
.todo-info {
  display: flex;
  align-items: center;
  gap: 12px;
}
.todo-label {
  font-size: 13px;
  color: #262626;
}
.todo-count {
  font-size: 18px;
  font-weight: 700;
}
.todo-arrow {
  color: #bfbfbf;
  font-size: 18px;
}

/* 状态列表 */
.status-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.status-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
}
.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.status-label {
  flex: 1;
  font-size: 13px;
  color: #262626;
}
.status-count {
  font-size: 16px;
  font-weight: 700;
  color: #1f1f1f;
}

/* 快捷入口 */
.shortcut-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}
.shortcut-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 16px 8px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
  font-size: 12px;
  color: #595959;
}
.shortcut-btn:hover {
  background: #e6f7ff;
  border-color: #1890ff;
  color: #1890ff;
}
.shortcut-icon {
  font-size: 24px;
}

.chart-empty {
  text-align: center;
  padding: 32px 0;
  color: #bfbfbf;
  font-size: 13px;
}

/* 响应式 */
@media (max-width: 1200px) {
  .stat-cards {
    grid-template-columns: repeat(2, 1fr);
  }
  .chart-row {
    grid-template-columns: 1fr;
  }
  .chart-row:last-child {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 768px) {
  .stat-cards {
    grid-template-columns: 1fr;
  }
}
</style>
