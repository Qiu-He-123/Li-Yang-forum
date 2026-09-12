<script setup lang="ts">
/**
 * 全局 AI 助手（漂浮按钮 + 底部抽屉）
 * 用户用自然语言告诉 AI"想做/要去哪"，AI 解析意图并引导完成操作：
 * - 支持项目 2 交易平台 / 广场 / 商城 / 活动等全部站点操作
 * - 匹配到意图直接跳转，匹配不到给出建议入口
 */
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { useSessionStore } from '../stores/session'
import { http } from '../api/http'
import { Icon } from './native'
import { aiFabEnabled, getAiFabPos, setAiFabPos } from '../utils/aiFab'

const open = ref(false)
const input = ref('')
const history: string[] = []
const busy = ref(false)

// ===== 点我提问：登录才显示 + 可拖动 + 记忆位置 + 设置开关 =====
const fabLeft = ref(14)
const fabTop = ref<number>(0)
const dragging = ref(false)

function fabVisible(): boolean {
  return aiFabEnabled.value && !!session.userId
}

/** 计算悬浮按钮位置：靠边贴住，避免拖出可视区。 */
function boundFab(left: number, top: number) {
  const fallbackW = 132 // 按钮约 132px 宽
  const fallbackH = 46
  const maxLeft = window.innerWidth - fallbackW - 8
  const maxTop = Math.max(10, window.innerHeight - fallbackH - 80)
  fabLeft.value = Math.max(8, Math.min(maxLeft, left))
  fabTop.value = Math.max(10, Math.min(maxTop, top))
}

function initFabPos() {
  const saved = getAiFabPos()
  if (saved) {
    boundFab(saved.left, saved.top)
  } else {
    fabTop.value = window.innerHeight - 80 - 46 // 默认贴底
    boundFab(fabLeft.value, fabTop.value)
  }
}

let dragState: { startX: number; startY: number; left: number; top: number } | null = null

function onFabDown(e: PointerEvent) {
  dragState = { startX: e.clientX, startY: e.clientY, left: fabLeft.value, top: fabTop.value }
  dragging.value = true
}

function onFabMove(e: PointerEvent) {
  if (!dragState) return
  e.preventDefault()
  const dx = e.clientX - dragState.startX
  const dy = e.clientY - dragState.startY
  boundFab(dragState.left + dx, dragState.top + dy)
}

function onFabUp() {
  if (!dragState) return
  dragState = null
  dragging.value = false
  setAiFabPos({ left: fabLeft.value, top: fabTop.value })
}

onMounted(() => {
  initFabPos()
})

interface Intent {
  keys: string[]
  /** 引导文案（命中后展示并一般会跳转到目标页） */
  text?: string
  /** 纯文字回答：命中后只回复、不跳转（寒暄/答疑场景） */
  respond?: string
  run?: (router: ReturnType<typeof useRouter>) => void
  needAuth?: boolean
}

const router = useRouter()
const session = useSessionStore()

const reply = ref('')
const done = ref(false)

/** 常见操作意图表：每一项都是站点内真实可完成的操作 */
const intents: Intent[] = [
  // ===== 寒暄/答疑：纯文字回复，不跳转、不弹入口 =====
  {
    keys: ['你是谁', '你是', '什么助手', '你是干嘛'],
    respond:
      '我是同伴圈的 AI 助手呀～能帮你找单、发单、看钱包、逛广场、喂宠物、开组局…想去哪或想做什么，直接跟我说就行，我会直接带你过去。',
  },
  {
    keys: ['你好', '在吗', '嗨', 'hello', 'hi', '哈喽'],
    respond: '你好呀 👋 需要我帮你做点什么？找单、发单、逛官网都可以直接开口。',
  },
  {
    keys: ['谢谢', '感谢', '谢了', '辛苦了'],
    respond: '不客气～能帮上忙就好。还有别的事随时喊我。',
  },
  {
    keys: ['能干嘛', '有什么用', '能做什么', '会什么', '功能'],
    respond:
      '我现在能帮你：1️⃣ 找单/接单 2️⃣ 发布带悬赏的任务 3️⃣ 看交易币钱包 4️⃣ 逛广场、发动态 5️⃣ 喂宠物、逛商城 6️⃣ 开组局、漂流瓶、金币中心…想知道哪个，把需求说出来就行。',
  },
  { keys: ['再见', '拜拜', '晚安', '走了', '下A'], respond: '好嘞，再见～有需要随时找我。' },
  { keys: ['接单', '接个单', '接任务', '我要接', '帮我接', '大厅', '任务大厅', '找任务', '赚钱', '做任务', '互助', '校园任务', '看任务', '找单'], text: '前往接单大厅看看', needAuth: true, run: (r) => r.push('/orders?tab=hall') },
  { keys: ['发布任务', '发个任务', '发任务', '发布一个', '求助', '找人办事', '悬赏', '发单', '我想发布', '帮我发'], text: '发布求助任务（悬赏交易币）', needAuth: true, run: (r) => r.push('/orders/publish') },
  { keys: ['我的订单', '我发布的', '我接的'], text: '查看我的订单', needAuth: true, run: (r) => r.push('/orders/my') },
  { keys: ['钱包', '充值', '提现', '交易币', '兑换', '余额'], text: '进入交易币钱包（充值/提现）', needAuth: true, run: (r) => r.push('/orders/wallet') },
  { keys: ['商城', '宠物', '云养', '领养', '买宠物', '装扮', '道具'], text: '前往宠物商城', run: (r) => r.push('/pet-shop') },
  { keys: ['我的宠物', '我的萌宠', '看看宠物', '宠物状态'], text: '进入我的养宠面板', needAuth: true, run: (r) => r.push('/pet-play') },
  { keys: ['签到', '打卡', '领金币', '金币', '积分', '福利'], text: '打开金币中心领取金币', needAuth: true, run: (r) => r.push('/coins') },
  { keys: ['活动', '官方活动', '报名'], text: '打开活动中心', run: (r) => r.push('/activities') },
  { keys: ['组局', '开黑', '房间', '联机'], text: '看看组局/房间', run: (r) => r.push('/gatherings') },
  { keys: ['发帖', '发动态', '发布', '写帖子', '记录', '发个动态', '新动态', '发条', '匿名'], text: '去发布一条新动态', needAuth: true, run: (r) => r.push('/post/create') },
  { keys: ['官网', '项目', '主页', '作品', '公司'], text: '前往西果官方网站', run: (r) => r.push('/xiguo') },
  { keys: ['广场', '首页', '看看', '逛逛', '帖子', '动态'], text: '回到广场首页', run: (r) => r.push('/') },
  { keys: ['评论', '回复'], text: '去广场看看帖子并参与评论', run: (r) => r.push('/') },
  { keys: ['帮我', '配对', '缘分', '交友', '同城'], text: '打开缘分/邂逅功能', needAuth: true, run: (r) => r.push('/match') },
  { keys: ['瓶子', '漂流瓶', '许愿'], text: '去漂流瓶许个愿', needAuth: true, run: (r) => r.push('/bottle') },
  { keys: ['圈子', '社区'], text: '浏览圈子列表', run: (r) => r.push('/circles') },
  { keys: ['游戏', '玩法', '小游戏', '玩耍', '戳'], text: '打开各种小游戏', run: (r) => r.push('/pet-play') },
  { keys: ['消息', '通知', '私信', '未读'], text: '查看消息通知', needAuth: true, run: (r) => r.push('/notifications') },
  { keys: ['设置', '改密码', '隐私', '通知设置'], text: '打开设置', needAuth: true, run: (r) => r.push('/settings') },
  { keys: ['我的资料', '改名', '头像', '资料', '个人信息'], text: '打开我的个人主页', needAuth: true, run: (r) => r.push('/settings') },
  { keys: ['反馈', '意见', '投诉', '建议'], text: '进入意见反馈（被采纳可加金币）', run: (r) => r.push('/feedback') },
]

function parse(currentInput: string): Intent | null {
  const lower = currentInput.toLowerCase()
  for (const it of intents) {
    if (it.keys.some((k) => lower.includes(k.toLowerCase()))) return it
  }
  return null
}

async function ask() {
  const text = input.value.trim()
  if (!text || busy.value) return
  history.push(text)
  busy.value = true
  done.value = false
  reply.value = '让我想想你要做什么…'
  await nextTick()

  const intent = parse(text)
  await nextTick()
  await wait(450)

  if (!intent) {
    reply.value = '帮你找到这些入口，选一个点进去就能搞定 👇'
    done.value = true
    busy.value = false
    input.value = ''
    logAssistant(text, intent, false)
    return
  }

  // 寒暄/答疑意图：只回复文字，不跳转、不弹入口
  if (intent.respond) {
    reply.value = intent.respond
    done.value = true
    busy.value = false
    input.value = ''
    logAssistant(text, intent, true)
    return
  }

  if (intent.needAuth && !session.userId) {
    reply.value = `这个操作需要先登录。${intent.text}（登录后才能进行）👇`
    done.value = true
    busy.value = false
    input.value = ''
    logAssistant(text, intent, true)
    return
  }

  reply.value = `好的，这就带你去做：${intent.text}`
  done.value = true
  busy.value = false
  input.value = ''
  logAssistant(text, intent, true)
  await wait(350)
  intent.run?.(router)
  close()
}

function wait(ms: number) {
  return new Promise((r) => setTimeout(r, ms))
}

/** best-effort 埋点：把一次 AI 会话记入后端日志（失败静默，不影响体验）。 */
function logAssistant(text: string, intent: Intent | null, hit: boolean) {
  if (!session.userId) return
  http
    .post('/assistant/log', {
      input: text.slice(0, 255),
      intent: intent?.keys?.[0] ?? '',
      reply: (reply.value || '').slice(0, 2000),
      action: intent?.text ?? '',
      hit,
    })
    .catch(() => {
      /* 静默 */
    })
}

function close() {
  open.value = false
  reply.value = ''
  done.value = false
}

function toggle() {
  open.value = !open.value
  if (open.value) {
    reply.value = ''
    done.value = false
    pickExamples() // 每次打开随机换一批示例
  }
}

function useQuick(intent: Intent) {
  intent.run?.(router)
  close()
}

// ===== 可选的「试试这样对我说」示例池：随机抽取、支持刷新 =====
const examplePool: string[] = [
  '我想发布一个任务，悬赏找人帮忙',
  '接单大厅有什么单可以接？',
  '钱包怎么充交易币？',
  '带我去宠物商城',
  '去活动中心看看有什么活动',
  '帮我发个代取快递的单，悬赏20币',
  '我要发一条新动态',
  '看看今天我该干嘛',
  '找学弟代点名怎么发单',
  '想去官网逛逛',
  '今天签到的金币在哪领？',
  '开一局游戏组局',
  '帮我看看交易币余额',
  '去漂流瓶许个愿',
  '最近有什么校园互助任务？',
  '心里话想匿名发出去',
]
const shownExamples = ref<string[]>([])
function pickExamples(n = 6) {
  const pool = [...examplePool]
  const picked: string[] = []
  const count = Math.min(n, pool.length)
  for (let i = 0; i < count; i++) {
    const idx = Math.floor(Math.random() * pool.length)
    picked.push(pool.splice(idx, 1)[0])
  }
  shownExamples.value = picked
}
function refreshExamples() {
  pickExamples()
}

/** 快捷建议：精选多样入口供直接点击 */
const quickSuggestions = computed(() => {
  const all = intents
  const pick = ['前往接单大厅看看', '发布求助任务（悬赏交易币）', '打开金币中心领取金币', '去看看各种小游戏', '去漂流瓶许个愿', '进入意见反馈（被采纳可加金币）']
  return all.filter((it): it is Intent & { text: string } => !!it.text && pick.includes(it.text)).slice(0, 6)
})
</script>

<template>
  <!-- 漂浮 AI 按钮（可拖动 + 记住位置；仅登录显示；设置中可关闭） -->
  <button
    v-if="fabVisible() && !open"
    class="ai-fab"
    :class="{ 'ai-fab--dragging': dragging }"
    :style="{ left: fabLeft + 'px', top: fabTop + 'px' }"
    type="button"
    aria-label="打开 AI 助手提问"
    title="想知道什么？点我提问"
    @pointerdown="onFabDown"
    @pointermove="onFabMove"
    @pointerup="onFabUp"
    @pointercancel="onFabUp"
    @pointerdown.stop
    @click="toggle"
  >
    <span class="ai-fab-ring" aria-hidden="true"></span>
    <span class="ai-fab-icon"><Icon name="sparkles" :size="22" /></span>
    <span class="ai-fab-label">点我提问</span>
  </button>

  <Teleport to="body">
    <Transition name="ai-pop">
      <div v-if="open" class="ai-mask" @click.self="close">
        <div class="ai-sheet" role="dialog" aria-modal="true">
          <header class="ai-head">
            <div class="ai-avatar">
              <Icon name="sparkles" :size="18" />
            </div>
            <div class="ai-head-txt">
              <h2>AI 助手</h2>
              <p>告诉我你想做什么，我来帮你完成</p>
            </div>
            <button class="ai-close" type="button" aria-label="关闭" @click="close">
              <Icon name="x" :size="20" />
            </button>
          </header>

          <div class="ai-chat">
            <div v-if="reply" class="ai-bubble" :class="{ 'ai-bubble--out': !done }">
              <span class="ai-dot" v-for="i in 3" :key="i"></span>
              <span v-if="!done" class="ai-bubble-txt">{{ reply }}</span>
              <template v-else>
                <span class="ai-bubble-txt" v-html="reply.replace(/(👇)/g, '<br/>')"></span>
                <div class="ai-chips">
                  <button v-for="it in quickSuggestions" :key="it.text" type="button" class="ai-chip" @click="useQuick(it)">
                    {{ it.text }}
                  </button>
                </div>
              </template>
            </div>
            <div v-else class="ai-hint">
              <p class="ai-hint-title">试试这样对我说：</p>
              <ul class="ai-examples">
                <li v-for="(ex, i) in shownExamples" :key="i">
                  <button type="button" @click="input = ex">“{{ ex }}”</button>
                </li>
              </ul>
              <button type="button" class="ai-refresh" @click="refreshExamples">
                换一批示例 ↻
              </button>
            </div>
          </div>

          <footer class="ai-foot">
            <input
              v-model="input"
              class="ai-input"
              type="text"
              maxlength="80"
              placeholder="说出你想做的事…"
              @keydown.enter="ask"
            />
            <button class="ai-send" type="button" :disabled="busy" @click="ask">
              <Icon name="send" :size="18" />
            </button>
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.ai-fab {
  position: fixed;
  /* left/top 由 inline 样式控制，支持拖动与记忆位置 */
  z-index: 960;
  height: 46px;
  padding: 0 16px 0 8px;
  border: none;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: linear-gradient(135deg, #0a0a0f, #2b2b35);
  color: #fff;
  cursor: grab;
  touch-action: none;
  box-shadow: 0 8px 22px rgba(17, 17, 26, 0.32);
  transition: box-shadow 0.14s ease;
  user-select: none;
  -webkit-user-select: none;
}
.ai-fab--dragging { cursor: grabbing; box-shadow: 0 12px 30px rgba(17, 17, 26, 0.5); }
.ai-fab-label {
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  white-space: nowrap;
  letter-spacing: 0.01em;
}
.ai-fab-icon {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: rgba(255, 255, 255, 0.12);
}
.ai-fab-ring {
  position: absolute;
  inset: -4px;
  border-radius: 999px;
  border: 1px solid rgba(124, 98, 255, 0.5);
  animation: ai-ring 2.4s infinite;
}
@keyframes ai-ring {
  0% { opacity: 0.7; transform: scale(0.98); }
  70%, 100% { opacity: 0; transform: scale(1.12); }
}

.ai-mask {
  position: fixed;
  inset: 0;
  z-index: 2000;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: flex-end;
  justify-content: center;
}
.ai-sheet {
  width: 100%;
  max-width: 560px;
  height: 72vh;
  background: #fff;
  border-radius: 22px 22px 0 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.ai-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 18px;
  border-bottom: 1px solid #f0f0f2;
}
.ai-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: #fff;
  background: linear-gradient(135deg, #5856d6, #8a3ffc);
}
.ai-head-txt { flex: 1; }
.ai-head-txt h2 { margin: 0; font-size: 17px; font-weight: 800; }
.ai-head-txt p { margin: 2px 0 0; font-size: 12px; color: #8e8e93; }
.ai-close { width: 32px; height: 32px; border: none; background: #f0f0f2; border-radius: 50%; cursor: pointer; display: grid; place-items: center; color: #5a5a62; }

.ai-chat { flex: 1; overflow-y: auto; padding: 18px; background: #fafafa; }
.ai-hint-title { margin: 0 0 12px; font-size: 14px; font-weight: 700; color: #1d1d1f; }
.ai-examples { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 8px; }
.ai-examples li button {
  width: 100%;
  text-align: left;
  padding: 11px 14px;
  border: 1px solid #ececf0;
  border-radius: 12px;
  background: #fff;
  color: #3a3a42;
  font-size: 13px;
  cursor: pointer;
}
.ai-examples li button:hover { border-color: #5856d6; color: #5856d6; }
.ai-refresh {
  margin-top: 12px;
  width: 100%;
  padding: 9px 0;
  border: 1px dashed #c8c9d4;
  border-radius: 12px;
  background: transparent;
  color: #6e6e73;
  font-size: 13px;
  cursor: pointer;
  transition: color 0.15s ease, border-color 0.15s ease, background 0.15s ease;
}
.ai-refresh:hover { color: #5856d6; border-color: #5856d6; background: #f7f6ff; }

.ai-bubble {
  max-width: 100%;
  padding: 13px 15px;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}
.ai-bubble--out { background: #f0f0ff; }
.ai-bubble-txt { font-size: 14px; line-height: 1.7; color: #1d1d1f; }
.ai-bubble .ai-dot:nth-of-type(1) { animation: blink 1s infinite; }
.ai-bubble .ai-dot:nth-of-type(2) { animation: blink 1s 0.2s infinite; }
.ai-bubble .ai-dot:nth-of-type(3) { animation: blink 1s 0.4s infinite; }
@keyframes blink { 50% { opacity: 0.2; } }
.ai-dot { display: none; }
.ai-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.ai-chip {
  padding: 7px 13px;
  border-radius: 999px;
  border: 1px solid #e0e0ea;
  background: #fff;
  color: #5856d6;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.ai-foot { display: flex; gap: 10px; padding: 12px 14px calc(14px + env(safe-area-inset-bottom, 0px)); border-top: 1px solid #f0f0f2; }
.ai-input {
  flex: 1;
  height: 44px;
  padding: 0 16px;
  border: 1px solid #e5e5ea;
  border-radius: 22px;
  font-size: 15px;
  outline: none;
  box-sizing: border-box;
}
.ai-input:focus { border-color: #5856d6; box-shadow: 0 0 0 3px rgba(88, 86, 214, 0.12); }
.ai-send {
  width: 44px;
  height: 44px;
  border: none;
  border-radius: 50%;
  background: linear-gradient(135deg, #5856d6, #8a3ffc);
  color: #fff;
  cursor: pointer;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.ai-send:disabled { opacity: 0.5; }

.ai-pop-enter-active, .ai-pop-leave-active { transition: all 0.25s var(--ease-apple, ease); }
.ai-pop-enter-from, .ai-pop-leave-to { opacity: 0; }
.ai-pop-enter-from .ai-sheet, .ai-pop-leave-to .ai-sheet { transform: translateY(100%); }

@media (min-width: 720px) {
  .ai-sheet { height: 640px; border-radius: 22px; margin-bottom: 4vh; }
}
</style>