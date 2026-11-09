<template>
  <div class="min-w-0 flex-1 overflow-y-auto">
    <div class="mx-auto flex max-w-[1100px] flex-col gap-[18px] px-4 pt-5 pb-12 md:px-9 md:pt-7">
      <header class="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 class="page-title">Accounts</h1>
          <p class="mt-1 text-sm text-ink-soft">Your Audible accounts. Each one's library is scanned into the app.</p>
        </div>
        <button type="button" class="btn-primary" @click="openAddModal()">
          <PlusIcon class="size-4" />Add account
        </button>
      </header>

      <div v-if="store.accounts.length === 0 && !store.loading" class="card flex flex-col items-center gap-2 px-6 py-12 text-center">
        <UserRoundIcon class="size-8 text-ink-faint" aria-hidden="true" />
        <p class="font-semibold">No accounts yet</p>
        <p class="text-sm text-ink-soft">Add your Audible account to import your library.</p>
        <button type="button" class="btn-primary mt-2" @click="openAddModal()">Add account</button>
      </div>

      <div v-else class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        <article v-for="account in store.accounts" :key="account.id" class="card flex flex-col gap-4 p-5">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <h2 class="truncate text-base font-semibold">{{ account.account_name || account.email }}</h2>
              <p class="truncate font-mono text-xs text-ink-soft" :title="account.email">{{ account.email }}</p>
            </div>
            <span class="chip shrink-0">{{ account.locale.toUpperCase() }}</span>
          </div>
          <dl class="flex justify-between text-sm">
            <dt class="text-ink-soft">Last scanned</dt>
            <dd class="font-medium">{{ account.last_scanned_at ? formatRelative(account.last_scanned_at) : 'Never' }}</dd>
          </dl>
          <div class="flex flex-wrap gap-2">
            <button type="button" class="btn-secondary flex-1" :disabled="scanningId === account.id" @click="scan(account)">
              <RefreshCwIcon class="size-4" :class="scanningId === account.id ? 'animate-spin' : ''" />
              {{ scanningId === account.id ? 'Scanning…' : 'Scan library' }}
            </button>
            <button type="button" class="btn-secondary flex-1" title="Log in again, e.g. if Audible refuses downloads" @click="openAddModal(account)">
              <KeyRoundIcon class="size-4" />Reconnect
            </button>
          </div>
          <p v-if="scanResult[account.id]" class="-mt-2 text-xs text-ink-soft">{{ scanResult[account.id] }}</p>
          <div class="flex gap-2 border-t border-line-faint pt-3">
            <button type="button" class="btn flex-1 h-10 text-ink-soft hover:bg-paper" @click="openEditModal(account)">Rename</button>
            <button type="button" class="btn flex-1 h-10 text-destructive hover:bg-warn-soft" @click="removeModal.account = account">Remove</button>
          </div>
        </article>
      </div>
    </div>
  </div>

  <!-- Add / reconnect account -->
  <Dialog :open="modal.open" @update:open="val => { if (!val) resetModal() }">
    <DialogContent>
      <DialogHeader>
        <DialogTitle>
          {{ modal.step === 1 ? (modal.reconnect ? 'Reconnect account' : 'Add Audible account') : modal.step === 2 ? 'Complete login' : modal.reconnect ? 'Reconnected' : 'Account added' }}
        </DialogTitle>
        <DialogDescription v-if="modal.step === 1">
          {{ modal.reconnect
            ? 'Log in again with the same Amazon account. Your library, downloads, tags and ratings are kept.'
            : 'Connect an Audible account to import its library.' }}
        </DialogDescription>
        <DialogDescription v-else-if="modal.step === 2">Paste the address Amazon sends you to after logging in.</DialogDescription>
      </DialogHeader>

      <template v-if="modal.step === 1">
        <div class="flex flex-col gap-4 py-2">
          <label class="flex flex-col gap-1.5 text-sm font-medium">
            Display name
            <input v-model="modal.name" class="textbox" placeholder="My Audible" />
          </label>
          <label class="flex flex-col gap-1.5 text-sm font-medium">
            Region
            <select v-model="modal.locale" class="textbox cursor-pointer" :disabled="modal.reconnect">
              <option v-for="r in regions" :key="r.value" :value="r.value">{{ r.label }}</option>
            </select>
          </label>
          <p v-if="modal.error" class="text-xs text-destructive">{{ modal.error }}</p>
        </div>
        <DialogFooter>
          <button type="button" class="btn-secondary" @click="resetModal">Cancel</button>
          <button type="button" class="btn-primary" :disabled="modal.loading" @click="startAuth">
            {{ modal.loading ? 'Opening…' : 'Log in with Audible' }}
          </button>
        </DialogFooter>
      </template>

      <template v-if="modal.step === 2">
        <div class="flex flex-col gap-4 py-2">
          <ol class="list-inside list-decimal space-y-2 text-sm text-ink-soft">
            <li>An Amazon login page has opened in a new tab.</li>
            <li>Sign in with your Audible / Amazon account.</li>
            <li>You'll end up on a <strong class="text-ink">“Looking for something?”</strong> page. That's expected.</li>
            <li>Copy the <strong class="text-ink">whole address</strong> from that tab's address bar and paste it below.</li>
          </ol>
          <label class="flex flex-col gap-1.5 text-sm font-medium">
            Address
            <input
              v-model="modal.responseUrl"
              class="textbox font-mono text-xs"
              placeholder="https://www.amazon.co.uk/ap/maplanding?openid.oa2.authorization_code=…"
            />
          </label>
          <p v-if="modal.error" class="text-xs text-destructive">{{ modal.error }}</p>
          <p v-else class="text-xs text-ink-soft">It starts with https://www.amazon.</p>
        </div>
        <DialogFooter>
          <button type="button" class="btn-secondary" @click="resetModal">Cancel</button>
          <button type="button" class="btn-primary" :disabled="modal.loading || !modal.responseUrl" @click="completeAuth">
            {{ modal.loading ? 'Connecting…' : 'Connect' }}
          </button>
        </DialogFooter>
      </template>

      <template v-if="modal.step === 3">
        <div class="flex flex-col items-center gap-3 py-6 text-center">
          <span class="flex size-12 items-center justify-center rounded-full bg-ok-soft text-ok"><CheckIcon class="size-6" /></span>
          <p class="font-semibold">{{ modal.reconnect ? 'Logged in again' : 'Account added' }}</p>
          <p class="font-mono text-xs text-ink-soft">{{ modal.addedEmail }}</p>
          <p class="text-sm text-ink-soft">{{ modal.reconnect ? 'Downloads use the new login from now on.' : 'Scan its library from the Library page or here.' }}</p>
        </div>
        <DialogFooter>
          <button type="button" class="btn-primary" @click="resetModal">Done</button>
        </DialogFooter>
      </template>
    </DialogContent>
  </Dialog>

  <!-- Rename -->
  <Dialog :open="editModal.open" @update:open="val => { if (!val) editModal.open = false }">
    <DialogContent>
      <DialogHeader>
        <DialogTitle>Rename account</DialogTitle>
        <DialogDescription>Only changes how it's shown here.</DialogDescription>
      </DialogHeader>
      <label class="flex flex-col gap-1.5 py-2 text-sm font-medium">
        Display name
        <input v-model="editModal.name" class="textbox" placeholder="My Audible" @keydown.enter="saveEdit" />
      </label>
      <DialogFooter>
        <button type="button" class="btn-secondary" @click="editModal.open = false">Cancel</button>
        <button type="button" class="btn-primary" :disabled="editModal.loading" @click="saveEdit">
          {{ editModal.loading ? 'Saving…' : 'Save' }}
        </button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <!-- Remove: also removes that account's books from the library. -->
  <Dialog :open="!!removeModal.account" @update:open="val => { if (!val) removeModal.account = null }">
    <DialogContent>
      <DialogHeader>
        <DialogTitle>Remove {{ removeModal.account?.account_name || removeModal.account?.email }}?</DialogTitle>
        <DialogDescription>
          Its books disappear from the library here, along with their download status, tags and ratings.
          Downloaded audiobook files stay on disk. To fix a login problem, use Reconnect instead.
        </DialogDescription>
      </DialogHeader>
      <DialogFooter>
        <button type="button" class="btn-secondary" @click="removeModal.account = null">Cancel</button>
        <button type="button" class="btn bg-destructive font-semibold text-white" @click="confirmRemove">Remove account</button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue'
import { CheckIcon, KeyRoundIcon, PlusIcon, RefreshCwIcon, UserRoundIcon } from '@lucide/vue'
import type { Account } from '@/api/client'
import { useAccountsStore } from '@/stores/accounts'
import { api } from '@/api/client'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'

const regions = [
  { value: 'us', label: 'United States' }, { value: 'uk', label: 'United Kingdom' },
  { value: 'ca', label: 'Canada' }, { value: 'de', label: 'Germany' }, { value: 'fr', label: 'France' },
  { value: 'au', label: 'Australia' }, { value: 'jp', label: 'Japan' }, { value: 'in', label: 'India' },
  { value: 'es', label: 'Spain' },
]

const store = useAccountsStore()

function formatRelative(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diffMs / 60000)
  const hours = Math.floor(mins / 60)
  const days = Math.floor(hours / 24)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} minute${mins !== 1 ? 's' : ''} ago`
  if (hours < 24) return `${hours} hour${hours !== 1 ? 's' : ''} ago`
  return `${days} day${days !== 1 ? 's' : ''} ago`
}

const modal = reactive({
  open: false,
  reconnect: false,
  step: 1,
  locale: 'us',
  name: '',
  state: '',
  responseUrl: '',
  addedEmail: '',
  loading: false,
  error: '',
})

const editModal = reactive({
  open: false,
  accountId: null as number | null,
  name: '',
  loading: false,
})

onMounted(() => store.fetchAccounts())

const scanningId = ref<number | null>(null)
const scanResult = reactive<Record<number, string>>({})
async function scan(account: Account) {
  scanningId.value = account.id
  scanResult[account.id] = ''
  try {
    const { imported } = await api.accounts.scan(account.id)
    scanResult[account.id] = `Found ${imported} book${imported === 1 ? '' : 's'}.`
    await store.fetchAccounts()
  } catch (e: any) {
    scanResult[account.id] = `Scan failed: ${e.message}`
  } finally {
    scanningId.value = null
  }
}

const removeModal = reactive({ account: null as Account | null })
async function confirmRemove() {
  if (!removeModal.account) return
  await store.deleteAccount(removeModal.account.id)
  removeModal.account = null
}

// With an account: log in again for it (same region and name; the server updates it in place).
function openAddModal(account?: Account) {
  modal.open = true
  modal.step = 1
  modal.reconnect = !!account
  modal.locale = account?.locale ?? 'us'
  modal.name = account?.account_name ?? ''
  modal.state = ''
  modal.responseUrl = ''
  modal.error = ''
  modal.loading = false
}

function resetModal() {
  modal.open = false
  modal.step = 1
}

function openEditModal(account: Account) {
  editModal.accountId = account.id
  editModal.name = account.account_name
  editModal.loading = false
  editModal.open = true
}

async function saveEdit() {
  if (!editModal.accountId) return
  const name = editModal.name.trim()
  if (!name) return
  editModal.loading = true
  try {
    await store.updateAccount(editModal.accountId, { account_name: name })
    editModal.open = false
  } finally {
    editModal.loading = false
  }
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
