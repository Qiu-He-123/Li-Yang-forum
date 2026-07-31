<script setup lang="ts">
/**
 * 原生发帖编辑器（替代 Element Plus 版本）
 * 对齐设计稿：发帖页.html
 * - 顶部固定栏：返回 + 标题 + 发布
 * - 编辑器卡片：圈子选择下拉 + 标题输入 + 正文 + 工具条
 * - 图片网格：3 列，最多 9 张
 * - 选项卡片：匿名发布 + 标记原创（iOS 开关）
 *
 * 阶段二新增：
 * - 话题（#）选择 + 标签展示
 * - @好友 选择 + 头像列表展示
 * - 位置 选择 + 标签展示
 * - 表情面板（6 分类 + 最近使用）
 * - 投票编辑器
 * - 草稿自动保存（debounce 2s + beforeunload）
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

import { Icon, Switch as NativeSwitch, Dialog as NativeDialog } from '../native'
import { toast } from '../native/Toast'
import { createPost, updatePost } from '../../api/post'
import { uploadImage } from '../../api/image'
import { searchTopics, hotTopics, type Topic } from '../../api/topic'
import type { PollCreate } from '../../api/poll'
import { listFollowing } from '../../api/follow'
import { useCircleStore } from '../../stores/circle'
import { usePostStore } from '../../stores/post'
import { useSessionStore } from '../../stores/session'
import { useSchoolStore } from '../../stores/school'
import type { FollowUser } from '../../types/api'

const props = defineProps<{
  postId?: number
  initialContent?: string
  initialTitle?: string | null
  initialCategory?: string
  initialImageUrls?: string[]
  initialIsAnonymous?: boolean
  initialIsOriginal?: boolean
  /** 初始帖子是否含 AI 内容 */
  initialHasAiContent?: boolean
  /** 阶段二：初始话题名 */
  initialTopicName?: string | null
  /** 阶段二：初始位置 */
  initialLocation?: string | null
  /** 阶段二：初始 @ 好友 id 列表 */
  initialMentionUserIds?: number[]
  /** 编辑模式：初始校区 id（用于回填校区选择） */
  initialSchoolId?: number
}>()

const emit = defineEmits<{ (e: 'published'): void; (e: 'updated'): void }>()

const circleStore = useCircleStore()
const schoolStore = useSchoolStore()
const postStore = usePostStore()
const session = useSessionStore()

// 表单
const title = ref(props.initialTitle ?? '')
const content = ref(props.initialContent ?? '')
const category = ref(props.initialCategory ?? '校园圈')
const schoolId = ref<number | undefined>(undefined)
const isAnonymous = ref(props.initialIsAnonymous ?? false)
const isOriginal = ref(props.initialIsOriginal ?? false)
const hasAiContent = ref(props.initialHasAiContent ?? false)
const imageUrls = ref<string[]>(props.initialImageUrls ? [...props.initialImageUrls] : ([] as string[]))

// ============ 阶段二：新增表单状态 ============
const topicName = ref<string | null>(props.initialTopicName ?? null)
const location = ref<string | null>(props.initialLocation ?? null)
const mentionUserIds = ref<number[]>(props.initialMentionUserIds ? [...props.initialMentionUserIds] : [])
/** @好友详情（id → nickname + avatar_url），用于编辑器下方头像展示 */
const mentionUsers = ref<Map<number, FollowUser>>(new Map())
const pollData = ref<PollCreate | null>(null)

// 初始选校区：编辑模式优先使用 initialSchoolId，否则用第一个校区
if (props.initialSchoolId) {
  schoolId.value = props.initialSchoolId
} else if (schoolStore.schools.length) {
  schoolId.value = schoolStore.schools[0].id
}
watch(
  () => schoolStore.schools,
  (schools) => {
    if (schools.length && !schoolId.value) {
      schoolId.value = props.initialSchoolId || schools[0].id
    }
  },
)
watch(
  () => props.initialSchoolId,
  (val) => {
    if (val) schoolId.value = val
  },
)

// 编辑模式：props 变化时同步表单
watch(
  () => props.postId,
  () => {
    title.value = props.initialTitle ?? ''
    content.value = props.initialContent ?? ''
    category.value = props.initialCategory ?? '校园圈'
    isAnonymous.value = props.initialIsAnonymous ?? false
    isOriginal.value = props.initialIsOriginal ?? false
    hasAiContent.value = props.initialHasAiContent ?? false
    hasSelectedCircle.value = !!props.initialCategory && props.initialCategory !== '校园圈'
    imageUrls.value = props.initialImageUrls ? [...props.initialImageUrls] : []
    topicName.value = props.initialTopicName ?? null
    location.value = props.initialLocation ?? null
    mentionUserIds.value = props.initialMentionUserIds ? [...props.initialMentionUserIds] : []
    mentionUsers.value = new Map()
    pollData.value = null
  },
)

// 圈子选择底部面板
const showCircleSheet = ref(false)
const circleSheetTab = ref<'recommend' | 'recent' | 'followed'>('recent')
const circleSearchKeyword = ref('')
const showNoCirclePrompt = ref(false)
/** 用户是否已手动选择过圈子（用于判断发布时是否需要提示） */
const hasSelectedCircle = ref(!!props.initialCategory && props.initialCategory !== '校园圈')
const circleSelectRef = ref<HTMLElement | null>(null)

const circles = computed(() => circleStore.circles)

const currentCircleName = computed(() => {
  const c = circles.value.find((x) => x.slug === category.value || x.name === category.value)
  return c?.name || category.value || '校园圈'
})

/** 已加入的圈子 */
const followedCircles = computed(() => circles.value.filter((c) => c.is_joined))

/** 根据标题 + 正文内容推荐圈子 */
const recommendedCircles = computed(() => {
  const text = (title.value + ' ' + content.value).trim().toLowerCase()
  const excludeDefault = circles.value.filter(c => c.slug !== 'default')

  if (!text) {
    return [...excludeDefault]
      .sort((a, b) => b.member_count - a.member_count)
      .slice(0, 5)
  }

  // 有内容：匹配圈子名称/描述
  const matched = excludeDefault.filter(c =>
    c.name.toLowerCase().includes(text) ||
    (c.description || '').toLowerCase().includes(text)
  )

  if (matched.length >= 4) return matched.slice(0, 5)

  // 不足4个，补充热门圈子
  const matchedSlugs = new Set(matched.map(c => c.slug))
  const fillers = excludeDefault
    .filter(c => !matchedSlugs.has(c.slug))
    .sort((a, b) => b.member_count - a.member_count)

  return [...matched, ...fillers].slice(0, 5)
})

/** 搜索圈子结果 */
const searchResults = computed(() => {
  const kw = circleSearchKeyword.value.trim().toLowerCase()
  if (!kw) return []
  return circles.value.filter(c =>
    c.slug !== 'default' && (
      c.name.toLowerCase().includes(kw) ||
      (c.description || '').toLowerCase().includes(kw)
    )
  )
})

/** 推荐圈子标签 */
function getCircleTag(_circle: { slug: string; name: string }, index: number): string {
  const tags = ['近期发帖最多', '上次发帖', '最近常逛', '热门推荐', '你可能感兴趣']
  return tags[index] || '推荐'
}

/** 圈子头像渐变色（参考 CircleDetail.vue 的 avatarGradient） */
function avatarGradient(id?: number) {
  const palettes = [
    'linear-gradient(135deg, #66abff, #007aff)',
    'linear-gradient(135deg, #34c759, #2e8dff)',
    'linear-gradient(135deg, #ff9500, #007aff)',
    'linear-gradient(135deg, #5856d6, #af52de)',
    'linear-gradient(135deg, #d1d1d6, #8e8e93)',
  ]
  if (id == null) return palettes[4]
  return palettes[id % 5]
}

/** 数量格式化（参考 CircleDetail.vue 的 formatCount） */
function formatCount(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, '') + 'w'
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k'
  return String(n)
}

function openCircleSheet() {
  showCircleSheet.value = true
}

function closeCircleSheet() {
  showCircleSheet.value = false
}

function selectCircle(c: { slug: string; name: string }) {
  category.value = c.slug
  hasSelectedCircle.value = true
}

function selectCircleFromSheet(c: { slug: string; name: string }) {
  selectCircle(c)
  showCircleSheet.value = false
}

// 全局点击外部关闭：话题下拉 / @浮层 / 位置浮层 / 表情面板
const toolbarRef = ref<HTMLElement | null>(null)
function onClickOutside(e: MouseEvent) {
  const target = e.target as Node
  // 如果点击的是工具栏按钮，由 toggleTool 处理开关，不在此关闭
  if (toolbarRef.value && toolbarRef.value.contains(target)) {
    return
  }
  if (topicWrapRef.value && !topicWrapRef.value.contains(target)) {
    showTopicPanel.value = false
  }
  if (mentionWrapRef.value && !mentionWrapRef.value.contains(target)) {
    showMentionPanel.value = false
  }
  if (locationWrapRef.value && !locationWrapRef.value.contains(target)) {
    showLocationPanel.value = false
  }
  if (emojiWrapRef.value && !emojiWrapRef.value.contains(target)) {
    showEmojiPanel.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', onClickOutside)
  // 加载圈子列表
  if (session.userId && !circles.value.length) {
    circleStore.loadCircles()
  }
  // 确保校区数据已加载（编辑模式下 PostDetail 不会预加载 schoolStore）
  if (!schoolStore.schools.length) {
    schoolStore.loadSchools()
  }
  // 页面关闭/刷新时尝试同步保存一次草稿
  window.addEventListener('beforeunload', onBeforeUnload)
})

onUnmounted(() => {
  document.removeEventListener('click', onClickOutside)
  window.removeEventListener('beforeunload', onBeforeUnload)
  // 清理草稿自动保存定时器
  if (draftTimer) {
    clearTimeout(draftTimer)
  }
})

// 标题字数
const MAX_TITLE = 30
const titleCount = computed(() => title.value.length)
const titleIsMax = computed(() => titleCount.value >= MAX_TITLE)

// 正文自适应
const bodyRef = ref<HTMLTextAreaElement | null>(null)
// 输入法 composition 状态：拼音输入中显示真实文本，避免候选词消失
const isComposing = ref(false)
function onCompositionStart() {
  isComposing.value = true
}
function onCompositionEnd() {
  isComposing.value = false
  // composition 结束后触发一次 input 同步 v-model
  onContentInput()
}
function autoResize() {
  nextTick(() => {
    if (!bodyRef.value) return
    bodyRef.value.style.height = 'auto'
    bodyRef.value.style.height = Math.max(200, bodyRef.value.scrollHeight) + 'px'
  })
}
watch(content, autoResize)

/** 正文输入事件：自适应高度 + 检测 # / @ 触发 */
function onContentInput() {
  autoResize()
  // 检测 # 和 @ 触发（延迟一帧确保 v-model 已同步）
  nextTick(() => {
    detectTopicTrigger()
    detectMentionTrigger()
  })
}

/** 高亮渲染：#话题名 和 @昵称 显示蓝色 */
const highlightedContent = computed(() => {
  const text = content.value
  if (!text) return '<span style="color: transparent;">.</span>'
  // HTML 转义
  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  // 高亮 #话题名（#后跟非空白字符，直到空白或行尾）
  const withTopic = escaped.replace(/#([^\s#@]+)/g, '<span class="hl-topic">#$1</span>')
  // 高亮 @昵称（@后跟非空白字符）
  const withMention = withTopic.replace(/@([^\s#@]+)/g, '<span class="hl-mention">@$1</span>')
  // 末尾换行符需要保留（否则高度不一致）
  return withMention.replace(/\n/g, '<br>') + '<br>'
})

/** 同步 textarea 滚动到 highlight overlay */
function syncScroll() {
  const el = bodyRef.value
  const hl = el?.parentElement?.querySelector('.body-highlight') as HTMLElement | null
  if (el && hl) {
    hl.scrollTop = el.scrollTop
    hl.scrollLeft = el.scrollLeft
  }
}

// ============ 光标位置计算 ============
/** 浮层定位坐标 */
const popoverTop = ref(0)
const popoverLeft = ref(0)

/** 计算 textarea 当前光标位置（相对于 .editor-wrap），用于定位浮层。
 *
 * 改进点（修复"点击位置和表情没反应"）：
 * 1. 若 textarea 未聚焦，将光标位置回退到文本末尾，避免 selectionStart 为 0 导致浮层定位错误
 * 2. 浮层顶边 = 光标所在行底部（caretTop + 当前行高），确保浮层在光标下方
 * 3. 浮层左右边界 clamp 到 .editor-wrap 内，避免跑出视口
 */
function updateCaretPosition() {
  const el = bodyRef.value
  if (!el) return
  const editorWrap = el.closest('.editor-wrap') as HTMLElement
  if (!editorWrap) return

  // 创建镜像 div 计算光标位置
  const mirror = document.createElement('div')
  const style = window.getComputedStyle(el)
  const copyProps: string[] = [
    'boxSizing', 'width', 'height', 'overflowX', 'overflowY',
    'borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth',
    'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
    'fontStyle', 'fontVariant', 'fontWeight', 'fontStretch', 'fontSize',
    'fontSizeAdjust', 'lineHeight', 'fontFamily', 'textAlign', 'textTransform',
    'textIndent', 'textDecoration', 'letterSpacing', 'wordSpacing', 'tabSize',
  ]
  copyProps.forEach((p) => {
    mirror.style.setProperty(p, style.getPropertyValue(p))
  })
  mirror.style.position = 'absolute'
  mirror.style.visibility = 'hidden'
  mirror.style.whiteSpace = 'pre-wrap'
  mirror.style.wordWrap = 'break-word'

  // 光标位置：未聚焦时回退到文本末尾，确保浮层出现在内容末尾下方
  const fallbackPos = el.value.length
  const pos = document.activeElement === el ? (el.selectionStart ?? fallbackPos) : fallbackPos
  mirror.textContent = el.value.slice(0, pos)
  const span = document.createElement('span')
  span.textContent = '\u200b'
  mirror.appendChild(span)
  document.body.appendChild(mirror)

  const rect = el.getBoundingClientRect()
  const spanRect = span.getBoundingClientRect()
  const mirrorRect = mirror.getBoundingClientRect()
  document.body.removeChild(mirror)

  // 光标相对于 textarea 的位置
  const caretTop = spanRect.top - mirrorRect.top
  const caretLeft = spanRect.left - mirrorRect.left

  const wrapRect = editorWrap.getBoundingClientRect()
  // 解析行高，用于把浮层顶边对齐到光标所在行的底部
  const lineHeightStr = style.getPropertyValue('lineHeight')
  let lineHeight = 24
  const parsed = parseFloat(lineHeightStr)
  if (!Number.isNaN(parsed) && parsed > 0) lineHeight = parsed

  // 浮层顶边 = textarea 顶部偏移 + 光标顶部 + 行高（让浮层在光标所在行下方）
  let top = rect.top - wrapRect.top + caretTop + lineHeight + 4
  let left = rect.left - wrapRect.left + caretLeft

  // 浮层宽度（与 CSS .popover-panel 一致：300px，宽浮层 360px）
  const panelWidth = 300
  // 限制浮层在 .editor-wrap 内
  const wrapWidth = wrapRect.width
  if (left + panelWidth > wrapWidth) {
    left = Math.max(0, wrapWidth - panelWidth - 8)
  }
  if (left < 0) left = 0

  popoverTop.value = top
  popoverLeft.value = left
}

// ============ 光标位置插入工具 ============
/** 在 textarea 当前光标位置插入文本，并把光标移到插入文本之后 */
function insertAtCursor(text: string) {
  const el = bodyRef.value
  if (!el) {
    content.value += text
    return
  }
  const start = el.selectionStart ?? content.value.length
  const end = el.selectionEnd ?? content.value.length
  content.value = content.value.slice(0, start) + text + content.value.slice(end)
  nextTick(() => {
    const pos = start + text.length
    el.focus()
    el.setSelectionRange(pos, pos)
    autoResize()
  })
}

// 图片上传
const uploading = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
/** 每张上传中图片的进度（图片索引 → 0-100） */
const uploadProgress = ref<Record<number, number>>({})
/** 正在上传的图片数量 */
const uploadingCount = ref(0)

function triggerFileInput() {
  if (imageUrls.value.length >= 9) {
    toast.info('最多 9 张图片')
    return
  }
  fileInputRef.value?.click()
}

async function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files || !input.files.length) return
  uploading.value = true
  uploadingCount.value = 0
  try {
    const files = Array.from(input.files)
    const remaining = 9 - imageUrls.value.length
    const filesToUpload = files.slice(0, remaining)
    if (files.length > remaining) {
      toast.info(`最多还能上传 ${remaining} 张`)
    }
    uploadingCount.value = filesToUpload.length
    for (let i = 0; i < filesToUpload.length; i++) {
      const file = filesToUpload[i]
      const startIdx = imageUrls.value.length
      // 先占位一个 loading URL
      imageUrls.value.push('__uploading__')
      uploadProgress.value[startIdx] = 0
      try {
        const { data } = await uploadImage(file, (percent) => {
          uploadProgress.value[startIdx] = percent
        })
        // 替换占位 URL 为真实 URL
        imageUrls.value[startIdx] = data.data.url
        delete uploadProgress.value[startIdx]
      } catch (err) {
        // 上传失败，移除占位
        imageUrls.value.splice(startIdx, 1)
        delete uploadProgress.value[startIdx]
        throw err
      }
      uploadingCount.value--
    }
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    uploading.value = false
    input.value = '' // 允许重复选择同一文件
  }
}

function removeImage(idx: number) {
  imageUrls.value.splice(idx, 1)
}

// 工具按钮
const activeTools = ref<Set<string>>(new Set())
function toggleTool(tool: string) {
  // 判断当前工具对应的面板是否已打开
  const wasOpen =
    (tool === 'topic' && showTopicPanel.value) ||
    (tool === 'mention' && showMentionPanel.value) ||
    (tool === 'location' && showLocationPanel.value) ||
    (tool === 'emoji' && showEmojiPanel.value)

  // 先关闭所有浮层面板
  showTopicPanel.value = false
  showMentionPanel.value = false
  showLocationPanel.value = false
  showEmojiPanel.value = false

  // 如果已打开，则仅关闭（切换效果）
  if (wasOpen) {
    activeTools.value.delete(tool)
    return
  }

  // 清除其他工具的 active 状态，标记当前工具
  activeTools.value.clear()
  activeTools.value.add(tool)

  // 打开对应面板
  if (tool === 'image') {
    triggerFileInput()
    activeTools.value.delete('image')
  } else if (tool === 'topic') {
    openTopicPanel()
  } else if (tool === 'mention') {
    void openMentionPanel()
  } else if (tool === 'location') {
    openLocationPanel()
  } else if (tool === 'emoji') {
    openEmojiPanel()
  } else if (tool === 'vote') {
    openPollEditor()
    activeTools.value.delete('vote')
  }
}

// ============ 话题选择（输入 # 触发 + 工具栏按钮触发） ============
const topicWrapRef = ref<HTMLElement | null>(null)
const showTopicPanel = ref(false)
const topicKeyword = ref('')
const topicResults = ref<Topic[]>([])
const topicSearching = ref(false)
let topicSearchTimer: ReturnType<typeof setTimeout> | null = null
/** 话题搜索浮层是否由输入 # 触发（决定选择后是否替换光标前的 #xxx） */
let topicTriggeredByInput = false

/** 工具栏按钮：立即弹出话题列表（不插入 #），定位到光标下方 */
function openTopicPanel() {
  // 关闭其他面板
  showMentionPanel.value = false
  showLocationPanel.value = false
  showEmojiPanel.value = false
  // 先 focus textarea 并把光标移到末尾，确保 selectionStart 有效
  if (bodyRef.value) {
    bodyRef.value.focus()
    const end = bodyRef.value.value.length
    bodyRef.value.setSelectionRange(end, end)
  }
  // 计算光标位置，定位浮层（nextTick 确保 focus 生效后再计算）
  nextTick(() => {
    updateCaretPosition()
    // 不插入 #，直接弹出列表
    topicTriggeredByInput = false
    // 触发搜索（空关键词也显示热门话题）
    doTopicSearch('')
    showTopicPanel.value = true
  })
}

/** 输入时检测 # 触发话题搜索 */
function detectTopicTrigger() {
  const el = bodyRef.value
  if (!el) return
  const pos = el.selectionStart
  const before = el.value.slice(0, pos)
  // 找最后一个 #
  const hashIdx = before.lastIndexOf('#')
  if (hashIdx < 0) {
    if (showTopicPanel.value && topicTriggeredByInput) {
      showTopicPanel.value = false
    }
    return
  }
  // # 后的文字（到光标位置）
  const afterHash = before.slice(hashIdx + 1)
  // 如果 # 前面是非空白字符，说明不是话题（如 "a#b"）
  if (hashIdx > 0 && !/\s/.test(before[hashIdx - 1])) {
    if (showTopicPanel.value && topicTriggeredByInput) {
      showTopicPanel.value = false
    }
    return
  }
  // # 后不能有空格或换行，且长度 <= 32
  if (afterHash.includes(' ') || afterHash.includes('\n') || afterHash.length > 32) {
    if (showTopicPanel.value && topicTriggeredByInput) {
      showTopicPanel.value = false
    }
    return
  }
  // 触发话题搜索
  topicTriggeredByInput = true
  topicKeyword.value = afterHash
  showMentionPanel.value = false
  showLocationPanel.value = false
  showEmojiPanel.value = false
  doTopicSearch(afterHash)
  showTopicPanel.value = true
}

/** 执行话题搜索（带 debounce） */
function doTopicSearch(q: string) {
  if (topicSearchTimer) clearTimeout(topicSearchTimer)
  topicKeyword.value = q
  if (!q.trim()) {
    // 空关键词：加载热门话题
    topicSearching.value = true
    topicSearchTimer = setTimeout(async () => {
      try {
        const { data } = await hotTopics(10, {
          showGlobalLoading: false,
          showGlobalError: false,
        })
        topicResults.value = data.data || []
      } catch {
        topicResults.value = []
      } finally {
        topicSearching.value = false
      }
    }, 100)
    return
  }
  topicSearching.value = true
  topicSearchTimer = setTimeout(async () => {
    try {
      const { data } = await searchTopics(q.trim(), {
        showGlobalLoading: false,
        showGlobalError: false,
      })
      topicResults.value = data.data || []
    } catch {
      topicResults.value = []
    } finally {
      topicSearching.value = false
    }
  }, 250)
}

/** 选择话题：在光标处插入 #话题名（蓝色高亮由 overlay 处理） */
function selectTopic(name: string) {
  if (!bodyRef.value) return
  const el = bodyRef.value
  const pos = el.selectionStart
  const before = el.value.slice(0, pos)
  const after = el.value.slice(pos)
  if (topicTriggeredByInput) {
    // 输入 # 触发：替换光标前的 #xxx 为 #话题名
    const hashIdx = before.lastIndexOf('#')
    if (hashIdx >= 0) {
      const newBefore = before.slice(0, hashIdx)
      const insertText = `#${name} `
      content.value = newBefore + insertText + after
      topicName.value = name
      nextTick(() => {
        const newPos = hashIdx + insertText.length
        el.focus()
        el.setSelectionRange(newPos, newPos)
        autoResize()
      })
    } else {
      insertAtCursor(`#${name} `)
      topicName.value = name
    }
  } else {
    // 工具栏触发：直接在光标处插入 #话题名
    const insertText = `#${name} `
    content.value = before + insertText + after
    topicName.value = name
    nextTick(() => {
      const newPos = pos + insertText.length
      el.focus()
      el.setSelectionRange(newPos, newPos)
      autoResize()
    })
  }
  showTopicPanel.value = false
  topicTriggeredByInput = false
}

function removeTopic() {
  topicName.value = null
}

// ============ @好友（输入 @ 触发 + 工具栏按钮触发） ============
const mentionWrapRef = ref<HTMLElement | null>(null)
const showMentionPanel = ref(false)
const mentionKeyword = ref('')
const mentionList = ref<FollowUser[]>([])
const mentionLoading = ref(false)
/** @ 浮层是否由输入 @ 触发（决定选择后是否替换光标前的 @xxx） */
let mentionTriggeredByInput = false

/** 工具栏按钮：立即弹出好友列表（不插入 @），定位到光标下方 */
async function openMentionPanel() {
  showTopicPanel.value = false
  showLocationPanel.value = false
  showEmojiPanel.value = false
  // 先 focus textarea 并把光标移到末尾，确保 selectionStart 有效
  if (bodyRef.value) {
    bodyRef.value.focus()
    const end = bodyRef.value.value.length
    bodyRef.value.setSelectionRange(end, end)
  }
  await nextTick()
  // 计算光标位置，定位浮层
  updateCaretPosition()
  // 不插入 @，直接弹出列表
  mentionTriggeredByInput = false
  mentionKeyword.value = ''
  showMentionPanel.value = true
  await loadMentionList()
}

/** 输入时检测 @ 触发好友列表 */
function detectMentionTrigger() {
  const el = bodyRef.value
  if (!el) return
  if (!session.userId) return
  const pos = el.selectionStart
  const before = el.value.slice(0, pos)
  // 找最后一个 @
  const atIdx = before.lastIndexOf('@')
  if (atIdx < 0) {
    if (showMentionPanel.value && mentionTriggeredByInput) {
      showMentionPanel.value = false
    }
    return
  }
  // @ 后的文字（到光标位置）
  const afterAt = before.slice(atIdx + 1)
  // 如果 @ 前面是非空白字符，说明不是 @ 提及（如 "a@b"）
  if (atIdx > 0 && !/\s/.test(before[atIdx - 1])) {
    if (showMentionPanel.value && mentionTriggeredByInput) {
      showMentionPanel.value = false
    }
    return
  }
  // @ 后不能有空格或换行，且长度 <= 32
  if (afterAt.includes(' ') || afterAt.includes('\n') || afterAt.length > 32) {
    if (showMentionPanel.value && mentionTriggeredByInput) {
      showMentionPanel.value = false
    }
    return
  }
  // 触发好友列表
  mentionTriggeredByInput = true
  mentionKeyword.value = afterAt
  showTopicPanel.value = false
  showLocationPanel.value = false
  showEmojiPanel.value = false
  // 首次触发时加载好友列表
  if (!mentionList.value.length) {
    void loadMentionList()
  }
  showMentionPanel.value = true
}

async function loadMentionList() {
  if (!session.userId) return
  mentionLoading.value = true
  try {
    const { data } = await listFollowing(session.userId, {
      showGlobalLoading: false,
      showGlobalError: false,
    })
    mentionList.value = data.data || []
    // 同步缓存被 @ 用户的详情
    mentionList.value.forEach((u) => {
      mentionUsers.value.set(u.id, u)
    })
  } catch {
    mentionList.value = []
  } finally {
    mentionLoading.value = false
  }
}

const filteredMentions = computed(() => {
  const kw = mentionKeyword.value.trim().toLowerCase()
  if (!kw) return mentionList.value
  return mentionList.value.filter((u) => u.nickname.toLowerCase().includes(kw))
})

function selectMention(user: FollowUser) {
  if (!mentionUserIds.value.includes(user.id)) {
    mentionUserIds.value.push(user.id)
    mentionUsers.value.set(user.id, user)
  }
  if (mentionTriggeredByInput && bodyRef.value) {
    // 输入 @ 触发：替换光标前的 @xxx 为 @昵称
    const el = bodyRef.value
    const pos = el.selectionStart
    const before = el.value.slice(0, pos)
    const after = el.value.slice(pos)
    const atIdx = before.lastIndexOf('@')
    if (atIdx >= 0) {
      const newBefore = before.slice(0, atIdx)
      const insertText = `@${user.nickname} `
      content.value = newBefore + insertText + after
      nextTick(() => {
        const newPos = atIdx + insertText.length
        el.focus()
        el.setSelectionRange(newPos, newPos)
        autoResize()
      })
    } else {
      insertAtCursor(`@${user.nickname} `)
    }
  } else {
    // 工具栏触发：直接在光标处插入 @昵称
    if (bodyRef.value) {
      const el = bodyRef.value
      const pos = el.selectionStart
      const before = el.value.slice(0, pos)
      const after = el.value.slice(pos)
      const insertText = `@${user.nickname} `
      content.value = before + insertText + after
      nextTick(() => {
        const newPos = pos + insertText.length
        el.focus()
        el.setSelectionRange(newPos, newPos)
        autoResize()
      })
    } else {
      content.value += `@${user.nickname} `
    }
  }
  showMentionPanel.value = false
  mentionTriggeredByInput = false
}

function removeMention(userId: number) {
  mentionUserIds.value = mentionUserIds.value.filter((id) => id !== userId)
  mentionUsers.value.delete(userId)
}

// ============ 位置 ============
const locationWrapRef = ref<HTMLElement | null>(null)
const showLocationPanel = ref(false)
const locationInput = ref('')
const presetLocations = ['教学楼', '食堂', '图书馆', '操场', '宿舍', '校门口']

function openLocationPanel() {
  showTopicPanel.value = false
  showMentionPanel.value = false
  showEmojiPanel.value = false
  // 先 focus textarea 并把光标移到末尾，确保 selectionStart 有效
  if (bodyRef.value) {
    bodyRef.value.focus()
    const end = bodyRef.value.value.length
    bodyRef.value.setSelectionRange(end, end)
  }
  nextTick(() => {
    updateCaretPosition()
    showLocationPanel.value = true
    locationInput.value = location.value ?? ''
  })
}

function selectLocation(loc: string) {
  if (loc.length > 50) {
    toast.info('位置最多 50 字')
    return
  }
  location.value = loc
  showLocationPanel.value = false
}

function confirmCustomLocation() {
  const v = locationInput.value.trim()
  if (!v) return
  selectLocation(v)
}

function removeLocation() {
  location.value = null
}

// ============ 表情面板（微信风格方框 + 收藏 + 上传） ============
const emojiWrapRef = ref<HTMLElement | null>(null)
const showEmojiPanel = ref(false)
const emojiActiveTab = ref<'recent' | 'faces' | 'gestures' | 'animals' | 'food' | 'activities' | 'symbols' | 'fav'>('faces')
/** 收藏表情：可以是 Unicode emoji 字符，也可以是图片 URL（自定义上传） */
interface FavEmoji {
  type: 'emoji' | 'image'
  value: string
  id: string
}
const favEmojis = ref<FavEmoji[]>(loadFavEmojis())
const emojiFileInput = ref<HTMLInputElement | null>(null)

const EMOJI_CATEGORIES: Record<Exclude<typeof emojiActiveTab.value, 'recent' | 'fav'>, string[]> = {
  faces: ['😀', '😃', '😄', '😁', '😆', '😅', '😂', '🤣', '😊', '😇', '🙂', '🙃', '😉', '😌', '😍', '🥰', '😘', '😋', '😛', '😝', '🤪', '🤓', '😎', '🥳', '😏', '😒', '😞', '😔', '😕', '🙁', '😣', '😖', '😫', '😩', '🥺', '😢', '😭', '😤', '😠', '😡', '🤬', '🤯', '😳', '🥵', '🥶', '😱', '😨', '😰', '😥', '😓', '🤗', '🤔', '🤭', '🤫', '😶', '😐', '😑', '😬', '🙄', '😯', '😦', '😮', '🥱', '😴', '🤤', '🤐', '🥴', '🤢', '🤮', '🤧', '😷', '🤒', '🤕'],
  gestures: ['👍', '👎', '👊', '✊', '🤛', '🤜', '👏', '🙌', '👐', '🤲', '🙏', '🤝', '💪', '👋', '🤚', '🖐', '✋', '🖖', '👌', '🤌', '🤏', '✌️', '🤞', '🤟', '🤘', '👈', '👉', '👆', '👇', '☝️', '✍️'],
  animals: ['🐶', '🐱', '🐭', '🐹', '🐰', '🦊', '🐻', '🐼', '🐨', '🐯', '🦁', '🐮', '🐷', '🐸', '🐵', '🐔', '🐧', '🐦', '🐤', '🦆', '🦅', '🦉', '🦇', '🐺', '🐗', '🐴', '🦄', '🐝', '🐛', '🦋', '🐌', '🐞', '🐜', '🐢', '🐍', '🦎', '🦖', '🦕', '🐙', '🦑', '🦐', '🦀', '🐠', '🐟', '🐬', '🐳', '🐋', '🦈'],
  food: ['🍎', '🍐', '🍊', '🍋', '🍌', '🍉', '🍇', '🍓', '🫐', '🍈', '🍒', '🍑', '🥭', '🍍', '🥥', '🥝', '🍅', '🍆', '🥑', '🥦', '🥬', '🥒', '🌶', '🌽', '🥕', '🥔', '🍠', '🥐', '🍞', '🥖', '🧀', '🥚', '🍳', '🥞', '🥓', '🥩', '🍗', '🍖', '🌭', '🍔', '🍟', '🍕', '🥪', '🥙', '🌮', '🌯', '🥗', '🥘', '🍝', '🍜', '🍲', '🍛', '🍣', '🍱', '🥟', '🍤', '🍙', '🍚', '🍘', '🍥', '🥠', '🍢', '🍡', '🍧', '🍨', '🍦', '🥧', '🧁', '🍰', '🎂', '🍮', '🍭', '🍬', '🍫', '🍿', '🍩', '🍪'],
  activities: ['⚽', '🏀', '🏈', '⚾', '🎾', '🏐', '🏉', '🎱', '🏓', '🏸', '🏒', '🏑', '🥍', '🏏', '⛳', '🪁', '🏹', '🎣', '🥊', '🥋', '🎽', '🛹', '🛷', '⛸', '🥌', '🎿', '⛷', '🏂', '🏋️', '🤼', '🤸', '🤺', '🤾', '🏌️', '🏇', '🧘', '🏄', '🏊', '🚣', '🧗', '🚵', '🚴', '🏆', '🥇', '🥈', '🥉', '🏅', '🎖', '🎟', '🎫', '🎪', '🤹', '🎭', '🎨', '🎬', '🎤', '🎧', '🎼', '🎹', '🥁', '🎷', '🎺', '🎸', '🪕', '🎻', '🎲', '♟', '🎯', '🎳', '🎮', '🎰', '🧩'],
  symbols: ['❤️', '🧡', '💛', '💚', '💙', '💜', '🖤', '🤍', '🤎', '💔', '❣️', '💕', '💞', '💓', '💗', '💖', '💘', '💝', '💟', '☮️', '✝️', '☪️', '🕉', '☸️', '✡️', '🔯', '🕎', '☯️', '☦️', '🛐', '⛎', '♈', '♉', '♊', '♋', '♌', '♍', '♎', '♏', '♐', '♑', '♒', '♓', '🆔', '⚛️', '🉑', '☢️', '☣️', '📴', '📳', '🈶', '🈚', '🈸', '🈺', '🈷️', '✴️', '🆚', '💮', '🉐', '㊙️', '㊗️', '🈴', '🈵', '🈹', '🈲', '🅰️', '🅱️', '🆎', '🆑', '🅾️', '🆘', '❌', '⭕', '🛑', '⛔', '📛', '🚫', '💯', '💢', '♨️', '🚷', '🚯', '🚳', '🚱', '🔞', '📵', '🚭', '❗', '❕', '❓', '❔', '‼️', '⁉️', '🔅', '🔆', '〽️', '⚠️', '🚸', '🔱', '⚜️', '🔰', '♻️', '✅', '🈯', '💹', '❇️', '✳️', '❎', '🌐', '💠', 'Ⓜ️', '🌀', '💤'],
}

const RECENT_EMOJI_KEY = 'post-editor-recent-emojis'
const FAV_EMOJI_KEY = 'post-editor-fav-emojis'
const recentEmojis = ref<string[]>(loadRecentEmojis())

function loadRecentEmojis(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_EMOJI_KEY)
    if (!raw) return []
    const arr = JSON.parse(raw)
    return Array.isArray(arr) ? arr.slice(0, 24) : []
  } catch {
    return []
  }
}

function loadFavEmojis(): FavEmoji[] {
  try {
    const raw = localStorage.getItem(FAV_EMOJI_KEY)
    if (!raw) return []
    const arr = JSON.parse(raw)
    return Array.isArray(arr) ? arr : []
  } catch {
    return []
  }
}

function saveFavEmojis() {
  try {
    localStorage.setItem(FAV_EMOJI_KEY, JSON.stringify(favEmojis.value))
  } catch {
    /* ignore */
  }
}

function saveRecentEmoji(emoji: string) {
  const next = [emoji, ...recentEmojis.value.filter((e) => e !== emoji)].slice(0, 24)
  recentEmojis.value = next
  try {
    localStorage.setItem(RECENT_EMOJI_KEY, JSON.stringify(next))
  } catch {
    /* ignore */
  }
}

function openEmojiPanel() {
  showTopicPanel.value = false
  showMentionPanel.value = false
  showLocationPanel.value = false
  // 表情面板锚定到工具栏按钮下方（而不是光标下方），更符合微信/抖音交互习惯
  // 先 focus textarea 保持可输入
  if (bodyRef.value) {
    bodyRef.value.focus()
  }
  nextTick(() => {
    // 计算工具栏按钮的位置：浮层顶边 = 工具栏顶部 - editor-wrap 顶部 - 浮层高度 - 8px
    const toolbar = toolbarRef.value
    const editorWrap = toolbar?.closest('.editor-wrap') as HTMLElement | null
    if (toolbar && editorWrap) {
      const tbRect = toolbar.getBoundingClientRect()
      const wrapRect = editorWrap.getBoundingClientRect()
      // 浮层高度约 380px，定位到工具栏上方
      const panelHeight = 380
      popoverTop.value = Math.max(8, tbRect.top - wrapRect.top - panelHeight - 8)
      // 浮层左对齐到表情按钮
      const btn = toolbar.querySelector('[data-tool="emoji"]') as HTMLElement | null
      if (btn) {
        const btnRect = btn.getBoundingClientRect()
        popoverLeft.value = Math.max(0, btnRect.left - wrapRect.left)
      } else {
        popoverLeft.value = 0
      }
    }
    showEmojiPanel.value = true
  })
}

const currentEmojiList = computed<(string)[]>(() => {
  if (emojiActiveTab.value === 'recent') return recentEmojis.value
  if (emojiActiveTab.value === 'fav') return [] // 收藏 tab 单独渲染
  return EMOJI_CATEGORIES[emojiActiveTab.value]
})

function pickEmoji(emoji: string) {
  insertAtCursor(emoji)
  saveRecentEmoji(emoji)
}

/** 收藏 / 取消收藏 Unicode emoji（长按或点击收藏按钮） */
function toggleFavEmoji(emoji: string) {
  const idx = favEmojis.value.findIndex((f) => f.type === 'emoji' && f.value === emoji)
  if (idx >= 0) {
    favEmojis.value.splice(idx, 1)
  } else {
    favEmojis.value.push({ type: 'emoji', value: emoji, id: `e_${Date.now()}_${Math.random().toString(36).slice(2, 8)}` })
  }
  saveFavEmojis()
}

function isFavEmoji(emoji: string): boolean {
  return favEmojis.value.some((f) => f.type === 'emoji' && f.value === emoji)
}

/** 点击收藏的表情 */
function pickFavEmoji(item: FavEmoji) {
  if (item.type === 'emoji') {
    pickEmoji(item.value)
  } else {
    // 图片表情：插入 markdown 图片语法
    insertAtCursor(`![表情](${item.value})`)
  }
}

/** 删除收藏表情 */
function removeFavEmoji(id: string) {
  const idx = favEmojis.value.findIndex((f) => f.id === id)
  if (idx >= 0) {
    favEmojis.value.splice(idx, 1)
    saveFavEmojis()
  }
}

/** 上传图片表情 */
async function onUploadEmoji(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  if (!file.type.startsWith('image/')) {
    toast.error('只能上传图片文件')
    return
  }
  if (file.size > 1024 * 1024) {
    toast.error('表情图片不能超过 1MB')
    return
  }
  try {
    const { data } = await uploadImage(file)
    const url = data.data.url
    favEmojis.value.push({
      type: 'image',
      value: url,
      id: `img_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    })
    saveFavEmojis()
    toast.success('表情已添加到收藏')
  } catch (err) {
    toast.error((err as Error).message || '上传失败')
  } finally {
    target.value = ''
  }
}

function triggerUploadEmoji() {
  emojiFileInput.value?.click()
}

// ============ 投票编辑器 ============
const showPollEditor = ref(false)
const pollTitle = ref('')
const pollOptions = ref<string[]>(['', ''])
const pollMultiVote = ref(false)
const pollDeadline = ref<string>('')

function openPollEditor() {
  // 如果已有投票数据，回填
  if (pollData.value) {
    pollTitle.value = pollData.value.title
    pollOptions.value = [...pollData.value.options]
    pollMultiVote.value = pollData.value.multi_vote
    pollDeadline.value = pollData.value.deadline ? toLocalDatetime(pollData.value.deadline) : ''
  } else {
    pollTitle.value = ''
    pollOptions.value = ['', '']
    pollMultiVote.value = false
    pollDeadline.value = ''
  }
  showPollEditor.value = true
}

function toLocalDatetime(iso: string): string {
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return ''
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
  } catch {
    return ''
  }
}

function addPollOption() {
  if (pollOptions.value.length >= 6) {
    toast.info('最多 6 个选项')
    return
  }
  pollOptions.value.push('')
}

function removePollOption(idx: number) {
  if (pollOptions.value.length <= 2) {
    toast.info('至少 2 个选项')
    return
  }
  pollOptions.value.splice(idx, 1)
}

function confirmPoll() {
  const t = pollTitle.value.trim()
  if (!t) {
    toast.info('请填写投票标题')
    return
  }
  if (t.length > 100) {
    toast.info('投票标题最多 100 字')
    return
  }
  const opts = pollOptions.value.map((o) => o.trim()).filter((o) => o.length > 0)
  if (opts.length < 2) {
    toast.info('至少需要 2 个有效选项')
    return
  }
  if (opts.some((o) => o.length > 100)) {
    toast.info('每个选项最多 100 字')
    return
  }
  pollData.value = {
    title: t,
    multi_vote: pollMultiVote.value,
    deadline: pollDeadline.value ? new Date(pollDeadline.value).toISOString() : null,
    options: opts,
  }
  showPollEditor.value = false
}

function removePoll() {
  pollData.value = null
}

// ============ 草稿自动保存 ============
const hasUnsavedContent = computed(() => {
  return !!(content.value.trim() || title.value.trim() || imageUrls.value.length || topicName.value || location.value || pollData.value)
})

let draftTimer: ReturnType<typeof setTimeout> | null = null
const isSubmitting = ref(false)
/** 草稿是否正在保存中（避免 beforeunload 与定时器重复保存） */
const isSavingDraft = ref(false)
/** 上一次保存的草稿 id（首次创建后保留，后续走 update） */
const draftPostId = ref<number | null>(props.postId ?? null)

watch(
  [title, content, category, imageUrls, topicName, location, pollData],
  () => {
    if (isSubmitting.value || isSavingDraft.value) return
    if (!hasUnsavedContent.value) return
    if (draftTimer) clearTimeout(draftTimer)
    draftTimer = setTimeout(() => {
      void saveDraft(true)
    }, 2000)
  },
  { deep: true },
)

async function saveDraft(silent = false) {
  if (!session.userId) return
  if (isSubmitting.value || isSavingDraft.value) return
  if (!hasUnsavedContent.value) return
  isSavingDraft.value = true
  try {
    const payload = {
      content: content.value,
      title: title.value.trim() || null,
      category: category.value,
      school_id: schoolId.value!,
      is_anonymous: isAnonymous.value,
      is_original: isOriginal.value,
      has_ai_content: hasAiContent.value,
      image_urls: imageUrls.value,
      is_draft: true,
      topic_name: topicName.value,
      location: location.value,
      mention_user_ids: mentionUserIds.value,
      poll: pollData.value,
    }
    if (draftPostId.value) {
      await updatePost(draftPostId.value, payload)
    } else {
      const { data } = await createPost(payload)
      // 保存新创建的草稿 id，后续走 update
      const newId = (data as any)?.data?.id
      if (newId) draftPostId.value = newId
    }
    // 静默保存不弹 toast，仅在控制台输出日志
    // eslint-disable-next-line no-console
    console.log('[PostEditor] draft saved', { silent })
  } catch (err) {
    if (!silent) toast.error((err as Error).message)
    // eslint-disable-next-line no-console
    console.warn('[PostEditor] draft save failed', err)
  } finally {
    isSavingDraft.value = false
  }
}

function onBeforeUnload(e: BeforeUnloadEvent) {
  if (isSubmitting.value) return
  if (!hasUnsavedContent.value) return
  // 浏览器规范： returnValue 非空时会弹原生提示
  e.preventDefault()
  e.returnValue = ''
  // 尝试用 fetch keepalive 同步保存一次（不阻塞卸载）
  try {
    const payload = {
      content: content.value,
      title: title.value.trim() || null,
      category: category.value,
      school_id: schoolId.value,
      is_anonymous: isAnonymous.value,
      is_original: isOriginal.value,
      has_ai_content: hasAiContent.value,
      image_urls: imageUrls.value,
      is_draft: true,
      topic_name: topicName.value,
      location: location.value,
      mention_user_ids: mentionUserIds.value,
      poll: pollData.value,
    }
    const url = draftPostId.value ? `/api/posts/${draftPostId.value}` : '/api/posts'
    const method = draftPostId.value ? 'PATCH' : 'POST'
    fetch(url, {
      method,
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      keepalive: true,
    }).catch(() => {})
  } catch {
    /* ignore */
  }
}

// 提交
const submitting = isSubmitting
const isEditMode = () => props.postId != null
const canSubmit = computed(
  () => !!content.value.trim() && !!schoolId.value && !submitting.value,
)

function buildPayload(asDraft: boolean) {
  return {
    content: content.value,
    title: title.value.trim() || null,
    category: category.value,
    school_id: schoolId.value!,
    is_anonymous: isAnonymous.value,
    is_original: isOriginal.value,
    has_ai_content: hasAiContent.value,
    image_urls: imageUrls.value,
    is_draft: asDraft,
    topic_name: topicName.value,
    location: location.value,
    mention_user_ids: mentionUserIds.value,
    poll: pollData.value,
  }
}

function resetForm() {
  title.value = ''
  content.value = ''
  imageUrls.value = []
  topicName.value = null
  location.value = null
  mentionUserIds.value = []
  mentionUsers.value = new Map()
  pollData.value = null
}

async function publish(asDraft = false) {
  if (!session.userId) {
    toast.error('请先登录')
    return
  }
  if (!content.value.trim()) {
    toast.error('内容不能为空')
    return
  }
  if (!schoolId.value) {
    toast.error('请选择校区')
    return
  }
  // 非草稿发布时，如果未选择圈子，弹出提示
  if (!asDraft && !hasSelectedCircle.value) {
    showNoCirclePrompt.value = true
    return
  }
  await doPublish(asDraft)
}

async function continuePublishWithoutCircle() {
  showNoCirclePrompt.value = false
  await doPublish(false)
}

async function doPublish(asDraft: boolean) {
  submitting.value = true
  try {
    const payload = buildPayload(asDraft) as ReturnType<typeof buildPayload> & { is_public?: boolean }
    if (!isEditMode() && !asDraft) payload.is_public = true
    if (isEditMode()) {
      await updatePost(props.postId!, payload)
      toast.success('已更新')
      emit('updated')
    } else {
      await createPost(payload)
      toast.success(asDraft ? '草稿已保存' : '发布成功，内容审核中')
      if (!asDraft) {
        resetForm()
        // 已发布的草稿 id 清理
        draftPostId.value = null
        emit('published')
      }
    }
    postStore.setPage(1)
    await postStore.loadPosts()
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    submitting.value = false
  }
}

// ============ 模板辅助函数 ============
/** 头像背景兜底色（实际头像图通过 v-if 在模板中处理） */
function mentionAvatarStyle(_uid: number): Record<string, string> {
  return { background: 'var(--brand-500)' }
}
/** 截止时间格式化（用于投票预览卡片） */
function formatDeadline(iso: string): string {
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return ''
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  } catch {
    return ''
  }
}

// 暴露给父组件
defineExpose({
  publish,
  canSubmit,
  submitting,
  hasUnsavedContent,
  saveDraft: () => saveDraft(false),
})
</script>

<template>
  <div class="editor-wrap">
    <!-- 编辑器卡片 -->
    <section class="editor-card">
      <!-- 标题行 -->
      <div class="title-row">
        <input
          v-model="title"
          class="title-input"
          type="text"
          :maxlength="MAX_TITLE"
          placeholder="标题：一句话说清楚（5-30字）"
          aria-label="帖子标题"
        />
        <span class="title-count" :class="{ 'is-max': titleIsMax }">{{ titleCount }}/{{ MAX_TITLE }}</span>
      </div>

      <!-- 正文（带 highlight overlay：#话题 和 @用户 显示蓝色） -->
      <div class="body-wrap">
        <div class="body-highlight" aria-hidden="true" v-html="highlightedContent" />
        <textarea
          ref="bodyRef"
          v-model="content"
          class="body-input body-input-overlay"
          :class="{ 'is-composing': isComposing }"
          placeholder="分享你的校园生活..."
          aria-label="帖子正文"
          maxlength="5000"
          @input="onContentInput"
          @compositionstart="onCompositionStart"
          @compositionend="onCompositionEnd"
          @scroll="syncScroll"
        />
        <div class="body-counter" :class="{ 'is-max': content.length >= 5000 }">
          {{ content.length }} / 5000
        </div>
      </div>

      <!-- 工具条 -->
      <div ref="toolbarRef" class="toolbar" role="toolbar" aria-label="编辑工具">
        <button
          v-for="tool in [
            { key: 'image', label: '图片', icon: 'image' },
            { key: 'topic', label: '话题', icon: 'tag' },
            { key: 'mention', label: '@好友', icon: 'at' },
            { key: 'location', label: '位置', icon: 'map-pin' },
            { key: 'emoji', label: '表情', icon: 'smile' },
            { key: 'vote', label: '投票', icon: 'circle-question' },
          ]"
          :key="tool.key"
          class="tool-btn"
          :class="{ 'is-active': activeTools.has(tool.key) }"
          :data-tool="tool.key"
          type="button"
          @click="toggleTool(tool.key)"
        >
          <Icon :name="tool.icon" :size="22" />
          <span class="tool-label">{{ tool.label }}</span>
        </button>
      </div>
    </section>

    <!-- 话题搜索浮层（定位到光标下方） -->
    <div
      v-if="showTopicPanel"
      ref="topicWrapRef"
      class="floating-panel topic-panel popover-panel"
      :style="{ top: popoverTop + 'px', left: popoverLeft + 'px' }"
    >
      <div class="panel-head">
        <span class="panel-title">{{ topicKeyword.trim() ? '搜索话题' : '热门话题' }}</span>
        <button class="panel-close" type="button" @click="showTopicPanel = false">
          <Icon name="x" :size="16" />
        </button>
      </div>
      <div class="topic-input-row">
        <Icon name="search" :size="14" :color="'var(--text-500)'" />
        <input
          v-model="topicKeyword"
          class="panel-input"
          type="text"
          placeholder="搜索话题，找不到可创建新话题"
          @input="doTopicSearch(($event.target as HTMLInputElement).value)"
        />
      </div>
      <div v-if="topicSearching" class="panel-loading">搜索中…</div>
      <div v-else-if="topicResults.length" class="topic-results">
        <div
          v-for="t in topicResults"
          :key="t.id"
          class="topic-item"
          @click="selectTopic(t.name)"
        >
          <span class="topic-name">#{{ t.name }}</span>
          <span class="topic-hot">
            <Icon name="flame" :size="12" :color="'var(--state-warning-text, #ff9500)'" />
            {{ t.post_count }} 帖
          </span>
        </div>
      </div>
      <div v-else-if="topicKeyword.trim()" class="topic-item" @click="selectTopic(topicKeyword.trim())">
        <span class="topic-name">创建新话题 #{{ topicKeyword.trim() }}</span>
      </div>
      <div v-else class="panel-empty">暂无热门话题，输入关键词搜索</div>
    </div>

    <!-- @好友浮层（定位到光标下方） -->
    <div
      v-if="showMentionPanel"
      ref="mentionWrapRef"
      class="floating-panel mention-panel popover-panel"
      :style="{ top: popoverTop + 'px', left: popoverLeft + 'px' }"
    >
      <div class="panel-head">
        <span class="panel-title">@ 好友</span>
        <button class="panel-close" type="button" @click="showMentionPanel = false">
          <Icon name="x" :size="16" />
        </button>
      </div>
      <div class="topic-input-row">
        <Icon name="search" :size="14" :color="'var(--text-500)'" />
        <input
          v-model="mentionKeyword"
          class="panel-input"
          type="text"
          placeholder="搜索昵称"
        />
      </div>
      <div v-if="mentionLoading" class="panel-loading">加载中…</div>
      <div v-else-if="filteredMentions.length" class="mention-list">
        <div
          v-for="u in filteredMentions"
          :key="u.id"
          class="mention-item"
          @click="selectMention(u)"
        >
          <div
            class="mention-avatar"
            :style="
              u.avatar_url
                ? { backgroundImage: `url(${u.avatar_url})` }
                : { background: 'var(--brand-500)' }
            "
          >
            <span v-if="!u.avatar_url">{{ u.nickname.charAt(0).toUpperCase() }}</span>
          </div>
          <span class="mention-name">{{ u.nickname }}</span>
          <Icon v-if="mentionUserIds.includes(u.id)" name="check" :size="16" :color="'var(--brand-500)'" />
        </div>
      </div>
      <div v-else class="panel-empty">暂无关注的好友</div>
    </div>

    <!-- 位置浮层（定位到光标下方） -->
    <div
      v-if="showLocationPanel"
      ref="locationWrapRef"
      class="floating-panel location-panel popover-panel"
      :style="{ top: popoverTop + 'px', left: popoverLeft + 'px' }"
    >
      <div class="panel-head">
        <span class="panel-title">选择位置</span>
        <button class="panel-close" type="button" @click="showLocationPanel = false">
          <Icon name="x" :size="16" />
        </button>
      </div>
      <div class="location-presets">
        <button
          v-for="loc in presetLocations"
          :key="loc"
          class="location-chip"
          type="button"
          @click="selectLocation(loc)"
        >
          {{ loc }}
        </button>
      </div>
      <input
        v-model="locationInput"
        class="panel-input"
        type="text"
        :maxlength="50"
        placeholder="自定义位置（最多 50 字）"
        @keyup.enter="confirmCustomLocation"
      />
      <button class="btn btn-primary btn-block" type="button" @click="confirmCustomLocation">确定</button>
    </div>

    <!-- 表情面板（微信风格方框 + 收藏 + 上传，定位到光标下方） -->
    <div
      v-if="showEmojiPanel"
      ref="emojiWrapRef"
      class="floating-panel emoji-panel popover-panel popover-panel--wide"
      :style="{ top: popoverTop + 'px', left: popoverLeft + 'px' }"
    >
      <div class="emoji-tabs">
        <button
          v-for="tab in [
            { key: 'recent', label: '最近' },
            { key: 'fav', label: '收藏' },
            { key: 'faces', label: '表情' },
            { key: 'gestures', label: '手势' },
            { key: 'animals', label: '动物' },
            { key: 'food', label: '食物' },
            { key: 'activities', label: '活动' },
            { key: 'symbols', label: '符号' },
          ]"
          :key="tab.key"
          class="emoji-tab"
          :class="{ 'is-active': emojiActiveTab === tab.key }"
          type="button"
          @click="emojiActiveTab = tab.key as typeof emojiActiveTab"
        >
          {{ tab.label }}
        </button>
      </div>
      <!-- 收藏 tab：支持图片表情 + 上传 -->
      <template v-if="emojiActiveTab === 'fav'">
        <div class="emoji-fav-header">
          <span class="fav-tip">长按表情可收藏，点击使用</span>
          <button class="fav-upload-btn" type="button" @click="triggerUploadEmoji">
            <Icon name="plus" :size="14" />
            添加表情
          </button>
          <input
            ref="emojiFileInput"
            type="file"
            accept="image/*"
            style="display: none"
            @change="onUploadEmoji"
          />
        </div>
        <div v-if="favEmojis.length" class="emoji-grid fav-grid">
          <div
            v-for="item in favEmojis"
            :key="item.id"
            class="emoji-cell fav-cell"
            :class="{ 'is-image': item.type === 'image' }"
          >
            <button
              v-if="item.type === 'image'"
              class="emoji-img-btn"
              type="button"
              @click="pickFavEmoji(item)"
            >
              <img :src="item.value" alt="表情" />
            </button>
            <button
              v-else
              class="emoji-char-btn"
              type="button"
              @click="pickFavEmoji(item)"
            >{{ item.value }}</button>
            <button
              class="fav-remove"
              type="button"
              aria-label="删除"
              @click.stop="removeFavEmoji(item.id)"
            >
              <Icon name="x" :size="10" />
            </button>
          </div>
        </div>
        <div v-else class="panel-empty">
          <Icon name="star" :size="32" :color="'var(--text-300)'" />
          <p>还没有收藏的表情</p>
          <p class="panel-empty-sub">点击表情分类里的表情即可使用，长按可收藏</p>
        </div>
      </template>
      <!-- 其他分类 tab -->
      <template v-else>
        <div v-if="currentEmojiList.length" class="emoji-grid">
          <button
            v-for="(emoji, idx) in currentEmojiList"
            :key="emoji + idx"
            class="emoji-cell"
            :class="{ 'is-fav': isFavEmoji(emoji) }"
            type="button"
            @click="pickEmoji(emoji)"
            @contextmenu.prevent="toggleFavEmoji(emoji)"
          >{{ emoji }}</button>
        </div>
        <div v-else class="panel-empty">还没有最近使用的表情</div>
      </template>
    </div>

    <!-- 投票编辑器 -->
    <NativeDialog v-model="showPollEditor" title="创建投票" width="480px">
      <div class="poll-form">
        <div class="form-row">
          <label class="form-label">标题（必填）</label>
          <input
            v-model="pollTitle"
            class="form-input"
            type="text"
            :maxlength="100"
            placeholder="投票标题"
          />
        </div>
        <div class="form-row">
          <label class="form-label">选项（2-6 个）</label>
          <div v-for="(opt, idx) in pollOptions" :key="idx" class="poll-option-row">
            <input
              v-model="pollOptions[idx]"
              class="form-input"
              type="text"
              :maxlength="100"
              :placeholder="`选项 ${idx + 1}`"
            />
            <button
              v-if="pollOptions.length > 2"
              class="poll-option-del"
              type="button"
              @click="removePollOption(idx)"
            >
              <Icon name="x" :size="14" />
            </button>
          </div>
          <button
            v-if="pollOptions.length < 6"
            class="btn btn-outline btn-sm"
            type="button"
            @click="addPollOption"
          >
            <Icon name="plus" :size="14" />
            添加选项
          </button>
        </div>
        <div class="form-row form-row--inline">
          <label class="form-label">多选</label>
          <NativeSwitch v-model="pollMultiVote" />
        </div>
        <div class="form-row">
          <label class="form-label">截止时间（可选）</label>
          <input
            v-model="pollDeadline"
            class="form-input"
            type="datetime-local"
          />
        </div>
      </div>
      <template #footer>
        <button class="btn btn-outline" type="button" @click="showPollEditor = false">取消</button>
        <button class="btn btn-primary" type="button" @click="confirmPoll">确定</button>
      </template>
    </NativeDialog>

    <!-- 已选话题 / 位置 / @好友 / 投票 预览 -->
    <section v-if="topicName || location || mentionUserIds.length || pollData" class="extras-card">
      <div v-if="topicName" class="extra-chip extra-chip--topic">
        <Icon name="tag" :size="13" />
        <span>#{{ topicName }}</span>
        <button class="extra-del" type="button" @click="removeTopic">
          <Icon name="x" :size="12" />
        </button>
      </div>
      <div v-if="location" class="extra-chip extra-chip--location">
        <Icon name="map-pin" :size="13" />
        <span>{{ location }}</span>
        <button class="extra-del" type="button" @click="removeLocation">
          <Icon name="x" :size="12" />
        </button>
      </div>
      <div v-if="mentionUserIds.length" class="extra-mentions">
        <div
          v-for="uid in mentionUserIds"
          :key="uid"
          class="mention-avatar mention-avatar--sm"
          :style="mentionAvatarStyle(uid)"
          :title="mentionUsers.get(uid)?.nickname || ''"
        >
          <span v-if="!mentionUsers.get(uid)?.avatar_url">{{ (mentionUsers.get(uid)?.nickname || 'U').charAt(0).toUpperCase() }}</span>
          <button class="extra-del extra-del--avatar" type="button" @click="removeMention(uid)">
            <Icon name="x" :size="10" />
          </button>
        </div>
      </div>
      <div v-if="pollData" class="extra-poll">
        <div class="extra-poll-head">
          <Icon name="circle-question" :size="14" />
          <span class="extra-poll-title">{{ pollData.title }}</span>
          <button class="extra-del" type="button" @click="removePoll">
            <Icon name="x" :size="12" />
          </button>
        </div>
        <div v-for="(opt, idx) in pollData.options" :key="idx" class="extra-poll-opt">
          {{ idx + 1 }}. {{ opt }}
        </div>
        <div class="extra-poll-meta">
          {{ pollData.multi_vote ? '多选' : '单选' }}
          <span v-if="pollData.deadline"> · 截止 {{ formatDeadline(pollData.deadline) }}</span>
        </div>
      </div>
    </section>

    <!-- 图片卡片 -->
    <section class="images-card">
      <div class="images-head">
        <span class="images-title">图片</span>
        <span class="images-hint">已选 {{ imageUrls.length }} 张 · 最多 9 张</span>
      </div>
      <div class="image-grid">
        <div v-for="(url, i) in imageUrls" :key="'img-' + i" class="img-cell">
          <!-- 上传中：显示进度条 -->
          <template v-if="url === '__uploading__'">
            <div class="upload-progress-overlay">
              <Icon name="refresh" :size="28" class="spin" />
              <div class="progress-bar-wrap">
                <div class="progress-bar-fill" :style="{ width: (uploadProgress[i] || 0) + '%' }" />
              </div>
              <span class="progress-text">{{ uploadProgress[i] || 0 }}%</span>
            </div>
          </template>
          <!-- 已上传 -->
          <template v-else>
            <img :src="url" :alt="`已选图片${i + 1}`" loading="lazy" />
            <button class="del-badge" type="button" aria-label="删除图片" @click="removeImage(i)">
              <Icon name="x" :size="14" color="#fff" />
            </button>
          </template>
        </div>
        <button
          v-if="imageUrls.length < 9"
          class="add-cell"
          type="button"
          :disabled="uploading"
          aria-label="添加图片"
          @click="triggerFileInput"
        >
          <Icon v-if="!uploading" name="plus" :size="28" />
          <Icon v-else name="refresh" :size="22" />
        </button>
      </div>
      <input
        ref="fileInputRef"
        type="file"
        accept="image/jpeg,image/png,image/gif,image/webp"
        multiple
        hidden
        @change="onFileChange"
      />
    </section>

    <!-- 校区选择行 -->
    <section class="school-select-card">
      <div class="school-select-row">
        <span class="school-select-label">
          <Icon name="map-pin" :size="16" :color="'var(--brand-500)'" />
          <span>校区</span>
        </span>
        <div class="school-chips">
          <button
            v-for="s in schoolStore.schools"
            :key="s.id"
            type="button"
            class="school-chip"
            :class="{ 'is-active': schoolId === s.id }"
            @click="schoolId = s.id"
          >{{ s.name }}</button>
          <span v-if="!schoolStore.schools.length" class="school-empty">
            {{ schoolStore.loaded ? '校区加载失败，请刷新重试' : '校区加载中…' }}
          </span>
        </div>
      </div>
    </section>

    <!-- 圈子选择行 -->
    <section class="circle-select-card">
      <button class="circle-select-btn" type="button" @click="openCircleSheet">
        <Icon name="map-pin" :size="18" :color="'var(--brand-500)'" />
        <span class="circle-select-text">
          {{ hasSelectedCircle ? currentCircleName : '选择圈子' }}
        </span>
        <span v-if="!hasSelectedCircle" class="circle-select-hint">选圈子让更多人看到</span>
        <Icon name="chevron-right" :size="16" :color="'var(--text-400)'" />
      </button>
    </section>

    <!-- 选项卡片 -->
    <section class="options-card">
      <div class="option-row">
        <span class="option-ic">
          <Icon name="user" :size="20" color="#fff" />
        </span>
        <div class="option-text">
          <span class="option-label">匿名发布</span>
          <span class="option-desc">不展示你的昵称与头像</span>
        </div>
        <NativeSwitch v-model="isAnonymous" />
      </div>
      <div class="option-row">
        <span class="option-ic">
          <Icon name="pen-line" :size="20" color="#fff" />
        </span>
        <div class="option-text">
          <span class="option-label">标记原创</span>
          <span class="option-desc">声明本帖为原创内容</span>
        </div>
        <NativeSwitch v-model="isOriginal" />
      </div>
      <div class="option-row">
        <span class="option-ic option-ic--purple">
          <Icon name="sparkles" :size="20" color="#fff" />
        </span>
        <div class="option-text">
          <span class="option-label">含AI内容</span>
          <span class="option-desc">声明帖子包含AI生成内容</span>
        </div>
        <NativeSwitch v-model="hasAiContent" />
      </div>
    </section>

    <!-- 提交按钮（不在编辑器卡片内，由父页面顶部触发；此处保留底部草稿入口） -->
    <div v-if="!isEditMode()" class="draft-row">
      <button class="btn btn-outline btn-pill" type="button" :disabled="submitting" @click="publish(true)">
        <Icon name="file" :size="14" />
        存为草稿
      </button>
    </div>
    <!-- 编辑模式：确认编辑按钮 -->
    <div v-else class="draft-row">
      <button
        class="btn btn-primary btn-pill"
        type="button"
        :disabled="submitting || !canSubmit"
        @click="publish(false)"
      >
        <Icon name="check" :size="14" />
        确认编辑
      </button>
    </div>

    <!-- 圈子选择底部面板 -->
    <Teleport to="body">
      <Transition name="sheet">
        <div v-if="showCircleSheet" class="circle-sheet-overlay" @click.self="closeCircleSheet">
          <div class="circle-sheet" role="dialog" aria-modal="true" aria-label="选择圈子">
            <!-- 拖拽指示器 -->
            <div class="sheet-handle" @click="closeCircleSheet"></div>

            <!-- 总标题 + 搜索框 -->
            <div class="sheet-header">
              <h2 class="sheet-title">选择圈子</h2>
              <div class="sheet-search">
                <Icon name="search" :size="16" :color="'var(--text-400)'" />
                <input
                  v-model="circleSearchKeyword"
                  type="text"
                  class="sheet-search-input"
                  placeholder="搜索圈子"
                />
                <button v-if="circleSearchKeyword" class="sheet-search-clear" type="button" @click="circleSearchKeyword = ''">
                  <Icon name="x" :size="14" :color="'var(--text-400)'" />
                </button>
              </div>
            </div>

            <!-- 搜索结果 -->
            <div v-if="circleSearchKeyword.trim()" class="sheet-section">
              <h3 class="sheet-section-title">搜索结果</h3>
              <div v-if="searchResults.length" class="sheet-list">
                <div v-for="c in searchResults" :key="c.slug"
                     class="sheet-item"
                     :class="{ 'is-selected': c.slug === category }"
                     @click="selectCircleFromSheet(c)">
                  <span class="sheet-item-icon" :style="{ background: avatarGradient(c.id) }">
                    {{ (c.name || 'C').charAt(0) }}
                  </span>
                  <div class="sheet-item-info">
                    <span class="sheet-item-name">{{ c.name }}</span>
                    <span class="sheet-item-desc">{{ formatCount(c.member_count) }} 成员</span>
                  </div>
                  <Icon v-if="c.slug === category" name="check" :size="18" :color="'var(--brand-500)'" />
                </div>
              </div>
              <div v-else class="sheet-empty">未找到匹配的圈子</div>
            </div>

            <template v-if="!circleSearchKeyword.trim()">
              <!-- 为你推荐（固定区域，至少显示3个完整） -->
              <div class="sheet-section sheet-recommended">
                <h3 class="sheet-section-title">为你推荐</h3>
                <div v-if="recommendedCircles.length" class="sheet-list">
                  <div
                    v-for="(c, idx) in recommendedCircles"
                    :key="c.slug"
                    class="sheet-item"
                    :class="{ 'is-selected': c.slug === category }"
                    @click="selectCircleFromSheet(c)"
                  >
                    <span
                      class="sheet-item-icon"
                      :style="{ background: avatarGradient(c.id) }"
                    >{{ (c.name || 'C').charAt(0) }}</span>
                    <div class="sheet-item-info">
                      <span class="sheet-item-name">{{ c.name }}</span>
                      <span class="sheet-item-desc">{{ getCircleTag(c, idx) }} · {{ formatCount(c.member_count) }} 成员</span>
                    </div>
                    <Icon v-if="c.slug === category" name="check" :size="18" :color="'var(--brand-500)'" />
                  </div>
                </div>
                <div v-else class="sheet-empty">暂无推荐圈子</div>
              </div>

              <!-- Tab 切换（固定不动，不随列表滚动） -->
              <div class="sheet-tabs-bar">
                <button
                  class="sheet-tab"
                  :class="{ 'is-active': circleSheetTab === 'recent' }"
                  type="button"
                  @click="circleSheetTab = 'recent'"
                >最近在逛</button>
                <button
                  class="sheet-tab"
                  :class="{ 'is-active': circleSheetTab === 'followed' }"
                  type="button"
                  @click="circleSheetTab = 'followed'"
                >我的关注</button>
              </div>

              <!-- 圈子列表（可滚动） -->
              <div class="sheet-section sheet-list-section">
                <div v-if="(circleSheetTab === 'followed' ? followedCircles : circles).length" class="sheet-list">
                  <div
                    v-for="c in (circleSheetTab === 'followed' ? followedCircles : circles)"
                    :key="c.slug"
                    class="sheet-item"
                    :class="{ 'is-selected': c.slug === category }"
                    @click="selectCircleFromSheet(c)"
                  >
                    <span
                      class="sheet-item-icon"
                      :style="{ background: avatarGradient(c.id) }"
                    >{{ (c.name || 'C').charAt(0) }}</span>
                    <div class="sheet-item-info">
                      <span class="sheet-item-name">{{ c.name }}</span>
                      <span class="sheet-item-desc">{{ formatCount(c.member_count) }} 成员</span>
                    </div>
                    <Icon v-if="c.slug === category" name="check" :size="18" :color="'var(--brand-500)'" />
                  </div>
                </div>
                <div v-else class="sheet-empty">
                  {{ circleSheetTab === 'followed' ? '暂无关注的圈子' : '暂无圈子' }}
                </div>
              </div>
            </template>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- 无吧发布提示 -->
    <NativeDialog v-model="showNoCirclePrompt" title="选择圈子" width="380px">
      <p class="no-circle-prompt-text">
        你的帖子还没有选择圈子，选择一个合适的圈子可以让更多人看到。是否要选择圈子？
      </p>
      <template #footer>
        <button class="btn btn-outline" type="button" @click="continuePublishWithoutCircle">不选择了</button>
        <button
          class="btn btn-primary"
          type="button"
          @click="showNoCirclePrompt = false; openCircleSheet()"
        >选择圈子</button>
      </template>
    </NativeDialog>
  </div>
</template>

<style scoped>
.editor-wrap {
  display: flex;
  flex-direction: column;
  gap: 12px;
  position: relative;
}

/* 编辑器卡片 */
.editor-card {
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  overflow: visible;
  position: relative;
}

/* 圈子选择行 */
.circle-row {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 0.5px solid var(--bg-300);
}
.row-label {
  font-size: 13px;
  color: var(--text-500);
  font-weight: 500;
}
.circle-select {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  border: none;
  cursor: pointer;
  font-family: inherit;
  padding: 4px 6px;
  margin: -4px -6px;
  border-radius: var(--radius-sm);
  transition: background 0.15s var(--ease-apple);
}
.circle-select:hover {
  background: var(--bg-100);
}
.circle-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--brand-500);
}

/* 下拉 */
.circle-dropdown {
  position: absolute;
  top: calc(100% + 6px);
  right: 14px;
  z-index: 30;
  min-width: 188px;
  background: var(--bg-50);
  border-radius: var(--radius-md);
  box-shadow: 0 8px 24px -8px rgba(0, 0, 0, 0.08), 0 4px 8px -4px rgba(0, 0, 0, 0.05);
  padding: 6px;
  transform-origin: top right;
}
.dropdown-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  font-size: 15px;
  color: var(--text-800);
  cursor: pointer;
  transition: background 0.15s var(--ease-apple);
}
.dropdown-item:hover {
  background: var(--bg-100);
}
.dropdown-item.is-selected {
  color: var(--brand-500);
  font-weight: 600;
}
.dropdown-empty {
  padding: 12px;
  text-align: center;
  font-size: 13px;
  color: var(--text-500);
}

.dropdown-enter-active,
.dropdown-leave-active {
  transition: opacity 0.15s var(--ease-apple), transform 0.15s var(--ease-apple);
}
.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-6px) scale(0.98);
}

/* 标题行 */
.title-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 18px;
  border-bottom: 0.5px solid var(--bg-300);
}
.title-input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  font-family: inherit;
  font-size: 17px;
  font-weight: 600;
  color: var(--text-800);
  padding: 2px 0;
  line-height: 1.5;
}
.title-input::placeholder {
  color: var(--text-500);
  font-weight: 500;
}
.title-count {
  font-size: 13px;
  color: var(--text-500);
  flex-shrink: 0;
  margin-top: 4px;
  font-variant-numeric: tabular-nums;
  transition: color 0.15s var(--ease-apple);
}
.title-count.is-max {
  color: var(--error);
}

/* 正文 */
.body-input {
  display: block;
  width: 100%;
  min-height: 200px;
  border: none;
  outline: none;
  background: transparent;
  font-family: inherit;
  font-size: 15px;
  line-height: 1.65;
  color: var(--text-800);
  padding: 16px 18px;
  resize: none;
  overflow: hidden;
}
.body-input::placeholder {
  color: var(--text-500);
}

/* 正文高亮 overlay 容器：#话题 和 @用户 显示蓝色 */
.body-wrap {
  position: relative;
}
.body-highlight {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  pointer-events: none;
  color: var(--text-800);
  font-family: inherit;
  font-size: 15px;
  line-height: 1.65;
  padding: 16px 18px;
  white-space: pre-wrap;
  word-wrap: break-word;
  overflow: hidden;
  letter-spacing: normal;
}
/* textarea 文字透明、光标可见，覆盖在高亮层之上 */
.body-input-overlay {
  position: relative;
  z-index: 1;
  background: transparent;
  color: transparent;
  caret-color: var(--text-800);
  /* 注意：不使用 -webkit-text-fill-color: transparent，否则会导致输入法拼音候选词也透明看不见 */
}
.body-input-overlay::placeholder {
  color: var(--text-500);
}
/* 输入法输入中（composition 期间）：显示真实文本，避免拼音候选词消失 */
.body-input-overlay.is-composing {
  color: var(--text-800);
}
.body-input-overlay.is-composing::placeholder {
  color: var(--text-500);
}
.body-counter {
  position: absolute;
  right: 8px;
  bottom: 4px;
  font-size: 11px;
  color: var(--text-400);
  background: rgba(255, 255, 255, 0.8);
  padding: 2px 6px;
  border-radius: 4px;
  pointer-events: none;
  z-index: 2;
}
.body-counter.is-max {
  color: #ef4444;
  font-weight: 600;
}
.body-highlight :deep(.hl-topic),
.body-highlight :deep(.hl-mention) {
  color: var(--brand-500);
  font-weight: 500;
}

/* 工具条 */
.toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 12px;
  border-top: 0.5px solid var(--bg-300);
  overflow-x: auto;
  scrollbar-width: none;
}
.toolbar::-webkit-scrollbar {
  display: none;
}
.tool-btn {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  min-width: 56px;
  padding: 8px 6px;
  border-radius: var(--radius-sm);
  background: transparent;
  border: none;
  cursor: pointer;
  font-family: inherit;
  color: var(--text-600);
  transition: all 0.15s var(--ease-apple);
}
.tool-btn:hover {
  background: var(--bg-100);
}
.tool-btn.is-active {
  color: var(--brand-500);
  background: var(--brand-50);
}
.tool-label {
  font-size: 12px;
  font-weight: 500;
}

/* ============ 阶段二：浮层面板（话题 / @ / 位置 / 表情） ============ */
.floating-panel {
  position: relative;
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  padding: 12px 14px;
  z-index: 20;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 320px;
  overflow: hidden;
}
/* 浮层绝对定位（话题/@好友/位置/表情：定位到光标下方） */
.popover-panel {
  position: absolute;
  width: 300px;
  max-width: calc(100% - 20px);
  z-index: 100;
  box-shadow: var(--shadow-md, 0 4px 16px rgba(0, 0, 0, 0.12));
}
/* 宽浮层（表情面板） */
.popover-panel--wide {
  width: 360px;
  max-height: 380px;
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-800);
}
.panel-close {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: none;
  background: var(--bg-100);
  color: var(--text-600);
  cursor: pointer;
  display: grid;
  place-items: center;
  transition: background 0.15s var(--ease-apple);
}
.panel-close:hover {
  background: var(--bg-200);
}
.panel-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--bg-300);
  border-radius: var(--radius-sm);
  background: var(--bg-50);
  font-family: inherit;
  font-size: 14px;
  color: var(--text-800);
  outline: none;
  transition: all 0.15s var(--ease-apple);
}
.panel-input:focus {
  border-color: var(--brand-500);
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.12);
}
.panel-loading,
.panel-empty {
  padding: 16px 0;
  text-align: center;
  font-size: 13px;
  color: var(--text-500);
}

/* 话题结果 */
.topic-results {
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow-y: auto;
  flex: 1;
}
.topic-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.15s var(--ease-apple);
}
.topic-item:hover {
  background: var(--bg-100);
}
.topic-name {
  font-size: 14px;
  color: var(--brand-500);
  font-weight: 500;
}
.topic-count {
  font-size: 12px;
  color: var(--text-500);
}
/* 话题热度（带火焰图标） */
.topic-hot {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  color: var(--text-500);
}
/* 搜索行（话题/@好友共用） */
.topic-input-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid var(--bg-300);
  border-radius: var(--radius-sm);
  background: var(--bg-50);
  transition: border-color 0.15s var(--ease-apple);
}
.topic-input-row:focus-within {
  border-color: var(--brand-500);
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.12);
}
.topic-input-row .panel-input {
  flex: 1;
  min-width: 0;
  border: none;
  background: transparent;
  padding: 0;
  box-shadow: none;
}
.topic-input-row .panel-input:focus {
  box-shadow: none;
}

/* @好友列表 */
.mention-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow-y: auto;
  flex: 1;
}
.mention-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.15s var(--ease-apple);
}
.mention-item:hover {
  background: var(--bg-100);
}
.mention-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background-size: cover;
  background-position: center;
  color: #fff;
  display: grid;
  place-items: center;
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
}
.mention-avatar--sm {
  width: 28px;
  height: 28px;
  font-size: 11px;
  position: relative;
}
.mention-name {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  color: var(--text-800);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 位置浮层 */
.location-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.location-chip {
  padding: 5px 12px;
  border-radius: 999px;
  border: 1px solid var(--bg-300);
  background: var(--bg-50);
  font-family: inherit;
  font-size: 12.5px;
  color: var(--text-600);
  cursor: pointer;
  transition: all 0.15s var(--ease-apple);
}
.location-chip:hover {
  background: var(--brand-50);
  border-color: var(--brand-500);
  color: var(--brand-600);
}

/* 表情面板 */
.emoji-tabs {
  display: flex;
  gap: 4px;
  overflow-x: auto;
  scrollbar-width: none;
  padding-bottom: 4px;
}
.emoji-tabs::-webkit-scrollbar {
  display: none;
}
.emoji-tab {
  padding: 4px 10px;
  border-radius: 999px;
  border: none;
  background: var(--bg-100);
  font-family: inherit;
  font-size: 12px;
  color: var(--text-600);
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.15s var(--ease-apple);
}
.emoji-tab.is-active {
  background: var(--brand-500);
  color: #fff;
}
.emoji-grid {
  display: grid;
  /* 微信风格方框：等宽方格 */
  grid-template-columns: repeat(auto-fill, minmax(40px, 1fr));
  gap: 4px;
  overflow-y: auto;
  flex: 1;
  padding: 4px;
}
.emoji-cell {
  font-size: 22px;
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 6px;
  border-radius: var(--radius-sm);
  transition: background 0.15s var(--ease-apple);
  line-height: 1;
  /* 微信风格方框：正方形 */
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
.emoji-cell:hover {
  background: var(--bg-100);
}
.emoji-cell.is-fav {
  background: rgba(0, 122, 255, 0.08);
}
/* 收藏表情 tab */
.emoji-fav-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 4px;
  gap: 8px;
}
.fav-tip {
  font-size: 12px;
  color: var(--text-500);
}
.fav-upload-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border-radius: var(--radius-sm);
  background: var(--brand-500);
  color: #fff;
  font-size: 13px;
  border: none;
  cursor: pointer;
  transition: opacity 0.15s var(--ease-apple);
}
.fav-upload-btn:hover {
  opacity: 0.85;
}
.fav-grid {
  grid-template-columns: repeat(auto-fill, minmax(60px, 1fr));
}
.fav-cell {
  position: relative;
  aspect-ratio: 1;
  border: 1px solid var(--bg-200);
  border-radius: var(--radius-sm);
  overflow: hidden;
}
.fav-cell.is-image {
  background: var(--bg-50);
}
.emoji-img-btn {
  width: 100%;
  height: 100%;
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.emoji-img-btn img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}
.emoji-char-btn {
  width: 100%;
  height: 100%;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 26px;
  line-height: 1;
}
.fav-remove {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.5);
  color: #fff;
  border: none;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.15s var(--ease-apple);
}
.fav-cell:hover .fav-remove {
  opacity: 1;
}
.panel-empty-sub {
  font-size: 12px;
  color: var(--text-400);
  margin-top: 4px;
}

/* ============ 已选标签预览 ============ */
.extras-card {
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  padding: 12px 14px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.extra-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12.5px;
  font-weight: 500;
}
.extra-chip--topic {
  background: var(--brand-50);
  color: var(--brand-600);
}
.extra-chip--location {
  background: var(--bg-100);
  color: var(--text-700);
}
.extra-del {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: none;
  background: rgba(0, 0, 0, 0.15);
  color: inherit;
  cursor: pointer;
  padding: 0;
  margin-left: 2px;
  transition: background 0.15s var(--ease-apple);
}
.extra-del:hover {
  background: rgba(0, 0, 0, 0.3);
}
.extra-del--avatar {
  position: absolute;
  top: -4px;
  right: -4px;
  background: var(--error);
  color: #fff;
}
.extra-mentions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.extra-poll {
  width: 100%;
  background: var(--brand-50);
  border-radius: var(--radius-md);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.extra-poll-head {
  display: flex;
  align-items: center;
  gap: 6px;
}
.extra-poll-title {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  color: var(--brand-600);
}
.extra-poll-opt {
  font-size: 13px;
  color: var(--text-700);
  padding-left: 4px;
}
.extra-poll-meta {
  font-size: 11px;
  color: var(--text-500);
  margin-top: 2px;
}

/* 图片卡片 */
.images-card {
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  padding: 16px;
}
.images-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.images-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-800);
}
.images-hint {
  font-size: 13px;
  color: var(--text-500);
}
.image-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}
.img-cell {
  position: relative;
  aspect-ratio: 1 / 1;
  border-radius: var(--radius-sm);
  overflow: hidden;
  box-shadow: var(--shadow-xs);
  background: var(--bg-100);
}
.img-cell img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.del-badge {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  transition: all 0.15s var(--ease-apple);
}
.del-badge:hover {
  background: rgba(0, 0, 0, 0.75);
  transform: scale(1.05);
}
.add-cell {
  aspect-ratio: 1 / 1;
  border-radius: var(--radius-sm);
  background: var(--bg-100);
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-500);
  transition: all 0.15s var(--ease-apple);
}
.add-cell:hover:not(:disabled) {
  background: var(--bg-200);
  color: var(--text-800);
}
.add-cell:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

/* 上传进度条 */
.upload-progress-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  background: var(--bg-100);
  color: var(--text-500);
}
.spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.progress-bar-wrap {
  width: 70%;
  height: 4px;
  background: var(--bg-300);
  border-radius: 2px;
  overflow: hidden;
}
.progress-bar-fill {
  height: 100%;
  background: var(--brand-500);
  border-radius: 2px;
  transition: width 0.2s ease;
}
.progress-text {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-600);
}

/* 选项卡片 */
.options-card {
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  overflow: hidden;
}
.option-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 18px;
}
.option-row + .option-row {
  border-top: 0.5px solid var(--bg-300);
}
.option-ic {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: var(--brand-500);
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.option-ic--green {
  background: var(--success, #34c759);
}
.option-ic--purple {
  background: linear-gradient(135deg, #af52de, #5856d6);
}
.option-text {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.option-label {
  font-size: 15px;
  color: var(--text-800);
  font-weight: 500;
}
.option-desc {
  font-size: 12px;
  color: var(--text-500);
  margin-top: 2px;
}

/* 草稿按钮行 */
.draft-row {
  display: flex;
  justify-content: center;
  padding: 8px 0;
}

/* 投票表单 */
.poll-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.poll-form .form-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.poll-form .form-row--inline {
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
}
.poll-form .form-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-800);
}
.poll-form .form-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--bg-300);
  border-radius: var(--radius-sm);
  background: var(--bg-50);
  font-family: inherit;
  font-size: 14px;
  color: var(--text-800);
  outline: none;
  transition: all 0.15s var(--ease-apple);
}
.poll-form .form-input:focus {
  border-color: var(--brand-500);
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.12);
}
.poll-option-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.poll-option-del {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: none;
  background: var(--bg-100);
  color: var(--text-500);
  cursor: pointer;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  transition: all 0.15s var(--ease-apple);
}
.poll-option-del:hover {
  background: var(--state-error-surface);
  color: var(--error);
}

/* 通用按钮 */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 8px 16px;
  border-radius: var(--radius-sm);
  border: none;
  font-family: inherit;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s var(--ease-apple);
}
.btn-primary {
  background: var(--brand-500);
  color: #fff;
}
.btn-primary:hover:not(:disabled) {
  background: var(--brand-600);
}
.btn-outline {
  background: transparent;
  border: 1px solid var(--bg-300);
  color: var(--text-700);
}
.btn-outline:hover:not(:disabled) {
  background: var(--bg-100);
}
.btn-pill {
  border-radius: 999px;
  padding: 8px 18px;
}
.btn-sm {
  padding: 5px 10px;
  font-size: 12.5px;
  align-self: flex-start;
}
.btn-block {
  width: 100%;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ============ 校区选择卡片 ============ */
.school-select-card {
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  overflow: hidden;
}
.school-select-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 18px;
  flex-wrap: wrap;
}
.school-select-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-700);
  flex-shrink: 0;
}
.school-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  flex: 1;
  min-width: 0;
}
.school-chip {
  padding: 5px 12px;
  border-radius: 999px;
  border: 1px solid var(--bg-300);
  background: var(--bg-50);
  font-family: inherit;
  font-size: 13px;
  color: var(--text-600);
  cursor: pointer;
  transition: all 0.15s var(--ease-apple);
}
.school-chip:hover {
  background: var(--bg-100);
  border-color: var(--bg-300);
}
.school-chip.is-active {
  background: var(--brand-50);
  color: var(--brand-600);
  border-color: var(--brand-500);
  font-weight: 600;
}
.school-empty {
  font-size: 12px;
  color: var(--text-400);
  padding: 4px 0;
}

/* ============ 圈子选择卡片 ============ */
.circle-select-card {
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  overflow: hidden;
}
.circle-select-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 14px 18px;
  background: transparent;
  border: none;
  cursor: pointer;
  font-family: inherit;
}
.circle-select-text {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-800);
  flex: 1;
  text-align: left;
}
.circle-select-hint {
  font-size: 13px;
  color: var(--text-400);
}

/* ============ 圈子选择底部面板 ============ */
.circle-sheet-overlay {
  position: fixed;
  inset: 0;
  z-index: 9998;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: flex-end;
  justify-content: center;
}
.circle-sheet {
  width: 100%;
  max-width: 640px;
  /* 至少占六分之五（约 83.3%），取 90vh 保证留点边缘空间 */
  max-height: 90vh;
  background: var(--bg-50);
  border-radius: 20px 20px 0 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.sheet-handle {
  width: 36px;
  height: 4px;
  background: var(--bg-300);
  border-radius: 2px;
  margin: 8px auto 4px;
  cursor: pointer;
  flex-shrink: 0;
}
.sheet-header {
  padding: 4px 16px 12px;
  flex-shrink: 0;
  border-bottom: 0.5px solid var(--bg-300);
}
.sheet-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-900);
  margin: 0 0 12px;
  text-align: center;
}
.sheet-search {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--bg-100);
  border-radius: 10px;
  padding: 8px 12px;
}
.sheet-search-input {
  flex: 1;
  border: none;
  background: transparent;
  font-size: 14px;
  color: var(--text-800);
  outline: none;
  font-family: inherit;
}
.sheet-search-input::placeholder {
  color: var(--text-400);
}
.sheet-search-clear {
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 2px;
  display: grid;
  place-items: center;
}
.sheet-section {
  padding: 0 16px;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}
.sheet-section + .sheet-section {
  border-top: 0.5px solid var(--bg-300);
  padding-top: 4px;
}
.sheet-section-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-800);
  margin: 12px 0 8px;
}

/* ============ 圈子选择 sheet 布局优化 ============ */
/* 为你推荐：固定区域，至少能显示3个完整圈子（每项约 56px，3项≈168px + 标题） */
.sheet-recommended {
  flex: 0 0 auto;
  max-height: 240px;
  overflow-y: auto;
  border-bottom: 0.5px solid var(--bg-300);
}
/* Tab 切换栏：固定不动，不随列表滚动 */
.sheet-tabs-bar {
  display: flex;
  gap: 8px;
  padding: 10px 16px 8px;
  background: var(--bg-50);
  border-bottom: 0.5px solid var(--bg-300);
  flex-shrink: 0;
  position: sticky;
  top: 0;
  z-index: 2;
}
/* 圈子列表：可滚动 */
.sheet-list-section {
  flex: 1;
  min-height: 120px;
}

/* 保留旧 .sheet-tabs 兼容（已被 .sheet-tabs-bar 替代） */
.sheet-tabs {
  display: flex;
  gap: 8px;
  margin: 12px 0 8px;
}
.sheet-tab {
  padding: 6px 16px;
  border-radius: 999px;
  font-size: 13px;
  border: 1px solid var(--bg-200);
  background: var(--bg-50);
  color: var(--text-500);
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s var(--ease-apple);
}
.sheet-tab.is-active {
  background: var(--brand-500);
  color: #fff;
  border-color: var(--brand-500);
}
.sheet-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-bottom: 12px;
}
.sheet-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 8px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background 0.15s var(--ease-apple);
}
.sheet-item:hover {
  background: var(--bg-100);
}
.sheet-item.is-selected {
  background: var(--brand-50);
}
.sheet-item-icon {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  flex-shrink: 0;
}
.sheet-item-info {
  flex: 1;
  min-width: 0;
}
.sheet-item-name {
  display: block;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-800);
}
.sheet-item-desc {
  display: block;
  font-size: 12px;
  color: var(--text-400);
  margin-top: 2px;
}
.sheet-empty {
  padding: 16px 0;
  text-align: center;
  font-size: 13px;
  color: var(--text-500);
  padding-bottom: 16px;
}

/* 面板滑入动画 */
.sheet-enter-active,
.sheet-leave-active {
  transition: opacity 0.25s var(--ease-apple);
}
.sheet-enter-active .circle-sheet,
.sheet-leave-active .circle-sheet {
  transition: transform 0.25s var(--ease-apple);
}
.sheet-enter-from,
.sheet-leave-to {
  opacity: 0;
}
.sheet-enter-from .circle-sheet,
.sheet-leave-to .circle-sheet {
  transform: translateY(100%);
}

/* 无吧发布提示文本 */
.no-circle-prompt-text {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-700);
}

/* 响应式 */
@media (max-width: 768px) {
  .circle-row,
  .title-row {
    padding-left: 14px;
    padding-right: 14px;
  }
  .circle-row {
    padding-top: 12px;
    padding-bottom: 12px;
  }
  .row-label {
    font-size: 12px;
  }
  .circle-name {
    font-size: 14px;
  }
  .circle-dropdown {
    right: 10px;
    min-width: 168px;
  }
  .title-input {
    font-size: 16px;
  }
  .title-count {
    font-size: 12px;
  }
  .body-input {
    padding: 14px;
    font-size: 15px;
    min-height: 180px;
  }
  .toolbar {
    padding: 6px;
    gap: 2px;
  }
  .tool-btn {
    min-width: 50px;
    padding: 6px 4px;
  }
  .tool-label {
    font-size: 11px;
  }
  .images-card {
    padding: 14px;
  }
  .image-grid {
    gap: 6px;
  }
  .circle-select-btn {
    padding-left: 14px;
    padding-right: 14px;
  }
  .option-row {
    padding-left: 14px;
    padding-right: 14px;
  }
}
</style>
