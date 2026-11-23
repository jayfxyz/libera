<template>
  <div class="min-w-0 flex-1 overflow-y-auto">
    <div class="flex max-w-[760px] flex-col gap-5 px-4 pt-5 pb-12 md:px-9 md:pt-7">
      <header class="flex items-center justify-between gap-3">
        <div class="min-w-0">
          <h1 class="page-title">Accounts</h1>
          <p class="mt-1 hidden text-sm text-ink-soft sm:block">Your Audible accounts. Each one's library is scanned into the app.</p>
        </div>
        <button v-if="store.accounts.length" type="button" class="btn-primary h-10 px-3.5" @click="openAddModal()">
          <PlusIcon class="size-4" /><span>Add<span class="hidden sm:inline"> account</span></span>
        </button>
      </header>

      <section v-if="store.accounts.length === 0 && !store.loading" class="card flex flex-col items-center px-6 py-10 text-center">
        <span class="mb-4 flex size-12 items-center justify-center rounded-xl border border-line bg-paper text-ink-soft">
          <LibraryBigIcon class="size-6" aria-hidden="true" />
        </span>
        <h2 class="mb-1.5 text-base font-semibold">No Audible accounts yet</h2>
        <p class="mb-6 max-w-[260px] text-sm leading-relaxed text-ink-soft">Connect an Audible account to scan its library into Libera.</p>
        <button type="button" class="btn-primary" @click="openAddModal()"><PlusIcon class="size-4" />Add account</button>
      </section>

      <template v-else>
        <ul class="flex flex-col gap-2.5">
          <li
            v-for="account in store.accounts"
            :key="account.id"
            class="card flex min-h-[72px] items-center gap-3 px-4 py-3.5"
          >
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2.5">
                <span class="size-2 shrink-0 rounded-full" :class="dotFor(account)" :title="scans[account.id]?.failed ? 'Last scan failed' : 'Connected'" />
                <h2 class="truncate text-[15px] font-semibold leading-snug">{{ account.account_name || account.email }}</h2>
              </div>
              <p class="mt-0.5 truncate pl-[18px] text-[13px] leading-snug text-ink-soft">
                <span :title="regionName(account.locale)">{{ regionBadge(account.locale) }}</span>
                <span class="mx-1 text-ink-faint">·</span>
                <span :class="scans[account.id]?.failed ? 'font-medium text-warn-ink' : scans[account.id]?.scanning ? 'text-brand' : ''">{{ metaFor(account) }}</span>
              </p>
            </div>

            <button
              type="button"
              class="btn-secondary size-9 shrink-0 px-0"
              :disabled="scans[account.id]?.scanning"
              :aria-label="`Scan library for ${accountLabel(account)}`"
              title="Scan library"
              @click="scan(account)"
            >
              <RefreshCwIcon class="size-4" :class="scans[account.id]?.scanning ? 'animate-spin text-brand' : ''" />
            </button>

            <DropdownMenu>
              <DropdownMenuTrigger as-child>
                <button
                  type="button"
                  class="flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-lg text-ink-soft hover:bg-paper hover:text-ink data-[state=open]:bg-paper data-[state=open]:text-ink"
                  :aria-label="`More options for ${accountLabel(account)}`"
                >
                  <EllipsisVerticalIcon class="size-4" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" class="w-64 p-0 py-1.5">
                <div class="border-b border-line-faint px-3.5 pt-1 pb-2.5">
                  <p class="mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-soft">Account ID</p>
                  <div class="flex items-center justify-between gap-2">
                    <span class="truncate font-mono text-[11px] select-all" :title="account.email">{{ account.email }}</span>
                    <button
                      type="button"
                      class="inline-flex shrink-0 cursor-pointer items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium"
                      :class="copiedId === account.id ? 'bg-ok-soft text-ok-ink' : 'bg-chip-soft text-ink hover:bg-chip'"
                      @click="copyAccountId(account)"
                    >
                      <CheckIcon v-if="copiedId === account.id" class="size-3" /><CopyIcon v-else class="size-3" />
                      {{ copiedId === account.id ? 'Copied' : 'Copy' }}
                    </button>
                  </div>
                </div>
                <div class="px-1.5 py-1">
                  <DropdownMenuItem :disabled="scans[account.id]?.scanning" @select="scan(account)">
                    <RefreshCwIcon class="size-4 text-ink-soft" />Scan library
                  </DropdownMenuItem>
                  <DropdownMenuItem @select="openAddModal(account)">
                    <KeyRoundIcon class="size-4 text-ink-soft" />Reconnect
                  </DropdownMenuItem>
                  <DropdownMenuItem @select="openEditModal(account)">
                    <PencilIcon class="size-4 text-ink-soft" />Rename
                  </DropdownMenuItem>
                </div>
                <div class="border-t border-line-faint px-1.5 pt-1">
                  <DropdownMenuItem class="text-destructive data-highlighted:bg-warn-soft" @select="removeModal.account = account">
                    <Trash2Icon class="size-4" />Remove
                  </DropdownMenuItem>
                </div>
              </DropdownMenuContent>
            </DropdownMenu>
          </li>
        </ul>

        <div class="-mt-2 flex items-center justify-between px-1">
          <span class="text-xs text-ink-faint">{{ store.accounts.length }} account{{ store.accounts.length === 1 ? '' : 's' }}</span>
          <button
            type="button"
            class="-mr-2 inline-flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-ink-soft hover:bg-surface hover:text-ink disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="scanningAll"
            @click="scanAll"
          >
            <RefreshCwIcon class="size-3.5" :class="scanningAll ? 'animate-spin' : ''" />{{ scanningAll ? 'Scanning…' : 'Scan all' }}
          </button>
        </div>
      </template>
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
                Copy that page's whole address (URL) and paste it here:
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
import {
  CheckIcon, CopyIcon, EllipsisVerticalIcon, ExternalLinkIcon, KeyRoundIcon, LibraryBigIcon, PencilIcon, PlusIcon,
  RefreshCwIcon, Trash2Icon,
} from '@lucide/vue'
import type { Account } from '@/api/client'
import { useAccountsStore } from '@/stores/accounts'
import { flag, regionBadge, regions } from '@/lib/regions'
import { api } from '@/api/client'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
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

const accountLabel = (account: Account) => account.account_name || account.email

// --- scanning: each row shows its own progress and result ---------------------------
interface ScanState {
  scanning: boolean
  message: string // "Found 54 books" for a few seconds, or why the scan failed
  failed: boolean
}
const scans = reactive<Record<number, ScanState>>({})
const SCAN_RESULT_SHOWN_MS = 4000

async function scan(account: Account) {
  const state: ScanState = { scanning: true, message: '', failed: false }
  scans[account.id] = state
  try {
    const { imported } = await api.accounts.scan(account.id)
    state.message = `Found ${imported} book${imported === 1 ? '' : 's'}`
    await store.fetchAccounts()
    setTimeout(() => clearScanMessage(account.id, state), SCAN_RESULT_SHOWN_MS)
  } catch (e: unknown) {
    state.failed = true
    state.message = `Couldn't scan: ${e instanceof Error ? e.message : String(e)}`
  } finally {
    state.scanning = false
  }
}

/** Back to "Scanned … ago", unless another scan has started since. */
function clearScanMessage(accountId: number, state: ScanState) {
  if (scans[accountId] === state) delete scans[accountId]
}

const scanningAll = ref(false)
async function scanAll() {
  scanningAll.value = true
  try {
    for (const account of store.accounts) await scan(account)
  } finally {
    scanningAll.value = false
  }
}

function metaFor(account: Account) {
  const state = scans[account.id]
  if (state?.scanning) return 'Scanning…'
  if (state?.message) return state.message
  return account.last_scanned_at ? `Scanned ${formatRelative(account.last_scanned_at)}` : 'Never scanned'
}

function dotFor(account: Account) {
  const state = scans[account.id]
  if (state?.scanning) return 'bg-brand animate-pulse'
  if (state?.failed) return 'bg-warn'
  return 'bg-ok'
}

const copiedId = ref<number | null>(null)
async function copyAccountId(account: Account) {
  try {
    await navigator.clipboard.writeText(account.email)
    copiedId.value = account.id
    setTimeout(() => { if (copiedId.value === account.id) copiedId.value = null }, 1500)
  } catch {
    // Clipboard blocked: the ID is selectable instead.
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
