<script setup lang="ts">
/**
 * 宠物拜访场景（Teleport 到 body，覆盖在目标卡片上方）
 * - 访客宠物（我的漂浮宠）飞到"自己的帖子"卡片内做互动
 * - hostPet=false（本人帖子，卡片未展示对方宠物）→ 单宠拜访；不再做"双宠互动"
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { MyPetItem } from '../../api/petShop'
import PetAnimation from './PetAnimation.vue'
import { pickInteractions, type PetInteraction } from './petInteractions'

const props = withDefaults(
  defineProps<{
    /** 访客（我的）宠物 */
    visitor: MyPetItem
    /** 对方宠物名 */
    hostName: string
    /** 是否有对方宠物（本人帖子=false → 单宠拜访） */
    hostPet?: boolean
    /** 目标卡片屏幕矩形（用于初次落位） */
    origin: { x: number; y: number; width: number; height: number }
    /** 每个互动的展示时长 ms */
    stepMs?: number
    /** 互动个数 */
    count?: number
  }>(),
  { hostPet: false, stepMs: 1800, count: 3 },
)

const emit = defineEmits<{ (e: 'finish'): void }>()

const visitorName = computed<string>(() => props.visitor.nickname || props.visitor.name || '我')

const interaction = ref<PetInteraction | null>(null)
const bubble = ref('')
const step = ref(0)

const stylePos = computed(() => ({
  left: props.origin.x + 'px',
  top: props.origin.y + 'px',
  width: Math.max(150, props.origin.width) + 'px',
}))

function actionFor(key: string): string {
  return key
}

let stepTimer: number | null = null

function runNext(i: number) {
  if (i >= props.count) {
    finish()
    return
  }
  step.value = i
  const act = pickInteractions(1)[0] ?? {
    key: 'wave',
    emoji: '👋',
    mine: 'interact',
    theirs: 'interact',
    text: '一起玩！',
  }
  interaction.value = act
  bubble.value = act.text
    .replace('{mine}', visitorName.value)
    .replace('{theirs}', props.hostName || '伙伴')
  stepTimer = window.setTimeout(() => runNext(i + 1), props.stepMs)
}

function finish() {
  if (stepTimer !== null) window.clearTimeout(stepTimer)
  stepTimer = null
  emit('finish')
}

onMounted(() => {
  runNext(0)
})

onBeforeUnmount(() => {
  if (stepTimer !== null) window.clearTimeout(stepTimer)
})
</script>

<template>
  <Teleport to="body">
    <div class="pet-visit-scene" :style="stylePos">
      <Transition name="pv-bubble" appear>
        <div v-if="interaction" class="pv-bubble">
          <span class="pv-bubble__emoji">{{ interaction.emoji }}</span>
          <span class="pv-bubble__text">{{ bubble }}</span>
        </div>
      </Transition>
      <div class="pv-stage">
      <!-- 访客（我的） -->
      <div class="pv-side pv-side--visitor">
        <PetAnimation :key="visitor.id" :anim="visitor.anim" :action="interaction ? actionFor(interaction.mine) : 'stand'" :size="54" :interactive="false" :show-tabs="false" />
        <span class="pv-name">{{ visitorName }}</span>
      </div>
      <!-- 有对方宠物才展示"双宠互动"舞台 -->
      <template v-if="hostPet">
        <span class="pv-vs">VS</span>
        <div class="pv-side">
          <div class="pv-host-emtpy">
            <span class="pv-host-icon">🧸</span>
          </div>
          <span class="pv-name">{{ hostName }}</span>
        </div>
      </template>
    </div>
    </div>
  </Teleport>
</template>

<style scoped>
.pet-visit-scene {
  position: fixed;
  z-index: 1750;
  pointer-events: none;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.pv-bubble {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(23, 32, 64, 0.1);
  box-shadow: 0 4px 16px rgba(23, 32, 64, 0.14);
  font-size: 13px;
  color: #172040;
  max-width: 200px;
}
.pv-bubble__emoji {
  font-size: 18px;
}
.pv-bubble__text {
  line-height: 1.4;
}
.pv-stage {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(6px);
  border: 1px solid rgba(23, 32, 64, 0.06);
}
.pv-side {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}
.pv-name {
  font-size: 11px;
  color: #6b7280;
  max-width: 60px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pv-host-emtpy {
  width: 54px;
  height: 54px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 30px;
  background: rgba(47, 107, 255, 0.06);
  border-radius: 12px;
}
.pv-vs {
  font-size: 12px;
  font-weight: 700;
  color: #2f6bff;
  padding-bottom: 18px;
}
.pv-bubble-enter-active,
.pv-bubble-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease;
}
.pv-bubble-enter-from,
.pv-bubble-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>