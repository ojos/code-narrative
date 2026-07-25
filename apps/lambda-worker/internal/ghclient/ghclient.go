// Package ghclient は GitHub からの tarball 取得とコミットログ取得を担う。
//
// 対象は public リポジトリのみ（SPEC スコープ）。未認証でも動作するが、
// GITHUB_TOKEN が与えられた場合は Authorization ヘッダへ注入してレート制限を
// 60 回/時から 5,000 回/時へ引き上げる。
package ghclient

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"

	"github.com/ojos/code-narrative/apps/lambda-worker/internal/model"
)

// 既定のエンドポイント。テストではフィールドを差し替えて httptest を指す。
const (
	defaultAPIBase      = "https://api.github.com"
	defaultCodeloadBase = "https://codeload.github.com"
)

// ErrInvalidRepoURL は repo_url が期待形式でない場合に返る。
var ErrInvalidRepoURL = errors.New("repo_url は https://github.com/{owner}/{repo} 形式である必要があります")

// HTTPError は GitHub API がエラーステータスを返した場合のエラー。
//
// ステータスコードを保持し、恒久（4xx: 存在しない/非公開/認証不可など、再試行で
// 解決しない）と一時（5xx など、再試行で解決し得る）を分類できるようにする。
type HTTPError struct {
	// Op は失敗した操作名（"tarball" / "commits"）。
	Op string
	// StatusCode は受信した HTTP ステータスコード。
	StatusCode int
}

// Error はエラーメッセージを返す。
func (e *HTTPError) Error() string {
	return fmt.Sprintf("GitHub %s 取得が異常応答: status=%d", e.Op, e.StatusCode)
}

// Permanent は 4xx（再試行しても解決しないクライアントエラー）かどうかを返す。
func (e *HTTPError) Permanent() bool {
	return e.StatusCode >= 400 && e.StatusCode < 500
}

// IsPermanent は err が恒久的な HTTPError（4xx）かどうかを返す。
//
// 4xx でない HTTPError（5xx 等）やネットワーク/タイムアウト等の非 HTTPError は
// 一時障害とみなし false を返す。
func IsPermanent(err error) bool {
	var he *HTTPError
	if errors.As(err, &he) {
		return he.Permanent()
	}
	return false
}

// Client は GitHub の tarball / REST API へアクセスする HTTP クライアント。
type Client struct {
	// httpClient は REST API（コミットログ等）用。応答が小さいためハード
	// タイムアウトを設定する。
	httpClient *http.Client
	// downloadClient は tarball ダウンロード用。Client.Timeout は本文読了までの
	// ハード期限であり、Body を呼び出し側（Untar）へ渡す tarball 取得では展開全体に
	// 及んで正当な大リポジトリを偽陰性で失敗させる。そのため Timeout は設定せず、
	// 取得〜展開の期限は ctx（Lambda デッドライン）で制御する。
	downloadClient *http.Client
	token          string
	apiBase        string
	codeloadBase   string
}

// New は GitHub クライアントを生成する。token が空文字の場合は未認証で動作する。
func New(token string) *Client {
	return &Client{
		httpClient:     &http.Client{Timeout: 60 * time.Second},
		downloadClient: &http.Client{},
		token:          token,
		apiBase:        defaultAPIBase,
		codeloadBase:   defaultCodeloadBase,
	}
}

// ownerRepoPattern は GitHub が owner / リポジトリ名に許容する文字種。
//
// ホストは github.com に固定しているため SSRF には当たらないが、抽出した値は
// codeload / REST API の URL パスへそのまま埋め込むため、想定外の文字（"/" や
// ".." など）を早期に弾いて堅牢化する。
var ownerRepoPattern = regexp.MustCompile(`^[A-Za-z0-9._-]+$`)

// isValidSegment は owner / repo として受理できるセグメントかを判定する。
//
// 文字種に加えて "." と ".." を明示的に弾く。両者は許容文字のみで構成される
// ため、パターン一致だけではカレント／親ディレクトリ参照が通ってしまう。
func isValidSegment(s string) bool {
	if s == "." || s == ".." {
		return false
	}
	return ownerRepoPattern.MatchString(s)
}

// ParseRepoURL は repo_url から owner と repo を抽出し検証する。
//
// 受理するのはホストが github.com で、パスが厳密に 2 セグメント
// （owner/repo）の URL のみ。末尾の ".git" は除去する。owner / repo は
// GitHub の許容文字種（英数字と "." "_" "-"）に一致する必要がある。
func ParseRepoURL(rawURL string) (owner, repo string, err error) {
	u, perr := url.Parse(strings.TrimSpace(rawURL))
	if perr != nil {
		return "", "", fmt.Errorf("%w: %v", ErrInvalidRepoURL, perr)
	}
	if u.Scheme != "https" || u.Host != "github.com" {
		return "", "", fmt.Errorf("%w: host=%q", ErrInvalidRepoURL, u.Host)
	}
	segments := strings.Split(strings.Trim(u.Path, "/"), "/")
	if len(segments) != 2 || segments[0] == "" || segments[1] == "" {
		return "", "", fmt.Errorf("%w: path=%q", ErrInvalidRepoURL, u.Path)
	}
	owner = segments[0]
	repo = strings.TrimSuffix(segments[1], ".git")
	if !isValidSegment(owner) {
		return "", "", fmt.Errorf("%w: owner=%q", ErrInvalidRepoURL, owner)
	}
	if !isValidSegment(repo) {
		return "", "", fmt.Errorf("%w: repo=%q", ErrInvalidRepoURL, repo)
	}
	return owner, repo, nil
}

// setAuth は token が設定されていれば Authorization ヘッダを付与する。
func (c *Client) setAuth(req *http.Request) {
	if c.token != "" {
		req.Header.Set("Authorization", "Bearer "+c.token)
	}
}

// FetchTarball は codeload から HEAD の tar.gz ストリームを取得する。
//
// 呼び出し側は返却された io.ReadCloser を必ず Close する責務を負う。
func (c *Client) FetchTarball(ctx context.Context, owner, repo string) (io.ReadCloser, error) {
	endpoint := fmt.Sprintf("%s/%s/%s/tar.gz/HEAD", c.codeloadBase, owner, repo)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, fmt.Errorf("tarball リクエスト生成に失敗: %w", err)
	}
	c.setAuth(req)
	resp, err := c.downloadClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("tarball 取得に失敗: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		resp.Body.Close()
		return nil, &HTTPError{Op: "tarball", StatusCode: resp.StatusCode}
	}
	return resp.Body, nil
}

// commitAPIResponse は GitHub REST /commits 応答の必要部分のみを写す型。
type commitAPIResponse struct {
	Commit struct {
		Message string `json:"message"`
		Author  struct {
			Name string `json:"name"`
			Date string `json:"date"`
		} `json:"author"`
	} `json:"commit"`
}

// FetchCommits は直近 limit 件のコミット（メッセージ・日時・作者）を取得する。
func (c *Client) FetchCommits(ctx context.Context, owner, repo string, limit int) ([]model.Commit, error) {
	endpoint := fmt.Sprintf("%s/repos/%s/%s/commits?per_page=%d", c.apiBase, owner, repo, limit)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, fmt.Errorf("commits リクエスト生成に失敗: %w", err)
	}
	req.Header.Set("Accept", "application/vnd.github+json")
	c.setAuth(req)
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("commits 取得に失敗: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, &HTTPError{Op: "commits", StatusCode: resp.StatusCode}
	}
	return decodeCommits(resp.Body)
}

// decodeCommits は REST API 応答の JSON をドメイン型 []model.Commit へ変換する。
func decodeCommits(r io.Reader) ([]model.Commit, error) {
	var raw []commitAPIResponse
	if err := json.NewDecoder(r).Decode(&raw); err != nil {
		return nil, fmt.Errorf("commits の JSON 解析に失敗: %w", err)
	}
	commits := make([]model.Commit, 0, len(raw))
	for _, c := range raw {
		commits = append(commits, model.Commit{
			Message: c.Commit.Message,
			Date:    c.Commit.Author.Date,
			Author:  c.Commit.Author.Name,
		})
	}
	return commits, nil
}
