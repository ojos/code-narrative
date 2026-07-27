package ghclient

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
)

func TestParseRepoURL(t *testing.T) {
	// errContains は「どの検証で弾かれたか」まで固定したいケースで指定する。
	// 空なら ErrInvalidRepoURL であることのみを検証する。
	//
	// 文字種検証のケースでは必須。パーセントエンコードされた "/" は url.Parse が
	// デコードするためセグメント数が増え、意図した文字種検証ではなくセグメント数
	// チェックで弾かれてしまう（テストが別の理由で緑になる）。
	cases := []struct {
		name        string
		in          string
		owner       string
		repo        string
		wantError   bool
		errContains string
	}{
		{"正常", "https://github.com/ojos/code-narrative", "ojos", "code-narrative", false, ""},
		{"末尾.git除去", "https://github.com/ojos/code-narrative.git", "ojos", "code-narrative", false, ""},
		{"末尾スラッシュ", "https://github.com/ojos/code-narrative/", "ojos", "code-narrative", false, ""},
		{"ホスト不正", "https://gitlab.com/ojos/repo", "", "", true, "host="},
		{"http不可", "http://github.com/ojos/repo", "", "", true, "host="},
		{"セグメント過多", "https://github.com/ojos/repo/tree/main", "", "", true, "path="},
		{"セグメント不足", "https://github.com/ojos", "", "", true, "path="},
		{"owner に許容外文字", "https://github.com/oj@os/repo", "", "", true, "owner="},
		{"repo に許容外文字", "https://github.com/ojos/re%20po", "", "", true, "repo="},
		{"repo が親ディレクトリ参照", "https://github.com/ojos/..", "", "", true, "repo="},
		{"許容記号は通す", "https://github.com/o-j.o_s/re-po.name_1", "o-j.o_s", "re-po.name_1", false, ""},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			owner, repo, err := ParseRepoURL(c.in)
			if c.wantError {
				if !errors.Is(err, ErrInvalidRepoURL) {
					t.Fatalf("ErrInvalidRepoURL を期待したが: %v", err)
				}
				if c.errContains != "" && !strings.Contains(err.Error(), c.errContains) {
					t.Errorf("エラーが %q を含むことを期待したが: %v", c.errContains, err)
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

	_, err := c.FetchTarball(context.Background(), "o", "r")
	if err == nil {
		t.Fatal("404 応答はエラーになるべき")
	}
	var he *HTTPError
	if !errors.As(err, &he) || he.StatusCode != http.StatusNotFound {
		t.Fatalf("HTTPError(404) を期待したが: %v", err)
	}
	if !IsPermanent(err) {
		t.Error("404 は恒久エラーであるべき")
	}
}

func TestHTTPError_Classification(t *testing.T) {
	cases := []struct {
		status    int
		permanent bool
	}{
		{http.StatusBadRequest, true},   // 400
		{http.StatusUnauthorized, true}, // 401
		{http.StatusForbidden, true},    // 403
		{http.StatusNotFound, true},     // 404
		{http.StatusGone, true},         // 410
		{http.StatusInternalServerError, false},
		{http.StatusServiceUnavailable, false},
	}
	for _, c := range cases {
		err := &HTTPError{Op: "tarball", StatusCode: c.status}
		if got := IsPermanent(err); got != c.permanent {
			t.Errorf("status=%d IsPermanent=%v, want %v", c.status, got, c.permanent)
		}
	}
	// 非 HTTPError（ネットワーク等）は恒久ではない（一時障害扱い）。
	if IsPermanent(errors.New("network")) {
		t.Error("非 HTTPError は恒久であってはならない")
	}
}

func TestNew_UsesDefaultEndpointsWhenEnvUnset(t *testing.T) {
	// 環境変数が無い＝本番と同じ条件。実 GitHub を指すことを固定する。
	t.Setenv(envAPIBase, "")
	t.Setenv(envCodeloadBase, "")
	os.Unsetenv(envAPIBase)
	os.Unsetenv(envCodeloadBase)

	c := New("")
	if c.apiBase != defaultAPIBase {
		t.Errorf("apiBase = %q, want %q", c.apiBase, defaultAPIBase)
	}
	if c.codeloadBase != defaultCodeloadBase {
		t.Errorf("codeloadBase = %q, want %q", c.codeloadBase, defaultCodeloadBase)
	}
}

func TestNew_OverridesEndpointsFromEnv(t *testing.T) {
	// ローカル環境がスタブを指すための経路。末尾スラッシュは除去される。
	t.Setenv(envAPIBase, "http://github-stub:8080/")
	t.Setenv(envCodeloadBase, "http://github-stub:8080")

	c := New("")
	if want := "http://github-stub:8080"; c.apiBase != want {
		t.Errorf("apiBase = %q, want %q", c.apiBase, want)
	}
	if want := "http://github-stub:8080"; c.codeloadBase != want {
		t.Errorf("codeloadBase = %q, want %q", c.codeloadBase, want)
	}
}

func TestNew_BlankEnvFallsBackToDefault(t *testing.T) {
	// 空白のみの値は「未設定」と同じ扱いにし、不正なベース URL を組み立てない。
	t.Setenv(envAPIBase, "   ")
	t.Setenv(envCodeloadBase, "")

	c := New("")
	if c.apiBase != defaultAPIBase {
		t.Errorf("apiBase = %q, want %q", c.apiBase, defaultAPIBase)
	}
	if c.codeloadBase != defaultCodeloadBase {
		t.Errorf("codeloadBase = %q, want %q", c.codeloadBase, defaultCodeloadBase)
	}
}
