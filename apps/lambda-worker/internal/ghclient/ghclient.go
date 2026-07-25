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

// Client は GitHub の tarball / REST API へアクセスする HTTP クライアント。
type Client struct {
	httpClient   *http.Client
	token        string
	apiBase      string
	codeloadBase string
}

// New は GitHub クライアントを生成する。token が空文字の場合は未認証で動作する。
func New(token string) *Client {
	return &Client{
		httpClient:   &http.Client{Timeout: 60 * time.Second},
		token:        token,
		apiBase:      defaultAPIBase,
		codeloadBase: defaultCodeloadBase,
	}
}

// ParseRepoURL は repo_url から owner と repo を抽出し検証する。
//
// 受理するのはホストが github.com で、パスが厳密に 2 セグメント
// （owner/repo）の URL のみ。末尾の ".git" は除去する。
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
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("tarball 取得に失敗: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		resp.Body.Close()
		return nil, fmt.Errorf("tarball 取得が異常応答: status=%d", resp.StatusCode)
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
		return nil, fmt.Errorf("commits 取得が異常応答: status=%d", resp.StatusCode)
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
