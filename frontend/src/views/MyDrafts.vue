<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import AppHeader from '../components/header/AppHeader.vue'
import EmptyState from '../components/common/EmptyState.vue'
import MarkdownText from '../components/common/MarkdownText.vue'
import { fetchMyDrafts } from '../api/user'
import { deletePost, updatePost } from '../api/post'
import { useSessionStore } from '../stores/session'
import type { Post } from '../types/api'

const router = useRouter()
const session = useSessionStore()

const drafts = ref<Post[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const { data } = await fetchMyDrafts()
    drafts.value = data.data
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function publish(post: Post) {
  try {
    await ElMessageBox.confirm('确认发布该草稿？发布后将在首页显示。', '发布草稿', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await updatePost(post.id, { is_draft: false })
    ElMessage.success('已发布')
    drafts.value = drafts.value.filter((p) => p.id !== post.id)
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function remove(post: Post) {
  try {
    await ElMessageBox.confirm('确认删除该草稿？删除后不可恢复。', '删除草稿', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await deletePost(post.id)
    ElMessage.success('已删除')
    drafts.value = drafts.value.filter((p) => p.id !== post.id)
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

function edit(post: Post) {
  // T4-5 编辑功能：暂时用 prompt 简易编辑（编辑器组件待 T6 完成）
  ElMessageBox.prompt('编辑草稿内容', '编辑', {
    inputType: 'textarea',
    inputValue: post.content,
    inputValidator: (val: string) => val.trim().length > 0 || '内容不能为空',
  })
    .then(async ({ value }) => {
      try {
        await updatePost(post.id, { content: value })
        ElMessage.success('已保存')
        await load()
      } catch (error) {
        ElMessage.error((error as Error).message)
      }
    })
    .catch(() => {})
}

function fmtTime(t?: string | null) {
  if (!t) return ''
  return t.replace('T', ' ').slice(0, 16)
}

onMounted(() => {
  if (!session.userId) {
    ElMessage.info('请先登录')
    router.push('/')
  } else {
    load()
  }
})
</script>

<template>
  <main class="min-h-screen pb-16 lg:pb-0">
    <AppHeader />
    <div class="mx-auto max-w-3xl px-4 py-5" v-loading="loading">
      <div class="mb-4 flex items-center justify-between">
        <h2 class="m-0 text-lg font-black">我的草稿</h2>
        <span class="text-xs text-slate-500">{{ drafts.length }} 条草稿</span>
      </div>

      <div v-if="drafts.length" class="space-y-3">
        <div
          v-for="post in drafts"
          :key="post.id"
          class="rounded border border-ly-line bg-white p-4"
        >
          <div class="mb-1 flex items-center justify-between text-xs text-slate-500">
            <span>{{ post.category }} · {{ post.school }}</span>
            <span>{{ fmtTime(post.created_at) }}</span>
          </div>
          <MarkdownText :content="post.content" class="m-0 mb-3 text-sm" :clamp="5" />
          <div class="flex gap-2">
            <el-button size="small" type="primary" @click="publish(post)">发布</el-button>
            <el-button size="small" @click="edit(post)">编辑</el-button>
            <el-button size="small" type="danger" @click="remove(post)">删除</el-button>
          </div>
        </div>
      </div>

      <EmptyState v-else text="暂无草稿，发帖时勾选「保存为草稿」即可在此查看" />
    </div>
  </main>
</template>
