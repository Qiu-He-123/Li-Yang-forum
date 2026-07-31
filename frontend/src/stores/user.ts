import { defineStore } from 'pinia'
import { ref } from 'vue'

import { fetchMe } from '../api/user'
import type { Profile } from '../types/api'

export const useUserStore = defineStore('user', () => {
  const profile = ref<Profile | null>(null)
  const profileLoaded = ref(false)
  const profileLoading = ref(false)
  const profileError = ref('')
  let loadPromise: Promise<Profile | null> | null = null

  async function loadProfile() {
    if (loadPromise) return loadPromise

    profileLoading.value = true
    profileError.value = ''
    loadPromise = (async () => {
      try {
        const { data } = await fetchMe({
          showGlobalLoading: false,
          showGlobalError: false,
        })
        profile.value = data.data
        profileLoaded.value = true
        return profile.value
      } catch (error) {
        profileLoaded.value = true
        profileError.value = (error as Error).message || 'profile load failed'
        // Keep the last good profile. A temporary request failure must not erase
        // the nickname/avatar and make the UI look like it is still loading.
        return profile.value
      } finally {
        profileLoading.value = false
        loadPromise = null
      }
    })()

    return loadPromise
  }

  function clearProfile() {
    profile.value = null
    profileLoaded.value = false
    profileLoading.value = false
    profileError.value = ''
    loadPromise = null
  }

  return { profile, profileLoaded, profileLoading, profileError, loadProfile, clearProfile }
})
