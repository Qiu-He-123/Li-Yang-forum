<script setup lang="ts">
/**
 * 宠物商城管理（后台，真实后端）
 * - 商品列表：搜索 / 分类筛选 / 状态筛选 / 分页
 * - 新增/编辑商品（图片上传 + 3D 模型 GLB/GLTF 上传，带进度）
 * - 上下架 / 删除
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules, type UploadFile } from 'element-plus'
import {
  adminPetShopCategories,
  adminPetShopCreate,
  adminPetShopDelete,
  adminPetShopList,
  adminPetShopToggle,
  adminPetShopUpdate,
  adminPetShopUploadImage,
  adminPetShopUploadModel,
  adminPetAiUpdateProduct,
  type AdminPetCategory,
  type AdminPetProduct,
  type PetProductCreatePayload,
} from '../../api/admin'
import { adminUploadPetZip } from '../../api/petShop'

// ====== 列表 ======
const loading = ref(false)
const list = ref<AdminPetProduct[]>([])
const total = ref(0)
const page = reactive({ page: 1, page_size: 10 })

const searchKeyword = ref('')
const filterCategory = ref('')
const filterStatus = ref<number | ''>('')

// 分类（后端加载）
const categories = ref<AdminPetCategory[]>([])
const categoryNames = ref<string[]>([])

function isImageUrl(url: string | null | undefined): boolean {
  return !!url && (url.startsWith('/') || url.startsWith('http'))
}

async function loadCategories() {
  try {
    const { data } = await adminPetShopCategories()
    categories.value = (data as any).data ?? []
    categoryNames.value = categories.value.map((c) => c.name)
  } catch {
    categories.value = []
    categoryNames.value = []
  }
}

function onSearch() {
  page.page = 1
  load()
}

async function load() {
  loading.value = true
  try {
    const { data } = await adminPetShopList({
      keyword: searchKeyword.value || undefined,
      category: filterCategory.value || undefined,
      status: filterStatus.value === '' ? undefined : filterStatus.value,
      page: page.page,
      page_size: page.page_size,
    })
    list.value = (data as any).data?.items || []
    total.value = (data as any).data?.total || 0
  } catch {
    // 错误提示由 http 拦截器统一处理
  } finally {
    loading.value = false
  }
}

// ====== 新增/编辑 ======
const dialogVisible = ref(false)
const dialogMode = ref<'create' | 'edit'>('create')
const formRef = ref<FormInstance>()
const form = reactive({
  id: 0,
  name: '',
  category: '',
  price: 0,
  original_price: 0,
  stock: 0,
  image_url: '',
  model_3d_url: '',
  description: '',
  status: 1,
  // 商品类型（1=萌宠领养 2=道具 3=进化道具）
  kind: 1,
  // 宠物是否可飞行（仅 kind=1）
  can_fly: false,
  // 道具好感加成（kind=2 食物）
  affinity_gain: 0,
  // 道具按子类型定制的数值（kind=2）：affinity/satiety/mood/play/stamina/health
  attrsObj: {} as Record<string, number>,
  attrType: 'food' as 'food' | 'toy' | 'medical' | 'daily',
  ai_enabled: false,
  ai_wake_enabled: false,
  ai_persona: '',
  game_speech: '',
})
const rules: FormRules = {
  name: [{ required: true, message: '请输入商品名称', trigger: 'blur' }],
  category: [{ required: true, message: '请选择或输入分类', trigger: 'change' }],
  price: [{ required: true, message: '请输入售价', trigger: 'blur' }],
  stock: [{ required: true, message: '请输入库存', trigger: 'blur' }],
}
const submitting = ref(false)

// 道具子类型 → 可定制的数值字段
const ATTR_TYPES: Record<'food' | 'toy' | 'medical' | 'daily', { label: string; fields: [string, string][] }> = {
  food: { label: '食物（狗粮/猫粮/零食）', fields: [['affinity', '好感增加'], ['satiety', '饱腹增加']] },
  toy: { label: '玩具', fields: [['affinity', '好感增加'], ['mood', '心情增加'], ['play', '玩耍值增加']] },
  medical: { label: '医疗', fields: [['affinity', '好感增加'], ['mood', '心情增加'], ['stamina', '体力增加'], ['health', '健康增加']] },
  daily: { label: '日用', fields: [['affinity', '好感增加'], ['mood', '心情增加']] },
}
function attrValuesOf(key: string, fieldName: string): number {
  return Number(form.attrsObj[fieldName] ?? 0) || 0
}
function setAttrValue(fieldName: string, val: number | null) {
  const v = Number(val ?? 0) || 0
  if (v <= 0) delete form.attrsObj[fieldName]
  else form.attrsObj[fieldName] = v
}
function attrFields() {
  return ATTR_TYPES[form.attrType].fields
}
// 切换类型时重置 attrs
function onKindChange() {
  form.attrsObj = {}
}
function onAttrTypeChange() {
  form.attrsObj = {}
}

// 图片上传状态
const imageUploading = ref(false)
// 3D 模型上传状态
const modelUploading = ref(false)
const modelProgress = ref(0)

function openCreate() {
  dialogMode.value = 'create'
  form.id = 0
  form.name = ''
  form.category = categoryNames.value[0] || ''
  form.price = 0
  form.original_price = 0
  form.stock = 0
  form.image_url = ''
  form.model_3d_url = ''
  form.description = ''
  form.status = 1
  form.kind = 1
  form.can_fly = false
  form.affinity_gain = 0
  form.attrsObj = {}
  form.attrType = 'food'
  form.ai_enabled = false
  form.ai_wake_enabled = false
  form.ai_persona = ''
  form.game_speech = ''
  dialogVisible.value = true
}

function openEdit(row: any) {
  dialogMode.value = 'edit'
  form.id = row.id
  form.name = row.name
  form.category = row.category || ''
  form.price = row.price
  form.original_price = row.original_price ?? 0
  form.stock = row.stock
  form.image_url = row.image_url || ''
  form.model_3d_url = row.model_3d_url || ''
  form.description = row.description || ''
  form.status = row.status
  form.kind = row.kind ?? 1
  form.can_fly = !!row.can_fly
  form.affinity_gain = row.affinity_gain ?? 0
  const attrs = row.attrs && typeof row.attrs === 'object' ? row.attrs : {}
  form.attrsObj = { ...(attrs as Record<string, number>) }
  // 由已填字段反推道具子类型：含 play→玩具；含 stamina/health→医疗；有 satiety→食物；否则按分类猜
  form.attrType = (attrs as any).play
    ? 'toy'
    : (attrs as any).stamina || (attrs as any).health
      ? 'medical'
      : (attrs as any).satiety
        ? 'food'
        : /玩具/.test(row.category || '')
          ? 'toy'
          : /狗粮|猫粮|零食|食物/.test(row.category || '')
            ? 'food'
            : /医疗|保健/.test(row.category || '')
              ? 'medical'
              : 'daily'
  if (form.affinity_gain) form.attrsObj = { ...form.attrsObj, affinity: form.affinity_gain }
  form.ai_enabled = !!row.ai_enabled
  form.ai_wake_enabled = !!row.ai_wake_enabled
  form.ai_persona = row.ai_persona || ''
  form.game_speech = row.game_speech || ''
  dialogVisible.value = true
}

async function onSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      const payload: Record<string, any> = {
        name: form.name.trim(),
        category: form.category.trim(),
        price: form.price,
        original_price: form.original_price > 0 ? form.original_price : null,
        stock: form.stock,
        image_url: form.image_url.trim() || '',
        model_3d_url: form.model_3d_url.trim() || '',
        description: form.description.trim(),
        status: form.status,
        kind: form.kind,
      }
      if (form.kind === 1) {
        payload.can_fly = form.can_fly
      } else if (form.kind === 2) {
        const gains = Object.fromEntries(
          Object.entries(form.attrsObj).filter(([, v]) => Number(v) > 0),
        )
        if (gains.affinity) payload.affinity_gain = Number(gains.affinity)
        if (Object.keys(gains).length) payload.attrs = gains
      }
      let savedProductId = form.id
      if (dialogMode.value === 'create') {
        const { data } = await adminPetShopCreate(payload as PetProductCreatePayload)
        savedProductId = (data as any).data?.id ?? form.id
        ElMessage.success('创建成功')
      } else {
        await adminPetShopUpdate(form.id, payload as Partial<PetProductCreatePayload>)
        ElMessage.success('更新成功')
      }
      // 宠物（kind=1）附带保存 AI 设定（与商品"放一起"管理）
      if (savedProductId && form.kind === 1) {
        try {
          await adminPetAiUpdateProduct(savedProductId, {
            ai_enabled: form.ai_enabled,
            ai_wake_enabled: form.ai_wake_enabled,
            ai_persona: form.ai_persona.trim(),
            game_speech: form.game_speech.trim() || undefined,
          })
        } catch {
          // AI 设定保存失败不阻塞商品保存，拦截器已提示
        }
      }
      dialogVisible.value = false
      load()
      // 分类可能被新建，刷新分类列表
      loadCategories()
    } catch {
      // 错误提示由 http 拦截器统一处理
    } finally {
      submitting.value = false
    }
  })
}

// ====== 图片上传（≤5MB，也支持直接填 emoji/URL） ======
async function onImageFileChange(file: UploadFile) {
  if (!file.raw) return
  if (file.raw.size > 5 * 1024 * 1024) {
    ElMessage.error('图片大小不能超过 5MB')
    return
  }
  imageUploading.value = true
  try {
    const { data } = await adminPetShopUploadImage(file.raw)
    form.image_url = (data as any).data.url
    ElMessage.success('图片上传成功')
  } catch {
    // 错误提示由 http 拦截器统一处理
  } finally {
    imageUploading.value = false
  }
}

// ====== 3D 模型上传（GLB/GLTF，≤20MB，带进度） ======
async function onModelFileChange(file: UploadFile) {
  if (!file.raw) return
  const name = file.raw.name.toLowerCase()
  if (!name.endsWith('.glb') && !name.endsWith('.gltf')) {
    ElMessage.error('仅支持 GLB / GLTF 格式的 3D 模型文件')
    return
  }
  if (file.raw.size > 20 * 1024 * 1024) {
    ElMessage.error('模型文件大小不能超过 20MB')
    return
  }
  modelUploading.value = true
  modelProgress.value = 0
  try {
    const { data } = await adminPetShopUploadModel(file.raw, (p) => {
      modelProgress.value = p
    })
    form.model_3d_url = (data as any).data.url
    ElMessage.success('3D 模型上传成功')
  } catch {
    // 错误提示由 http 拦截器统一处理
  } finally {
    modelUploading.value = false
    modelProgress.value = 0
  }
}

function clearModel() {
  form.model_3d_url = ''
}

// ====== 上传 ZIP 制作宠物（仅萌宠领养 kind=1，≤20MB） ======
const zipUploading = ref(false)
const zipStatus = ref('')

function categoryNameById(id: number | null | undefined): string {
  if (id == null) return ''
  const c = categories.value.find((x) => x.id === id)
  return c ? c.name : ''
}

async function onZipFileChange(file: UploadFile) {
  if (!file.raw) return
  const name = file.raw.name.toLowerCase()
  const ext = name.includes('.') ? name.split('.').pop() || '' : ''
  if (!['zip', 'rar', '7z'].includes(ext)) {
    ElMessage.error('仅支持 ZIP / RAR / 7Z 压缩包（DyberPet 宠物资源常以 RAR 发布，改后缀无效已无需）')
    return
  }
  // 前端放宽到服务端原始读取上限（100MB）；最终以服务端"帧图压缩后 ≤20MB"判定为准
  if (file.raw.size > 100 * 1024 * 1024) {
    ElMessage.error('原始压缩包不能超过 100MB')
    return
  }
  // 若当前表单已选了已存在的分类，则随表单字段一并提交
  let categoryId: number | undefined
  if (form.category) {
    const c = categories.value.find((x) => x.name === form.category)
    if (c) categoryId = c.id
  }
  zipUploading.value = true
  // 上传中的阶段提示：先传文件，再服务端解析/压缩帧图（耗时较长）
  zipStatus.value = `正在上传「${file.raw.name}」并解析动作…`
  const statusTimer = window.setTimeout(() => {
    zipStatus.value = '正在压缩帧图为 WebP（帧数多可能需要 1~2 分钟）…'
  }, 4000)
  try {
    const { data } = await adminUploadPetZip(
      file.raw,
      {
        name: form.name.trim() || undefined,
        price: form.price > 0 ? form.price : undefined,
        category_id: categoryId,
        description: form.description.trim() || undefined,
      },
    )
    const product = (data as any).data?.product
    if (product) {
      if (product.name) form.name = product.name
      if (product.price != null) form.price = product.price
      if (product.category) form.category = product.category
      else if (product.category_id) form.category = categoryNameById(product.category_id)
      if (product.description) form.description = product.description
      if (product.image_url) form.image_url = product.image_url
      if (product.model_3d_url) form.model_3d_url = product.model_3d_url
      ElMessage.success(`宠物制作成功：${product.name}，已完成信息回填`)
    } else {
      ElMessage.success('ZIP 已上传，请完善其它信息后保存')
    }
  } catch (e: unknown) {
    const err = e as { message?: string; response?: { data?: { msg?: string } } }
    ElMessage.error(err.response?.data?.msg || err.message || '上传宠物失败，请检查压缩包格式后重试')
    zipStatus.value = '上传失败，请重试'
  } finally {
    window.clearTimeout(statusTimer)
    zipUploading.value = false
    // 稍后清空失败态文字
    window.setTimeout(() => {
      zipStatus.value = ''
    }, 3000)
  }
}

// ====== 上下架 ======
async function toggleStatus(row: any) {
  const newStatus = row.status === 1 ? 0 : 1
  try {
    const { data } = await adminPetShopToggle(row.id, newStatus)
    row.status = (data as any).data.status
    ElMessage.success(newStatus === 1 ? '已上架' : '已下架')
  } catch {
    // 错误提示由 http 拦截器统一处理
  }
}

// ====== 删除 ======
async function onDelete(row: any) {
  try {
    await ElMessageBox.confirm(`确定删除商品「${row.name}」吗？`, '确认删除', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await adminPetShopDelete(row.id)
    ElMessage.success('删除成功')
    load()
  } catch {
    // 取消或错误
  }
}

onMounted(() => {
  loadCategories()
  load()
})
</script>

<template>
  <div class="admin-pet-shop">
    <!-- 筛选栏 -->
    <div class="filter-bar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索商品名称..."
        clearable
        style="width: 240px"
        @keyup.enter="onSearch"
        @clear="onSearch"
      />
      <el-select v-model="filterCategory" placeholder="全部分类" clearable style="width: 140px" @change="onSearch">
        <el-option v-for="c in categoryNames" :key="c" :label="c" :value="c" />
      </el-select>
      <el-select v-model="filterStatus" placeholder="全部状态" clearable style="width: 120px" @change="onSearch">
        <el-option label="已上架" :value="1" />
        <el-option label="已下架" :value="0" />
      </el-select>
      <el-button type="primary" @click="onSearch">搜索</el-button>
      <div style="flex: 1"></div>
      <el-button type="primary" @click="openCreate">+ 新增商品</el-button>
    </div>

    <!-- 数据表格 -->
    <el-table v-loading="loading" :data="list" border stripe style="width: 100%">
      <el-table-column prop="id" label="ID" width="70" align="center" />
      <el-table-column label="商品" min-width="260">
        <template #default="{ row }">
          <div style="display: flex; align-items: center; gap: 12px">
            <div
              style="width: 48px; height: 48px; border-radius: 8px; background: #f2f4f7; display: flex; align-items: center; justify-content: center; font-size: 28px; flex-shrink: 0; overflow: hidden"
            >
              <img
                v-if="isImageUrl(row.image_url)"
                :src="row.image_url"
                style="width: 100%; height: 100%; object-fit: cover"
                alt=""
              />
              <template v-else>{{ row.image_url || '🐾' }}</template>
            </div>
            <div>
              <div style="font-weight: 500; color: #1d1d1f; margin-bottom: 2px">
                {{ row.name }}
                <el-tag v-if="row.model_3d_url" size="small" style="margin-left: 6px">3D</el-tag>
                <el-tag v-if="(row.kind ?? 1) !== 1" size="small" type="info" style="margin-left: 6px">{{
                  row.kind === 2 ? '道具' : '进化'
                }}</el-tag>
                <el-tag v-else :type="row.ai_enabled ? 'success' : 'info'" size="small" style="margin-left: 6px">
                  {{ row.ai_enabled ? 'AI' : '无AI' }}
                </el-tag>
              </div>
              <div style="font-size: 12px; color: #86868b">{{ row.category }}</div>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="价格" width="140" align="center">
        <template #default="{ row }">
          <div style="color: #ff3b30; font-weight: 600">¥{{ row.price }}</div>
          <div v-if="row.original_price" style="font-size: 12px; color: #86868b; text-decoration: line-through">
            ¥{{ row.original_price }}
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="stock" label="库存" width="90" align="center" />
      <el-table-column prop="sales" label="销量" width="90" align="center" />
      <el-table-column label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.status === 1 ? 'success' : 'info'" size="small">
            {{ row.status === 1 ? '已上架' : '已下架' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="170" align="center" />
      <el-table-column label="操作" width="220" align="center" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="openEdit(row)">编辑</el-button>
          <el-button :type="row.status === 1 ? 'warning' : 'success'" link size="small" @click="toggleStatus(row)">
            {{ row.status === 1 ? '下架' : '上架' }}
          </el-button>
          <el-button type="danger" link size="small" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pagination-wrap">
      <el-pagination
        v-model:current-page="page.page"
        v-model:page-size="page.page_size"
        :total="total"
        layout="total, prev, pager, next, jumper"
        background
        @current-change="load"
      />
    </div>

    <!-- 新增/编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'create' ? '新增商品' : '编辑商品'"
      width="560px"
      :close-on-click-modal="false"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="商品名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入商品名称" maxlength="100" show-word-limit />
        </el-form-item>
        <el-form-item label="商品类型">
          <el-radio-group v-model="form.kind" @change="onKindChange">
            <el-radio-button :value="1">萌宠领养</el-radio-button>
            <el-radio-button :value="2">道具</el-radio-button>
            <el-radio-button :value="3">进化道具</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <!-- 萌宠领养（kind=1）：上传 ZIP 制作宠物 -->
        <el-form-item v-if="form.kind === 1" label="压缩包制作">
          <div class="upload-row">
            <el-upload
              :auto-upload="false"
              :show-file-list="false"
              accept=".zip,.rar,.7z,application/zip,application/x-rar-compressed,application/x-7z-compressed"
              :on-change="onZipFileChange"
            >
              <el-button :loading="zipUploading">
                {{ zipUploading ? '处理中...' : '上传宠物压缩包' }}
              </el-button>
            </el-upload>
            <el-progress
              v-if="zipUploading"
              :percentage="100"
              :indeterminate="true"
              :duration="1.5"
              :show-text="false"
              style="flex: 1"
            />
          </div>
          <div v-if="zipUploading" class="zip-status uploading">{{ zipStatus }}</div>
          <div v-else-if="zipStatus" class="zip-status">{{ zipStatus }}</div>
          <span class="upload-tip">
            支持 ZIP / RAR / 7Z 压缩包：内含 act_conf.json 动作配置 + action/ 帧图 PNG（DyberPet 格式）。
            服务端自动压缩帧图，压缩后总大小 ≤20MB 才通过；帧图过多会超限，需精简帧数后重试。
            上传成功会按宠物名自动回填名称/价格/分类等信息。
          </span>
        </el-form-item>
        <el-form-item label="分类" prop="category">
          <el-select
            v-model="form.category"
            placeholder="选择或输入新分类（自动创建）"
            style="width: 100%"
            filterable
            allow-create
            default-first-option
          >
            <el-option v-for="c in categoryNames" :key="c" :label="c" :value="c" />
          </el-select>
        </el-form-item>
        <el-form-item label="售价" prop="price">
          <el-input-number v-model="form.price" :min="0" :precision="2" :step="1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="原价">
          <el-input-number v-model="form.original_price" :min="0" :precision="2" :step="1" style="width: 100%" placeholder="留空表示无原价" />
        </el-form-item>
        <el-form-item label="库存" prop="stock">
          <el-input-number v-model="form.stock" :min="0" :step="1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="商品图片">
          <div class="upload-row">
            <el-upload
              :auto-upload="false"
              :show-file-list="false"
              accept="image/png,image/jpeg,image/webp,image/gif"
              :on-change="onImageFileChange"
            >
              <el-button :loading="imageUploading">
                {{ imageUploading ? '上传中...' : isImageUrl(form.image_url) ? '重新上传' : '上传图片' }}
              </el-button>
            </el-upload>
            <div v-if="form.image_url" class="upload-preview">
              <img v-if="isImageUrl(form.image_url)" :src="form.image_url" alt="商品图" />
              <span v-else class="upload-preview__emoji">{{ form.image_url }}</span>
            </div>
            <el-input
              v-model="form.image_url"
              placeholder="图片 URL 或 emoji（如 🐱）"
              style="flex: 1"
            />
          </div>
        </el-form-item>
        <el-form-item label="3D 模型">
          <div class="upload-row">
            <el-upload
              :auto-upload="false"
              :show-file-list="false"
              accept=".glb,.gltf"
              :on-change="onModelFileChange"
            >
              <el-button :loading="modelUploading">
                {{ modelUploading ? `上传中 ${modelProgress}%` : form.model_3d_url ? '重新上传' : '上传 GLB/GLTF' }}
              </el-button>
            </el-upload>
            <el-input
              v-model="form.model_3d_url"
              placeholder="3D 模型地址（选填，上传后自动填入）"
              style="flex: 1"
            />
            <el-button v-if="form.model_3d_url" link type="danger" @click="clearModel">清除</el-button>
          </div>
          <div class="upload-tip">支持 GLB / GLTF，≤20MB。上传后商品详情页将以 360° 3D 形式展示。</div>
        </el-form-item>
        <el-form-item label="商品描述">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="商品描述..." maxlength="500" show-word-limit />
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="form.status">
            <el-radio :value="1">上架</el-radio>
            <el-radio :value="0">下架</el-radio>
          </el-radio-group>
        </el-form-item>

        <!-- 宠物是否可飞行（仅萌宠领养 kind=1）：开启后宠物在帖子卡片/悬浮宠会自动触发飞行动作 -->
        <el-form-item v-if="form.kind === 1" label="允许飞行">
          <el-switch v-model="form.can_fly" />
          <span class="upload-tip" style="margin-left: 10px">开启后该宠物会自动触发"上抛悬空再落回"的飞行行为</span>
        </el-form-item>

        <!-- 道具数值定制（仅道具 kind=2）：按子类型暴露不同数值编辑框 -->
        <template v-if="form.kind === 2">
          <el-divider content-position="left">道具数值定制</el-divider>
          <el-form-item label="道具子类型">
            <el-select v-model="form.attrType" style="width: 100%" @change="onAttrTypeChange">
              <el-option v-for="(t, key) in ATTR_TYPES" :key="key" :label="t.label" :value="key" />
            </el-select>
            <span class="upload-tip">不同子类型的道具可定制的数值不同；未填写的数值按默认生效。</span>
          </el-form-item>
          <el-form-item v-for="[fieldName, label] in attrFields()" :key="fieldName" :label="label">
            <el-input-number
              :model-value="attrValuesOf(label, fieldName)"
              :min="0"
              :step="1"
              :precision="0"
              style="width: 100%"
              placeholder="留空表示使用默认值"
              @update:model-value="setAttrValue(fieldName, $event as number | null)"
            />
          </el-form-item>
        </template>

        <!-- 宠物 AI 设定（仅萌宠领养 kind=1） -->
        <el-divider v-if="form.kind === 1" content-position="left">宠物 AI 设定</el-divider>
        <template v-if="form.kind === 1">
          <el-form-item label="启用 AI 对话">
            <el-switch v-model="form.ai_enabled" />
            <span class="upload-tip" style="margin-left: 10px">开启后宠物用大模型对话，失败/超限输出彩蛋话术</span>
          </el-form-item>
          <el-form-item label="允许主动找你">
            <el-switch v-model="form.ai_wake_enabled" />
            <span class="upload-tip" style="margin-left: 10px">开启后宠物会按人设自主规划时间主动找你</span>
          </el-form-item>
          <el-form-item label="人设文案">
            <el-input
              v-model="form.ai_persona"
              type="textarea"
              :rows="4"
              placeholder="描述该宠物的性格、口癖、爱好、背景。可用 {pet_name}、{owner} 占位。留空用默认人设。"
              maxlength="1000"
              show-word-limit
            />
          </el-form-item>
          <el-form-item label="游戏触发话术">
            <el-input
              v-model="form.game_speech"
              type="textarea"
              :rows="3"
              placeholder='陪我玩时宠物说的话，JSON 对象，选填。例如：{"start":"开始啦！","win":"你好棒！","lose":"再来一次嘛~","good":"不错不错~"}。留空用内置默认。'
              maxlength="1000"
              show-word-limit
            />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmit">
          {{ dialogMode === 'create' ? '创建' : '保存' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.admin-pet-shop {
  padding: 0;
}
.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
.upload-row {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
}
.upload-preview {
  width: 48px;
  height: 48px;
  border-radius: 8px;
  background: #f2f4f7;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  flex-shrink: 0;
  font-size: 26px;
}
.upload-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.upload-tip {
  width: 100%;
  font-size: 12px;
  color: #86868b;
  margin-top: 6px;
  line-height: 1.5;
}
.zip-status {
  width: 100%;
  font-size: 13px;
  color: #1d1d1f;
  margin-top: 6px;
}
.zip-status.uploading {
  color: #1677ff;
}
</style>
