<template>
  <div class="min-w-0 flex-1 overflow-y-auto">
    <div class="flex max-w-[1100px] flex-col gap-[18px] px-4 pt-5 pb-12 md:px-9 md:pt-7">
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
            <span class="chip shrink-0 gap-1 font-sans text-xs" :title="regionName(account.locale)">{{ regionBadge(account.locale) }}</span>
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
    <DialogContent @interact-outside="keepOpenDuringLogin">
      <DialogHeader>
        <DialogTitle>
          {{ modal.step === 1 ? (modal.reconnect ? 'Reconnect account' : 'Add Audible account') : modal.step === 2 ? 'Log in to Amazon' : modal.reconnect ? 'Reconnected' : 'Account added' }}
        </DialogTitle>
        <DialogDescription v-if="modal.step === 1">
          {{ modal.reconnect
            ? 'Log in again with the same Amazon account. Your library, downloads, tags and ratings are kept.'
            : 'Connect an Audible account to import its library.' }}
        </DialogDescription>
        <DialogDescription v-else-if="modal.step === 2">Open this login page and sign in.</DialogDescription>
      </DialogHeader>

      <template v-if="modal.step === 1">
        <div class="flex flex-col gap-4 py-2">
          <div class="rounded-[10px] bg-paper px-4 py-3 text-sm">
            <p class="mb-2 font-semibold">How it works</p>
            <ol class="list-outside list-decimal space-y-1.5 pl-4 text-ink-soft">
              <li>Libera creates a one-time Amazon login link for your region.</li>
              <li>You sign in on Amazon's own page. Libera never sees your password.</li>
              <li>Amazon then shows a <strong class="text-ink">“Looking for something?”</strong> page. That's expected: its address (URL) contains a one-time code.</li>
              <li>You paste that address here. Libera uses the code to register a device on your account, which shows up as an Audible iPhone app in your Amazon devices.</li>
              <li>The login is stored only on this server. Reconnecting replaces the old device.</li>
            </ol>
          </div>
          <label class="flex flex-col gap-1.5 text-sm font-medium">
            Display name
            <input v-model="modal.name" class="textbox" placeholder="My Audible" />
          </label>
          <label class="flex flex-col gap-1.5 text-sm font-medium">
            Region
            <SelectField v-model="modal.locale" :options="regionOptions" :disabled="modal.reconnect" />
          </label>
          <p v-if="modal.error" class="text-xs text-destructive">{{ modal.error }}</p>
        </div>
        <DialogFooter>
          <button type="button" class="btn-secondary" @click="resetModal">Cancel</button>
          <button type="button" class="btn-primary" :disabled="modal.loading" @click="startAuth">
            {{ modal.loading ? 'Preparing…' : 'Continue' }}
          </button>
        </DialogFooter>
      </template>

      <template v-if="modal.step === 2">
        <div class="flex min-w-0 flex-col gap-4 py-2">
          <div class="flex min-w-0 items-center gap-1 rounded-[10px] border border-line bg-paper py-1 pr-1 pl-3">
            <code class="min-w-0 flex-1 truncate font-mono text-xs" :title="modal.authUrl">{{ modal.authUrl }}</code>
            <button
              type="button"
              class="flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-lg text-ink-soft hover:bg-surface hover:text-ink"
              :aria-label="modal.copied ? 'Copied' : 'Copy the login address'"
              :title="modal.copied ? 'Copied' : 'Copy'"
              @click="copyLoginUrl"
            >
              <CheckIcon v-if="modal.copied" class="size-4 text-ok" />
              <CopyIcon v-else class="size-4" />
            </button>
          </div>
          <a :href="modal.authUrl" target="_blank" rel="noopener noreferrer" class="btn-primary self-start" @click="revealPaste">
            <ExternalLinkIcon class="size-4" />Open login page
          </a>

          <template v-if="modal.revealed">
            <label class="flex flex-col gap-1.5 border-t border-line-faint pt-4 text-sm font-medium">
              <span>
                After signing in you'll land on <strong>“Looking for something?”</strong>.
                Copy that page's whole address and paste it here:
              </span>
              <input
                v-model="modal.responseUrl"
                class="textbox font-mono text-xs"
                :placeholder="`https://www.amazon.${amazonDomain}/ap/maplanding?…`"
              />
            </label>
            <p v-if="modal.error" class="text-xs text-destructive">{{ modal.error }}</p>
          </template>
        </div>
        <DialogFooter>
          <button type="button" class="btn-secondary" @click="resetModal">Cancel</button>
          <button v-if="modal.expired" type="button" class="btn-primary" @click="startAgain">Start again</button>
          <button
            v-else-if="modal.revealed"
            type="button"
            class="btn-primary"
            :disabled="modal.loading || !modal.responseUrl"
            @click="completeAuth"
          >
            {{ modal.loading ? 'Connecting…' : 'Connect' }}
          </button>
        </DialogFooter>
      </template>

      <template v-if="modal.step === 3">
        <div class="flex flex-col items-center gap-3 py-6 text-center">
          <span class="flex size-12 items-center justify-center rounded-full bg-ok-soft text-ok"><CheckIcon class="size-6" /></span>
          <p class="font-semibold">{{ modal.reconnect ? 'Logged in again' : 'Account added' }}</p>
          <p class="font-mono text-xs text-ink-soft">{{ modal.addedEmail }}</p>
          <p v-if="modal.importing" class="flex items-center gap-2 text-sm text-ink-soft">
            <RefreshCwIcon class="size-4 animate-spin" />Importing your library…
          </p>
          <p v-else-if="modal.importError" class="text-sm text-destructive">Couldn't import the library: {{ modal.importError }}</p>
          <p v-else-if="modal.imported !== null" class="text-sm text-ink-soft">
            Found {{ modal.imported }} book{{ modal.imported === 1 ? '' : 's' }}.
          </p>
        </div>
        <DialogFooter>
          <button v-if="modal.importError" type="button" class="btn-secondary" @click="importLibrary">Try again</button>
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
import { computed, reactive, ref, onMounted } from 'vue'
import { CheckIcon, CopyIcon, ExternalLinkIcon, KeyRoundIcon, PlusIcon, RefreshCwIcon, UserRoundIcon } from '@lucide/vue'
import type { Account } from '@/api/client'
import { useAccountsStore } from '@/stores/accounts'
import { flag, regionBadge, regions } from '@/lib/regions'
import { api } from '@/api/client'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { SelectField, type SelectOption } from '@/components/ui/select'

const regionOptions: SelectOption[] = regions.map((r) => ({ value: r.value, label: `${flag(r.value)} ${r.label}` }))

const regionName = (locale: string) => regions.find((r) => r.value === locale)?.label ?? locale.toUpperCase()

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
  state: '', // the server's key for this login (it holds the PKCE verifier)
  authUrl: '', // Amazon's login page for this login
  revealed: false, // the login page was opened or copied: show the paste box
  copied: false,
  expired: false, // the server no longer knows this login: start again
  responseUrl: '',
  addedId: null as number | null,
  addedEmail: '',
  importing: false, // scanning the new login's library
  imported: null as number | null,
  importError: '',
  loading: false,
  error: '',
})

// "amazon.co.uk": the domain the user returns to, for the paste box's hint.
const amazonDomain = computed(() => {
  try {
    return new URL(modal.authUrl).hostname.replace(/^www\.amazon\./, '')
  } catch {
    return 'com'
  }
})

// --- a login in progress survives the tab being reloaded ------------------------------
// Phones often discard a background tab while the user signs in on Amazon; without
// this the dialog, and the state the pasted address must match, would be gone.
const PENDING_LOGIN_KEY = 'libera.pendingLogin'

interface PendingLogin {
  reconnect: boolean
  locale: string
  name: string
  state: string
  authUrl: string
  revealed: boolean
}

function savePendingLogin() {
  const pending: PendingLogin = {
    reconnect: modal.reconnect, locale: modal.locale, name: modal.name,
    state: modal.state, authUrl: modal.authUrl, revealed: modal.revealed,
  }
  try {
    sessionStorage.setItem(PENDING_LOGIN_KEY, JSON.stringify(pending))
  } catch {
    // storage blocked (private mode): the dialog just won't survive a reload
  }
}

function clearPendingLogin() {
  try {
    sessionStorage.removeItem(PENDING_LOGIN_KEY)
  } catch {
    // nothing was saved
  }
}

function restorePendingLogin() {
  let pending: PendingLogin | null = null
  try {
    pending = JSON.parse(sessionStorage.getItem(PENDING_LOGIN_KEY) ?? 'null')
  } catch {
    return
  }
  if (!pending?.state || !pending.authUrl) return
  Object.assign(modal, pending, {
    open: true, step: 2, copied: false, expired: false, responseUrl: '', error: '', loading: false,
  })
}

const editModal = reactive({
  open: false,
  accountId: null as number | null,
  name: '',
  loading: false,
})

onMounted(() => {
  store.fetchAccounts()
  restorePendingLogin()
})

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
  modal.authUrl = ''
  modal.revealed = false
  modal.copied = false
  modal.expired = false
  modal.responseUrl = ''
  modal.error = ''
  modal.loading = false
  modal.addedId = null
  modal.importing = false
  modal.imported = null
  modal.importError = ''
}

function resetModal() {
  modal.open = false
  modal.step = 1
  clearPendingLogin()
}

/** While logging in, only Cancel or ✕ close the dialog: a stray tap outside would lose the login. */
function keepOpenDuringLogin(event: Event) {
  if (modal.step === 2) event.preventDefault()
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
    modal.authUrl = auth_url
    modal.step = 2
    savePendingLogin()
  } catch (e: unknown) {
    modal.error = e instanceof Error ? e.message : String(e)
  } finally {
    modal.loading = false
  }
}

/** The login page was opened or copied: the user will come back with an address to paste. */
function revealPaste() {
  modal.revealed = true
  savePendingLogin()
}

async function copyLoginUrl() {
  try {
    await navigator.clipboard.writeText(modal.authUrl)
    modal.copied = true
    setTimeout(() => (modal.copied = false), 2000)
  } catch {
    modal.error = "Couldn't copy. Use Open login page instead."
  }
  revealPaste()
}

/** Scan the library of the login just completed (new or reconnected). A failure leaves
 *  the account in place: it can be retried here or scanned later. */
async function importLibrary() {
  if (modal.addedId === null) return
  modal.importing = true
  modal.importError = ''
  modal.imported = null
  try {
    const { imported } = await api.accounts.scan(modal.addedId)
    modal.imported = imported
    await store.fetchAccounts()
  } catch (e: unknown) {
    modal.importError = e instanceof Error ? e.message : String(e)
  } finally {
    modal.importing = false
  }
}

/** A fresh login link, keeping the name and region. */
function startAgain() {
  clearPendingLogin()
  modal.step = 1
  modal.expired = false
  modal.revealed = false
  modal.responseUrl = ''
  modal.error = ''
}

async function completeAuth() {
  modal.loading = true
  modal.error = ''
  try {
    const { id, email } = await api.accounts.authComplete(modal.state, modal.responseUrl)
    clearPendingLogin()
    modal.addedId = id
    modal.addedEmail = email
    modal.step = 3
    await store.fetchAccounts()
    importLibrary() // not awaited: the dialog shows its progress, and Done works meanwhile
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : ''
    // The server forgets logins when it restarts (they live in memory).
    if (message.includes('unknown auth state')) {
      modal.expired = true
      modal.error = 'This login link has expired. Start again to get a new one.'
    } else {
      modal.error = message || 'Could not connect the account. Make sure you pasted the whole address.'
    }
  } finally {
    modal.loading = false
  }
}
</script>
