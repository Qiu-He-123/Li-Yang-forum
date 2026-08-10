<script setup lang="ts">
/**
 * AI 审核配置（DeepSeek）
 *
 * 功能：
 * - 启用/禁用 DeepSeek AI 审核
 * - 配置 API Key / Base URL / 模型名
 * - 配置审核失败内容自动删除天数
 * - 测试连接（一键验证配置是否正确）
 * - 在线试审文本（验证 AI 审核效果）
 * - 显示当前 AI 审核人设（system prompt）
 * - 一键跳转 DeepSeek 官网申请密钥
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  adminCleanupAudit,
  adminDeepSeekAuditText,
  adminDeepSeekTest,
  adminGetDeepSeekPrompts,
  adminGetDeepSeekConfig,
  adminUpdateDeepSeekConfig,
  type DeepSeekAuditResult,
  type DeepSeekConfig,
  type DeepSeekTestResult,
} from '../../api/admin'

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const auditing = ref(false)
const cleaning = ref(false)

const config = reactive<DeepSeekConfig>({
  enabled: false,
  api_key: '',
  base_url: 'https://api.deepseek.com/v1',
  model: 'deepseek-chat',
  auto_delete_days: 0,
  audit_scope: ['post', 'comment', 'bottle', 'image'],
  manual_review_triggers: ['ai_unavailable'],
})

// 审核范围选项
const scopeOptions = [
  { label: '帖子（标题 + 正文）', value: 'post', hint: '发布 / 编辑帖子时用 AI 审核标题与正文' },
  { label: '评论', value: 'comment', hint: '发表评论时用 AI 审核' },
  { label: '漂流瓶', value: 'bottle', hint: '投放漂流瓶时用 AI 审核内容' },
  { label: '帖子图片', value: 'image', hint: '含图片的帖子直接转人工审核（AI 暂不支持图片识别）' },
]

// 人工复核触发条件选项
const triggerOptions = [
  {
    label: 'AI 服务不可用',
    value: 'ai_unavailable',
    hint: '未开启 / 未配置 Key / 无额度 / 调用失败时转人工审核，不直接放行',
  },
  {
    label: 'AI 判定违规',
    value: 'violation',
    hint: 'AI 判定违规时保留内容转人工复核，不自动拦截、不累计警告',
  },
  {
    label: '中 / 高严重度违规',
    value: 'high_severity',
    hint: 'AI 判定为 high / medium 严重度时强制转人工复核',
  },
  {
    label: '敏感类别',
    value: 'sensitive_category',
    hint: '涉及政治敏感 / 色情 / 暴力 / 违法 / 欺凌 / 自残 / 隐私等类别时强制转人工复核',
  },
]

// 显示用脱敏 key（首次加载后展示，编辑时显示明文）
const apiKeyMasked = ref('')
const apiKeyEditing = ref(false)

const testResult = ref<DeepSeekTestResult | null>(null)
const auditInput = ref('')
const auditResult = ref<DeepSeekAuditResult | null>(null)
const cleanupResult = ref<{ enabled: boolean; days: number; deleted_posts: number; deleted_comments: number } | null>(null)

// AI 审核人设（从后端接口实时获取，与线上使用保持一致）
const prompts = ref<Record<string, string>>({})
const promptLabels: Record<string, string> = {
  post: '帖子（标题+正文）',
  comment: '评论',
  bottle: '漂流瓶',
  generic: '通用文本',
}
const activePromptTab = ref('post')

// 在线试审的场景选择（决定用哪套 prompt）
const auditScenario = ref('generic')
const auditScenarioOptions = [
  { value: 'post', label: '帖子（标题+正文）' },
  { value: 'comment', label: '评论' },
  { value: 'bottle', label: '漂流瓶' },
  { value: 'generic', label: '通用文本' },
]

async function load() {
  loading.value = true
  try {
    const [cfgResp, promptsResp] = await Promise.all([
      adminGetDeepSeekConfig(),
      adminGetDeepSeekPrompts(),
    ])
    const { data } = cfgResp
    const cfg = data.data
    config.enabled = !!cfg.enabled
    config.base_url = cfg.base_url || 'https://api.deepseek.com/v1'
    config.model = cfg.model || 'deepseek-chat'
    config.auto_delete_days = Number(cfg.auto_delete_days || 0)
    config.audit_scope = Array.isArray(cfg.audit_scope) ? [...cfg.audit_scope] : ['post', 'comment', 'bottle', 'image']
    config.manual_review_triggers = Array.isArray(cfg.manual_review_triggers)
      ? [...cfg.manual_review_triggers]
      : ['ai_unavailable']
    // API Key 不回显明文，仅显示脱敏
    apiKeyMasked.value = maskKey(cfg.api_key || '')
    config.api_key = cfg.api_key || ''
    apiKeyEditing.value = false

    prompts.value = promptsResp.data.data.prompts || {}
    const labels = promptsResp.data.data.labels || {}
    Object.assign(promptLabels, labels)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

function maskKey(key: string): string {
  if (!key) return ''
  if (key.length <= 8) return '*'.repeat(key.length)
  return key.slice(0, 4) + '*'.repeat(key.length - 8) + key.slice(-4)
}

async function onSave() {
  saving.value = true
  try {
    const payload: Partial<DeepSeekConfig> = {
      enabled: config.enabled,
      base_url: config.base_url,
      model: config.model,
      auto_delete_days: Number(config.auto_delete_days) || 0,
      audit_scope: [...config.audit_scope],
      manual_review_triggers: [...config.manual_review_triggers],
    }
    // 仅在编辑模式且输入了新 key 时才提交
    if (apiKeyEditing.value && config.api_key) {
      payload.api_key = config.api_key
    }
    await adminUpdateDeepSeekConfig(payload)
    ElMessage.success('已保存配置')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    saving.value = false
  }
}

async function onTest() {
  testing.value = true
  testResult.value = null
  try {
    // 测试前先保存当前表单（避免测试旧配置）
    await onSave()
    const { data } = await adminDeepSeekTest()
    testResult.value = data.data
    if (data.data.ok) {
      ElMessage.success(data.data.msg)
    } else {
      ElMessage.warning(data.data.msg)
    }
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    testing.value = false
  }
}

async function onAudit() {
  if (!auditInput.value.trim()) {
    ElMessage.warning('请输入待审核文本')
    return
  }
  auditing.value = true
  auditResult.value = null
  try {
    const { data } = await adminDeepSeekAuditText(auditInput.value, auditScenario.value)
    auditResult.value = data.data
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    auditing.value = false
  }
}

async function onCleanup() {
  try {
    await ElMessageBox.confirm(
      `确认立即清理审核失败超过 ${config.auto_delete_days} 天的内容？此操作不可恢复。`,
      '自动清理',
      { type: 'warning' },
    )
  } catch {
    return
  }
  cleaning.value = true
  cleanupResult.value = null
  try {
    const { data } = await adminCleanupAudit()
    cleanupResult.value = data.data
    if (data.data.enabled) {
      ElMessage.success(`已清理 ${data.data.deleted_posts + data.data.deleted_comments} 条`)
    } else {
      ElMessage.info('未启用自动删除（天数为 0）')
    }
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    cleaning.value = false
  }
}

function onEditKey() {
  apiKeyEditing.value = true
  config.api_key = ''
}

function onCancelEditKey() {
  apiKeyEditing.value = false
  config.api_key = ''
}

function openDeepSeekOfficial() {
  window.open('https://platform.deepseek.com/api_keys', '_blank')
}

const severityMeta: Record<string, { type: 'success' | 'warning' | 'danger' | 'info'; text: string }> = {
  high: { type: 'danger', text: '严重' },
  medium: { type: 'warning', text: '中等' },
  low: { type: 'info', text: '轻微' },
  none: { type: 'info', text: '无' },
}

onMounted(() => load())
</script>

<template>
  <div v-loading="loading" class="admin-page">
    <!-- 页头 -->
    <div class="page-header">
      <div>
        <h2 class="page-title">AI 审核配置</h2>
        <p class="page-subtitle">基于 DeepSeek 的智能内容审核，自动判定帖子和评论是否违规</p>
      </div>
      <div class="header-actions">
        <el-button type="primary" plain @click="openDeepSeekOfficial">前往 DeepSeek 申请密钥</el-button>
        <el-button :icon="'Refresh'" @click="load">刷新</el-button>
      </div>
    </div>

    <!-- 配置表单 -->
    <div class="form-card">
      <div class="card-title">
        <span class="title-text">基础配置</span>
        <el-tag v-if="config.enabled" type="success" size="small">已启用</el-tag>
        <el-tag v-else type="info" size="small">未启用</el-tag>
      </div>

      <el-form label-width="140px" label-position="right" class="config-form">
        <el-form-item label="启用 DeepSeek">
          <el-switch v-model="config.enabled" />
          <span class="form-hint">开启后，按下方「审核范围」对帖子、评论、漂流瓶等内容进行 AI 审核</span>
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
                v-model="config.api_key"
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
            v-model="config.base_url"
            placeholder="https://api.deepseek.com/v1"
            clearable
          />
          <span class="form-hint">默认 https://api.deepseek.com/v1，兼容 OpenAI 协议</span>
        </el-form-item>

        <el-form-item label="模型名">
          <el-input
            v-model="config.model"
            placeholder="deepseek-chat"
            clearable
          />
          <span class="form-hint">推荐 deepseek-chat（通用对话模型，性价比高）</span>
        </el-form-item>

        <el-form-item label="自动删除天数">
          <el-input-number
            v-model="config.auto_delete_days"
            :min="0"
            :max="365"
            :step="1"
            controls-position="right"
          />
          <span class="form-hint">审核失败（rejected）的内容超过 N 天后自动删除；0 表示不自动删除</span>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="saving" @click="onSave">保存配置</el-button>
          <el-button :loading="testing" @click="onTest">测试连接</el-button>
          <el-button
            type="warning"
            plain
            :loading="cleaning"
            :disabled="!config.auto_delete_days"
            @click="onCleanup"
          >
            立即清理过期内容
          </el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- 审核范围与人工复核策略 -->
    <div class="form-card">
      <div class="card-title">
        <span class="title-text">审核范围与人工复核策略</span>
        <span class="form-hint">控制哪些内容需要审核、哪些情况转人工复核</span>
      </div>

      <el-form label-width="140px" label-position="right" class="config-form">
        <el-form-item label="需要审核的内容">
          <div class="scope-group">
            <el-checkbox-group v-model="config.audit_scope">
              <el-checkbox v-for="opt in scopeOptions" :key="opt.value" :value="opt.value">
                <div class="opt-label">{{ opt.label }}</div>
                <div class="opt-hint">{{ opt.hint }}</div>
              </el-checkbox>
            </el-checkbox-group>
            <div v-if="!config.audit_scope.length" class="scope-empty">
              未选择任何范围 = 全部内容免审直接放行（不推荐）
            </div>
          </div>
        </el-form-item>

        <el-form-item label="转人工复核">
          <div class="scope-group">
            <el-checkbox-group v-model="config.manual_review_triggers">
              <el-checkbox v-for="opt in triggerOptions" :key="opt.value" :value="opt.value">
                <div class="opt-label">{{ opt.label }}</div>
                <div class="opt-hint">{{ opt.hint }}</div>
              </el-checkbox>
            </el-checkbox-group>
            <div class="scope-note">
              除以上可配置条件外，以下情况固定进入人工审核，无法关闭：管理员手动审核操作、后台审核流程异常。
            </div>
          </div>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="saving" @click="onSave">保存配置</el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- 测试结果 -->
    <div v-if="testResult" class="result-card">
      <div class="card-title">
        <span class="title-text">连接测试结果</span>
        <el-tag :type="testResult.ok ? 'success' : 'danger'" size="small">
          {{ testResult.ok ? '成功' : '失败' }}
        </el-tag>
      </div>
      <div class="result-body">
        <div class="result-msg">{{ testResult.msg }}</div>
        <div v-if="testResult.sample" class="sample-result">
          <div class="sample-row">
            <span class="sample-label">示例输入：</span>
            <span class="sample-text">"你好"</span>
          </div>
          <div class="sample-row">
            <span class="sample-label">审核结果：</span>
            <el-tag :type="testResult.sample.pass ? 'success' : 'danger'" size="small">
              {{ testResult.sample.pass ? '通过' : '拦截' }}
            </el-tag>
          </div>
          <div v-if="testResult.sample.reason" class="sample-row">
            <span class="sample-label">原因：</span>
            <span class="sample-text">{{ testResult.sample.reason }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 清理结果 -->
    <div v-if="cleanupResult" class="result-card">
      <div class="card-title">
        <span class="title-text">自动清理结果</span>
      </div>
      <div class="result-body">
        <div v-if="!cleanupResult.enabled" class="result-msg">未启用自动删除（天数为 0）</div>
        <div v-else>
          <div class="result-msg">
            已清理超过 {{ cleanupResult.days }} 天的审核失败内容：
            <strong>帖子 {{ cleanupResult.deleted_posts }} 条</strong>，
            <strong>评论 {{ cleanupResult.deleted_comments }} 条</strong>
          </div>
        </div>
      </div>
    </div>

    <!-- 在线试审 -->
    <div class="form-card">
      <div class="card-title">
        <span class="title-text">在线试审</span>
        <span class="form-hint">选择场景后输入文本，立即调用 DeepSeek 按对应 prompt 审核</span>
      </div>
      <div class="audit-scenario">
        <span class="audit-label">审核场景：</span>
        <el-select v-model="auditScenario" style="width: 200px">
          <el-option
            v-for="opt in auditScenarioOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
        <span class="form-hint">不同场景使用不同审核规则（如评论不把“是的”“好”当灌水）</span>
      </div>
      <el-input
        v-model="auditInput"
        type="textarea"
        :rows="3"
        placeholder="请输入要审核的文本内容（最多 2000 字）"
        maxlength="2000"
        show-word-limit
      />
      <div class="audit-actions">
        <el-button
          type="primary"
          :loading="auditing"
          :disabled="!auditInput.trim()"
          @click="onAudit"
        >
          开始审核
        </el-button>
        <el-button @click="auditInput = ''; auditResult = null">清空</el-button>
      </div>

      <div v-if="auditResult" class="audit-result">
        <div class="audit-row">
          <span class="audit-label">审核结果：</span>
          <el-tag :type="auditResult.pass ? 'success' : 'danger'" size="default">
            {{ auditResult.pass ? '✓ 通过' : '✗ 拦截' }}
          </el-tag>
          <el-tag
            v-if="auditResult.severity && auditResult.severity !== 'none'"
            :type="severityMeta[auditResult.severity]?.type || 'info'"
            size="default"
            style="margin-left: 8px"
          >
            {{ severityMeta[auditResult.severity]?.text || auditResult.severity }}
          </el-tag>
          <el-tag
            v-if="auditResult.category && auditResult.category !== 'none'"
            type="warning"
            size="default"
            style="margin-left: 8px"
          >
            {{ auditResult.category }}
          </el-tag>
          <el-tag v-if="auditResult.content_type" type="info" size="default" style="margin-left: 8px">
            {{ promptLabels[auditResult.content_type] || auditResult.content_type }}
          </el-tag>
        </div>
        <div v-if="auditResult.reason" class="audit-row">
          <span class="audit-label">违规原因：</span>
          <span class="audit-text">{{ auditResult.reason }}</span>
        </div>
        <div v-if="auditResult.skipped" class="audit-row">
          <span class="audit-label">提示：</span>
          <span class="audit-text" style="color: #e6a23c">DeepSeek 未启用或调用失败，已跳过</span>
        </div>
      </div>
    </div>

    <!-- AI 审核人设 -->
    <div class="form-card">
      <div class="card-title">
        <span class="title-text">AI 审核人设（System Prompt）</span>
        <span class="form-hint">只读，按内容场景分开设置，由系统内置，确保审核一致性</span>
      </div>
      <el-tabs v-model="activePromptTab">
        <el-tab-pane
          v-for="opt in auditScenarioOptions"
          :key="opt.value"
          :label="opt.label"
          :name="opt.value"
        >
          <pre class="prompt-box">{{ prompts[opt.value] || '（加载中…）' }}</pre>
        </el-tab-pane>
      </el-tabs>
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
  max-width: 720px;
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
.scope-group {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.scope-group :deep(.el-checkbox-group) {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
}
.scope-group :deep(.el-checkbox) {
  height: auto;
  margin-right: 0;
  align-items: flex-start;
}
.scope-group :deep(.el-checkbox__label) {
  white-space: normal;
  line-height: 1.4;
}
.opt-label {
  font-size: 14px;
  color: #262626;
  font-weight: 500;
}
.opt-hint {
  font-size: 12px;
  color: #8c8c8c;
  margin-top: 2px;
}
.scope-empty {
  font-size: 12px;
  color: #fa541c;
  padding: 6px 10px;
  background: #fff7e6;
  border-radius: 6px;
  display: inline-block;
}
.scope-note {
  font-size: 12px;
  color: #8c8c8c;
  background: #fafafa;
  border: 1px dashed #e8e8e8;
  border-radius: 6px;
  padding: 8px 12px;
  line-height: 1.6;
}
.result-body {
  font-size: 14px;
  color: #262626;
  line-height: 1.6;
}
.result-msg {
  margin-bottom: 8px;
}
.sample-result {
  background: #fafafa;
  padding: 12px 16px;
  border-radius: 6px;
  margin-top: 8px;
}
.sample-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 13px;
}
.sample-label {
  color: #8c8c8c;
  min-width: 80px;
}
.sample-text {
  color: #262626;
}
.audit-actions {
  margin-top: 12px;
  display: flex;
  gap: 8px;
}
.audit-scenario {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.audit-scenario .form-hint {
  margin-left: 4px;
}
.audit-result {
  margin-top: 16px;
  padding: 16px;
  background: #fafafa;
  border-radius: 6px;
  border-left: 3px solid #1890ff;
}
.audit-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 14px;
}
.audit-label {
  color: #8c8c8c;
  min-width: 80px;
}
.audit-text {
  color: #262626;
  line-height: 1.5;
}
.prompt-box {
  background: #fafafa;
  padding: 16px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.6;
  color: #595959;
  font-family: 'Consolas', 'Monaco', monospace;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 480px;
  overflow-y: auto;
  border: 1px solid #f0f0f0;
}
</style>
