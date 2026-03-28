package domain

import "time"

type ContentType string

const (
	ContentTypeProduct ContentType = "Product"
	ContentTypeEpisode ContentType = "Episode"
	ContentTypeParent  ContentType = "Parent"
)

type LiberatedStatus string

const (
	StatusNotLiberated     LiberatedStatus = "not_liberated"
	StatusLiberated        LiberatedStatus = "liberated"
	StatusError            LiberatedStatus = "error"
	StatusPartialDownload  LiberatedStatus = "partial_download"
)

type OutputFormat string

const (
	FormatM4B OutputFormat = "m4b"
	FormatMP3 OutputFormat = "mp3"
)

type ContributorRole string

const (
	RoleAuthor    ContributorRole = "author"
	RoleNarrator  ContributorRole = "narrator"
	RolePublisher ContributorRole = "publisher"
)

type Book struct {
	ID              int64
	AudibleID       string
	Title           string
	Subtitle        string
	Description     string
	LengthMinutes   int
	ContentType     ContentType
	Locale          string
	IsAbridged      bool
	IsSpatial       bool
	DatePublished   *time.Time
	Language        string
	CoverURL        string
	Authors         []string
	Narrators       []string
	Publisher       string
	Series          []SeriesEntry
	Categories      []string
	AudibleRating   float32
	AudibleRatingCount int
}

type SeriesEntry struct {
	SeriesID   string
	SeriesName string
	BookIndex  string
}

type LibraryBook struct {
	BookID          int64
	Book            *Book
	AccountID       int64
	DateAdded       time.Time
	IsDeleted       bool
	IsAudiblePlus   bool
	LiberationStatus LiberatedStatus
	Tags            string
	UserRating      float32
	IsFinished      bool
	LastDownloaded  *time.Time
	LastFormat      *OutputFormat
}
