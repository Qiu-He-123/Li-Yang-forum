<script setup lang="ts">
/**
 * 订单详情（项目 2）
 * 按状态与身份展示操作：接单 / 交付 / 验收 / 取消 / 曝光
 */
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { Icon } from '../../components/native'
import { toast } from '../../components/native/Toast'
import {
  getOrder,
  acceptOrder,
  deliverOrder,
  confirmOrder,
  cancelOrder,
  boostOrder,
  ORDER_STATUS_META,
  type OrderTask,
} from '../../api/order'

const route = useRoute()
const router = useRouter()
const task = ref<OrderTask | null>(null)
const loading = ref(true)
const acting = ref(false)
const deliverNote = ref('')
const showDeliver = ref(false)

async function load() {
  loading.value = true
  try {
    const { data } = await getOrder(Number(route.params.id))
    task.value = data.data
  } catch (e) {
    toast.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

async function act(fn: () => Promise<unknown>, msg: string) {
  if (acting.value) return
  acting.value = true
  try {
    const r = (await fn()) as { data: { data: OrderTask; platform_cut?: number } }
    task.value = r.data.data
    if (msg) toast.success(msg)
    if (r.data.platform_cut != null && r.data.platform_cut > 0) {
      toast.success(`平台抽成 ${r.data.platform_cut} 交易币已结算`)
    }
  } catch (e) {
    toast.error((e as Error).message)
  } finally {
    acting.value = false
  }
}

function onAccept() {
  if (!window.confirm('确认接单？接单后请尽快完成后交付。')) return
  act(() => acceptOrder(task.value!.id), '接单成功')
}

async function onDeliver() {
  if (!deliverNote.value.trim()) { toast.error('请填写交付说明'); return }
  await act(() => deliverOrder(task.value!.id, deliverNote.value.trim()), '已交付，等待发布者验收')
  showDeliver.value = false
}

function onConfirm() {
  if (!window.confirm('确认验收并发放悬赏给接单人？（将按后台比例扣除平台抽成）')) return
  act(() => confirmOrder(task.value!.id), '验收成功，悬赏已发放')
}

function onCancel() {
  if (!window.confirm('确认取消任务？托管悬赏将退回你的钱包。')) return
  act(() => cancelOrder(task.value!.id), '已取消，悬赏已退回')
}

function onBoost() {
  if (!window.confirm('确认花费曝光费用提升排序？（费用从钱包扣除）')) return
  act(() => boostOrder(task.value!.id), '曝光成功，任务已置顶')
}

function fmtTime(t: string | null | undefined): string {
  if (!t) return ''
  return t.replace('T', ' ').slice(0, 16)
}

function goBack() { router.push('/orders') }

onMounted(load)
</script>

<template>
  <div class="od-page">
    <header class="od-header">
      <button class="od-back" type="button" aria-label="返回" @click="goBack">
        <Icon name="chevron-left" :size="22" />
      </button>
      <h1>任务详情</h1>
      <div class="od-spacer" />
    </header>

    <main v-if="task" class="od-body" :class="'od--' + task.status">
      <section class="od-card">
        <div class="od-top">
          <span class="od-cat">{{ task.category }}</span>
          <span class="od-status" :class="ORDER_STATUS_META[task.status]?.cls || ''">
            {{ ORDER_STATUS_META[task.status]?.text || task.status }}
          </span>
        </div>
        <h2 class="od-title">{{ task.title }}</h2>
        <p class="od-desc">{{ task.content }}</p>

        <div class="od-reward">
          <span class="od-reward-num">{{ task.reward }}</span>
          <span class="od-reward-unit">交易币悬赏</span>
        </div>

        <div class="od-meta">
          <div class="od-meta-row"><span>发布者</span><b>{{ task.poster_name || '用户' + task.user_id }}</b></div>
          <div v-if="task.assignee_name" class="od-meta-row"><span>接单人</span><b>{{ task.assignee_name }}</b></div>
          <div class="od-meta-row"><span>发布时间</span><b>{{ fmtTime(task.created_at) }}</b></div>
          <div v-if="task.completed_at" class="od-meta-row"><span>完成时间</span><b>{{ fmtTime(task.completed_at) }}</b></div>
          <div v-if="task.deliver_note" class="od-meta-row od-deliver"><span>交付说明</span><b>{{ task.deliver_note }}</b></div>
        </div>
      </section>

      <!-- 操作面板 -->
      <section class="od-actions">
        <!-- 发布者：待接单可取消 / 曝光 -->
        <template v-if="task.is_mine">
          <button v-if="task.status === 'open'" class="od-btn od-btn--ghost" type="button" :disabled="acting" @click="onBoost">
            🔥 曝光置顶
          </button>
          <button v-if="task.status === 'open'" class="od-btn od-btn--danger" type="button" :disabled="acting" @click="onCancel">
            取消任务
          </button>
          <button v-if="task.status === 'done'" class="od-btn od-btn--primary" type="button" :disabled="acting" @click="onConfirm">
            验收并发放悬赏
          </button>
        </template>

        <!-- 接单人：交付 -->
        <template v-else-if="task.is_assigned_to_me">
          <button v-if="task.status === 'in_progress'" class="od-btn od-btn--primary" type="button" @click="showDeliver = true">
            提交交付
          </button>
        </template>

        <!-- 游客：接单 -->
        <template v-else>
          <button v-if="task.status === 'open'" class="od-btn od-btn--primary" type="button" :disabled="acting" @click="onAccept">
            接下这单
          </button>
          <p v-else class="od-noop">该任务暂不可接单</p>
        </template>
      </section>

      <!-- 交付输入 -->
      <section v-if="showDeliver" class="od-deliver-box">
        <textarea
          v-model="deliverNote"
          class="od-textarea"
          maxlength="500"
          placeholder="填写交付内容 / 完成凭证…"
        />
        <button class="od-btn od-btn--primary" type="button" :disabled="acting" @click="onDeliver">
          确认交付
        </button>
        <button class="od-btn od-btn--ghost" type="button" @click="showDeliver = false">取消</button>
      </section>
    </main>
  </div>
</template>

<style scoped>
.od-page { min-height: 100vh; background: #f7f8fb; color: #1d1d1f; padding-bottom: 40px; }
.od-header {
  position: sticky; top: 0; z-index: 10; display: flex; align-items: center; gap: 8px;
  padding: calc(10px + env(safe-area-inset-top, 0px)) 14px 10px;
  background: rgba(255,255,255,0.86);
  -webkit-backdrop-filter: saturate(1.8) blur(16px);
  backdrop-filter: saturate(1.8) blur(16px);
  border-bottom: 1px solid rgba(0,0,0,0.05);
}
.od-header h1 { margin: 0; font-size: 18px; font-weight: 800; flex: 1; text-align: center; }
.od-back { width: 34px; height: 34px; border: none; background: transparent; cursor: pointer; display: grid; place-items: center; }
.od-spacer { width: 34px; }
.od-body { padding: 16px; max-width: 680px; margin: 0 auto; }
.od-card { background: #fff; border-radius: 18px; padding: 18px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
.od-top { display: flex; align-items: center; justify-content: space-between; }
.od-cat { font-size: 12px; color: #0071e3; background: rgba(0,113,227,0.08); padding: 3px 10px; border-radius: 8px; font-weight: 700; }
.od-status { font-size: 13px; font-weight: 800; }
.st-open { color: #0071e3; } .st-going { color: #ff9500; } .st-done { color: #34c759; }
.st-completed { color: #6e6e73; } .st-cancel { color: #ff3b30; }
.od-title { font-size: 20px; font-weight: 800; margin: 14px 0 8px; letter-spacing: -0.01em; }
.od-desc { font-size: 15px; line-height: 1.65; color: #4a4a50; margin: 0 0 14px; white-space: pre-wrap; }
.od-reward { display: flex; align-items: baseline; gap: 6px; padding: 12px 0; border-top: 1px solid #f0f0f2; border-bottom: 1px solid #f0f0f2; }
.od-reward-num { font-size: 28px; font-weight: 800; background: linear-gradient(120deg,#0071e3,#5856d6); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
.od-reward-unit { font-size: 13px; color: #6e6e73; }
.od-meta { margin-top: 14px; display: flex; flex-direction: column; gap: 8px; }
.od-meta-row { display: flex; justify-content: space-between; gap: 12px; font-size: 14px; }
.od-meta-row span { color: #8e8e93; flex-shrink: 0; }
.od-meta-row b { font-weight: 600; color: #1d1d1f; text-align: right; word-break: break-all; }
.od-meta-row.od-deliver { flex-direction: column; }
.od-deliver b { white-space: pre-wrap; }

.od-actions { margin-top: 18px; display: flex; flex-direction: column; gap: 10px; }
.od-btn { width: 100%; height: 48px; border: none; border-radius: 24px; font-size: 15px; font-weight: 700; cursor: pointer; }
.od-btn:disabled { opacity: 0.6; }
.od-btn--primary { background: linear-gradient(135deg,#0071e3,#5856d6); color: #fff; box-shadow: 0 8px 20px rgba(0,113,227,0.3); }
.od-btn--ghost { background: #eef3ff; color: #0071e3; }
.od-btn--danger { background: #fff; color: #ff3b30; border: 1px solid #ffd0cc; }
.od-noop { text-align: center; color: #b0b0b6; font-size: 14px; padding: 12px; }
.od-deliver-box { margin-top: 12px; background: #fff; border-radius: 16px; padding: 14px; display: flex; flex-direction: column; gap: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
.od-textarea { width: 100%; min-height: 100px; padding: 12px; border: 1px solid #e5e5ea; border-radius: 12px; font-size: 15px; line-height: 1.6; outline: none; resize: vertical; box-sizing: border-box; }
.od-textarea:focus { border-color: #0071e3; }
</style>