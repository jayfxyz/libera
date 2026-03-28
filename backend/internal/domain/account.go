package domain

type Account struct {
	ID              int64
	AccountName     string
	Email           string
	Locale          string
	LibraryScanEnabled bool
}
