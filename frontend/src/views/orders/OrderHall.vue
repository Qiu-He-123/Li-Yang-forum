<script setup lang="ts">
/**
 * 接单大厅（项目 2 · 求助 / 接单 / AI 对话助手）
 * - 接单大厅：全部分类横滑 + 任务瀑布流
 * - 求助：使用帮助
 * - AI 助手：豆包式对话，帮找单/发单/看钱包
 */
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import EmptyState from '../../components/common/EmptyState.vue'
import InfiniteScrollFooter from '../../components/common/InfiniteScrollFooter.vue'
import { Icon } from '../../components/native'
import { toast } from '../../components/native/Toast'
import {
  acceptOrder,
  createOrder,
  listOrders,
  orderAiChat,
  orderAiHistory,
  ORDER_STATUS_META,
  type AiCard,
  type AiChatMsg,
  type OrderAiState,
  type OrderTask,
} from '../../api/order'
import { useInfiniteScroll } from '../../composables/useInfiniteScroll'

const router = useRouter()
const route = useRoute()

/** 左侧导航：接单大厅 / 求助 / AI 助手 */
const activeSide = ref<'hall' | 'help' | 'ai'>('hall')

/** 打磨中提示：任何方式进入接单大厅页面都会弹出 */
const showNotice = ref(false)

// 支持 /orders?tab=hall|help|ai 直达指定标签页
const tabParam = String(route.query.tab || '')
if (tabParam === 'hall' || tabParam === 'help' || tabParam === 'ai') activeSide.value = tabParam

const items = ref<OrderTask[]>([])
const categories = ref<string[]>([])
const activeCat = ref('') // '' = 全部
const total = ref(0)
const page = ref(1)
const pageSize = 12
const loading = ref(false)
const hasMore = computed(() => items.value.length < total.value)

function parseList(data: { items: OrderTask[]; categories?: string[]; total: number }) {
  if (data.categories?.length) categories.value = data.categories
  return data.items || []
}

async function fetchPage(pageNo: number) {
  const { data } = await listOrders({
    category: activeCat.value || undefined,
    page: pageNo,
    page_size: pageSize,
  })
  const resp = data.data
  return {
    rows: parseList(resp as unknown as { items: OrderTask[]; categories?: string[]; total: number }),
    total: resp.total,
  }
}

async function loadMore() {
  const next = page.value + 1
  const { rows, total: t } = await fetchPage(next)
  const ids = new Set(items.value.map((i) => i.id))
  items.value = [...items.value, ...rows.filter((i) => !ids.has(i.id))]
  total.value = t
  page.value = next
}

const { loading: loadingMore, error: scrollError, retry } = useInfiniteScroll({
  hasMore,
  onLoadMore: loadMore,
})

async function loadFirst() {
  loading.value = true
  try {
    const { rows, total: t } = await fetchPage(1)
    items.value = rows
    total.value = t
    page.value = 1
  } catch (e) {
    toast.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

function onCat(v: string) {
  activeCat.value = v
  loadFirst()
}

function goDetail(t: OrderTask) {
  router.push(`/orders/${t.id}`)
}

function goPublish() {
  router.push('/orders/publish')
}

function goWallet() {
  router.push('/orders/lottery')
}

function goMine() {
  router.push('/orders/my')
}

function goBack() {
  // 接单大厅的返回统一回到同伴圈首页，避免 history.back() 跳到异常页面
  router.push('/')
}

function onSide(v: 'hall' | 'help' | 'ai') {
  activeSide.value = v
  if (v === 'hall' && items.value.length === 0) loadFirst()
  if (v === 'ai' && aiMessages.value.length === 0 && !aiLoaded.value) loadAiHistory()
}

/* ================= 订单 AI 对话助手 ================= */
const aiMessages = ref<AiChatMsg[]>([])
const aiInput = ref('')
const aiBusy = ref(false)
const aiLoaded = ref(false)
const aiState = ref<OrderAiState | null>(null)
const aiChatEl = ref<HTMLElement | null>(null)

async function loadAiHistory() {
  if (aiLoaded.value) return
  try {
    const { data } = await orderAiHistory()
    aiMessages.value = data.data.history
    aiState.value = data.data.state
  } catch {
    /* 未登录等静默 */
  } finally {
    aiLoaded.value = true
    scrollAi()
  }
}

function scrollAi() {
  nextTick(() => {
    if (aiChatEl.value) aiChatEl.value.scrollTop = aiChatEl.value.scrollHeight
  })
}

async function sendAi() {
  const text = aiInput.value.trim()
  if (!text || aiBusy.value) return
  aiInput.value = ''
  aiMessages.value.push({ role: 'user', content: text })
  aiBusy.value = true
  scrollAi()
  try {
    const { data } = await orderAiChat(text)
    aiMessages.value.push(...data.data.new_messages)
    aiState.value = data.data.state
  } catch (e) {
    aiMessages.value.push({ role: 'assistant', content: (e as Error).message })
  } finally {
    aiBusy.value = false
    scrollAi()
  }
}

function useAiExample(txt: string) {
  aiInput.value = txt
  sendAi()
}

function aiQuick(cmd: string) {
  useAiExample(cmd)
}

async function onConfirmPublish(card: AiCard) {
  const d = (card.data || {}) as { title?: string; content?: string; category?: string; reward?: number }
  if (!d.title || !d.content || !d.reward) {
    toast.error('发单信息不完整')
    return
  }
  try {
    await createOrder({ title: d.title, content: d.content, category: d.category || '其他', reward: d.reward })
    toast.success('发布成功')
    goMine()
  } catch (e) {
    toast.error((e as Error).message)
  }
}

async function onConfirmAccept(card: AiCard) {
  const d = (card.data || {}) as { task_id?: number }
  if (!d.task_id) {
    toast.error('缺少任务')
    return
  }
  try {
    await acceptOrder(d.task_id)
    toast.success('接单成功')
    goMine()
  } catch (e) {
    toast.error((e as Error).message)
  }
}

/* ================= 任务卡片渲染 ================= */
function fmtReward(t: OrderTask) {
  return t.reward
}
function openTask(id: number) {
  router.push(`/orders/${id}`)
}

onMounted(() => {
  loadFirst()
  showNotice.value = true
})
</script>

<template>
  <div class="oh-page" :class="{ 'oh-ai-mode': activeSide === 'ai' }">
    <header class="oh-header">
      <button class="oh-back" type="button" aria-label="返回" @click="goBack">
        <Icon name="chevron-left" :size="22" />
      </button>
      <div class="oh-header-title">
        <h1>{{ activeSide === 'hall' ? '接单大厅' : activeSide === 'help' ? '求助中心' : 'AI 助手' }}</h1>
        <p>求助 · 接单 · 完单</p>
      </div>
      <div class="oh-header-actions">
        <button type="button" class="oh-chip-btn" @click="goMine">
          <Icon name="history" :size="18" /> 我的订单
        </button>
        <button type="button" class="oh-chip-btn" @click="goWallet">
          <Icon name="wallet" :size="18" /> 钱包
        </button>
      </div>
    </header>

    <div class="oh-body">
      <!-- 左侧导航栏 -->
      <aside class="oh-sidebar" aria-label="主导航">
        <button
          type="button"
          class="oh-nav-item"
          :class="{ active: activeSide === 'hall' }"
          @click="onSide('hall')"
        >
          <span class="oh-nav-icon">🛒</span>
          <span class="oh-nav-label">接单大厅</span>
        </button>
        <button
          type="button"
          class="oh-nav-item"
          :class="{ active: activeSide === 'help' }"
          @click="onSide('help')"
        >
          <span class="oh-nav-icon">🆘</span>
          <span class="oh-nav-label">求助</span>
        </button>
        <button
          type="button"
          class="oh-nav-item"
          :class="{ active: activeSide === 'ai' }"
          @click="onSide('ai')"
        >
          <span class="oh-nav-icon">✨</span>
          <span class="oh-nav-label">AI 助手</span>
        </button>
      </aside>

      <!-- 接单大厅 -->
      <section v-if="activeSide === 'hall'" class="oh-main">
        <nav class="oh-cats" aria-label="任务分类">
          <button
            type="button"
            class="oh-cat"
            :class="{ active: activeCat === '' }"
            @click="onCat('')"
          >全部</button>
          <button
            v-for="c in categories"
            :key="c"
            type="button"
            class="oh-cat"
            :class="{ active: activeCat === c }"
            @click="onCat(c)"
          >{{ c }}</button>
        </nav>

        <main class="oh-list">
          <EmptyState v-if="!loading && items.length === 0" text="暂无任务" />

          <article
            v-for="t in items"
            :key="t.id"
            class="oh-card"
            :class="{ mine: t.is_mine, done_card: t.status === 'completed' }"
            @click="goDetail(t)"
          >
            <div class="oh-card-top">
              <span class="oh-cat-tag">{{ t.category }}</span>
              <span class="oh-status" :class="ORDER_STATUS_META[t.status]?.cls || ''">
                {{ ORDER_STATUS_META[t.status]?.text || t.status }}
              </span>
            </div>
            <h2 class="oh-title">{{ t.title }}</h2>
            <p class="oh-desc">{{ t.content }}</p>
            <div class="oh-card-bottom">
              <div class="oh-reward">
                <span class="oh-reward-num">{{ t.reward }}</span>
                <span class="oh-reward-unit">交易币</span>
              </div>
              <div class="oh-post-meta">
                <span v-if="t.boost" class="oh-boost">🔥 曝光×{{ t.boost }}</span>
                <span>发布者 {{ t.poster_name || '用户' + t.user_id }}</span>
                <span v-if="t.assignee_name" class="oh-assignee">接单人 {{ t.assignee_name }}</span>
              </div>
            </div>
          </article>

          <InfiniteScrollFooter :loading="loadingMore" :error="scrollError" :has-more="hasMore" :has-items="items.length > 0" @retry="retry" />
        </main>
      </section>

      <!-- 求助 -->
      <section v-else-if="activeSide === 'help'" class="oh-panel">
        <div class="oh-panel-hero">
          <h2>求助中心</h2>
          <p>有困难，发出来；有本事，接好单。互助让校园更温暖。</p>
          <button type="button" class="oh-panel-btn" @click="goPublish">发布求助</button>
        </div>
        <div class="oh-help-grid">
          <div class="oh-help-card">
            <span class="oh-help-icon">💬</span>
            <h3>怎么发单？</h3>
            <p>点击右上角「发布任务」，或在 AI 助手说一声「我想发单」，填写标题、悬赏交易币与描述即可上墙。</p>
          </div>
          <div class="oh-help-card">
            <span class="oh-help-icon">🤝</span>
            <h3>怎么接单？</h3>
            <p>在接单大厅挑选任务，或在 AI 助手说「帮我把这个单接了」，确认后即可接单，完成后由发布者结算交易币。</p>
          </div>
          <div class="oh-help-card">
            <span class="oh-help-icon">🪙</span>
            <h3>交易币是什么？</h3>
            <p>同伴圈内的通用代币，可用于发布悬赏与结算报酬，未来支持更多场景。</p>
          </div>
          <div class="oh-help-card">
            <span class="oh-help-icon">🛡️</span>
            <h3>交易安全</h3>
            <p>平台全程托管交易币，完单确认后才打款，双向评价保障，靠信用提现真实收益。</p>
          </div>
        </div>
      </section>

      <!-- AI 对话助手 -->
      <section v-else class="oh-panel oh-panel--ai">
        <div class="oh-ai-token" v-if="aiState">
          <span>今日已用 {{ aiState.daily_token }} / {{ aiState.daily_token_limit }} token</span>
        </div>

        <div ref="aiChatEl" class="oh-chat">
          <EmptyState v-if="aiMessages.length === 0 && !aiBusy" text="对我说一句话，帮你找单 / 发单 / 看钱包" />

          <template v-for="(m, i) in aiMessages" :key="i">
            <!-- 用户气泡 -->
            <div v-if="m.role === 'user'" class="oh-msg oh-msg--me">
              <div class="oh-msg-bubble">{{ m.content }}</div>
            </div>
            <!-- AI 文本 -->
            <div v-else-if="m.role === 'assistant' && m.content" class="oh-msg oh-msg--ai">
              <div class="oh-msg-avatar">✨</div>
              <div class="oh-msg-bubble">{{ m.content }}</div>
            </div>
            <!-- 工具卡片 -->
            <div v-else-if="m.role === 'tool' && m.meta" class="oh-msg oh-msg--ai">
              <div class="oh-msg-avatar">✨</div>
              <div class="oh-msg-cards">
                <!-- 任务列表 -->
                <template v-if="m.meta.type === 'tasks'">
                  <p v-if="m.meta.empty" class="oh-card-note">暂无可接的任务，过会儿再来看看~</p>
                  <div
                    v-for="t in (m.meta.tasks || [])"
                    :key="t.id"
                    class="oh-ai-task"
                    @click="openTask(t.id)"
                  >
                    <div class="oh-ai-task-top">
                      <span class="oh-cat-tag">{{ t.category }}</span>
                      <span class="oh-ai-task-reward">{{ fmtReward(t) }} 币</span>
                    </div>
                    <h3 class="oh-ai-task-title">{{ t.title }}</h3>
                    <p class="oh-ai-task-desc">{{ t.content }}</p>
                  </div>
                  <button
                    v-if="!m.meta.empty"
                    type="button"
                    class="oh-fullbtn"
                    @click.stop="useAiExample('去接单大厅看看还有什么单')"
                  >去大厅看更多</button>
                </template>
                <!-- 钱包 -->
                <div v-else-if="m.meta.type === 'wallet'" class="oh-wallet-card">
                  <div class="oh-wallet-num">{{ m.meta.balance }}</div>
                  <div class="oh-wallet-lab">可用交易币</div>
                  <div v-if="(m.meta.frozen ?? 0) > 0" class="oh-wallet-frozen">冻结 {{ m.meta.frozen }}</div>
                </div>
                <!-- 发单确认 -->
                <div v-else-if="m.meta.type === 'confirm' && m.meta.action === 'publish'" class="oh-confirm">
                  <h3 class="oh-confirm-title">📝 发单草稿</h3>
                  <p class="oh-confirm-row"><b>标题：</b>{{ (m.meta.data as any)?.title }}</p>
                  <p class="oh-confirm-row"><b>描述：</b>{{ (m.meta.data as any)?.content }}</p>
                  <p class="oh-confirm-row"><b>分类：</b>{{ (m.meta.data as any)?.category }}　<b>悬赏：</b>{{ (m.meta.data as any)?.reward }} 币</p>
                  <button type="button" class="oh-fullbtn oh-fullbtn--primary" @click="onConfirmPublish(m.meta)">确认发布</button>
                </div>
                <!-- 接单确认 -->
                <div v-else-if="m.meta.type === 'confirm' && m.meta.action === 'accept'" class="oh-confirm">
                  <h3 class="oh-confirm-title">确认接单</h3>
                  <p class="oh-confirm-row"><b>任务：</b>{{ m.meta.task?.title }}</p>
                  <p class="oh-confirm-row"><b>悬赏：</b>{{ m.meta.task?.reward }} 币</p>
                  <button type="button" class="oh-fullbtn oh-fullbtn--primary" @click="onConfirmAccept(m.meta)">确认接单</button>
                </div>
              </div>
            </div>
          </template>

          <!-- AI 输入中动画 -->
          <div v-if="aiBusy" class="oh-msg oh-msg--ai">
            <div class="oh-msg-avatar">✨</div>
            <div class="oh-msg-bubble oh-typing">
              <span></span><span></span><span></span>
            </div>
          </div>
        </div>

        <!-- 快捷引导（空会话时） -->
        <div v-if="aiMessages.length === 0 && !aiBusy" class="oh-ai-suggests">
          <button type="button" class="oh-chip" @click="aiQuick('帮我找点能赚钱的单')">帮我找点能赚钱的单</button>
          <button type="button" class="oh-chip" @click="aiQuick('我想发单找人帮个忙')">我想发单找人帮个忙</button>
          <button type="button" class="oh-chip" @click="aiQuick('看看我钱包还有多少交易币')">看钱包余额</button>
          <button type="button" class="oh-chip" @click="aiQuick('帮我发个代取快递的单，悬赏 20 币')">发个代取快递的单</button>
        </div>

        <!-- 输入栏 -->
        <footer class="oh-ai-foot">
          <input
            v-model="aiInput"
            class="oh-ai-input"
            type="text"
            maxlength="2000"
            :disabled="aiBusy"
            placeholder="说一句话，我帮你找单/发单…"
            @keydown.enter="sendAi"
          />
          <button class="oh-ai-send" type="button" :disabled="aiBusy || !aiInput.trim()" @click="sendAi">
            <Icon name="send" :size="18" />
          </button>
        </footer>
      </section>
    </div>

    <!-- 发布 + 钱包 悬浮（仅大厅显示发单） -->
    <div v-if="activeSide === 'hall'" class="oh-fabs">
      <button type="button" class="oh-fab oh-fab--wallet" @click="goWallet">
        <Icon name="gift" :size="20" />
      </button>
      <button type="button" class="oh-fab oh-fab--publish" @click="goPublish">
        <Icon name="plus" :size="22" /> 发布任务
      </button>
    </div>

    <!-- 打磨中提示弹窗：每次进入接单大厅都会出现，点「知道了」即返回，不进入页面 -->
    <Transition name="oh-notice">
      <div v-if="showNotice" class="oh-notice-mask" @click.self="goBack">
        <div class="oh-notice" role="dialog" aria-modal="true" aria-label="接单大厅打磨中">
          <div class="oh-notice-head">
            <span class="oh-notice-emoji">🔨</span>
            <h2>接单大厅 · 打磨中</h2>
          </div>
          <div class="oh-notice-body">
            <p>接单大厅还在持续打磨中，正式上线后，我们会第一时间在微信群「<b>立洋社区</b>」宣布，请留意群公告～</p>
            <p>在这里，你可以<b>免费找人帮忙</b>，也能顺手帮到别人、<b>赚到奖励</b>：</p>
            <ul>
              <li>首次发单、首次接单 <b>都有奖励</b></li>
              <li>奖励不限 —— 零食、文具、现金样样有</li>
              <li><b>无需充值</b>即可使用完整功能</li>
            </ul>
            <p class="oh-notice-slogan">想找人帮忙，随时开口 ✌️</p>
          </div>
          <button class="oh-notice-btn" type="button" @click="goBack">知道了</button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.oh-page {
  min-height: 100vh;
  padding-bottom: 96px;
  background: linear-gradient(180deg, #eef3ff 0%, #f7f8fb 30%, #f7f8fb 100%);
  color: #1d1d1f;
}
.oh-header {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: calc(10px + env(safe-area-inset-top, 0px)) 14px 10px;
  background: rgba(255, 255, 255, 0.82);
  -webkit-backdrop-filter: saturate(1.8) blur(16px);
  backdrop-filter: saturate(1.8) blur(16px);
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
}
.oh-back {
  width: 34px;
  height: 34px;
  border: none;
  background: transparent;
  cursor: pointer;
  color: #1d1d1f;
  display: grid;
  place-items: center;
}
.oh-header-title { flex: 1; }
.oh-header-title h1 { font-size: 19px; font-weight: 800; margin: 0; letter-spacing: -0.01em; }
.oh-header-title p { margin: 1px 0 0; font-size: 11px; color: #6e6e73; }
.oh-header-actions { display: flex; gap: 8px; }
.oh-chip-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 32px;
  padding: 0 12px;
  border-radius: 16px;
  border: 1px solid rgba(0, 113, 227, 0.28);
  background: rgba(0, 113, 227, 0.06);
  color: #0071e3;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.oh-cats {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding: 12px 14px;
  scrollbar-width: none;
}
.oh-cats::-webkit-scrollbar { display: none; }
.oh-cat {
  flex-shrink: 0;
  height: 30px;
  padding: 0 15px;
  border-radius: 15px;
  border: 1px solid transparent;
  background: #fff;
  color: #6e6e73;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}
.oh-cat.active {
  background: #0071e3;
  color: #fff;
  box-shadow: 0 4px 12px rgba(0, 113, 227, 0.3);
}
.oh-list { padding: 4px 14px; }
.oh-card {
  margin-bottom: 12px;
  padding: 14px;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  cursor: pointer;
  transition: transform 0.14s var(--ease-apple, ease), box-shadow 0.14s ease;
}
.oh-card:active { transform: scale(0.985); }
.oh-card.mine { border: 1px solid rgba(0, 113, 227, 0.2); }
.oh-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.oh-cat-tag {
  font-size: 12px;
  color: #0071e3;
  background: rgba(0, 113, 227, 0.08);
  padding: 2px 9px;
  border-radius: 8px;
  font-weight: 600;
}
.oh-status { font-size: 12px; font-weight: 700; }
.st-open { color: #0071e3; }
.st-going { color: #ff9500; }
.st-done { color: #34c759; }
.st-completed { color: #6e6e73; }
.st-cancel { color: #ff3b30; }
.oh-title {
  margin: 10px 0 6px;
  font-size: 17px;
  font-weight: 800;
  color: #1d1d1f;
  letter-spacing: -0.01em;
}
.oh-desc {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  color: #6e6e73;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.oh-card-bottom {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid #f0f0f2;
}
.oh-reward { display: flex; align-items: baseline; gap: 4px; }
.oh-reward-num {
  font-size: 22px;
  font-weight: 800;
  color: #0071e3;
  background: linear-gradient(120deg, #0071e3, #5856d6);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}
.oh-reward-unit { font-size: 12px; color: #6e6e73; }
.oh-post-meta {
  text-align: right;
  font-size: 12px;
  color: #8e8e93;
  line-height: 1.5;
  min-width: 0;
}
.oh-boost { color: #ff9500; margin-right: 6px; }
.oh-assignee { color: #5856d6; }
.oh-fabs {
  position: fixed;
  right: 16px;
  bottom: calc(78px + env(safe-area-inset-bottom, 0px));
  z-index: 30;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 10px;
}

/* ===== 左侧导航 + 三视图布局（桌面） ===== */
.oh-body {
  display: flex;
  gap: 0;
  max-width: 1180px;
  margin: 0 auto;
}
.oh-sidebar {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 16px 12px;
  width: 200px;
  flex-shrink: 0;
  /* 固定：聊天/列表滚动时左侧导航栏跟随吸顶不消失 */
  position: sticky;
  top: 12px;
  align-self: flex-start;
  max-height: calc(100vh - 24px);
  max-height: calc(100dvh - 24px);
}
.oh-nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 13px 16px;
  width: 100%;
  border: none;
  border-radius: 14px;
  background: transparent;
  color: #6e6e73;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  text-align: left;
  transition: background 0.16s ease, color 0.16s ease, transform 0.12s ease;
}
.oh-nav-item:hover { background: #fff; color: #1d1d1f; }
.oh-nav-item.active {
  background: linear-gradient(135deg, #0071e3, #5856d6);
  color: #fff;
  box-shadow: 0 8px 18px rgba(0, 113, 227, 0.28);
}
.oh-nav-icon { font-size: 20px; line-height: 1; }
.oh-main {
  flex: 1;
  min-width: 0;
}

/* 求助 & AI 面板 */
.oh-panel { flex: 1; min-width: 0; padding: 6px 16px 24px; }
.oh-panel-hero {
  background: linear-gradient(130deg, #0071e3, #5856d6);
  color: #fff;
  border-radius: 20px;
  padding: 26px 24px;
  margin-bottom: 16px;
  box-shadow: 0 12px 28px rgba(0, 113, 227, 0.28);
}
.oh-panel-hero h2 { margin: 0 0 8px; font-size: 26px; letter-spacing: -0.01em; }
.oh-panel-hero p { margin: 0 0 18px; font-size: 15px; opacity: 0.92; line-height: 1.6; }
.oh-panel-btn {
  border: none;
  border-radius: 999px;
  padding: 11px 24px;
  background: #fff;
  color: #5856d6;
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
  box-shadow: 0 6px 14px rgba(0, 0, 0, 0.12);
}
.oh-help-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
  gap: 14px;
}
.oh-help-card {
  background: #fff;
  border-radius: 16px;
  padding: 18px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}
.oh-help-icon { font-size: 26px; }
.oh-help-card h3 { margin: 8px 0 6px; font-size: 16px; }
.oh-help-card p { margin: 0; font-size: 13px; color: #6e6e73; line-height: 1.6; }

/* ===== AI 对话样式 ===== */
.oh-panel--ai {
  display: flex;
  flex-direction: column;
  min-height: 0;
  /* 高度锁顶到底：聊天区内部滚动，输入框固定在底部不随整页下滑 */
  height: calc(100vh - 118px);
  height: calc(100dvh - 118px);
}
.oh-ai-token {
  font-size: 12px;
  color: #8e8e93;
  text-align: right;
  padding: 0 2px 8px;
}
.oh-chat {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 6px 2px 16px;
}
.oh-msg { display: flex; gap: 8px; align-items: flex-start; }
.oh-msg--me { justify-content: flex-end; }
.oh-msg--me .oh-msg-bubble {
  background: linear-gradient(135deg, #0071e3, #5856d6);
  color: #fff;
  border-radius: 16px 16px 4px 16px;
}
.oh-msg--ai .oh-msg-bubble,
.oh-msg--ai .oh-msg-cards {
  background: #fff;
  border-radius: 16px 16px 16px 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}
.oh-msg-avatar {
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 15px;
  color: #fff;
  background: linear-gradient(135deg, #5856d6, #8a3ffc);
}
.oh-msg-bubble {
  max-width: 78%;
  padding: 11px 14px;
  font-size: 14px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}
.oh-msg-cards { max-width: 82%; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
.oh-card-note { margin: 0; font-size: 13px; color: #8e8e93; }
.oh-ai-task {
  border: 1px solid #ececf0;
  border-radius: 12px;
  padding: 10px 12px;
  cursor: pointer;
  background: #fafbfe;
}
.oh-ai-task:active { background: #f0f0f6; }
.oh-ai-task-top { display: flex; justify-content: space-between; align-items: center; }
.oh-ai-task-reward { font-size: 13px; font-weight: 800; color: #0071e3; }
.oh-ai-task-title { margin: 6px 0 4px; font-size: 15px; font-weight: 800; color: #1d1d1f; }
.oh-ai-task-desc {
  margin: 0;
  font-size: 13px;
  color: #6e6e73;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.oh-wallet-card {
  text-align: center;
  padding: 14px;
  background: radial-gradient(circle at 50% 0%, #fff, #f0f3ff);
  border-radius: 14px;
}
.oh-wallet-num {
  font-size: 30px;
  font-weight: 800;
  background: linear-gradient(120deg, #0071e3, #5856d6);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}
.oh-wallet-lab { font-size: 12px; color: #6e6e73; margin-top: 2px; }
.oh-wallet-frozen { font-size: 12px; color: #8e8e93; margin-top: 2px; }
.oh-confirm {
  border: 1px dashed rgba(0, 113, 227, 0.4);
  border-radius: 12px;
  padding: 12px;
  background: #f4f9ff;
}
.oh-confirm-title { margin: 0 0 8px; font-size: 15px; font-weight: 800; color: #1d1d1f; }
.oh-confirm-row { margin: 4px 0; font-size: 13px; color: #3a3a42; line-height: 1.6; }
.oh-confirm-row b { color: #1d1d1f; }
.oh-fullbtn {
  width: 100%;
  margin-top: 8px;
  border: none;
  border-radius: 999px;
  padding: 10px 0;
  background: #fff;
  color: #0071e3;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
}
.oh-fullbtn--primary {
  background: linear-gradient(135deg, #0071e3, #5856d6);
  color: #fff;
}
.oh-typing { display: flex; gap: 5px; align-items: center; padding: 14px; }
.oh-typing span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #aeb6c4;
  animation: ohblink 1.2s infinite;
}
.oh-typing span:nth-child(2) { animation-delay: 0.2s; }
.oh-typing span:nth-child(3) { animation-delay: 0.4s; }
@keyframes ohblink { 50% { opacity: 0.2; } }
.oh-ai-suggests {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 4px 0 12px;
}
.oh-chip {
  padding: 8px 14px;
  border-radius: 999px;
  border: 1px solid #dfe4f0;
  background: #fff;
  color: #4a4a58;
  font-size: 13px;
  cursor: pointer;
}
.oh-ai-foot {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 10px 0 6px;
  border-top: 1px solid #ececf0;
  flex-shrink: 0; /* 输入栏固定底部，不被聊天内容顶出 */
}
.oh-ai-input {
  flex: 1;
  height: 42px;
  padding: 0 16px;
  border: 1px solid #e5e5ea;
  border-radius: 21px;
  font-size: 14px;
  outline: none;
}
.oh-ai-input:focus { border-color: #0071e3; box-shadow: 0 0 0 3px rgba(0, 113, 227, 0.12); }
.oh-ai-send {
  width: 42px;
  height: 42px;
  border: none;
  border-radius: 50%;
  background: linear-gradient(135deg, #0071e3, #5856d6);
  color: #fff;
  display: grid;
  place-items: center;
  cursor: pointer;
  flex-shrink: 0;
}
.oh-ai-send:disabled { opacity: 0.5; }

.oh-fab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 46px;
  padding: 0 18px;
  border: none;
  border-radius: 23px;
  cursor: pointer;
  box-shadow: 0 10px 24px rgba(0, 113, 227, 0.35);
}
.oh-fab--publish {
  background: linear-gradient(135deg, #0071e3, #5856d6);
  color: #fff;
  font-size: 15px;
  font-weight: 700;
}
.oh-fab--wallet {
  width: 46px;
  padding: 0;
  justify-content: center;
  border-radius: 50%;
  background: #fff;
  color: #0071e3;
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.12);
}

/* 平板 & 电脑：居中网格，限制宽度 */
@media (min-width: 720px) {
  .oh-list {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 14px;
    max-width: 900px;
    margin: 0 auto;
    padding: 6px 22px 0;
  }
  .oh-card { margin-bottom: 0; }
}

/* 移动端：横向胶囊导航，替代左侧栏 */
@media (max-width: 719px) {
  .oh-body { flex-direction: column; }
  .oh-sidebar {
    flex-direction: row;
    width: 100%;
    padding: 10px 14px 2px;
    gap: 8px;
    overflow-x: auto;
    scrollbar-width: none;
  }
  .oh-sidebar::-webkit-scrollbar { display: none; }
  .oh-nav-item {
    flex-shrink: 0;
    width: auto;
    padding: 10px 16px;
    border-radius: 999px;
    background: #fff;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  }
  .oh-nav-item.active {
    background: linear-gradient(135deg, #0071e3, #5856d6);
    color: #fff;
  }
  .oh-panel { padding: 6px 14px 24px; }
  /* —— AI 助手独占模式：整页锁定视口高度，导航条/输入框/发送按钮固定，仅聊天区内部滚动 —— */
  .oh-ai-mode {
    height: 100vh;
    height: 100dvh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    padding-bottom: 0;
  }
  .oh-ai-mode .oh-header { flex: none; }
  .oh-ai-mode .oh-body { flex: 1 1 auto; min-height: 0; }
  .oh-ai-mode .oh-sidebar { flex: none; }
  .oh-ai-mode .oh-panel--ai {
    flex: 1 1 auto;
    min-height: 0;
    height: auto;
    padding-bottom: 0;
    display: flex;
    flex-direction: column;
  }
  .oh-ai-mode .oh-chat { flex: 1 1 auto; min-height: 0; margin-bottom: 0; }
  .oh-ai-mode .oh-ai-foot {
    flex: none;
    padding-bottom: calc(10px + env(safe-area-inset-bottom, 0px));
  }
}
@media (min-width: 1080px) {
  .oh-list { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .oh-header { padding-left: 24px; padding-right: 24px; }
}

/* ===== 打磨中提示弹窗 ===== */
.oh-notice-mask {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: rgba(20, 20, 30, 0.45);
  -webkit-backdrop-filter: blur(6px);
  backdrop-filter: blur(6px);
  display: grid;
  place-items: center;
  padding: 24px;
}
.oh-notice {
  width: min(92vw, 420px);
  max-height: 84vh;
  overflow-y: auto;
  background: #fff;
  border-radius: 24px;
  padding: 24px 22px 20px;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.28);
  text-align: left;
}
.oh-notice-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 4px;
}
.oh-notice-emoji {
  font-size: 30px;
  line-height: 1;
}
.oh-notice-head h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.01em;
  background: linear-gradient(120deg, #0071e3, #5856d6);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}
.oh-notice-body {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.oh-notice-body p {
  margin: 0;
  font-size: 14px;
  line-height: 1.65;
  color: #3a3a42;
}
.oh-notice-body b { color: #0071e3; }
.oh-notice-body ul {
  margin: 2px 0 2px;
  padding-left: 18px;
  color: #3a3a42;
  font-size: 14px;
  line-height: 1.7;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.oh-notice-slogan {
  margin-top: 4px;
  font-weight: 700;
  color: #1d1d1f !important;
}
.oh-notice-btn {
  width: 100%;
  margin-top: 18px;
  border: none;
  border-radius: 999px;
  padding: 12px 0;
  background: linear-gradient(135deg, #0071e3, #5856d6);
  color: #fff;
  font-size: 16px;
  font-weight: 700;
  cursor: pointer;
  box-shadow: 0 8px 18px rgba(0, 113, 227, 0.28);
}
.oh-notice-btn:active { transform: translateY(1px); }

.oh-notice-enter-active,
.oh-notice-leave-active {
  transition: opacity 0.24s ease;
}
.oh-notice-enter-active .oh-notice,
.oh-notice-leave-active .oh-notice {
  transition: transform 0.24s var(--ease-apple, ease);
}
.oh-notice-enter-from,
.oh-notice-leave-to {
  opacity: 0;
}
.oh-notice-enter-from .oh-notice,
.oh-notice-leave-to .oh-notice {
  transform: translateY(18px) scale(0.96);
}
</style>