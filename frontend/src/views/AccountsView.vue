<template>
  <div class="flex-1 flex flex-col overflow-hidden">
    <!-- Header -->
    <div class="border-b p-4 md:p-6 shrink-0">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="text-2xl font-semibold">Audible Accounts</h2>
          <p class="text-sm text-muted-foreground">Manage your Audible accounts and sync libraries</p>
        </div>
        <Button @click="openAddModal">
          <svg xmlns="http://www.w3.org/2000/svg" class="mr-2 h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          Add Account
        </Button>
      </div>
    </div>

    <!-- Account list -->
    <div class="flex-1 overflow-y-auto">
      <div class="p-4 md:p-6">
        <div v-if="store.accounts.length === 0 && !store.loading" class="flex flex-col items-center justify-center py-12 text-center">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-12 w-12 text-muted-foreground mb-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
          </svg>
          <h3 class="font-semibold mb-2">No accounts added</h3>
          <p class="text-sm text-muted-foreground mb-4">Add your first Audible account to get started</p>
          <Button @click="openAddModal">
            <svg xmlns="http://www.w3.org/2000/svg" class="mr-2 h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            Add Account
          </Button>
        </div>

        <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <Card v-for="account in store.accounts" :key="account.id" class="p-4 md:p-6">
            <div class="space-y-4">
              <!-- Name + locale badge -->
              <div class="flex items-start justify-between">
                <div class="min-w-0">
                  <h3 class="font-semibold truncate">{{ account.account_name || account.email }}</h3>
                  <p class="text-sm text-muted-foreground truncate">{{ account.email }}</p>
                </div>
                <Badge variant="outline" class="gap-1 shrink-0 ml-2">
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
                  </svg>
                  {{ account.locale.toUpperCase() }}
                </Badge>
              </div>

              <!-- Metadata rows -->
              <div class="space-y-1.5 text-sm">
                <div class="flex justify-between">
                  <span class="text-muted-foreground">Last scanned:</span>
                  <span class="font-medium text-xs">
                    {{ account.last_scanned_at ? formatRelative(account.last_scanned_at) : 'Never' }}
                  </span>
                </div>
                <div class="flex justify-between items-center">
                  <span class="text-muted-foreground">Status:</span>
                  <Badge variant="secondary" class="text-xs gap-1">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-2.5 w-2.5 text-green-500" viewBox="0 0 24 24" fill="currentColor">
                      <circle cx="12" cy="12" r="10"/>
                    </svg>
                    Connected
                  </Badge>
                </div>
              </div>

              <!-- Scan button -->
              <Button variant="outline" size="sm" class="w-full" @click="store.scanLibrary(account.id)">
                <svg xmlns="http://www.w3.org/2000/svg" class="mr-2 h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
                  <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                </svg>
                Scan Library
              </Button>

              <!-- Edit + Delete side-by-side -->
              <div class="flex gap-2">
                <Button variant="ghost" size="sm" class="flex-1" @click="openEditModal(account)">
                  <svg xmlns="http://www.w3.org/2000/svg" class="mr-2 h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                    <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" />
                  </svg>
                  Edit
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  class="flex-1 text-destructive hover:text-destructive"
                  @click="store.deleteAccount(account.id)"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" class="mr-2 h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
                  </svg>
                  Delete
                </Button>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  </div>

  <!-- Add Account Dialog -->
  <Dialog :open="modal.open" @update:open="val => { if (!val) resetModal() }">
    <DialogContent>
      <DialogHeader>
        <DialogTitle>
          {{ modal.step === 1 ? 'Add Audible Account' : modal.step === 2 ? 'Complete Login' : 'Account Added' }}
        </DialogTitle>
        <DialogDescription>
          {{ modal.step === 1 ? 'Connect a new Audible account to import your library' : modal.step === 2 ? 'Paste the redirect URL to complete authentication' : '' }}
        </DialogDescription>
      </DialogHeader>

      <!-- Step 1 -->
      <template v-if="modal.step === 1">
        <div class="space-y-4 py-2">
          <div class="space-y-2">
            <Label>Display Name</Label>
            <Input v-model="modal.name" placeholder="My Audible" />
          </div>
          <div class="space-y-2">
            <Label>Region</Label>
            <Select v-model="modal.locale">
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="us">🇺🇸 United States</SelectItem>
                <SelectItem value="uk">🇬🇧 United Kingdom</SelectItem>
                <SelectItem value="ca">🇨🇦 Canada</SelectItem>
                <SelectItem value="de">🇩🇪 Germany</SelectItem>
                <SelectItem value="fr">🇫🇷 France</SelectItem>
                <SelectItem value="au">🇦🇺 Australia</SelectItem>
                <SelectItem value="jp">🇯🇵 Japan</SelectItem>
                <SelectItem value="in">🇮🇳 India</SelectItem>
                <SelectItem value="es">🇪🇸 Spain</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="resetModal">Cancel</Button>
          <Button :disabled="modal.loading" @click="startAuth">
            {{ modal.loading ? 'Opening…' : 'Login with Audible' }}
          </Button>
        </DialogFooter>
      </template>

      <!-- Step 2 -->
      <template v-if="modal.step === 2">
        <div class="py-2 space-y-4">
          <ol class="text-sm text-muted-foreground space-y-2 list-decimal list-inside">
            <li>An Amazon login page has opened in a new tab.</li>
            <li>Sign in with your Audible / Amazon account.</li>
            <li>After login you'll see a <strong class="text-foreground">"Looking for Something?"</strong> error page — that's expected.</li>
            <li>Copy the <strong class="text-foreground">full URL</strong> from your browser's address bar and paste it below.</li>
          </ol>
          <div class="space-y-2">
            <Label>Response URL</Label>
            <Input
              v-model="modal.responseUrl"
              class="font-mono text-xs"
              placeholder="https://www.amazon.co.uk/ap/maplanding?openid.oa2.authorization_code=..."
            />
            <p v-if="modal.error" class="text-xs text-destructive">{{ modal.error }}</p>
            <p v-else class="text-xs text-muted-foreground">The URL should start with https://www.amazon.</p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="resetModal">Cancel</Button>
          <Button :disabled="modal.loading || !modal.responseUrl" @click="completeAuth">
            {{ modal.loading ? 'Connecting…' : 'Connect Account' }}
          </Button>
        </DialogFooter>
      </template>

      <!-- Step 3 -->
      <template v-if="modal.step === 3">
        <div class="py-6 text-center space-y-3">
          <div class="w-12 h-12 rounded-full bg-green-100 flex items-center justify-center mx-auto">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-green-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
          </div>
          <div>
            <h3 class="font-semibold">Account Added</h3>
            <p class="text-sm text-muted-foreground mt-1">{{ modal.addedEmail }}</p>
          </div>
        </div>
        <DialogFooter>
          <Button @click="resetModal">Done</Button>
        </DialogFooter>
      </template>
    </DialogContent>
  </Dialog>

  <!-- Edit Account Dialog -->
  <Dialog :open="editModal.open" @update:open="val => { if (!val) editModal.open = false }">
    <DialogContent>
      <DialogHeader>
        <DialogTitle>Edit Account</DialogTitle>
        <DialogDescription>Update the display name for this account</DialogDescription>
      </DialogHeader>
      <div class="space-y-4 py-2">
        <div class="space-y-2">
          <Label>Display Name</Label>
          <Input v-model="editModal.name" placeholder="My Audible" @keydown.enter="saveEdit" />
        </div>
      </div>
      <DialogFooter>
        <Button variant="outline" @click="editModal.open = false">Cancel</Button>
        <Button :disabled="editModal.loading" @click="saveEdit">
          {{ editModal.loading ? 'Saving…' : 'Save Changes' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>

<script setup lang="ts">
import { reactive, onMounted } from 'vue'
import type { Account } from '@/api/client'
import { useAccountsStore } from '@/stores/accounts'
import { api } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'

const store = useAccountsStore()

function formatRelative(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diffMs / 60000)
  const hours = Math.floor(mins / 60)
  const days = Math.floor(hours / 24)
  if (mins < 60) return `${mins} minute${mins !== 1 ? 's' : ''} ago`
  if (hours < 24) return `${hours} hour${hours !== 1 ? 's' : ''} ago`
  return `${days} day${days !== 1 ? 's' : ''} ago`
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

const editModal = reactive({
  open: false,
  accountId: null as number | null,
  name: '',
  loading: false,
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
