<script setup lang="ts">
/**
 * 发布组局页面（真实后端）
 * - 顶部：返回 + 标题 + 发布按钮
 * - 表单：标题、类型（线上/线下）、分类、时间、地点、人数、描述、图片（真实上传）
 */
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '../components/native'
import { useSessionStore } from '../stores/session'
import { useUIStore } from '../stores/ui'
import { toast } from '../components/native/Toast'
import { uploadImage } from '../api/image'
import { createGathering } from '../api/gathering'

const router = useRouter()
const session = useSessionStore()
const uiStore = useUIStore()

const submitting = ref(false)

// 表单
const form = reactive({
  title: '',
  type: 'online' as 'online' | 'offline',
  category: '游戏组局',
  start_time: '',
  end_time: '',
  location: '',
  max_people: 6,
  description: '',
  images: [] as string[],
})

const categories = ['游戏组局', '现实组局', '运动健身', '吃饭拼单', '学习自习', '其他']

function onBack() {
  if (window.history.length > 1) router.back()
  else router.push('/')
}

function setType(t: 'online' | 'offline') {
  form.type = t
}

// ====== 真实图片上传 ======
const fileInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
// 每张图的上传进度（与 form.images 下标对应，-1 表示不在上传）
const uploadProgress = ref<number[]>([])

function addImage() {
  if (form.images.length >= 9) {
    toast.error('最多上传 9 张图片')
    return
  }
  fileInput.value?.click()
}

function removeImage(index: number) {
  form.images.splice(index, 1)
  uploadProgress.value.splice(index, 1)
}

async function onFilesSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = '' // 允许重复选择同一文件
  if (!files.length) return

  const remain = 9 - form.images.length
  if (files.length > remain) {
    toast.error(`最多还能上传 ${remain} 张图片`)
  }

  for (const file of files.slice(0, remain)) {
    if (!file.type.startsWith('image/')) {
      toast.error('仅支持图片文件')
      continue
    }
    if (file.size > 5 * 1024 * 1024) {
      toast.error('单张图片不能超过 5MB')
      continue
    }
    const index = form.images.length
    form.images.push('') // 占位
    uploadProgress.value[index] = 0
    uploading.value = true
    try {
      const { data: resp } = await uploadImage(file, (p) => {
        uploadProgress.value[index] = p
      }, 'activity')
      form.images[index] = resp.data.url
    } catch {
      // 上传失败：移除占位
      form.images.splice(index, 1)
      uploadProgress.value.splice(index, 1)
    } finally {
      uploading.value = false
    }
  }
}

function isImageUrl(url: string | null | undefined): boolean {
  return !!url && (url.startsWith('/') || url.startsWith('http'))
}

// datetime-local 是本地时间，转成 UTC ISO 字符串发给后端
function toUtcIso(local: string): string | null {
  if (!local) return null
  const d = new Date(local)
  if (Number.isNaN(d.getTime())) return null
  return d.toISOString()
}

async function onPublish() {
  if (!session.isLoggedIn()) {
    uiStore.openAuthDialog()
    return
  }
  if (!form.title.trim()) {
    toast.error('请输入组局标题')
    return
  }
  if (!form.start_time) {
    toast.error('请选择开始时间')
    return
  }
  if (new Date(form.start_time).getTime() <= Date.now()) {
    toast.error('开始时间必须晚于当前时间')
    return
  }
  if (form.end_time && form.start_time && form.end_time <= form.start_time) {
    toast.error('结束时间必须晚于开始时间')
    return
  }
  if (form.type === 'offline' && !form.location.trim()) {
    toast.error('请填写线下地点')
    return
  }
  if (uploading.value) {
    toast.error('图片上传中，请稍候...')
    return
  }
  // 过滤掉上传失败的空占位
  const images = form.images.filter((u) => !!u)

  submitting.value = true
  try {
    await createGathering({
      title: form.title.trim(),
      type: form.type,
      category: form.category,
      start_time: toUtcIso(form.start_time) || form.start_time,
      end_time: toUtcIso(form.end_time),
      location: form.type === 'offline' ? form.location.trim() : null,
      max_people: form.max_people,
      description: form.description.trim(),
      images,
    })
    toast.success('发布成功')
    router.replace('/gatherings')
  } catch {
    // 错误提示由 http 拦截器统一处理
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="publish-gathering-page">
    <!-- 顶部导航 -->
    <header class="pg-header">
      <button class="pg-header__back" type="button" @click="onBack">
        <Icon name="chevron-left" :size="24" />
      </button>
      <h1 class="pg-header__title">发布组局</h1>
      <button
        class="pg-header__submit"
        :class="{ 'is-disabled': submitting }"
        :disabled="submitting"
        type="button"
        @click="onPublish"
      >
        {{ submitting ? '发布中...' : '发布' }}
      </button>
    </header>

    <!-- 表单内容 -->
    <main class="pg-body">
      <!-- 类型切换 -->
      <div class="pg-section">
        <div class="pg-type-switch">
          <button
            class="pg-type-btn"
            :class="{ 'is-active': form.type === 'online' }"
            type="button"
            @click="setType('online')"
          >
            <span class="pg-type-btn__icon">🎮</span>
            <span class="pg-type-btn__label">线上组局</span>
          </button>
          <button
            class="pg-type-btn"
            :class="{ 'is-active': form.type === 'offline' }"
            type="button"
            @click="setType('offline')"
          >
            <span class="pg-type-btn__icon">📍</span>
            <span class="pg-type-btn__label">线下组局</span>
          </button>
        </div>
      </div>

      <!-- 标题 -->
      <div class="pg-section">
        <input
          v-model="form.title"
          class="pg-title-input"
          type="text"
          placeholder="起个吸引人的标题吧..."
          maxlength="50"
        />
      </div>

      <!-- 分类选择 -->
      <div class="pg-section">
        <div class="pg-field">
          <div class="pg-field__label">组局分类</div>
          <div class="pg-cats">
            <button
              v-for="cat in categories"
              :key="cat"
              class="pg-cat"
              :class="{ 'is-active': form.category === cat }"
              type="button"
              @click="form.category = cat"
            >
              {{ cat }}
            </button>
          </div>
        </div>
      </div>

      <!-- 时间 -->
      <div class="pg-section">
        <div class="pg-field">
          <div class="pg-field__row">
            <div class="pg-field__label">开始时间</div>
            <input
              v-model="form.start_time"
              class="pg-field__input"
              type="datetime-local"
            />
          </div>
          <div class="pg-field__divider"></div>
          <div class="pg-field__row">
            <div class="pg-field__label">结束时间</div>
            <input
              v-model="form.end_time"
              class="pg-field__input"
              type="datetime-local"
            />
          </div>
        </div>
      </div>

      <!-- 地点（线下显示） -->
      <div v-if="form.type === 'offline'" class="pg-section">
        <div class="pg-field">
          <div class="pg-field__row">
            <div class="pg-field__label">活动地点</div>
            <input
              v-model="form.location"
              class="pg-field__input"
              type="text"
              placeholder="输入地点或点击选择"
            />
            <Icon name="map-pin" :size="16" class="pg-field__icon" />
          </div>
        </div>
      </div>

      <!-- 人数 -->
      <div class="pg-section">
        <div class="pg-field">
          <div class="pg-field__row">
            <div class="pg-field__label">人数上限</div>
            <div class="pg-people">
              <button
                class="pg-people__btn"
                type="button"
                @click="form.max_people = Math.max(2, form.max_people - 1)"
              >
                −
              </button>
              <span class="pg-people__num">{{ form.max_people }}人</span>
              <button
                class="pg-people__btn"
                type="button"
                @click="form.max_people = Math.min(50, form.max_people + 1)"
              >
                +
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 描述 -->
      <div class="pg-section">
        <textarea
          v-model="form.description"
          class="pg-desc"
          placeholder="介绍一下组局内容、注意事项、联系方式..."
          rows="5"
          maxlength="500"
        ></textarea>
        <div class="pg-desc__count">{{ form.description.length }}/500</div>
      </div>

      <!-- 图片上传（真实上传） -->
      <div class="pg-section">
        <div class="pg-field__label" style="margin-bottom: 12px">活动图片（选填，最多9张）</div>
        <div class="pg-images">
          <div
            v-for="(img, idx) in form.images"
            :key="idx"
            class="pg-img-item"
          >
            <img v-if="isImageUrl(img)" class="pg-img-item__photo" :src="img" alt="活动图片" />
            <div v-else class="pg-img-item__placeholder">
              <span class="pg-img-item__spinner"></span>
              <span class="pg-img-item__progress">{{ uploadProgress[idx] || 0 }}%</span>
            </div>
            <button class="pg-img-item__remove" type="button" @click="removeImage(idx)">
              <Icon name="x" :size="14" />
            </button>
          </div>
          <button
            v-if="form.images.length < 9"
            class="pg-img-add"
            type="button"
            @click="addImage"
          >
            <Icon name="plus" :size="24" />
            <span>{{ uploading ? '上传中...' : '添加图片' }}</span>
          </button>
        </div>
      </div>

      <!-- 隐藏文件选择器 -->
      <input
        ref="fileInput"
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif"
        multiple
        style="display: none"
        @change="onFilesSelected"
      />

      <div class="pg-bottom-space"></div>
    </main>
  </div>
</template>

<style scoped>
.publish-gathering-page {
  min-height: 100vh;
  background: var(--bg-100);
}

/* ====== 顶部导航 ====== */
.pg-header {
  position: sticky;
  top: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 48px;
  padding: 0 8px 0 4px;
  background: color-mix(in srgb, var(--bg-50) 92%, transparent);
  -webkit-backdrop-filter: blur(20px);
  backdrop-filter: blur(20px);
  border-bottom: 0.5px solid var(--bg-300);
  max-width: 720px;
  margin: 0 auto;
}
.pg-header__back {
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--text-800);
  border-radius: 50%;
  transition: background 150ms ease;
}
.pg-header__back:hover { background: var(--bg-200); }
.pg-header__back :deep(svg) { width: 24px; height: 24px; }
.pg-header__title {
  font-size: 17px;
  font-weight: 600;
  color: var(--text-900);
  margin: 0;
}
.pg-header__submit {
  padding: 6px 16px;
  background: var(--brand-500);
  color: #fff;
  border: none;
  border-radius: 16px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 150ms ease;
}
.pg-header__submit:hover { opacity: 0.85; }
.pg-header__submit.is-disabled { opacity: 0.5; cursor: not-allowed; }

/* ====== 表单主体 ====== */
.pg-body {
  max-width: 720px;
  margin: 0 auto;
  padding: 12px 16px;
}
.pg-section {
  background: var(--bg-50);
  border-radius: 14px;
  margin-bottom: 12px;
  overflow: hidden;
  border: 0.5px solid var(--bg-200);
}

/* 类型切换 */
.pg-type-switch {
  display: flex;
  gap: 10px;
  padding: 16px;
}
.pg-type-btn {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 16px 12px;
  background: var(--bg-100);
  border: 1.5px solid transparent;
  border-radius: 12px;
  cursor: pointer;
  transition: all 150ms ease;
}
.pg-type-btn.is-active {
  background: color-mix(in srgb, var(--brand-500) 8%, transparent);
  border-color: var(--brand-500);
}
.pg-type-btn__icon { font-size: 28px; }
.pg-type-btn__label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-700);
}
.pg-type-btn.is-active .pg-type-btn__label { color: var(--brand-500); }

/* 标题输入 */
.pg-title-input {
  width: 100%;
  padding: 18px 16px;
  border: none;
  background: transparent;
  font-size: 17px;
  font-weight: 600;
  color: var(--text-900);
  outline: none;
}
.pg-title-input::placeholder {
  color: var(--text-400);
  font-weight: 500;
}

/* 字段行 */
.pg-field { padding: 0 16px; }
.pg-field__row {
  display: flex;
  align-items: center;
  min-height: 50px;
  position: relative;
}
.pg-field__label {
  flex-shrink: 0;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-800);
  width: 80px;
}
.pg-field__input {
  flex: 1;
  border: none;
  background: transparent;
  font-size: 14px;
  color: var(--text-800);
  text-align: right;
  outline: none;
  min-width: 0;
}
.pg-field__icon {
  margin-left: 8px;
  color: var(--text-400);
  flex-shrink: 0;
}
.pg-field__icon :deep(svg) { width: 16px; height: 16px; }
.pg-field__divider {
  height: 0.5px;
  background: var(--bg-200);
  margin-left: 80px;
}

/* 分类标签 */
.pg-cats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 0 16px;
}
.pg-cat {
  padding: 7px 14px;
  background: var(--bg-100);
  border: 1px solid transparent;
  border-radius: 16px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-600);
  cursor: pointer;
  transition: all 150ms ease;
}
.pg-cat.is-active {
  background: color-mix(in srgb, var(--brand-500) 10%, transparent);
  border-color: var(--brand-500);
  color: var(--brand-500);
}

/* 人数选择 */
.pg-people {
  display: flex;
  align-items: center;
  gap: 16px;
}
.pg-people__btn {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-100);
  border: none;
  border-radius: 50%;
  font-size: 18px;
  font-weight: 500;
  color: var(--text-700);
  cursor: pointer;
  transition: background 150ms ease;
}
.pg-people__btn:hover { background: var(--bg-200); }
.pg-people__num {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-800);
  min-width: 48px;
  text-align: center;
}

/* 描述 */
.pg-desc {
  width: 100%;
  padding: 16px;
  border: none;
  background: transparent;
  font-size: 14px;
  color: var(--text-800);
  line-height: 1.6;
  outline: none;
  resize: none;
  font-family: inherit;
}
.pg-desc::placeholder { color: var(--text-400); }
.pg-desc__count {
  text-align: right;
  padding: 0 16px 12px;
  font-size: 12px;
  color: var(--text-400);
}

/* 图片上传 */
.pg-section .pg-field__label { padding: 16px 16px 0; }
.pg-images {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  padding: 0 16px 16px;
}
.pg-img-item {
  position: relative;
  aspect-ratio: 1;
  background: var(--bg-100);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.pg-img-item__photo {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.pg-img-item__placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  height: 100%;
}
.pg-img-item__spinner {
  width: 22px;
  height: 22px;
  border: 2.5px solid var(--bg-200);
  border-top-color: var(--brand-500);
  border-radius: 50%;
  animation: pg-spin 0.8s linear infinite;
}
@keyframes pg-spin {
  to { transform: rotate(360deg); }
}
.pg-img-item__progress {
  font-size: 11px;
  color: var(--text-400);
}
.pg-img-item__remove {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
  color: #fff;
  border: none;
  border-radius: 50%;
  cursor: pointer;
}
.pg-img-item__remove :deep(svg) { width: 14px; height: 14px; }
.pg-img-add {
  aspect-ratio: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  background: var(--bg-100);
  border: 1px dashed var(--bg-300);
  border-radius: 10px;
  color: var(--text-400);
  font-size: 11px;
  cursor: pointer;
  transition: all 150ms ease;
}
.pg-img-add:hover {
  border-color: var(--brand-400);
  color: var(--brand-500);
}
.pg-img-add :deep(svg) { width: 24px; height: 24px; }

.pg-bottom-space { height: 40px; }
</style>
