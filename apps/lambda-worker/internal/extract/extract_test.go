package extract

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"errors"
	"path/filepath"
	"sort"
	"strings"
	"testing"
)

// makeTarGz は path->content のマップから gzip 圧縮 tar を生成する。
// 各パスは先頭ディレクトリを含む（codeload の tarball 形状を模す）。
func makeTarGz(t *testing.T, files map[string]string) []byte {
	t.Helper()
	var buf bytes.Buffer
	gz := gzip.NewWriter(&buf)
	tw := tar.NewWriter(gz)

	paths := make([]string, 0, len(files))
	for p := range files {
		paths = append(paths, p)
	}
	sort.Strings(paths)

	for _, p := range paths {
		content := files[p]
		hdr := &tar.Header{
			Name:     p,
			Mode:     0o644,
			Size:     int64(len(content)),
			Typeflag: tar.TypeReg,
		}
		if err := tw.WriteHeader(hdr); err != nil {
			t.Fatalf("WriteHeader: %v", err)
		}
		if _, err := tw.Write([]byte(content)); err != nil {
			t.Fatalf("Write: %v", err)
		}
	}
	if err := tw.Close(); err != nil {
		t.Fatalf("tar Close: %v", err)
	}
	if err := gz.Close(); err != nil {
		t.Fatalf("gzip Close: %v", err)
	}
	return buf.Bytes()
}

func TestUntar_ExtractsAndStripsTopDir(t *testing.T) {
	data := makeTarGz(t, map[string]string{
		"repo-HEAD/README.md":   "# タイトル",
		"repo-HEAD/main.go":     "package main",
		"repo-HEAD/pkg/util.go": "package pkg",
	})
	dest := t.TempDir()

	repo, err := Untar(bytes.NewReader(data), dest, 200*1024*1024)
	if err != nil {
		t.Fatalf("Untar: %v", err)
	}
	if repo.RootDir != filepath.Join(dest, "repo-HEAD") {
		t.Errorf("RootDir = %q", repo.RootDir)
	}

	got := map[string]bool{}
	for _, f := range repo.Files {
		got[f.Path] = true
	}
	for _, want := range []string{"README.md", "main.go", filepath.Join("pkg", "util.go")} {
		if !got[want] {
			t.Errorf("Files に %q が含まれない: %+v", want, repo.Files)
		}
	}
}

func TestUntar_TooLarge(t *testing.T) {
	data := makeTarGz(t, map[string]string{
		"repo-HEAD/big.txt": strings.Repeat("x", 5000),
	})
	dest := t.TempDir()

	_, err := Untar(bytes.NewReader(data), dest, 1000) // 上限 1000 バイト
	if !errors.Is(err, ErrTooLarge) {
		t.Fatalf("ErrTooLarge を期待したが: %v", err)
	}
}

func TestUntar_RejectsPathTraversal(t *testing.T) {
	data := makeTarGz(t, map[string]string{
		"../evil.txt": "malicious",
	})
	dest := t.TempDir()

	_, err := Untar(bytes.NewReader(data), dest, 200*1024*1024)
	if err == nil {
		t.Fatal("パストラバーサルは拒否されるべき")
	}
}
