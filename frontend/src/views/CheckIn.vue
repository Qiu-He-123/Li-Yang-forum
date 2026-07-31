<script setup lang="ts">
/**
 * 每日签到页
 *
 * 功能：
 * - 顶部签到卡片：今日签到状态 + 连续天数 + 签到按钮
 * - 本月签到日历：可视化展示本月已签日期
 * - 签到规则说明
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import { checkInToday, getCheckInStatus, type CheckInStatus } from '../api/checkin'

const router = useRouter()

const status = ref<CheckInStatus | null>(null)
const loading = ref(false)
const checking = ref(false)

// 当前年月（用于日历展示）
const now = new Date()
const currentYear = now.getFullYear()
const currentMonth = now.getMonth() // 0-11
const today = now.getDate()

// 本月日历网格（含前导空位）
const calendarDays = computed(() => {
  const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate()
  const firstDayOfWeek = new Date(currentYear, currentMonth, 1).getDay() // 0=周日
  const checkedSet = new Set(status.value?.month_checked_days || [])

  const cells: Array<{ day: number | null; checked: boolean; isToday: boolean }> = []
  // 前导空位
  for (let i = 0; i < firstDayOfWeek; i++) {
    cells.push({ day: null, checked: false, isToday: false })
  }
  // 月内日期
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push({
      day: d,
      checked: checkedSet.has(d),
      isToday: d === today,
    })
  }
  return cells
})

const weekLabels = ['日', '一', '二', '三', '四', '五', '六']

async function loadStatus() {
  loading.value = true
  try {
    const { data } = await getCheckInStatus()
    status.value = data.data
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    loading.value = false
  }
}

async function onCheckIn() {
  if (checking.value || status.value?.checked_in_today) return
  checking.value = true
  try {
    const { data } = await checkInToday()
    toast.success(data.data.message)
    await loadStatus()
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    checking.value = false
  }
}

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push(`/user/${0}`)
}

onMounted(() => {
  loadStatus()
})
</script>

<template>
  <main class="page-checkin">
    <header class="page-header">
      <button class="icon-btn" type="button" aria-label="返回" @click="goBack">
        <Icon name="arrow-left" :size="20" />
      </button>
      <h1 class="page-title">每日签到</h1>
      <span class="icon-btn-placeholder" />
    </header>

    <div class="page-container">
      <!-- 签到卡片 -->
      <section class="checkin-card">
        <div class="card-bg" />
        <div class="card-content">
          <div class="card-top">
            <div class="card-icon">
              <Icon name="gift" :size="32" />
            </div>
            <div class="card-info">
              <div class="card-label">已连续签到</div>
              <div class="card-days">
                <span class="days-num">{{ status?.today_consecutive_days ?? 0 }}</span>
                <span class="days-unit">天</span>
              </div>
            </div>
          </div>
          <div class="card-desc">
            <p v-if="status?.checked_in_today">今日已签到，明天继续加油！</p>
            <p v-else>今日还未签到，点击下方按钮签到吧～</p>
          </div>
          <button
            class="checkin-btn"
            type="button"
            :disabled="checking || status?.checked_in_today"
            @click="onCheckIn"
          >
            <Icon v-if="checking" name="refresh" :size="18" />
            <Icon v-else-if="status?.checked_in_today" name="check" :size="18" />
            <Icon v-else name="gift" :size="18" />
            {{ checking ? '签到中…' : status?.checked_in_today ? '今日已签到' : '立即签到' }}
          </button>
        </div>
      </section>

      <!-- 本月日历 -->
      <section class="calendar-section">
        <div class="section-header">
          <h2 class="section-title">{{ currentYear }}年{{ currentMonth + 1 }}月签到日历</h2>
          <span class="section-stat">本月已签 {{ status?.total_month_count ?? 0 }} 天</span>
        </div>
        <div class="calendar">
          <div class="calendar-week">
            <span v-for="w in weekLabels" :key="w" class="week-cell">{{ w }}</span>
          </div>
          <div class="calendar-grid">
            <div
              v-for="(cell, i) in calendarDays"
              :key="i"
              class="calendar-cell"
              :class="{
                'is-empty': !cell.day,
                'is-checked': cell.checked,
                'is-today': cell.isToday,
              }"
            >
              <span v-if="cell.day" class="cell-day">{{ cell.day }}</span>
              <Icon v-if="cell.checked" name="check" :size="14" class="cell-check" />
            </div>
          </div>
        </div>
      </section>

      <!-- 签到规则 -->
      <section class="rules-section">
        <h2 class="section-title">签到规则</h2>
        <ul class="rules-list">
          <li>每日只能签到一次，签到后当日不可取消。</li>
          <li>连续签到每天奖励递增：第 1 天 1 分，第 2 天 2 分，以此类推，封顶 7 分。</li>
          <li>中断签到后，连续天数将重置为 1。</li>
          <li>积分可用于后续上线的积分商城兑换礼品。</li>
        </ul>
      </section>
    </div>
  </main>
</template>

<style scoped>
.page-checkin {
  min-height: 100vh;
  background: var(--bg-100);
  padding-bottom: calc(80px + env(safe-area-inset-bottom));
}

.page-header {
  position: sticky;
  top: 0;
  z-index: 50;
  background: rgba(255, 255, 255, 0.95);
  -webkit-backdrop-filter: blur(20px);
  backdrop-filter: blur(20px);
  border-bottom: 0.5px solid var(--bg-300);
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  padding-top: env(safe-area-inset-top);
}
.page-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-800);
  margin: 0;
  flex: 1;
  text-align: center;
}
.icon-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: transparent;
  cursor: pointer;
  display: grid;
  place-items: center;
  color: var(--text-600);
}
.icon-btn-placeholder {
  width: 36px;
  height: 36px;
  display: inline-block;
}

.page-container {
  max-width: 720px;
  margin: 0 auto;
  padding: 16px;
}

/* 签到卡片 */
.checkin-card {
  position: relative;
  border-radius: 20px;
  overflow: hidden;
  margin-bottom: 20px;
  box-shadow: var(--shadow-md);
}
.card-bg {
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, #ff9500 0%, #ff6b35 50%, #ff3b30 100%);
}
.card-content {
  position: relative;
  padding: 24px 20px;
  color: #fff;
}
.card-top {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
}
.card-icon {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  display: grid;
  place-items: center;
  color: #fff;
}
.card-info {
  flex: 1;
}
.card-label {
  font-size: 13px;
  opacity: 0.9;
  margin-bottom: 4px;
}
.card-days {
  display: flex;
  align-items: baseline;
  gap: 4px;
}
.days-num {
  font-size: 36px;
  font-weight: 800;
  line-height: 1;
}
.days-unit {
  font-size: 16px;
  opacity: 0.9;
}
.card-desc {
  font-size: 14px;
  opacity: 0.95;
  margin-bottom: 16px;
  min-height: 20px;
}
.card-desc p {
  margin: 0;
}
.checkin-btn {
  width: 100%;
  padding: 12px 0;
  border: none;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.95);
  color: #ff6b35;
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: all 0.15s;
  font-family: inherit;
}
.checkin-btn:hover:not(:disabled) {
  background: #fff;
  transform: translateY(-1px);
}
.checkin-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

/* 日历 */
.calendar-section {
  background: var(--bg-50);
  border-radius: 16px;
  padding: 16px;
  margin-bottom: 16px;
  box-shadow: var(--shadow-xs);
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.section-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-800);
  margin: 0;
}
.section-stat {
  font-size: 12px;
  color: var(--text-500);
}
.calendar-week {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 4px;
  margin-bottom: 8px;
}
.week-cell {
  text-align: center;
  font-size: 12px;
  color: var(--text-400);
  padding: 4px 0;
  font-weight: 500;
}
.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 4px;
}
.calendar-cell {
  aspect-ratio: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: var(--bg-100);
  position: relative;
  font-size: 13px;
  color: var(--text-600);
}
.calendar-cell.is-empty {
  background: transparent;
}
.calendar-cell.is-checked {
  background: linear-gradient(135deg, #ff9500, #ff6b35);
  color: #fff;
}
.calendar-cell.is-today:not(.is-checked) {
  border: 2px solid #ff9500;
}
.cell-day {
  font-weight: 500;
}
.cell-check {
  position: absolute;
  bottom: 2px;
}

/* 规则 */
.rules-section {
  background: var(--bg-50);
  border-radius: 16px;
  padding: 16px;
  box-shadow: var(--shadow-xs);
}
.rules-list {
  margin: 8px 0 0;
  padding-left: 20px;
  font-size: 13px;
  color: var(--text-500);
  line-height: 1.8;
}
.rules-list li {
  list-style: disc;
}

@media (max-width: 768px) {
  .page-header {
    height: 48px;
    padding: 0 12px;
    padding-top: env(safe-area-inset-top);
  }
  .page-container {
    padding: 12px;
  }
}
</style>
