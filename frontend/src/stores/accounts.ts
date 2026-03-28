import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Account } from '@/api/client'
import { api } from '@/api/client'

export const useAccountsStore = defineStore('accounts', () => {
  const accounts = ref<Account[]>([])
  const loading = ref(false)

  async function fetchAccounts() {
    loading.value = true
    try {
      accounts.value = await api.accounts.list()
    } finally {
      loading.value = false
    }
  }

  async function updateAccount(id: number, patch: { account_name?: string }) {
    await api.accounts.update(id, patch)
    const account = accounts.value.find((a) => a.id === id)
    if (account && patch.account_name !== undefined) account.account_name = patch.account_name
  }

  async function deleteAccount(id: number) {
    await api.accounts.delete(id)
    accounts.value = accounts.value.filter((a) => a.id !== id)
  }

  async function startAuth(locale: string, name: string) {
    const { auth_url } = await api.accounts.authStart(locale, name)
    window.open(auth_url, '_blank', 'noopener')
  }

  async function scanLibrary(id: number) {
    await api.accounts.scan(id)
  }

  return { accounts, loading, fetchAccounts, updateAccount, deleteAccount, startAuth, scanLibrary }
})
