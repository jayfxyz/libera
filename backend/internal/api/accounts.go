package api

import (
	"encoding/json"
	"net/http"
	"strconv"
	"sync"

	"github.com/go-chi/chi/v5"
	"github.com/web-libation/backend/internal/audible"
)

// pendingAuth maps OAuth state tokens to account metadata for the in-flight login.
var (
	pendingAuthMu sync.Mutex
	pendingAuth   = map[string]pendingAuthEntry{}
)

type pendingAuthEntry struct {
	Locale string
	Name   string
}

func (h *handlers) listAccounts(w http.ResponseWriter, r *http.Request) {
	rows, err := h.db.QueryContext(r.Context(),
		`SELECT id, account_name, email, locale, library_scan_enabled, last_scanned_at FROM accounts ORDER BY id`)
	if err != nil {
		httpError(w, err, http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	type account struct {
		ID                 int64   `json:"id"`
		AccountName        string  `json:"account_name"`
		Email              string  `json:"email"`
		Locale             string  `json:"locale"`
		LibraryScanEnabled bool    `json:"library_scan_enabled"`
		LastScannedAt      *string `json:"last_scanned_at"`
	}

	accounts := []account{}
	for rows.Next() {
		var a account
		if err := rows.Scan(&a.ID, &a.AccountName, &a.Email, &a.Locale, &a.LibraryScanEnabled, &a.LastScannedAt); err != nil {
			httpError(w, err, http.StatusInternalServerError)
			return
		}
		accounts = append(accounts, a)
	}

	writeJSON(w, accounts)
}

func (h *handlers) updateAccount(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(chi.URLParam(r, "id"), 10, 64)
	if err != nil {
		httpError(w, err, http.StatusBadRequest)
		return
	}
	var patch struct {
		AccountName *string `json:"account_name"`
	}
	if err := json.NewDecoder(r.Body).Decode(&patch); err != nil {
		httpError(w, err, http.StatusBadRequest)
		return
	}
	if patch.AccountName != nil {
		if _, err := h.db.ExecContext(r.Context(),
			`UPDATE accounts SET account_name = ? WHERE id = ?`, *patch.AccountName, id); err != nil {
			httpError(w, err, http.StatusInternalServerError)
			return
		}
	}
	w.WriteHeader(http.StatusNoContent)
}

func (h *handlers) createAccount(w http.ResponseWriter, r *http.Request) {
	http.Error(w, "use POST /api/accounts/auth/start", http.StatusMethodNotAllowed)
}

func (h *handlers) deleteAccount(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(chi.URLParam(r, "id"), 10, 64)
	if err != nil {
		httpError(w, err, http.StatusBadRequest)
		return
	}
	if _, err := h.db.ExecContext(r.Context(), `DELETE FROM accounts WHERE id = ?`, id); err != nil {
		httpError(w, err, http.StatusInternalServerError)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (h *handlers) authStart(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Locale string `json:"locale"`
		Name   string `json:"name"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		httpError(w, err, http.StatusBadRequest)
		return
	}
	if req.Locale == "" {
		req.Locale = "us"
	}

	result, err := h.audible.Register(r.Context(), audible.RegisterRequest{
		Locale: req.Locale,
	})
	if err != nil {
		httpError(w, err, http.StatusBadGateway)
		return
	}

	pendingAuthMu.Lock()
	pendingAuth[result.State] = pendingAuthEntry{Locale: req.Locale, Name: req.Name}
	pendingAuthMu.Unlock()

	writeJSON(w, map[string]string{"auth_url": result.AuthURL, "state": result.State})
}

// authComplete is called by Vue after the user has logged in at Amazon and
// copied the maplanding URL from their browser address bar.
func (h *handlers) authComplete(w http.ResponseWriter, r *http.Request) {
	var req struct {
		State       string `json:"state"`
		ResponseURL string `json:"response_url"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		httpError(w, err, http.StatusBadRequest)
		return
	}
	if req.State == "" || req.ResponseURL == "" {
		http.Error(w, "state and response_url are required", http.StatusBadRequest)
		return
	}

	pendingAuthMu.Lock()
	entry, ok := pendingAuth[req.State]
	if ok {
		delete(pendingAuth, req.State)
	}
	pendingAuthMu.Unlock()

	if !ok {
		http.Error(w, "unknown auth state — try starting login again", http.StatusBadRequest)
		return
	}

	result, err := h.audible.Callback(r.Context(), audible.CallbackRequest{
		State:       req.State,
		ResponseURL: req.ResponseURL,
	})
	if err != nil {
		httpError(w, err, http.StatusBadGateway)
		return
	}

	_, err = h.db.ExecContext(r.Context(),
		`INSERT INTO accounts (account_name, email, locale, audible_account_id) VALUES (?, ?, ?, ?)
		 ON CONFLICT(email) DO UPDATE SET
		 	account_name = excluded.account_name,
		 	audible_account_id = excluded.audible_account_id`,
		entry.Name, result.Email, entry.Locale, result.AccountID)
	if err != nil {
		httpError(w, err, http.StatusInternalServerError)
		return
	}

	writeJSON(w, map[string]string{"email": result.Email})
}

func (h *handlers) scanLibrary(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(chi.URLParam(r, "id"), 10, 64)
	if err != nil {
		httpError(w, err, http.StatusBadRequest)
		return
	}

	var audibleAccountID string
	if err := h.db.QueryRowContext(r.Context(),
		`SELECT audible_account_id FROM accounts WHERE id = ?`, id).Scan(&audibleAccountID); err != nil {
		httpError(w, err, http.StatusNotFound)
		return
	}

	books, err := h.audible.GetLibrary(r.Context(), audibleAccountID)
	if err != nil {
		httpError(w, err, http.StatusBadGateway)
		return
	}

	imported, err := importLibrary(r.Context(), h.db, id, books)
	if err != nil {
		httpError(w, err, http.StatusInternalServerError)
		return
	}

	h.db.ExecContext(r.Context(), `UPDATE accounts SET last_scanned_at = CURRENT_TIMESTAMP WHERE id = ?`, id)

	writeJSON(w, map[string]any{"imported": imported})
}
