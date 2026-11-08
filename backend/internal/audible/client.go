package audible

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"

	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

// Client calls the Python audible-svc over HTTP (internal only).
type Client struct {
	baseURL    string
	httpClient *http.Client
}

type ClientOption func(*Client)

// WithTracedTransport wraps the HTTP transport with OTel instrumentation so
// outgoing requests to audible-svc carry W3C traceparent headers.
func WithTracedTransport() ClientOption {
	return func(c *Client) {
		c.httpClient.Transport = otelhttp.NewTransport(http.DefaultTransport)
	}
}

func NewClient(baseURL string, opts ...ClientOption) *Client {
	c := &Client{
		baseURL: baseURL,
		httpClient: &http.Client{
			Timeout: 60 * time.Second,
		},
	}
	for _, o := range opts {
		o(c)
	}
	return c
}

// RegisterRequest initiates device registration and returns the Audible login URL.
type RegisterRequest struct {
	Locale string `json:"locale"`
}

type RegisterResponse struct {
	AuthURL string `json:"auth_url"`
	State   string `json:"state"`
}

func (c *Client) Register(ctx context.Context, req RegisterRequest) (*RegisterResponse, error) {
	var resp RegisterResponse
	if err := c.post(ctx, "/auth/register", req, &resp); err != nil {
		return nil, err
	}
	return &resp, nil
}

// CallbackRequest completes the OAuth flow.
// ResponseURL is the full Amazon redirect URL containing openid.oa2.authorization_code.
type CallbackRequest struct {
	State       string `json:"state"`
	ResponseURL string `json:"response_url"`
}

type CallbackResponse struct {
	AccountID       string `json:"account_id"`
	Email           string `json:"email"`
	ActivationBytes string `json:"activation_bytes"`
}

func (c *Client) Callback(ctx context.Context, req CallbackRequest) (*CallbackResponse, error) {
	var resp CallbackResponse
	if err := c.post(ctx, "/auth/callback", req, &resp); err != nil {
		return nil, err
	}
	return &resp, nil
}

// BookDTO is a minimal book representation from the Audible library scan.
type BookDTO struct {
	AudibleID       string    `json:"asin"`
	Title           string    `json:"title"`
	Subtitle        string    `json:"subtitle"`
	Description     string    `json:"description"`
	LengthMinutes   int       `json:"runtime_length_min"`
	Authors         []string  `json:"authors"`
	Narrators       []string  `json:"narrators"`
	Publisher       string    `json:"publisher_name"`
	CoverURL        string    `json:"cover_url"`
	Language        string    `json:"language"`
	DatePublished   string    `json:"release_date"`
	Series          []SeriesDTO `json:"series"`
	Categories      []string  `json:"categories"`
	AudibleRating   float32   `json:"rating"`
	IsAudiblePlus   bool      `json:"is_plus_catalog_item"`
	DateAdded       string    `json:"date_added"`
}

type SeriesDTO struct {
	AudibleID string `json:"asin"`
	Title     string `json:"title"`
	Sequence  string `json:"sequence"`
}

type DownloadInfoResponse struct {
	DownloadURL     string `json:"download_url"`
	Codec           string `json:"codec"`
	Format          string `json:"format"`           // "aax" or "aaxc"
	ActivationBytes string `json:"activation_bytes"` // AAX only
	Key             string `json:"key"`              // AAXC only
	IV              string `json:"iv"`               // AAXC only
}

func (c *Client) GetDownloadInfo(ctx context.Context, audibleAccountID, asin string) (*DownloadInfoResponse, error) {
	var resp DownloadInfoResponse
	path := fmt.Sprintf("/download/%s/%s", audibleAccountID, asin)
	if err := c.get(ctx, path, &resp); err != nil {
		return nil, err
	}
	return &resp, nil
}

// DownloadPDF downloads the PDF companion file for a book to destPath.
// Returns (false, nil) when the title has no PDF; (true, nil) on success.
func (c *Client) DownloadPDF(ctx context.Context, audibleAccountID, asin, destPath string) (bool, error) {
	path := fmt.Sprintf("/download/%s/%s/pdf", audibleAccountID, asin)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+path, nil)
	if err != nil {
		return false, err
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return false, fmt.Errorf("audible-svc request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return false, nil
	}
	if resp.StatusCode >= 400 {
		var e struct{ Detail string `json:"detail"` }
		json.NewDecoder(resp.Body).Decode(&e)
		return false, fmt.Errorf("audible-svc %s: %s", resp.Status, e.Detail)
	}

	f, err := os.Create(destPath)
	if err != nil {
		return false, err
	}
	defer f.Close()

	if _, err := io.Copy(f, resp.Body); err != nil {
		os.Remove(destPath)
		return false, err
	}
	return true, nil
}

func (c *Client) GetLibrary(ctx context.Context, accountID string) ([]BookDTO, error) {
	var books []BookDTO
	url := fmt.Sprintf("/library/%s", accountID)
	if err := c.get(ctx, url, &books); err != nil {
		return nil, err
	}
	return books, nil
}

func (c *Client) post(ctx context.Context, path string, body, out any) error {
	b, err := json.Marshal(body)
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+path, bytes.NewReader(b))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	return c.do(req, out)
}

func (c *Client) get(ctx context.Context, path string, out any) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+path, nil)
	if err != nil {
		return err
	}
	return c.do(req, out)
}

func (c *Client) do(req *http.Request, out any) error {
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("audible-svc request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		var e struct{ Detail string `json:"detail"` }
		json.NewDecoder(resp.Body).Decode(&e)
		return fmt.Errorf("audible-svc %s: %s", resp.Status, e.Detail)
	}

	return json.NewDecoder(resp.Body).Decode(out)
}

// AudibleChapter is one node of Audible's chapter tree. Parts/sections carry
// their nested chapters in Chapters; a parent's LengthMs covers only its own
// lead-in audio (often just the narrator reading the heading), not its children.
type AudibleChapter struct {
	Title         string           `json:"title"`
	StartOffsetMs int64            `json:"start_offset_ms"`
	LengthMs      int64            `json:"length_ms"`
	Chapters      []AudibleChapter `json:"chapters,omitempty"`
}

// ChapterInfo is Audible's chapter outline for a title (content metadata
// chapter_info, requested with chapter_titles_type=Tree).
type ChapterInfo struct {
	BrandIntroDurationMs int64            `json:"brandIntroDurationMs"`
	BrandOutroDurationMs int64            `json:"brandOutroDurationMs"`
	IsAccurate           bool             `json:"is_accurate"`
	RuntimeLengthMs      int64            `json:"runtime_length_ms"`
	Chapters             []AudibleChapter `json:"chapters"`
}

// GetChapters fetches Audible's chapter outline for a title.
func (c *Client) GetChapters(ctx context.Context, audibleAccountID, asin string) (*ChapterInfo, error) {
	var resp ChapterInfo
	path := fmt.Sprintf("/download/%s/%s/chapters", audibleAccountID, asin)
	if err := c.get(ctx, path, &resp); err != nil {
		return nil, err
	}
	return &resp, nil
}
