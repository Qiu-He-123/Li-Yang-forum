<script setup lang="ts">
/** 交易平台 · 平台配置（管理员）：兑换汇率 / 抽成 / 最低提现 / 曝光价 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { adminSettings, adminUpdateSettings } from '../../api/order'

const loading = ref(false)
const saving = ref(false)
const form = reactive({
  task_exchange_rate: 100 as number, // 1元 = N 交易币
  task_commission_rate: 5 as number, // 抽成 %
  task_withdraw_min_cents: 600 as number, // 最低提现（分）
  task_boost_price: 10 as number, // 单次曝光价（交易币）
})
const current = ref<Record<string, number>>({})

async function load() {
  loading.value = true
  try {
    const { data } = await adminSettings()
    current.value = data.data
    form.task_exchange_rate = data.data.rate ?? 100
    form.task_commission_rate = data.data.commission_rate ?? 5
    form.task_withdraw_min_cents = data.data.withdraw_min_cents ?? 600
    form.task_boost_price = data.data.boost_price ?? 10
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

async function save() {
  if (saving.value) return
  saving.value = true
  try {
    const { data } = await adminUpdateSettings({
      task_exchange_rate: Math.max(1, Math.round(form.task_exchange_rate)),
      task_commission_rate: Math.max(0, Math.min(100, Math.round(form.task_commission_rate))),
      task_withdraw_min_cents: Math.max(1, Math.round(form.task_withdraw_min_cents)),
      task_boost_price: Math.max(1, Math.round(form.task_boost_price)),
    })
    form.task_exchange_rate = data.data.rate
    form.task_commission_rate = data.data.commission_rate
    form.task_withdraw_min_cents = data.data.withdraw_min_cents
    form.task_boost_price = data.data.boost_price
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="admin-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">交易平台 · 平台配置</h2>
        <p class="page-subtitle">设置兑换汇率、任务抽成、最低提现与曝光价格</p>
      </div>
    </div>

    <div class="config-grid">
      <div class="config-card" v-for="field in [
        { key: 'task_exchange_rate', label: '兑换汇率', desc: '1 元人民币可兑换多少交易币', unit: '交易币' },
        { key: 'task_commission_rate', label: '任务抽成比例', desc: '发布者验收时，平台从悬赏中抽取的比例', unit: '%' },
        { key: 'task_withdraw_min_cents', label: '最低提现金额', desc: '提现的金额下限（单位：分）', unit: '分' },
        { key: 'task_boost_price', label: '单次曝光价格', desc: '任务置顶一次需消耗的交易币', unit: '交易币' },
      ]" :key="field.key">
        <div class="config-head">
          <h3>{{ field.label }}</h3>
          <span>{{ field.desc }}</span>
        </div>
        <div class="config-input">
          <el-input-number v-model="form[field.key as keyof typeof form]" :min="field.key === 'task_commission_rate' ? 0 : 1"
            :max="field.key === 'task_commission_rate' ? 100 : 100000" :step="1" controls-position="right" style="width: 200px" />
          <span class="config-unit">{{ field.unit }}</span>
        </div>
      </div>
    </div>

    <div class="save-bar">
      <el-button type="primary" size="large" :loading="saving" @click="save">保存全部配置</el-button>
    </div>
  </div>
</template>

<style scoped>
.config-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
.config-card { background: #fff; border-radius: 12px; padding: 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
.config-head h3 { margin: 0 0 6px; font-size: 16px; color: #262626; }
.config-head span { font-size: 12px; color: #8c8c8c; display: block; margin-bottom: 14px; line-height: 1.5; }
.config-input { display: flex; align-items: center; gap: 10px; }
.config-unit { font-size: 14px; color: #595959; }
.save-bar { margin-top: 20px; }
</style>