<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold">Accounts</h1>
      <button
        @click="openAddModal"
        class="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm font-medium"
      >
        Add Account
      </button>
    </div>

    <div v-if="store.accounts.length === 0 && !store.loading" class="text-gray-400">
      No accounts yet. Add an Audible account to get started.
    </div>

    <ul class="space-y-3">
      <li
        v-for="account in store.accounts"
        :key="account.id"
        class="flex items-center justify-between bg-gray-800 rounded-lg px-4 py-3"
      >
        <div class="flex items-center gap-3 min-w-0">
          <span class="text-2xl">{{ localeFlag(account.locale) }}</span>
          <div class="min-w-0">
            <!-- Inline name editing -->
            <div v-if="editingId === account.id" class="flex items-center gap-2 mb-0.5">
              <input
                v-model="editingName"
                @keydown.enter="saveEdit(account.id)"
                @keydown.escape="cancelEdit"
                ref="editInput"
                type="text"
                class="px-2 py-0.5 bg-gray-700 rounded text-sm font-medium outline-none focus:ring-2 focus:ring-indigo-500"
              />
              <button @click="saveEdit(account.id)" class="text-xs text-indigo-400 hover:text-indigo-300">Save</button>
              <button @click="cancelEdit" class="text-xs text-gray-500 hover:text-gray-300">Cancel</button>
            </div>
            <div v-else class="flex items-center gap-1.5">
              <span class="font-medium">{{ account.account_name || account.email }}</span>
              <button
                @click="startEdit(account)"
                class="text-gray-600 hover:text-gray-400 transition-colors"
                title="Rename"
              >
                <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                  <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" />
                </svg>
              </button>
            </div>
            <div class="text-sm text-gray-400">
              {{ account.locale.toUpperCase() }} · {{ account.email }}
              <span v-if="account.last_scanned_at" class="ml-2 text-gray-500">
                · Scanned {{ formatDate(account.last_scanned_at) }}
              </span>
              <span v-else class="ml-2 text-gray-500">· Never scanned</span>
            </div>
          </div>
        </div>
        <div class="flex gap-2 shrink-0 ml-4">
          <button
            @click="store.scanLibrary(account.id)"
            class="px-3 py-1 text-sm bg-gray-700 hover:bg-gray-600 rounded-lg"
          >
            Scan Library
          </button>
          <button
            @click="store.deleteAccount(account.id)"
            class="px-3 py-1 text-sm bg-red-900 hover:bg-red-800 rounded-lg"
          >
            Remove
          </button>
        </div>
      </li>
    </ul>

    <!-- Add Account Modal -->
    <div
      v-if="modal.open"
      class="fixed inset-0 bg-black/60 flex items-center justify-center z-50"
      @click.self="resetModal"
    >
      <div class="bg-gray-800 rounded-xl p-6 w-md">

        <!-- Step 1: pick locale + name, open login tab -->
        <template v-if="modal.step === 1">
          <h2 class="text-lg font-bold mb-4">Add Audible Account</h2>

          <label class="block text-sm text-gray-400 mb-1">Display Name</label>
          <input
            v-model="modal.name"
            type="text"
            placeholder="My Audible"
            class="w-full mb-3 px-3 py-2 bg-gray-700 rounded-lg text-sm outline-none"
          />

          <label class="block text-sm text-gray-400 mb-1">Region</label>
          <select v-model="modal.locale" class="w-full mb-5 px-3 py-2 bg-gray-700 rounded-lg text-sm outline-none">
            <option value="us">🇺🇸 United States</option>
            <option value="uk">🇬🇧 United Kingdom</option>
            <option value="ca">🇨🇦 Canada</option>
            <option value="de">🇩🇪 Germany</option>
            <option value="fr">🇫🇷 France</option>
            <option value="au">🇦🇺 Australia</option>
            <option value="jp">🇯🇵 Japan</option>
            <option value="in">🇮🇳 India</option>
            <option value="es">🇪🇸 Spain</option>
          </select>

          <div class="flex gap-3 justify-end">
            <button @click="resetModal" class="px-4 py-2 text-sm text-gray-400 hover:text-white">
              Cancel
            </button>
            <button
              @click="startAuth"
              :disabled="modal.loading"
              class="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-sm font-medium"
            >
              {{ modal.loading ? 'Opening…' : 'Login with Audible' }}
            </button>
          </div>
        </template>

        <!-- Step 2: paste the maplanding URL -->
        <template v-if="modal.step === 2">
          <h2 class="text-lg font-bold mb-3">Complete Login</h2>

          <ol class="text-sm text-gray-300 space-y-2 mb-4 list-decimal list-inside">
            <li>An Amazon login page has opened in a new tab.</li>
            <li>Sign in with your Audible / Amazon account.</li>
            <li>
              After login you'll see an <span class="text-white font-medium">"Looking for Something?"</span>
              error page — that's expected.
            </li>
            <li>
              Copy the <span class="text-white font-medium">full URL</span>
              from your browser's address bar and paste it below.
            </li>
          </ol>

          <input
            v-model="modal.responseUrl"
            type="text"
            placeholder="https://www.amazon.co.uk/ap/maplanding?openid.oa2.authorization_code=..."
            class="w-full mb-1 px-3 py-2 bg-gray-700 rounded-lg text-sm outline-none font-mono"
          />
          <p v-if="modal.error" class="text-xs text-red-400 mb-3">{{ modal.error }}</p>
          <p v-else class="text-xs text-gray-500 mb-3">The URL should start with https://www.amazon.</p>

          <div class="flex gap-3 justify-end">
            <button @click="resetModal" class="px-4 py-2 text-sm text-gray-400 hover:text-white">
              Cancel
            </button>
            <button
              @click="completeAuth"
              :disabled="modal.loading || !modal.responseUrl"
              class="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-sm font-medium"
            >
              {{ modal.loading ? 'Connecting…' : 'Connect Account' }}
            </button>
          </div>
        </template>

        <!-- Step 3: success -->
        <template v-if="modal.step === 3">
          <div class="text-center py-4">
            <div class="text-4xl mb-3">✓</div>
            <h2 class="text-lg font-bold mb-1">Account Added</h2>
            <p class="text-sm text-gray-400 mb-5">{{ modal.addedEmail }}</p>
            <button @click="resetModal" class="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm font-medium">
              Done
            </button>
          </div>
        </template>

      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, nextTick, onMounted } from 'vue'
import type { Account } from '@/api/client'
import { useAccountsStore } from '@/stores/accounts'
import { api } from '@/api/client'

const store = useAccountsStore()

const editingId = ref<number | null>(null)
const editingName = ref('')
const editInput = ref<HTMLInputElement | null>(null)

function startEdit(account: Account) {
  editingId.value = account.id
  editingName.value = account.account_name
  nextTick(() => editInput.value?.focus())
}

async function saveEdit(id: number) {
  const name = editingName.value.trim()
  if (name) await store.updateAccount(id, { account_name: name })
  cancelEdit()
}

function cancelEdit() {
  editingId.value = null
  editingName.value = ''
}

const localeFlags: Record<string, string> = {
  us: '🇺🇸', uk: '🇬🇧', ca: '🇨🇦', de: '🇩🇪',
  fr: '🇫🇷', au: '🇦🇺', jp: '🇯🇵', in: '🇮🇳', es: '🇪🇸',
}
function localeFlag(locale: string): string {
  return localeFlags[locale] ?? '🌐'
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

const modal = reactive({
  open: false,
  step: 1,
  locale: 'us',
  name: '',
  state: '',
  responseUrl: '',
  addedEmail: '',
  loading: false,
  error: '',
})

onMounted(() => store.fetchAccounts())

function openAddModal() {
  modal.open = true
  modal.step = 1
  modal.locale = 'us'
  modal.name = ''
  modal.state = ''
  modal.responseUrl = ''
  modal.error = ''
  modal.loading = false
}

function resetModal() {
  modal.open = false
  modal.step = 1
}

async function startAuth() {
  modal.loading = true
  modal.error = ''
  try {
    const name = modal.name || `Audible ${modal.locale.toUpperCase()}`
    const { auth_url, state } = await api.accounts.authStart(modal.locale, name)
    modal.state = state
    modal.name = name
    window.open(auth_url, '_blank', 'noopener')
    modal.step = 2
  } catch (e: any) {
    modal.error = e.message
  } finally {
    modal.loading = false
  }
}

async function completeAuth() {
  modal.loading = true
  modal.error = ''
  try {
    const { email } = await api.accounts.authComplete(modal.state, modal.responseUrl)
    modal.addedEmail = email
    modal.step = 3
    await store.fetchAccounts()
  } catch (e: any) {
    modal.error = e.message || 'Could not connect account. Make sure you pasted the full URL.'
  } finally {
    modal.loading = false
  }
}
</script>
