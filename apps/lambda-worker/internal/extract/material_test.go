package extract

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/ojos/code-narrative/apps/lambda-worker/internal/model"
)

// writeRepo は path->content を rootDir 配下へ書き出し、ExtractedRepo を構築する。
func writeRepo(t *testing.T, files map[string]string) *ExtractedRepo {
	t.Helper()
	root := t.TempDir()
	repo := &ExtractedRepo{RootDir: root}
	for p, content := range files {
		full := filepath.Join(root, p)
		if err := os.MkdirAll(filepath.Dir(full), 0o755); err != nil {
			t.Fatalf("MkdirAll: %v", err)
		}
		if err := os.WriteFile(full, []byte(content), 0o644); err != nil {
			t.Fatalf("WriteFile: %v", err)
		}
		repo.Files = append(repo.Files, FileEntry{Path: p, Size: int64(len(content))})
	}
	return repo
}

func materialTotal(m *model.Material) int {
	return len(m.DirectoryTree) + len(m.Readme) + len(m.SelectedFiles) + len(m.CommitLog)
}

func TestSelectMaterial_EnforcesTotalCap(t *testing.T) {
	// 各 50KB の 3 ファイル + README で合計 100KB を大きく超える素材を用意。
	big := strings.Repeat("A", 50*1024)
	repo := writeRepo(t, map[string]string{
		"README.md": strings.Repeat("R", 40*1024),
		"main.go":   big,
		"lib.go":    big,
		"svc.go":    big,
	})
	commits := []model.Commit{{Message: "初回コミット", Date: "2026-01-01", Author: "dev"}}

	const cap = 100 * 1024
	mat, digest, err := SelectMaterial(repo, commits, cap)
	if err != nil {
		t.Fatalf("SelectMaterial: %v", err)
	}
	if total := materialTotal(mat); total > cap {
		t.Errorf("素材合計 %d が上限 %d を超過", total, cap)
	}
	if digest == "" {
		t.Error("repo_digest が空")
	}
	if !strings.Contains(digest, "Directory tree") {
		t.Errorf("digest にツリー節がない: %q", digest[:min(80, len(digest))])
	}
}

func TestSelectMaterial_PrefersEntryPoint(t *testing.T) {
	repo := writeRepo(t, map[string]string{
		"README.md":     "readme",
		"zzz_helper.go": "package a // helper",
		"main.go":       "package main // entrypoint",
	})
	mat, digest, err := SelectMaterial(repo, nil, 100*1024)
	if err != nil {
		t.Fatalf("SelectMaterial: %v", err)
	}
	if !strings.Contains(mat.SelectedFiles, "main.go") {
		t.Errorf("エントリポイント main.go が選定されていない: %q", mat.SelectedFiles)
	}
	if !strings.Contains(digest, "main.go") {
		t.Errorf("digest に main.go がない")
	}
	if mat.Readme != "readme" {
		t.Errorf("README が抽出されていない: %q", mat.Readme)
	}
}

func TestSelectMaterial_ExcludesVendorDirs(t *testing.T) {
	repo := writeRepo(t, map[string]string{
		"main.go":                   "package main",
		"node_modules/lib/index.js": "module.exports = {}",
	})
	mat, _, err := SelectMaterial(repo, nil, 100*1024)
	if err != nil {
		t.Fatalf("SelectMaterial: %v", err)
	}
	if strings.Contains(mat.SelectedFiles, "node_modules") {
		t.Errorf("除外ディレクトリのファイルが選定された: %q", mat.SelectedFiles)
	}
}
