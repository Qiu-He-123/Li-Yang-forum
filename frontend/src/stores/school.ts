import { defineStore } from 'pinia'
import { ref } from 'vue'

import { listSchools } from '../api/school'
import type { School } from '../types/api'

export const useSchoolStore = defineStore('school', () => {
  const schools = ref<School[]>([])
  const loaded = ref(false)
  const error = ref('')

  async function loadSchools() {
    error.value = ''
    try {
      const { data } = await listSchools({
        showGlobalLoading: false,
        showGlobalError: false,
      })
      // 防御性处理：后端 ok() 历史版本曾把空列表转成 {}，这里兜底确保一定是数组
      const list = data?.data
      schools.value = Array.isArray(list) ? list : []
      loaded.value = true
    } catch (err) {
      // 加载失败时不写入假数据，避免发帖时 school_id 指向不存在的校区
      schools.value = []
      loaded.value = true
      error.value = (err as Error).message || '校区加载失败'
    }
  }

  return { schools, loaded, error, loadSchools }
})
