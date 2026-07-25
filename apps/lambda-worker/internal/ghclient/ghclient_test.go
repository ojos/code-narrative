package ghclient

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestParseRepoURL(t *testing.T) {
	cases := []struct {
		name      string
		in        string
		owner     string
		repo      string
		wantError bool
	}{
		{"正常", "https://github.com/ojos/code-narrative", "ojos", "code-narrative", false},
		{"末尾.git除去", "https://github.com/ojos/code-narrative.git", "ojos", "code-narrative", false},
		{"末尾スラッシュ", "https://github.com/ojos/code-narrative/", "ojos", "code-narrative", false},
		{"ホスト不正", "https://gitlab.com/ojos/repo", "", "", true},
		{"http不可", "http://github.com/ojos/repo", "", "", true},
		{"セグメント過多", "https://github.com/ojos/repo/tree/main", "", "", true},
		{"セグメント不足", "https://github.com/ojos", "", "", true},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			owner, repo, err := ParseRepoURL(c.in)
			if c.wantError {
				if !errors.Is(err, ErrInvalidRepoURL) {
					t.Fatalf("ErrInvalidRepoURL を期待したが: %v", err)
				}
				return
			}
			if err != nil {
				t.Fatalf("想定外エラー: %v", err)
			}
			if owner != c.owner || repo != c.repo {
				t.Errorf("owner/repo = %q/%q, want %q/%q", owner, repo, c.owner, c.repo)
			}
		})
	}
}

func TestFetchCommits_ParsesAndInjectsToken(t *testing.T) {
	var gotAuth string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		io.WriteString(w, `[
			{"commit":{"message":"初回コミット\n詳細","author":{"name":"dev","date":"2026-01-01T00:00:00Z"}}},
			{"commit":{"message":"修正","author":{"name":"dev2","date":"2026-01-02T00:00:00Z"}}}
		]`)
	}))
	defer srv.Close()

	c := New("secret-token")
	c.apiBase = srv.URL

	commits, err := c.FetchCommits(context.Background(), "ojos", "repo", 30)
	if err != nil {
		t.Fatalf("FetchCommits: %v", err)
	}
	if len(commits) != 2 {
		t.Fatalf("commits 件数 = %d", len(commits))
	}
	if commits[0].Author != "dev" || commits[0].Date != "2026-01-01T00:00:00Z" {
		t.Errorf("commit[0] = %+v", commits[0])
	}
	if gotAuth != "Bearer secret-token" {
		t.Errorf("Authorization = %q", gotAuth)
	}
}

func TestFetchCommits_NoTokenNoAuthHeader(t *testing.T) {
	var hasAuth bool
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, hasAuth = r.Header["Authorization"]
		io.WriteString(w, `[]`)
	}))
	defer srv.Close()

	c := New("")
	c.apiBase = srv.URL
	if _, err := c.FetchCommits(context.Background(), "o", "r", 30); err != nil {
		t.Fatalf("FetchCommits: %v", err)
	}
	if hasAuth {
		t.Error("未認証時に Authorization ヘッダを付与してはならない")
	}
}

func TestFetchTarball_ReturnsBody(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, "TARBALL")
	}))
	defer srv.Close()

	c := New("")
	c.codeloadBase = srv.URL

	body, err := c.FetchTarball(context.Background(), "o", "r")
	if err != nil {
		t.Fatalf("FetchTarball: %v", err)
	}
	defer body.Close()
	data, _ := io.ReadAll(body)
	if string(data) != "TARBALL" {
		t.Errorf("body = %q", string(data))
	}
}

func TestFetchTarball_ErrorStatus(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer srv.Close()

	c := New("")
	c.codeloadBase = srv.URL

	if _, err := c.FetchTarball(context.Background(), "o", "r"); err == nil {
		t.Fatal("404 応答はエラーになるべき")
	}
}
