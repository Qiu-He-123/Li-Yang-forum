<script setup lang="ts">
/**
 * 宠物 AI 管理（DeepSeek 引擎）
 *
 * 覆盖需求二「后台管理配置项」全部字段：
 * - DeepSeek API Key / Base URL / 模型选择（下拉，从官方 API 动态拉取）
 * - 主动消息间隔 / 每日主动消息最大次数 / 用户动作记录条数
 * - 每日 Token 上限 / Token 快用完阈值
 * - 赠送金币：每日 / 单次上限；增加 / 减少好感度：每日 / 单次上限
 * - 睡觉时长范围（分钟）
 * - 事件触发：看帖子详情 / 帖子列表 / 宠物商城 时长范围（秒）
 * - 连接测试 + 今日统计
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  adminPetAiConfig,
  adminPetAiModels,
  adminPetAiStats,
  adminPetAiTest,
  adminPetAiUpdateConfig,
  type PetAiConfig,
  type PetAiStats,
} from '../../api/petAi'

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const loadingModels = ref(false)

/** 表单（数值用 number，字符串用 string；enable 用 boolean） */
const form = reactive({
  pet_ai_enabled: false,
  pet_ai_api_key: '',
  pet_ai_base_url: 'https://api.deepseek.com/v1',
  pet_ai_model: 'deepseek-chat',
  pet_ai_proactive_interval_min: 30,
  pet_ai_daily_token_limit: 200000,
  pet_ai_token_warn_threshold: 30000,
  pet_ai_gift_coins_single: 5,
  pet_ai_gift_coins_daily: 50,
  pet_ai_affinity_add_single: 2,
  pet_ai_affinity_add_daily: 10,
  pet_ai_affinity_sub_single: 1,
  pet_ai_affinity_sub_daily: 5,
  pet_ai_sleep_min: 30,
  pet_ai_sleep_max: 180,
  pet_ai_event_post_detail_min: 30,
  pet_ai_event_post_detail_max: 90,
  pet_ai_event_post_list_min: 60,
  pet_ai_event_post_list_max: 180,
  pet_ai_event_pet_shop_min: 60,
  pet_ai_event_pet_shop_max: 180,
  pet_ai_event_cooldown_min: 60,
  pet_ai_daily_proactive_max: 10,
  pet_ai_user_actions_count: 10,
  pet_ai_default_persona: '',
})

// API Key 脱敏展示 / 编辑模式
const apiKeyMasked = ref('')
const apiKeyConfigured = ref(false)
const apiKeyEditing = ref(false)

const models = ref<string[]>([])
const testResult = ref<{ ok: boolean; msg: string } | null>(null)
const stats = ref<PetAiStats | null>(null)

const CONFIG_KEYS = [
  'pet_ai_enabled',
  'pet_ai_api_key',
  'pet_ai_base_url',
  'pet_ai_model',
  'pet_ai_proactive_interval_min',
  'pet_ai_daily_token_limit',
  'pet_ai_token_warn_threshold',
  'pet_ai_gift_coins_single',
  'pet_ai_gift_coins_daily',
  'pet_ai_affinity_add_single',
  'pet_ai_affinity_add_daily',
  'pet_ai_affinity_sub_single',
  'pet_ai_affinity_sub_daily',
  'pet_ai_sleep_min',
  'pet_ai_sleep_max',
  'pet_ai_event_post_detail_min',
  'pet_ai_event_post_detail_max',
  'pet_ai_event_post_list_min',
  'pet_ai_event_post_list_max',
  'pet_ai_event_pet_shop_min',
  'pet_ai_event_pet_shop_max',
  'pet_ai_event_cooldown_min',
  'pet_ai_daily_proactive_max',
  'pet_ai_user_actions_count',
  'pet_ai_default_persona',
]

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

async function load() {
  loading.value = true
  try {
    const [cfgResp, statsResp] = await Promise.all([
      adminPetAiConfig(),
      adminPetAiStats(),
    ])
    const cfg = cfgResp.data.data as unknown as Record<string, unknown>
    for (const key of CONFIG_KEYS) {
      if (key in cfg) {
        // 布尔字段单独处理
        if (key === 'pet_ai_enabled') (form as Record<string, unknown>)[key] = !!cfg[key]
        // 字符串字段单独处理
        else if (key === 'pet_ai_base_url') (form as Record<string, unknown>)[key] = String(cfg[key] || 'https://api.deepseek.com/v1')
        else if (key === 'pet_ai_model') (form as Record<string, unknown>)[key] = String(cfg[key] || 'deepseek-chat')
        else if (key === 'pet_ai_default_persona') (form as Record<string, unknown>)[key] = String(cfg[key] || '')
        else (form as Record<string, unknown>)[key] = num(cfg[key])
      }
    }
    apiKeyMasked.value = String(cfg.pet_ai_api_key || '')
    apiKeyConfigured.value = !!cfg.pet_ai_api_key_configured
    apiKeyEditing.value = false
    stats.value = statsResp.data.data
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

/** 拉取模型列表（模型下拉框数据源） */
async function loadModels(silent = false) {
  loadingModels.value = true
  try {
    const { data } = await adminPetAiModels()
    if (data.data.success) {
      models.value = data.data.models
      if (!silent && models.value.length) ElMessage.success(`已获取 ${models.value.length} 个模型`)
    } else if (!silent) {
      ElMessage.warning(data.data.error || '获取模型列表失败')
    }
  } catch (e) {
    if (!silent) ElMessage.error((e as Error).message)
  } finally {
    loadingModels.value = false
  }
}

async function onSave() {
  saving.value = true
  try {
    const payload: Record<string, unknown> = {}
    for (const key of CONFIG_KEYS) {
      if (key === 'pet_ai_api_key') continue // 由 apiKeyEditing 单独提交
      payload[key] = (form as Record<string, unknown>)[key]
    }
    // 仅在编辑模式且输入了新 key 时才提交
    if (apiKeyEditing.value && form.pet_ai_api_key.trim()) {
      payload.pet_ai_api_key = form.pet_ai_api_key.trim()
    }
    await adminPetAiUpdateConfig(payload)
    ElMessage.success('已保存配置')
    await load()
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    saving.value = false
  }
}

async function onTest() {
  testing.value = true
  testResult.value = null
  try {
    const { data } = await adminPetAiTest()
    testResult.value = data.data
    if (data.data.ok) {
      ElMessage.success(data.data.msg)
      await loadModels(true)
    } else {
      ElMessage.warning(data.data.msg)
    }
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    testing.value = false
  }
}

function onEditKey() {
  apiKeyEditing.value = true
  form.pet_ai_api_key = ''
}

function onCancelEditKey() {
  apiKeyEditing.value = false
  form.pet_ai_api_key = ''
}

function openDeepSeekOfficial() {
  window.open('https://platform.deepseek.com/api_keys', '_blank')
}

onMounted(() => {
  load()
  loadModels(true)
})
</script>

<template>
  <div v-loading="loading" class="admin-page">
    <!-- 页头 -->
    <div class="page-header">
      <div>
        <h2 class="page-title">宠物 AI 管理</h2>
        <p class="page-subtitle">基于 DeepSeek 的宠物拟人对话引擎，管理模型、主动消息、Token 与工具额度</p>
      </div>
      <div class="header-actions">
        <el-button type="primary" plain @click="openDeepSeekOfficial">前往 DeepSeek 申请密钥</el-button>
        <el-button :icon="'Refresh'" @click="load">刷新</el-button>
      </div>
    </div>

    <!-- 概览统计 -->
    <div v-if="stats" class="stats-row">
      <div class="stat-card">
        <div class="stat-num">{{ stats.ai_pet_count }}</div>
        <div class="stat-label">开启 AI 的宠物</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats.message_count }}</div>
        <div class="stat-label">累计消息</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats.today_token }}</div>
        <div class="stat-label">今日 Token</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats.today_proactive_count }}</div>
        <div class="stat-label">今日主动消息</div>
      </div>
    </div>

    <!-- 基础配置 -->
    <div class="form-card">
      <div class="card-title">
        <span class="title-text">DeepSeek 接入</span>
        <el-tag v-if="form.pet_ai_enabled" type="success" size="small">已启用</el-tag>
        <el-tag v-else type="info" size="small">未启用</el-tag>
      </div>
      <el-form label-width="150px" label-position="right" class="config-form">
        <el-form-item label="启用宠物 AI">
          <el-switch v-model="form.pet_ai_enabled" />
          <span class="form-hint">开启后，领养且逐只开启「AI 对话」的宠物可用 DeepSeek 聊天</span>
        </el-form-item>

        <el-form-item label="API Key">
          <div class="key-row">
            <template v-if="!apiKeyEditing">
              <el-input
                :model-value="apiKeyMasked || '未配置'"
                readonly
                placeholder="未配置"
                style="flex: 1"
              />
              <el-button type="primary" plain @click="onEditKey">修改</el-button>
            </template>
            <template v-else>
              <el-input
                v-model="form.pet_ai_api_key"
                type="password"
                show-password
                placeholder="请输入 DeepSeek API Key（sk-xxx）"
                style="flex: 1"
              />
              <el-button @click="onCancelEditKey">取消</el-button>
            </template>
          </div>
          <div class="form-hint">
            从
            <a href="https://platform.deepseek.com/api_keys" target="_blank" rel="noopener">DeepSeek 开放平台</a>
            获取 API Key
          </div>
        </el-form-item>

        <el-form-item label="Base URL">
          <el-input
            v-model="form.pet_ai_base_url"
            placeholder="https://api.deepseek.com/v1"
            clearable
          />
          <span class="form-hint">默认 https://api.deepseek.com/v1，兼容 OpenAI 协议</span>
        </el-form-item>

        <el-form-item label="模型选择">
          <div class="model-row">
            <el-select
              v-model="form.pet_ai_model"
              filterable
              allow-create
              placeholder="选择或输入模型名"
              style="width: 320px"
              :loading="loadingModels"
            >
              <el-option
                v-for="m in models"
                :key="m"
                :label="m"
                :value="m"
              />
            </el-select>
            <el-button :loading="loadingModels" @click="loadModels()">刷新模型列表</el-button>
          </div>
          <div class="form-hint">下拉框从 DeepSeek 官方 API（GET /models）动态拉取，也可手动输入模型名</div>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="saving" @click="onSave">保存配置</el-button>
          <el-button :loading="testing" @click="onTest">测试连接</el-button>
        </el-form-item>
      </el-form>

      <div v-if="testResult" class="test-result" :class="{ ok: testResult.ok, fail: !testResult.ok }">
        <strong>{{ testResult.ok ? '✓ 连接成功' : '✗ 连接失败' }}</strong>
        <span>{{ testResult.msg }}</span>
      </div>
    </div>

    <!-- 主动消息与 Token -->
    <div class="form-card">
      <div class="card-title">
        <span class="title-text">主动消息</span>
        <span class="form-hint">用户长时间不互动时，由决策 AI 规划何时主动联系</span>
      </div>
      <el-form label-width="150px" label-position="right" class="config-form">
        <el-form-item label="主动消息间隔（分钟）">
          <el-input-number v-model="form.pet_ai_proactive_interval_min" :min="1" :max="10080" :step="1" controls-position="right" />
          <span class="form-hint">用户与 AI 超过该时长无互动后，触发决策 AI 计算下次主动消息时间</span>
        </el-form-item>
        <el-form-item label="每日主动消息最大次数">
          <el-input-number v-model="form.pet_ai_daily_proactive_max" :min="0" :max="1000" :step="1" controls-position="right" />
          <span class="form-hint">AI 每天主动发消息的上限；事件触发也计入，0=不限制</span>
        </el-form-item>
        <el-form-item label="用户动作记录条数">
          <el-input-number v-model="form.pet_ai_user_actions_count" :min="0" :max="100" :step="1" controls-position="right" />
          <span class="form-hint">注入到 AI 上下文中的最近用户动作数量（默认 10）</span>
        </el-form-item>
      </el-form>
    </div>

    <!-- 默认提示词 -->
    <div class="form-card">
      <div class="card-title">
        <span class="title-text">默认提示词</span>
        <span class="form-hint">宠物未单独设置人设时使用的默认 AI 人设</span>
      </div>
      <el-form label-width="150px" label-position="right" class="config-form">
        <el-form-item label="提示词内容">
          <el-input
            v-model="form.pet_ai_default_persona"
            type="textarea"
            :rows="6"
            resize="vertical"
            placeholder="输入默认 AI 提示词，支持 {pet_name} / {owner} 占位符，使用 #换行符 分段"
          />
          <span class="form-hint">
            占位符说明：{pet_name} 替换为宠物名称，{owner} 替换为主人名称；
            使用 #换行符 可将 AI 回复拆分为多条消息依次发送
          </span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="onSave">保存配置</el-button>
          <el-button @click="load">恢复</el-button>
        </el-form-item>
      </el-form>
    </div>

    <div class="form-card">
      <div class="card-title">
        <span class="title-text">Token 控制</span>
        <span class="form-hint">成本控制与「困意 / 睡觉」机制</span>
      </div>
      <el-form label-width="150px" label-position="right" class="config-form">
        <el-form-item label="每日 Token 上限">
          <el-input-number v-model="form.pet_ai_daily_token_limit" :min="0" :max="100000000" :step="1000" controls-position="right" />
          <span class="form-hint">AI 每日可消耗的最大 token 数，达到后强制进入「睡觉」状态；0=不限制</span>
        </el-form-item>
        <el-form-item label="Token 快用完阈值">
          <el-input-number v-model="form.pet_ai_token_warn_threshold" :min="0" :max="100000000" :step="1000" controls-position="right" />
          <span class="form-hint">剩余 token 低于该值时 AI 启动「快睡觉模式」，回复中主动表达困意</span>
        </el-form-item>
      </el-form>
    </div>

    <!-- 工具额度 -->
    <div class="form-card">
      <div class="card-title">
        <span class="title-text">工具额度</span>
        <span class="form-hint">控制 AI 调用赠送金币 / 调整好感度等工具的频率</span>
      </div>
      <el-form label-width="150px" label-position="right" class="config-form">
        <el-form-item label="赠送金币 · 单次上限">
          <el-input-number v-model="form.pet_ai_gift_coins_single" :min="1" :max="10000" :step="1" controls-position="right" />
        </el-form-item>
        <el-form-item label="赠送金币 · 每日上限">
          <el-input-number v-model="form.pet_ai_gift_coins_daily" :min="1" :max="100000" :step="1" controls-position="right" />
        </el-form-item>
        <el-form-item label="增加好感度 · 单次上限">
          <el-input-number v-model="form.pet_ai_affinity_add_single" :min="1" :max="100" :step="1" controls-position="right" />
        </el-form-item>
        <el-form-item label="增加好感度 · 每日上限">
          <el-input-number v-model="form.pet_ai_affinity_add_daily" :min="1" :max="1000" :step="1" controls-position="right" />
        </el-form-item>
        <el-form-item label="减少好感度 · 单次上限">
          <el-input-number v-model="form.pet_ai_affinity_sub_single" :min="1" :max="100" :step="1" controls-position="right" />
        </el-form-item>
        <el-form-item label="减少好感度 · 每日上限">
          <el-input-number v-model="form.pet_ai_affinity_sub_daily" :min="1" :max="1000" :step="1" controls-position="right" />
        </el-form-item>
        <el-form-item label="睡觉时长范围（分钟）">
          <div class="range-row">
            <el-input-number v-model="form.pet_ai_sleep_min" :min="1" :max="1440" :step="1" controls-position="right" />
            <span class="range-sep">~</span>
            <el-input-number v-model="form.pet_ai_sleep_max" :min="1" :max="1440" :step="1" controls-position="right" />
          </div>
          <span class="form-hint">调用睡觉工具时在范围内随机取时长</span>
        </el-form-item>
      </el-form>
    </div>

    <!-- 事件触发 -->
    <div class="form-card">
      <div class="card-title">
        <span class="title-text">事件触发</span>
        <span class="form-hint">用户停留超过阈值时，自动触发 AI 说一句话（计入每日主动次数）</span>
      </div>
      <el-form label-width="150px" label-position="right" class="config-form">
        <el-form-item label="看帖子详情时长（秒）">
          <div class="range-row">
            <el-input-number v-model="form.pet_ai_event_post_detail_min" :min="0" :max="3600" :step="1" controls-position="right" />
            <span class="range-sep">~</span>
            <el-input-number v-model="form.pet_ai_event_post_detail_max" :min="0" :max="3600" :step="1" controls-position="right" />
          </div>
        </el-form-item>
        <el-form-item label="看帖子列表时长（秒）">
          <div class="range-row">
            <el-input-number v-model="form.pet_ai_event_post_list_min" :min="0" :max="3600" :step="1" controls-position="right" />
            <span class="range-sep">~</span>
            <el-input-number v-model="form.pet_ai_event_post_list_max" :min="0" :max="3600" :step="1" controls-position="right" />
          </div>
        </el-form-item>
        <el-form-item label="看宠物商城时长（秒）">
          <div class="range-row">
            <el-input-number v-model="form.pet_ai_event_pet_shop_min" :min="0" :max="3600" :step="1" controls-position="right" />
            <span class="range-sep">~</span>
            <el-input-number v-model="form.pet_ai_event_pet_shop_max" :min="0" :max="3600" :step="1" controls-position="right" />
          </div>
        </el-form-item>
        <el-form-item label="自动回复冷却（分钟）">
          <el-input-number v-model="form.pet_ai_event_cooldown_min" :min="0" :max="1440" :step="1" controls-position="right" />
          <span class="form-hint">同一宠物两次事件自动回复之间的最小间隔，防止"连着发"多条；0=不限制</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="onSave">保存配置</el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- 说明 -->
    <div class="form-card">
      <div class="card-title">
        <span class="title-text">使用说明</span>
      </div>
      <ol class="tips">
        <li>宠物级「AI 对话 / 主动找人 / 人设」在「宠物商城 → 编辑商品 → 宠物 AI 设定」中逐只配置。</li>
        <li>主动消息由决策 AI 基于最近聊天记录与用户动态规划发送时机，事件触发与主动消息共用每日次数。</li>
        <li>Token 耗尽自动睡觉；剩余低于阈值时 AI 会先表达困意，再继续对话直到耗尽。</li>
        <li>配置保存后即时生效，无需重启服务。</li>
      </ol>
    </div>
  </div>
</template>

<style scoped>
.admin-page {
  min-height: 100%;
}
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
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
.header-actions {
  display: flex;
  gap: 12px;
}
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-bottom: 16px;
}
.stat-card {
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 18px 20px;
  text-align: center;
}
.stat-num {
  font-size: 26px;
  font-weight: 700;
  color: #1890ff;
}
.stat-label {
  font-size: 12px;
  color: #8c8c8c;
  margin-top: 4px;
}
.form-card,
.result-card {
  background: #fff;
  padding: 20px 24px;
  border-radius: 8px;
  border: 1px solid #f0f0f0;
  margin-bottom: 16px;
}
.card-title {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f0f0;
}
.title-text {
  font-size: 16px;
  font-weight: 600;
  color: #1f1f1f;
}
.config-form {
  max-width: 760px;
}
.form-hint {
  margin-left: 12px;
  font-size: 12px;
  color: #8c8c8c;
}
.form-hint a {
  color: #1890ff;
  text-decoration: none;
}
.form-hint a:hover {
  text-decoration: underline;
}
.key-row {
  display: flex;
  gap: 8px;
  width: 100%;
}
.model-row {
  display: flex;
  gap: 8px;
  width: 100%;
}
.range-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.range-sep {
  color: #8c8c8c;
  font-size: 14px;
}
.test-result {
  margin-top: 12px;
  padding: 12px 16px;
  border-radius: 6px;
  font-size: 13px;
  display: flex;
  gap: 8px;
}
.test-result.ok {
  background: #f6ffed;
  color: #389e0d;
}
.test-result.fail {
  background: #fff2f0;
  color: #cf1322;
}
.tips {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: #595959;
  line-height: 1.9;
}
@media (max-width: 768px) {
  .stats-row {
    grid-template-columns: repeat(2, 1fr);
  }
  .model-row {
    flex-direction: column;
    align-items: flex-start;
  }
  .model-row .el-select {
    width: 100% !important;
  }
}
</style>
