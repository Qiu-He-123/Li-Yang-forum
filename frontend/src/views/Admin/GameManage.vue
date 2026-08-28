<script setup lang="ts">
/**
 * 游戏管理（后台）
 * 功能：
 *  - 游戏列表（含用户自制待审核游戏）
 *  - 编辑：每局金币奖励 / 每日领取上限 / 排序 / 上架下架 / 审核状态
 *  - 新增游戏
 *  - 删除游戏
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import {
  adminCreateGame,
  adminDeleteGame,
  adminListGames,
  adminUpdateGame,
  type GameItem,
} from '../../api/games'

const loading = ref(false)
const list = ref<GameItem[]>([])
const keyword = ref('')

async function load() {
  loading.value = true
  try {
    list.value = await adminListGames(keyword.value.trim())
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loading.value = false
  }
}
function onSearch() { void load() }

// ===== 新增游戏 =====
const createVisible = ref(false)
const formRef = ref<FormInstance>()
const form = ref({
  name: '',
  slug: '',
  type: 'single' as 'single' | 'multi',
  description: '',
  icon_url: '',
  reward_coins: 5,
  daily_limit: 5,
  affinity_daily_limit: 20,
  sort_order: 0,
})
const rules: FormRules = {
  name: [{ required: true, message: '请输入游戏名称', trigger: 'blur' }],
  slug: [
    { required: true, message: '请输入游戏标识（字母/数字/中划线）', trigger: 'blur' },
    { pattern: /^[a-z0-9-]+$/i, message: '仅支持字母、数字、中划线', trigger: 'blur' },
  ],
  reward_coins: [{ required: true, message: '请输入每局金币奖励', trigger: 'blur' }],
  daily_limit: [{ required: true, message: '请输入每日上限', trigger: 'blur' }],
}
const submitting = ref(false)

function openCreate() {
  form.value = {
    name: '',
    slug: '',
    type: 'single',
    description: '',
    icon_url: '',
    reward_coins: 5,
    daily_limit: 5,
    affinity_daily_limit: 20,
    sort_order: list.value.length + 1,
  }
  createVisible.value = true
}

async function submitCreate() {
  await formRef.value?.validate()
  submitting.value = true
  try {
    await adminCreateGame({
      name: form.value.name.trim(),
      slug: form.value.slug.trim(),
      type: form.value.type,
      description: form.value.description.trim() || undefined,
      icon_url: form.value.icon_url.trim() || undefined,
      reward_coins: Number(form.value.reward_coins),
      daily_limit: Number(form.value.daily_limit),
      affinity_daily_limit: Number(form.value.affinity_daily_limit),
      sort_order: Number(form.value.sort_order) || 0,
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

// ===== 编辑 =====
const editVisible = ref(false)
const editFormRef = ref<FormInstance>()
const editForm = ref<GameItem | null>(null)
const editRules: FormRules = {
  reward_coins: [{ required: true, message: '请输入每局金币奖励', trigger: 'blur' }],
  daily_limit: [{ required: true, message: '请输入每日上限', trigger: 'blur' }],
}

function openEdit(row: GameItem) {
  editForm.value = { ...row }
  editVisible.value = true
}

async function submitEdit() {
  if (!editForm.value) return
  await editFormRef.value?.validate()
  submitting.value = true
  try {
    await adminUpdateGame(editForm.value.id, {
      name: editForm.value.name,
      type: editForm.value.type,
      description: editForm.value.description,
      icon_url: editForm.value.icon_url,
      reward_coins: Number(editForm.value.reward_coins),
      daily_limit: Number(editForm.value.daily_limit),
      affinity_daily_limit: Number(editForm.value.affinity_daily_limit ?? 20),
      sort_order: Number(editForm.value.sort_order) || 0,
    })
    ElMessage.success('保存成功')
    editVisible.value = false
    void load()
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    submitting.value = false
  }
}

// ===== 上架 / 下架 =====
async function onToggleActive(row: GameItem) {
  try {
    await adminUpdateGame(row.id, { is_active: !row.is_active })
    ElMessage.success(row.is_active ? '已下架' : '已上架')
    void load()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

// ===== 审核（用户自制游戏） =====
async function onAudit(row: GameItem, status: 'active' | 'rejected') {
  try {
    await adminUpdateGame(row.id, { status, is_active: status === 'active' })
    ElMessage.success(status === 'active' ? '已审核通过并上架' : '已拒绝')
    void load()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

// ===== 删除 =====
async function onDelete(row: GameItem) {
  try {
    await ElMessageBox.confirm(`确认删除游戏「${row.name}」？删除后不可恢复。`, '删除游戏', {
      type: 'warning',
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
    })
    await adminDeleteGame(row.id)
    ElMessage.success('删除成功')
    void load()
  } catch (e: any) {
    if (e === 'cancel') return
    ElMessage.error((e as Error).message)
  }
}

const statusTag = computed(() => (s: string) => {
  if (s === 'pending') return { type: 'warning' as const, text: '待审核' }
  if (s === 'rejected') return { type: 'danger' as const, text: '已拒绝' }
  return { type: 'success' as const, text: '已上架' }
})

onMounted(() => { void load() })
</script>

<template>
  <div class="admin-page">
    <el-card shadow="never" class="toolbar">
      <div class="toolbar-left">
        <h2 class="page-title">游戏管理</h2>
        <p class="page-desc">管理游戏中心的每局金币奖励与每日领取上限；用户「制作游戏」的投稿在此审核后上架。金币奖励越高、每日上限越大，玩家赚金币越快（多人游戏仍可配置，暂未开放游玩）。</p>
      </div>
      <div class="toolbar-right">
        <el-input
          v-model="keyword"
          placeholder="搜索游戏名称"
          clearable
          style="width: 200px"
          @keyup.enter="onSearch"
          @clear="onSearch"
        />
        <el-button type="primary" icon="Plus" @click="openCreate">新增游戏</el-button>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="list" style="width: 100%">
        <el-table-column label="ID" prop="id" width="70" />
        <el-table-column label="图标/名称" min-width="200">
          <template #default="{ row }">
            <div class="game-cell">
              <span class="game-cell__icon">{{ row.icon_url || '🎮' }}</span>
              <div>
                <b>{{ row.name }}</b>
                <div class="muted" style="font-weight: 400; color: var(--el-text-color-secondary)">
                  {{ row.description || '—' }}
                </div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="标识" prop="slug" width="140">
          <template #default="{ row }"><code class="slug-code">{{ row.slug }}</code></template>
        </el-table-column>
        <el-table-column label="类型" width="90">
          <template #default="{ row }">
            <el-tag :type="row.type === 'single' ? 'primary' : 'warning'" effect="plain">
              {{ row.type === 'single' ? '单人' : '多人' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="金币奖励" width="130">
          <template #default="{ row }">
            <div>
              <el-tag type="success" effect="dark" size="small">+{{ row.reward_coins }}</el-tag>
              <div class="muted" style="font-size: 12px; margin-top: 4px">/ 次</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="每日上限" width="100">
          <template #default="{ row }">{{ row.daily_limit }} 次</template>
        </el-table-column>
        <el-table-column label="每日好感上限" width="110">
          <template #default="{ row }">
            <div>
              <el-tag type="warning" effect="plain" size="small">❤ {{ row.affinity_daily_limit ?? 0 }}</el-tag>
              <div class="muted" style="font-size: 12px; margin-top: 4px">/ 天</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="排序" prop="sort_order" width="80" />
        <el-table-column label="来源/状态" width="140">
          <template #default="{ row }">
            <div style="display:flex; flex-direction:column; gap:4px">
              <el-tag size="small" effect="plain">
                {{ row.source === 'user' ? '用户自制' : '内置' }}
              </el-tag>
              <el-tag size="small" :type="statusTag(row.status).type" :effect="row.status === 'active' ? 'dark' : 'plain'">
                {{ statusTag(row.status).text }}
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row as GameItem)">编辑</el-button>
            <el-button v-if="(row as GameItem).status === 'pending'" link type="success" @click="onAudit(row as GameItem, 'active')">通过</el-button>
            <el-button v-if="(row as GameItem).status === 'pending'" link type="danger" @click="onAudit(row as GameItem, 'rejected')">拒绝</el-button>
            <el-button link :type="(row as GameItem).is_active ? 'warning' : 'success'" @click="onToggleActive(row as GameItem)">
              {{ (row as GameItem).is_active ? '下架' : '上架' }}
            </el-button>
            <el-popconfirm title="删除后不可恢复，继续？" @confirm="onDelete(row as GameItem)">
              <template #reference>
                <el-button link type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增游戏 -->
    <el-dialog v-model="createVisible" title="新增游戏" width="560px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px" label-position="right">
        <el-form-item label="游戏名称" prop="name">
          <el-input v-model="form.name" maxlength="30" placeholder="如：飞机大战" />
        </el-form-item>
        <el-form-item label="游戏标识" prop="slug">
          <el-input v-model="form.slug" maxlength="60" placeholder="如：game-plane（字母/数字/中划线）" />
        </el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="form.type">
            <el-radio value="single">单人游戏</el-radio>
            <el-radio value="multi">多人游戏</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="图标">
          <el-input v-model="form.icon_url" maxlength="10" placeholder="一个 emoji，如：✈️" />
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="form.description" maxlength="100" type="textarea" :rows="2" placeholder="简单介绍玩法" />
        </el-form-item>
        <el-form-item label="每局金币" prop="reward_coins">
          <el-input-number v-model="form.reward_coins" :min="0" :max="10000" />
          <span class="form-tip">每领一次发放的金币数</span>
        </el-form-item>
        <el-form-item label="每日上限" prop="daily_limit">
          <el-input-number v-model="form.daily_limit" :min="1" :max="9999" />
          <span class="form-tip">每天最多领取次数</span>
        </el-form-item>
        <el-form-item label="每日好感上限">
          <el-input-number v-model="form.affinity_daily_limit" :min="0" :max="9999" />
          <span class="form-tip">玩这个游戏一天最多加多少好感</span>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" :min="0" :max="99999" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitCreate">保存</el-button>
      </template>
    </el-dialog>

    <!-- 编辑游戏 -->
    <el-dialog v-model="editVisible" title="编辑游戏" width="560px" destroy-on-close>
      <el-form v-if="editForm" ref="editFormRef" :model="editForm" :rules="editRules" label-width="110px" label-position="right">
        <el-form-item label="游戏名称">
          <el-input v-model="editForm.name" maxlength="30" />
        </el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="editForm.type">
            <el-radio value="single">单人游戏</el-radio>
            <el-radio value="multi">多人游戏</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="图标">
          <el-input v-model="editForm.icon_url" maxlength="10" />
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="editForm.description" maxlength="100" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="每局金币" prop="reward_coins">
          <el-input-number v-model="editForm.reward_coins" :min="0" :max="10000" />
          <span class="form-tip">每领一次发放的金币数</span>
        </el-form-item>
        <el-form-item label="每日上限" prop="daily_limit">
          <el-input-number v-model="editForm.daily_limit" :min="1" :max="9999" />
          <span class="form-tip">每天最多领取次数</span>
        </el-form-item>
        <el-form-item label="每日好感上限">
          <el-input-number v-model="editForm.affinity_daily_limit" :min="0" :max="9999" />
          <span class="form-tip">玩这个游戏一天最多加多少好感</span>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="editForm.sort_order" :min="0" :max="99999" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar {
  margin-bottom: 16px;
}
.toolbar-left {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.toolbar-right {
  display: flex;
  gap: 10px;
  align-items: center;
}
.page-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
}
.page-desc {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  max-width: 720px;
  line-height: 1.6;
}
.game-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}
.game-cell__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 10px;
  font-size: 20px;
  background: var(--el-fill-color-light);
  flex-shrink: 0;
}
.slug-code {
  font-size: 12px;
  color: var(--el-text-color-regular);
}
.form-tip {
  margin-left: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
