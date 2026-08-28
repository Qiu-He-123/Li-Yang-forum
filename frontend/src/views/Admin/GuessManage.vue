<script setup lang="ts">
/**
 * 今日竞猜管理（后台）
 * 功能：
 *  - 创建竞猜（标题/说明/截止时间/日期标签/2-8个选项）
 *  - 启用/停用（每日活跃竞猜唯一：激活则同日期其他竞猜自动被关闭）
 *  - 删除（未结算则自动按原路退款所有押注）
 *  - 结算（选择中奖选项 → 胜方用户按池子分红）
 *  - 查看详情：选项汇总 + 押注名单
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import {
  adminGuessCreate,
  adminGuessDelete,
  adminGuessDetail,
  adminGuessList,
  adminGuessSettle,
  adminGuessToggle,
  type GuessItem,
} from '../../api/guess'

const loading = ref(false)
const list = ref<GuessItem[]>([])
const total = ref(0)
const page = reactive({ page: 1, page_size: 20 })
const dateKey = ref('')

// 创建表单
const createVisible = ref(false)
const formRef = ref<FormInstance>()
const form = reactive({
  title: '',
  description: '',
  deadline: '',
  date_key: '',
  options: ['选项 A', '选项 B'],
})
const rules: FormRules = {
  title: [{ required: true, message: '请输入竞猜标题', trigger: 'blur' }],
  deadline: [{ required: true, message: '请设置截止时间', trigger: 'blur' }],
}
const submitting = ref(false)

// 详情/结算
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<GuessItem & { bets?: any[] } | null>(null)
const settleWinningOptionId = ref<number | null>(null)
const settleSubmitting = ref(false)

async function load() {
  loading.value = true
  try {
    const { data } = await adminGuessList({
      page: page.page,
      page_size: page.page_size,
      date_key: dateKey.value || undefined,
    })
    list.value = data.data.items || []
    total.value = data.data.total || 0
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

function onPage(p: number) { page.page = p; load() }
function onSearch() { page.page = 1; load() }

function openCreate() {
  const today = new Date()
  form.title = ''
  form.description = ''
  form.deadline = localInputDefault(today.getFullYear(), today.getMonth(), today.getDate(), 23, 59)
  form.date_key = dateKey.value || formatDateKey(today)
  form.options = ['选项 1', '选项 2']
  createVisible.value = true
}
function addOption() {
  if (form.options.length >= 8) return ElMessage.warning('最多 8 个选项')
  form.options.push(`选项 ${form.options.length + 1}`)
}
function removeOption(i: number) {
  if (form.options.length <= 2) return ElMessage.warning('至少保留 2 个选项')
  form.options.splice(i, 1)
}
function dateKeyFromDeadline() {
  if (form.deadline && !form.date_key) {
    try {
      const d = new Date(form.deadline)
      form.date_key = formatDateKey(d)
    } catch { /* ignore */ }
  }
}
async function submitCreate() {
  await formRef.value?.validate()
  if (form.options.some((s) => !s.trim())) {
    ElMessage.warning('选项不能为空')
    return
  }
  submitting.value = true
  try {
    await adminGuessCreate({
      title: form.title,
      description: form.description || undefined,
      deadline: new Date(form.deadline).toISOString(),
      date_key: form.date_key || undefined,
      options: form.options.map((s) => s.trim()).filter(Boolean),
    })
    ElMessage.success('创建成功')
    createVisible.value = false
    void load()
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    submitting.value = false
  }
}

async function onToggle(row: GuessItem) {
  try {
    await adminGuessToggle(row.id, !row.is_active)
    ElMessage.success(row.is_active ? '已下架' : '已上架为今日焦点')
    void load()
  } catch (e) { ElMessage.error((e as Error).message) }
}
async function onDelete(row: GuessItem) {
  try {
    await ElMessageBox.confirm(
      `删除后未结算押注会原路退款，确认删除「${row.title}」？`,
      '删除竞猜',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' },
    )
    await adminGuessDelete(row.id)
    ElMessage.success('删除成功')
    void load()
  } catch (e: any) {
    if (e === 'cancel') return
    ElMessage.error((e as Error).message)
  }
}

async function openDetail(row: GuessItem) {
  detailLoading.value = true
  detailVisible.value = true
  settleWinningOptionId.value = null
  try {
    const { data } = await adminGuessDetail(row.id)
    detail.value = data.data
    settleWinningOptionId.value = detail.value.winning_option_id ?? null
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    detailLoading.value = false
  }
}

async function settle() {
  if (!detail.value) return
  if (settleWinningOptionId.value == null) return ElMessage.warning('请选择中奖选项')
  try {
    await ElMessageBox.confirm(
      `将按中奖选项结算。结算后不能更改，确认继续？`,
      '结算押注',
      { type: 'warning' },
    )
    settleSubmitting.value = true
    await adminGuessSettle(detail.value.id, settleWinningOptionId.value)
    ElMessage.success('结算完成，积分奖励已发放/扣除')
    settleSubmitting.value = false
    await openDetail(detail.value)
    void load()
  } catch (e: any) {
    settleSubmitting.value = false
    if (e === 'cancel') return
    ElMessage.error((e as Error).message)
  }
}

function formatDateKey(d: Date) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${dd}`
}
function localInputDefault(y: number, mo: number, d: number, h: number, mi: number) {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${y}-${pad(mo + 1)}-${pad(d)}T${pad(h)}:${pad(mi)}`
}
function pct(opt: { total_points: number }, all: number) {
  if (all <= 0) return 0
  return ((opt.total_points / all) * 100).toFixed(1)
}

onMounted(() => {
  dateKey.value = formatDateKey(new Date())
  void load()
})
</script>

<template>
  <div class="admin-page">
    <el-card shadow="never" class="toolbar">
      <div class="toolbar-left">
        <h2 class="page-title">今日竞猜管理</h2>
        <p class="page-desc">创建每日的竞猜主题，截止后手动开奖；活跃的竞猜会在首页焦点区展示，登录用户首次进入自动弹押注弹窗。</p>
      </div>
      <div class="toolbar-right">
        <el-date-picker
          v-model="dateKey"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="筛选日期"
          clearable
          style="width: 180px"
          @change="onSearch"
        />
        <el-button type="primary" icon="Plus" @click="openCreate">创建今日竞猜</el-button>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="list" style="width: 100%">
        <el-table-column label="ID" prop="id" width="72" />
        <el-table-column label="日期" prop="date_key" width="120" />
        <el-table-column label="标题" min-width="220">
          <template #default="{ row }">
            <div>
              <b>{{ row.title }}</b>
              <div class="muted" style="font-weight: 400; color: var(--el-text-color-secondary)">
                {{ row.description || '—' }}
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag v-if="row.is_active" type="danger" effect="dark">今日活跃</el-tag>
            <el-tag v-else effect="plain">已下架</el-tag>
            <div style="margin-top:4px">
              <el-tag v-if="row.settled_at" size="small" type="success">已结算</el-tag>
              <el-tag v-else size="small" type="warning">未结算</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="押注概况" width="240">
          <template #default="{ row }">
            <div>总积分：<b>{{ ((row as unknown as GuessItem).total_points || 0).toLocaleString() }}</b></div>
            <div>参与：<b>{{ (row as unknown as GuessItem).total_users || 0 }}</b> 人</div>
            <div class="opts-mini">
              <span v-for="(o, i) in (row as unknown as GuessItem).options" :key="o.id" class="opt-mini">
                <el-tag size="small" :type="(row as unknown as GuessItem).winning_option_id === o.id ? 'success' : 'info'" effect="plain">
                  {{ ['A','B','C','D','E','F','G','H'][i] }}. {{ o.label }}
                </el-tag>
                <span class="muted">{{ o.total_points }} / {{ o.total_users }}人</span>
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="截止" width="180">
          <template #default="{ row }">{{ (row as unknown as GuessItem).deadline?.replace('T', ' ') || '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="320" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row as unknown as GuessItem)">详情/结算</el-button>
            <el-button link type="warning" @click="onToggle(row as unknown as GuessItem)">
              {{ (row as unknown as GuessItem).is_active ? '下架' : '设为今日' }}
            </el-button>
            <el-popconfirm title="删除后未结算押注原路退款，继续？" @confirm="onDelete(row as unknown as GuessItem)">
              <template #reference>
                <el-button link type="danger" :disabled="!!(row as unknown as GuessItem).settled_at">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        style="margin-top: 16px; justify-content: flex-end"
        layout="prev, pager, next, total"
        :page-size="page.page_size"
        :total="total"
        :current-page="page.page"
        @current-change="onPage"
      />
    </el-card>

    <!-- 创建表单 -->
    <el-dialog v-model="createVisible" title="创建今日竞猜" width="520px" destroy-on-close>
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="92px"
        label-position="right"
      >
        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" maxlength="120" placeholder="例如：今晚谁能夺冠？🏆🔥" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            maxlength="600"
            placeholder="补充说明，弹窗与焦点区都会展示（支持换行）"
          />
        </el-form-item>
        <el-form-item label="截止时间" prop="deadline">
          <el-date-picker
            v-model="form.deadline"
            type="datetime"
            format="YYYY-MM-DD HH:mm"
            value-format="YYYY-MM-DDTHH:mm"
            placeholder="截止押注时间"
            style="width: 100%"
            @change="dateKeyFromDeadline"
          />
        </el-form-item>
        <el-form-item label="日期标签">
          <el-date-picker
            v-model="form.date_key"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="留空则按截止日当天计算"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="选项">
          <div style="width: 100%">
            <div
              v-for="(_, i) in form.options"
              :key="i"
              style="display: flex; gap: 8px; margin-bottom: 6px; align-items: center"
            >
              <span class="muted" style="width: 24px">{{ ['A','B','C','D','E','F','G','H'][i] }}.</span>
              <el-input v-model="form.options[i]" maxlength="60" placeholder="选项内容" />
              <el-button link type="danger" @click="removeOption(i)" :disabled="form.options.length <= 2">删除</el-button>
            </div>
            <el-button plain icon="Plus" size="small" @click="addOption" :disabled="form.options.length >= 8">
              加选项（最多 8 个）
            </el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 详情 + 结算 -->
    <el-dialog v-model="detailVisible" title="竞猜详情 / 结算" width="640px" destroy-on-close top="6vh">
      <div v-if="detailLoading">加载中...</div>
      <div v-else-if="!detail">无数据</div>
      <div v-else>
        <h3 style="margin: 4px 0 6px">{{ detail.title }}</h3>
        <p class="muted" style="white-space: pre-wrap">{{ detail.description || '（无描述）' }}</p>
        <div style="display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 14px">
          <el-tag>日期：{{ detail.date_key }}</el-tag>
          <el-tag type="warning">截止：{{ detail.deadline?.replace('T', ' ') }}</el-tag>
          <el-tag v-if="detail.settled_at" type="success">已结算：{{ detail.settled_at.replace('T', ' ') }}</el-tag>
          <el-tag v-else type="danger">未结算</el-tag>
          <el-tag type="info">奖池：{{ (detail.total_points || 0).toLocaleString() }}</el-tag>
          <el-tag type="info">参与人数：{{ detail.total_users }}</el-tag>
        </div>

        <el-divider content-position="left">选项汇总</el-divider>
        <div style="display: flex; flex-direction: column; gap: 10px">
          <div
            v-for="(o, i) in detail.options"
            :key="o.id"
            class="opt-row"
            :class="{ winner: detail?.winning_option_id === o.id }"
          >
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px">
              <div>
                <b>{{ ['A','B','C','D','E','F','G','H'][i] }}. {{ o.label }}</b>
                <el-tag v-if="detail?.winning_option_id === o.id" type="success" size="small" effect="dark" style="margin-left: 6px">
                  冠军 👑
                </el-tag>
              </div>
              <div class="muted">{{ o.total_points }} pts · {{ o.total_users }} 人 · {{ pct(o, detail.total_points) }}%</div>
            </div>
            <el-progress
              :percentage="Number(pct(o, detail.total_points))"
              :color="detail?.winning_option_id === o.id ? '#67C23A' : '#F59E0B'"
              :stroke-width="10"
              :show-text="false"
            />
          </div>
        </div>

        <el-divider content-position="left">开奖操作</el-divider>
        <el-form label-width="100px">
          <el-form-item label="冠军选项">
            <el-select
              v-model="settleWinningOptionId"
              placeholder="请选择中奖选项"
              style="width: 100%"
              :disabled="!!detail?.settled_at"
            >
              <el-option
                v-for="(o, i) in detail.options"
                :key="o.id"
                :label="`${['A','B','C','D','E','F','G','H'][i]}. ${o.label}`"
                :value="o.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button
              type="success"
              :loading="settleSubmitting"
              :disabled="!!detail?.settled_at"
              @click="settle"
            >
              {{ detail?.settled_at ? '已结算完成' : '立即结算并发放奖励' }}
            </el-button>
            <el-alert
              type="warning"
              :closable="false"
              style="margin-left: 8px; flex: 1"
              show-icon
              title="结算后所有押注立刻发放奖金/扣除本金；胜方按奖池押注占比分红。"
            />
          </el-form-item>
        </el-form>

        <el-divider content-position="left">押注名单（最近 200 条）</el-divider>
        <el-table size="small" :data="detail.bets || []" max-height="340" style="width: 100%">
          <el-table-column label="UID" prop="user_id" width="80" />
          <el-table-column label="昵称" prop="nickname" min-width="120" show-overflow-tooltip />
          <el-table-column label="选项" width="100">
            <template #default="{ row }">
              {{ ((detail?.options || []).findIndex((o: any) => o.id === row.option_id) >= 0
                ? ['A','B','C','D','E','F','G','H'][(detail?.options || []).findIndex((o: any) => o.id === row.option_id)]
                : '-'
              ) }}
            </template>
          </el-table-column>
          <el-table-column label="押注" width="100">
            <template #default="{ row }">
              {{ row.skipped ? '跳过' : `${row.amount} pts` }}
            </template>
          </el-table-column>
          <el-table-column label="结果" width="140">
            <template #default="{ row }">
              <el-tag v-if="row.skipped" type="info" size="small">今日跳过</el-tag>
              <el-tag v-else-if="row.result === 'pending'" type="warning" size="small">待开奖</el-tag>
              <el-tag v-else-if="row.result === 'win'" type="success" size="small">
                赢 +{{ row.reward }}
              </el-tag>
              <el-tag v-else-if="row.result === 'lose'" type="danger" size="small">
                输 {{ row.reward }}
              </el-tag>
              <el-tag v-else size="small">{{ row.result }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="时间" prop="created_at" min-width="170" show-overflow-tooltip />
        </el-table>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.admin-page { display: flex; flex-direction: column; gap: 14px; }
.toolbar { display: flex; flex-direction: row; align-items: center; justify-content: space-between; gap: 16px; }
.toolbar-left { flex: 1; min-width: 0; }
.page-title { margin: 0 0 4px; font-size: 18px; }
.page-desc { margin: 0; color: var(--el-text-color-secondary); font-size: 13px; line-height: 1.6; }
.toolbar-right { display: flex; gap: 10px; align-items: center; }
.opts-mini { display: flex; flex-direction: column; gap: 4px; margin-top: 6px; }
.opt-mini { display: inline-flex; gap: 6px; align-items: center; }
.muted { color: var(--el-text-color-secondary); font-size: 12px; }
.opt-row {
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  background: var(--el-fill-color-light);
}
.opt-row.winner {
  border-color: var(--el-color-success);
  background: linear-gradient(180deg, #f0f9eb, #e1f3d8);
}
</style>
