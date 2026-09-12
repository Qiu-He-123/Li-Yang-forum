<script setup lang="ts">
/**
 * 发布任务（项目 2）
 * 填写标题 / 描述 / 分类 / 悬赏交易币，发布即从钱包托管。
 */
import { reactive, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'

import { Icon } from '../../components/native'
import { toast } from '../../components/native/Toast'
import { createOrder, getWallet } from '../../api/order'

const router = useRouter()
const submitting = ref(false)
const balance = ref<number | null>(null)
const form = reactive({
  title: '',
  content: '',
  category: '找人办事' as string,
  reward: '' as string,
})

const categories = [
  '代取快递', '代买代送', '找人办事', '学习互助',
  '组队开黑', '情感求助', '跑腿代领', '其他',
]

async function submit() {
  if (!form.title.trim()) { toast.error('请填写标题'); return }
  if (!form.content.trim()) { toast.error('请填写需求描述'); return }
  const reward = Number(form.reward)
  if (!reward || reward <= 0 || !Number.isInteger(reward)) {
    toast.error('请填写正整数悬赏交易币')
    return
  }
  if (balance.value !== null && reward > balance.value) {
    toast.error('交易币余额不足，请先充值')
    return
  }
  if (submitting.value) return
  submitting.value = true
  try {
    await createOrder({
      title: form.title.trim().slice(0, 64),
      content: form.content.trim().slice(0, 2000),
      category: form.category,
      reward,
    })
    toast.success('发布成功，悬赏已托管')
    router.push('/orders')
  } catch (e) {
    toast.error((e as Error).message)
  } finally {
    submitting.value = false
  }
}

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push('/orders')
}

onMounted(async () => {
  try {
    const { data } = await getWallet()
    balance.value = data.data?.balance ?? null
  } catch {
    balance.value = null
  }
})
</script>

<template>
  <div class="op-page">
    <header class="op-header">
      <button class="op-back" type="button" aria-label="返回" @click="goBack">
        <Icon name="chevron-left" :size="22" />
      </button>
      <h1>发布任务</h1>
      <div class="op-header-spacer" />
    </header>

    <main class="op-body">
      <div class="op-tip">
        <Icon name="info" :size="16" />
        <span>
          当前交易币余额 <b class="op-balance">{{ balance === null ? '—' : balance }}</b>。发布后悬赏立即从你的交易币钱包托管，任务完成由接单人验收后发放。
        </span>
      </div>

      <label class="op-field">
        <span class="op-label">任务标题 <em>*</em></span>
        <input
          v-model="form.title"
          class="op-input"
          type="text"
          maxlength="64"
          placeholder="例：帮我带一份午饭到 3 教 201"
        />
        <span class="op-count">{{ form.title.length }}/64</span>
      </label>

      <label class="op-field">
        <span class="op-label">需求描述 <em>*</em></span>
        <textarea
          v-model="form.content"
          class="op-textarea"
          maxlength="2000"
          placeholder="尽量说清楚要求、时间地点、交付方式等"
        />
        <span class="op-count">{{ form.content.length }}/2000</span>
      </label>

      <label class="op-field">
        <span class="op-label">任务分类 <em>*</em></span>
        <div class="op-cats">
          <button
            v-for="c in categories"
            :key="c"
            type="button"
            class="op-cat"
            :class="{ active: form.category === c }"
            @click="form.category = c"
          >{{ c }}</button>
        </div>
      </label>

      <label class="op-field">
        <span class="op-label">悬赏交易币 <em>*</em></span>
        <input
          v-model="form.reward"
          class="op-input op-input--reward"
          type="number"
          min="1"
          step="1"
          inputmode="numeric"
          placeholder="正整数，发布即托管"
        />
        <span class="op-reward-unit">交易币</span>
      </label>
    </main>

    <footer class="op-footer">
      <button class="op-submit" type="button" :disabled="submitting" @click="submit">
        {{ submitting ? '发布中…' : '确认发布' }}
      </button>
    </footer>
  </div>
</template>

<style scoped>
.op-page { min-height: 100vh; background: #f7f8fb; color: #1d1d1f; padding-bottom: 90px; }
.op-header {
  position: sticky; top: 0; z-index: 10;
  display: flex; align-items: center; gap: 8px;
  padding: calc(10px + env(safe-area-inset-top, 0px)) 14px 10px;
  background: rgba(255,255,255,0.86);
  -webkit-backdrop-filter: saturate(1.8) blur(16px);
  backdrop-filter: saturate(1.8) blur(16px);
  border-bottom: 1px solid rgba(0,0,0,0.05);
}
.op-header h1 { margin: 0; font-size: 18px; font-weight: 800; flex: 1; text-align: center; }
.op-back { width: 34px; height: 34px; border: none; background: transparent; cursor: pointer; display: grid; place-items: center; color: #1d1d1f; }
.op-header-spacer { width: 34px; }
.op-body { padding: 16px 16px 8px; max-width: 640px; margin: 0 auto; }
.op-tip {
  display: flex; align-items: flex-start; gap: 8px;
  padding: 10px 12px; border-radius: 12px;
  background: rgba(255,149,0,0.1); color: #a05a00;
  font-size: 13px; line-height: 1.5; margin-bottom: 16px;
}
.op-balance { font-size: 15px; font-weight: 800; color: #e0530a; }
.op-field {
  position: relative; display: block; margin-bottom: 20px;
}
.op-label { display: block; font-size: 15px; font-weight: 700; margin-bottom: 8px; }
.op-label em { color: #ff3b30; font-style: normal; }
.op-input {
  width: 100%; height: 46px; padding: 0 14px;
  border: 1px solid #e5e5ea; border-radius: 12px;
  background: #fff; font-size: 15px; color: #1d1d1f; outline: none;
  box-sizing: border-box;
}
.op-input:focus { border-color: #0071e3; box-shadow: 0 0 0 3px rgba(0,113,227,0.12); }
.op-textarea {
  width: 100%; min-height: 130px; padding: 12px 14px;
  border: 1px solid #e5e5ea; border-radius: 12px;
  background: #fff; font-size: 15px; line-height: 1.6; color: #1d1d1f;
  outline: none; resize: vertical; box-sizing: border-box;
}
.op-textarea:focus { border-color: #0071e3; box-shadow: 0 0 0 3px rgba(0,113,227,0.12); }
.op-count { position: absolute; right: 10px; font-size: 11px; color: #bfbfc4; top: 44px; }
.op-cats { display: flex; flex-wrap: wrap; gap: 8px; }
.op-cat {
  height: 32px; padding: 0 14px; border-radius: 16px;
  border: 1px solid #e5e5ea; background: #fff; color: #6e6e73;
  font-size: 13px; font-weight: 600; cursor: pointer;
}
.op-cat.active { background: #0071e3; color: #fff; border-color: #0071e3; }
.op-input--reward { padding-right: 80px; }
.op-reward-unit { position: absolute; right: 14px; top: 40px; font-size: 13px; color: #8e8e93; }
.op-footer {
  position: fixed; left: 0; right: 0; bottom: 0; z-index: 10;
  padding: 12px 16px calc(12px + env(safe-area-inset-bottom, 0px));
  background: rgba(255,255,255,0.9);
  -webkit-backdrop-filter: saturate(1.8) blur(16px);
  backdrop-filter: saturate(1.8) blur(16px);
  border-top: 1px solid rgba(0,0,0,0.05);
}
.op-submit {
  width: 100%; max-width: 640px; height: 50px; margin: 0 auto; display: block;
  border: none; border-radius: 25px; cursor: pointer;
  background: linear-gradient(135deg, #0071e3, #5856d6); color: #fff;
  font-size: 16px; font-weight: 700;
  box-shadow: 0 10px 24px rgba(0,113,227,0.35);
}
.op-submit:disabled { opacity: 0.6; }
@media (min-width: 720px) { .op-body { padding-top: 28px; } }
</style>