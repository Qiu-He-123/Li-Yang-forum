<script setup lang="ts">
/**
 * 抽奖管理（后台）—— 提现改抽奖
 * - 抽奖设置：券汇率 / 是否开启 / 管理员微信（兑付咨询）
 * - 奖品管理：权重（越大越容易抽到）、数量范围、爆率峰值、看广告加成、可看次数
 * - 抽取记录 / 兑付库存（待领 / 已领）
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { uploadImage } from '../../api/image'
import {
  adminCreateLotteryPrize,
  adminDeleteLotteryPrize,
  adminLotteryDraws,
  adminLotteryInventory,
  adminLotteryPrizes,
  adminLotterySettings,
  adminUpdateLotteryPrize,
  adminUpdateLotterySettings,
  type LotteryDrawRow,
  type LotteryInventoryRow,
  type LotteryPrize,
  type LotterySettings,
} from '../../api/order'

const settings = ref<LotterySettings>({ ticket_rate: 1, enabled: false, admin_wechat: '' })
const saving = ref(false)

// 奖品
const prizes = ref<LotteryPrize[]>([])
const loadingPrizes = ref(false)
const prizeDialog = reactive({
  visible: false,
  editing: false,
  id: 0,
  name: '',
  image_url: '',
  weight: 10,
  min_qty: 1,
  max_qty: 1,
  hot_qty: 1,
  ad_qty: 1,
  max_ad_times: 4,
  enabled: true,
})
const savingPrize = ref(false)

// 抽取记录 / 兑付库存
const tab = ref<'draws' | 'inventory'>('draws')
const draws = ref<LotteryDrawRow[]>([])
const inventory = ref<LotteryInventoryRow[]>([])
const drawTotal = ref(0)
const invTotal = ref(0)
const drawPage = reactive({ page: 1, page_size: 20 })
const invPage = reactive({ page: 1, page_size: 20 })
const drawStatus = ref('')
const invStatus = ref('')
const loadingList = ref(false)

async function loadSettings() {
  try {
    const { data } = await adminLotterySettings()
    settings.value = { ...data.data }
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}
async function saveSettings() {
  saving.value = true
  try {
    const { data } = await adminUpdateLotterySettings({ ...settings.value })
    settings.value = { ...data.data }
    ElMessage.success('抽奖设置已保存')
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    saving.value = false
  }
}

async function loadPrizes() {
  loadingPrizes.value = true
  try {
    const { data } = await adminLotteryPrizes()
    prizes.value = data.data.items || []
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loadingPrizes.value = false
  }
}

function openCreate() {
  Object.assign(prizeDialog, {
    visible: true, editing: false, id: 0,
    name: '', image_url: '', weight: 10, min_qty: 1, max_qty: 1, hot_qty: 1, ad_qty: 1, max_ad_times: 4, enabled: true,
  })
}
function openEdit(p: LotteryPrize) {
  Object.assign(prizeDialog, {
    visible: true, editing: true, id: p.id,
    name: p.name, image_url: p.image_url || '', weight: p.weight, min_qty: p.min_qty, max_qty: p.max_qty,
    hot_qty: p.hot_qty, ad_qty: p.ad_qty, max_ad_times: p.max_ad_times, enabled: p.enabled,
  })
}
async function savePrize() {
  if (!prizeDialog.name.trim()) { ElMessage.warning('请填写奖品名称'); return }
  if (prizeDialog.max_qty < prizeDialog.min_qty) { ElMessage.warning('数量上限不能小于下限'); return }
  savingPrize.value = true
  try {
    const payload = {
      name: prizeDialog.name,
      image_url: prizeDialog.image_url || null,
      weight: prizeDialog.weight,
      min_qty: prizeDialog.min_qty,
      max_qty: prizeDialog.max_qty,
      hot_qty: prizeDialog.hot_qty,
      ad_qty: prizeDialog.ad_qty,
      max_ad_times: prizeDialog.max_ad_times,
      enabled: prizeDialog.enabled,
    }
    if (prizeDialog.editing) {
      await adminUpdateLotteryPrize(prizeDialog.id, payload)
      ElMessage.success('奖品已更新')
    } else {
      await adminCreateLotteryPrize(payload)
      ElMessage.success('奖品已创建')
    }
    prizeDialog.visible = false
    await loadPrizes()
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    savingPrize.value = false
  }
}
async function removePrize(p: LotteryPrize) {
  try {
    await ElMessageBox.confirm(`确定删除奖品「${p.name}」吗？历史抽取记录会保留。`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await adminDeleteLotteryPrize(p.id)
    ElMessage.success('已删除')
    await loadPrizes()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}
async function togglePrize(p: LotteryPrize, enabled: boolean) {
  try {
    await adminUpdateLotteryPrize(p.id, { enabled })
    p.enabled = enabled
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

// ==================== 奖品图片：程序内选择并压缩上传 ====================
const prizeImgUploading = ref(false)
const prizeImageInput = ref<HTMLInputElement | null>(null)

function pickPrizeImage() {
  prizeImageInput.value?.click()
}

/** 把图片压缩到目标最大边长（默认 1024px、JPEG 0.82），返回优化后的 File */
function compressImage(file: File, maxSide = 1024, quality = 0.82): Promise<File> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    const url = URL.createObjectURL(file)
    img.onload = () => {
      URL.revokeObjectURL(url)
      const scale = Math.min(1, maxSide / Math.max(img.width, img.height))
      const w = Math.max(1, Math.round(img.width * scale))
      const h = Math.max(1, Math.round(img.height * scale))
      const canvas = document.createElement('canvas')
      canvas.width = w
      canvas.height = h
      const ctx = canvas.getContext('2d')
      if (!ctx) { reject(new Error('图片压缩失败：无法创建画布')); return }
      ctx.drawImage(img, 0, 0, w, h)
      canvas.toBlob(
        (blob) => {
          if (!blob) { reject(new Error('图片压缩失败')); return }
          resolve(new File([blob], 'prize.jpg', { type: blob.type }))
        },
        'image/jpeg',
        quality,
      )
    }
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('图片读取失败')) }
    img.src = url
  })
}

async function onPrizeImageChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = '' // 允许重复选择同一文件
  if (!file) return
  prizeImgUploading.value = true
  try {
    const compressed = await compressImage(file)
    const { data } = await uploadImage(compressed)
    prizeDialog.image_url = data.data.url
    ElMessage.success('图片已上传')
  } catch (err) {
    ElMessage.error((err as Error).message)
  } finally {
    prizeImgUploading.value = false
  }
}

async function loadDraws() {
  loadingList.value = true
  try {
    const { data } = await adminLotteryDraws({
      page: drawPage.page, page_size: drawPage.page_size,
      status: drawStatus.value || undefined,
    })
    draws.value = data.data.items || []
    drawTotal.value = data.data.total || 0
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loadingList.value = false
  }
}
async function loadInventory() {
  loadingList.value = true
  try {
    const { data } = await adminLotteryInventory({
      page: invPage.page, page_size: invPage.page_size,
      status: invStatus.value || undefined,
    })
    inventory.value = data.data.items || []
    invTotal.value = data.data.total || 0
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loadingList.value = false
  }
}
function switchTab(t: 'draws' | 'inventory') {
  tab.value = t
  if (t === 'draws') void loadDraws(); else void loadInventory()
}

onMounted(() => {
  void loadSettings()
  void loadPrizes()
  void loadDraws()
})
</script>

<template>
  <div class="admin-page">
    <!-- 抽奖设置 -->
    <el-card shadow="never">
      <template #header>抽奖设置</template>
      <el-form label-width="120px" style="max-width: 640px">
        <el-form-item label="开启抽奖">
          <el-switch v-model="settings.enabled" />
          <span class="muted" style="margin-left: 8px">关闭后用户将无法抽奖与兑换抽奖券（钱包入口隐藏）</span>
        </el-form-item>
        <el-form-item label="券汇率">
          <el-input-number v-model="settings.ticket_rate" :min="1" style="width: 180px" />
          <span class="muted" style="margin-left: 8px">1 抽奖券 = N 交易币</span>
        </el-form-item>
        <el-form-item label="兑付微信">
          <el-input v-model="settings.admin_wechat" placeholder="填写后领取时提示用户添加该微信兑付" clearable style="width: 320px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="saveSettings">保存设置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 奖品管理 -->
    <el-card shadow="never">
      <template #header>
        <div style="display: flex; align-items: center; justify-content: space-between">
          <span>奖品管理</span>
          <el-button type="primary" icon="Plus" @click="openCreate">新增奖品</el-button>
        </div>
      </template>
      <el-table v-loading="loadingPrizes" :data="prizes" style="width: 100%">
        <el-table-column label="奖品" min-width="160">
          <template #default="{ row }">
            <div style="display: flex; align-items: center; gap: 8px">
              <el-image v-if="row.image_url" :src="row.image_url" style="width: 34px; height: 34px; border-radius: 6px" fit="cover" />
              <div>
                <div><b>{{ row.name }}</b></div>
                <div class="muted">权重 {{ row.weight }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="数量范围" width="120">
          <template #default="{ row }">{{ row.min_qty }} ~ {{ row.max_qty }}</template>
        </el-table-column>
        <el-table-column label="爆率峰值" width="100">
          <template #default="{ row }"><el-tag size="small" type="danger">{{ row.hot_qty }}</el-tag></template>
        </el-table-column>
        <el-table-column label="看广告加成" width="130">
          <template #default="{ row }">+{{ row.ad_qty }} / 至多 {{ row.max_ad_times }} 次</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? '启用' : '停用' }}</el-tag></template>
        </el-table-column>
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row as LotteryPrize)">编辑</el-button>
            <el-switch size="small" :model-value="row.enabled" @change="(v: any) => togglePrize(row as LotteryPrize, !!v)" style="margin: 0 10px" />
            <el-button link type="danger" @click="removePrize(row as LotteryPrize)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 抽取记录 / 兑付库存 -->
    <el-card shadow="never">
      <template #header>
        <el-tabs v-model="tab" @tab-change="(name: any) => switchTab(name as 'draws' | 'inventory')">
          <el-tab-pane label="抽取记录" name="draws" />
          <el-tab-pane label="兑付库存" name="inventory" />
        </el-tabs>
      </template>

      <template v-if="tab === 'draws'">
        <div style="display: flex; gap: 10px; margin-bottom: 10px">
          <el-select v-model="drawStatus" clearable placeholder="全部状态" style="width: 140px" @change="loadDraws">
            <el-option label="待领取" value="pending" />
            <el-option label="已领取" value="claimed" />
          </el-select>
        </div>
        <el-table v-loading="loadingList" :data="draws" style="width: 100%">
          <el-table-column label="ID" prop="id" width="70" />
          <el-table-column label="用户" min-width="140">
            <template #default="{ row }">
              <div>{{ row.user_name || ('用户 #' + row.user_id) }}</div>
              <div class="muted">UID {{ row.user_id }}</div>
            </template>
          </el-table-column>
          <el-table-column label="奖品" prop="prize_name" min-width="120" />
          <el-table-column label="首摇" prop="base_qty" width="70" />
          <el-table-column label="广告加成" width="100">
            <template #default="{ row }">+{{ row.ad_qty_granted }}（{{ row.ad_times_used }}次）</template>
          </el-table-column>
          <el-table-column label="总量" width="80">
            <template #default="{ row }"><b>{{ row.total_qty }}</b></template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.status === 'claimed' ? 'success' : 'warning'" size="small">{{ row.status === 'claimed' ? '已领取' : '待领取' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="时间" prop="created_at" min-width="160" show-overflow-tooltip />
        </el-table>
        <el-pagination
          style="margin-top: 12px; justify-content: flex-end"
          layout="prev, pager, next, total"
          :page-size="drawPage.page_size" :total="drawTotal" :current-page="drawPage.page"
          @current-change="(p: number) => { drawPage.page = p; loadDraws() }"
        />
      </template>

      <template v-else>
        <div style="display: flex; gap: 10px; margin-bottom: 10px">
          <el-select v-model="invStatus" clearable placeholder="全部状态" style="width: 140px" @change="loadInventory">
            <el-option label="待兑付" value="pending" />
            <el-option label="已兑付" value="claimed" />
          </el-select>
        </div>
        <el-table v-loading="loadingList" :data="inventory" style="width: 100%">
          <el-table-column label="用户" min-width="140">
            <template #default="{ row }">
              <div>{{ row.user_name || ('用户 #' + row.user_id) }}</div>
              <div class="muted">UID {{ row.user_id }}</div>
            </template>
          </el-table-column>
          <el-table-column label="奖品" prop="prize_name" min-width="130">
            <template #default="{ row }">
              <div style="display: flex; align-items: center; gap: 8px">
                <el-image v-if="row.image_url" :src="row.image_url" style="width: 30px; height: 30px; border-radius: 4px" fit="cover" />
                <span>{{ row.prize_name }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="数量" prop="qty" width="80" />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.status === 'claimed' ? 'success' : 'warning'" size="small">{{ row.status === 'claimed' ? '已兑付' : '待兑付' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="兑付时间" prop="claimed_at" min-width="160" show-overflow-tooltip />
          <el-table-column label="时间" prop="created_at" min-width="160" show-overflow-tooltip />
        </el-table>
        <el-pagination
          style="margin-top: 12px; justify-content: flex-end"
          layout="prev, pager, next, total"
          :page-size="invPage.page_size" :total="invTotal" :current-page="invPage.page"
          @current-change="(p: number) => { invPage.page = p; loadInventory() }"
        />
      </template>
    </el-card>

    <!-- 奖品编辑对话框 -->
    <el-dialog v-model="prizeDialog.visible" :title="prizeDialog.editing ? '编辑奖品' : '新增奖品'" width="520px" top="6vh">
      <el-form label-width="120px">
        <el-form-item label="奖品名称" required>
          <el-input v-model="prizeDialog.name" placeholder="如：奶茶券" maxlength="64" />
        </el-form-item>
        <el-form-item label="奖品图片">
          <input
            ref="prizeImageInput"
            type="file"
            accept="image/*"
            style="display: none"
            @change="onPrizeImageChange"
          />
          <div class="prize-img-row">
            <div class="prize-img-preview">
              <el-image v-if="prizeDialog.image_url" :src="prizeDialog.image_url" fit="cover" />
              <span v-else class="prize-img-empty">📷</span>
            </div>
            <div class="prize-img-ctrl">
              <el-button :loading="prizeImgUploading" type="primary" plain @click="pickPrizeImage">
                {{ prizeImgUploading ? '上传中…' : '选择图片并上传' }}
              </el-button>
              <div class="muted">支持 JPG / PNG，选图后自动压缩再上传</div>
              <el-button v-if="prizeDialog.image_url" size="small" type="danger" text @click="prizeDialog.image_url = ''">
                移除图片
              </el-button>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="中奖权重">
          <el-input-number v-model="prizeDialog.weight" :min="1" style="width: 180px" />
          <span class="muted" style="margin-left: 8px">值越大越容易抽到</span>
        </el-form-item>
        <el-form-item label="数量下限">
          <el-input-number v-model="prizeDialog.min_qty" :min="1" style="width: 180px" />
        </el-form-item>
        <el-form-item label="数量上限">
          <el-input-number v-model="prizeDialog.max_qty" :min="1" style="width: 180px" />
        </el-form-item>
        <el-form-item label="爆率峰值">
          <el-input-number v-model="prizeDialog.hot_qty" :min="1" style="width: 180px" />
          <span class="muted" style="margin-left: 8px">首摇最容易摇到的数量</span>
        </el-form-item>
        <el-form-item label="看广告加成">
          <el-input-number v-model="prizeDialog.ad_qty" :min="1" style="width: 180px" />
          <span class="muted" style="margin-left: 8px">每次看广告追加数量</span>
        </el-form-item>
        <el-form-item label="最高看广告次数">
          <el-input-number v-model="prizeDialog.max_ad_times" :min="0" :max="10" style="width: 180px" />
          <span class="muted" style="margin-left: 8px">单次抽取看广告上限（用户默认 4）</span>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="prizeDialog.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="prizeDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="savingPrize" @click="savePrize">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.admin-page { display: flex; flex-direction: column; gap: 14px; }
.muted { color: var(--el-text-color-secondary); font-size: 12px; }
.prize-img-row { display: flex; align-items: flex-start; gap: 12px; }
.prize-img-preview { width: 64px; height: 64px; border-radius: 10px; overflow: hidden; background: #f2f3f5; flex-shrink: 0; }
.prize-img-preview .el-image { width: 64px; height: 64px; }
.prize-img-empty { display: flex; align-items: center; justify-content: center; width: 64px; height: 64px; font-size: 26px; }
.prize-img-ctrl { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; }
</style>