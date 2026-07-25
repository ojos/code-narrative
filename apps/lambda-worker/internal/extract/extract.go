// Package extract は tarball の展開と、LLM へ渡す物語素材の抽出を担う。
//
// 責務は 2 つに分かれる:
//  1. Untar: gzip 圧縮された tar ストリームを展開しつつ累計サイズ上限
//     （SPEC §4② の 200MB）を強制する。
//  2. SelectMaterial: 展開済みリポジトリとコミットログから、ディレクトリツリー・
//     README・主要ソースファイル・コミットログを合計 100KB を上限に詰める。
//
// あわせて DynamoDB 保存用の要旨（repo_digest = ツリー + 選定ファイル名一覧）を返す。
package extract

import (
	"archive/tar"
	"compress/gzip"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"github.com/ojos/code-narrative/apps/lambda-worker/internal/model"
)

// DigestMaxBytes は repo_digest の上限バイト数。
//
// DynamoDB の 1 アイテム上限（400KB）に対し、他属性ぶんの余裕を残すために
// 要旨自体を約 300KB へ制限する。
const DigestMaxBytes = 300 * 1024

// 選定する主要ソースファイルの最大件数。
const maxSelectedFiles = 6

// ErrTooLarge は展開後の累計サイズが上限を超えた場合に返る。
var ErrTooLarge = errors.New("展開後のリポジトリサイズが上限を超えました")

// FileEntry は展開済みリポジトリ内の 1 ファイルを表す。
type FileEntry struct {
	// Path はリポジトリルート（RootDir）からの相対パス。
	Path string
	// Size はファイルサイズ（バイト）。
	Size int64
}

// ExtractedRepo は展開済みリポジトリのメタ情報を保持する。
type ExtractedRepo struct {
	// RootDir は展開されたリポジトリのルートディレクトリ（絶対パス）。
	RootDir string
	// Files はルート配下の通常ファイル一覧。
	Files []FileEntry
}

// Service は worker から利用する抽出処理のアダプタ。
//
// パッケージ関数（Untar / SelectMaterial）をメソッドとして公開し、
// worker 側でインターフェイスとしてモック差し替えできるようにする。
type Service struct{}

// Untar は Service 経由でパッケージ関数 Untar を呼び出す。
func (Service) Untar(r io.Reader, destDir string, maxTotalBytes int64) (*ExtractedRepo, error) {
	return Untar(r, destDir, maxTotalBytes)
}

// SelectMaterial は Service 経由でパッケージ関数 SelectMaterial を呼び出す。
func (Service) SelectMaterial(repo *ExtractedRepo, commits []model.Commit, maxBytes int) (*model.Material, string, error) {
	return SelectMaterial(repo, commits, maxBytes)
}

// Untar は gzip 圧縮された tar ストリーム r を destDir 配下へ展開する。
//
// 展開済みバイト数の累計が maxTotalBytes を超えた時点で ErrTooLarge を返す
// （zip bomb 対策としてファイル単位でも書き込み量を制限する）。codeload の
// tarball は全エントリが "<repo>-<ref>/" という単一の先頭ディレクトリ配下に
// 入るため、RootDir はその先頭ディレクトリを指す。
func Untar(r io.Reader, destDir string, maxTotalBytes int64) (*ExtractedRepo, error) {
	gz, err := gzip.NewReader(r)
	if err != nil {
		return nil, fmt.Errorf("gzip 展開の初期化に失敗: %w", err)
	}
	defer gz.Close()

	tr := tar.NewReader(gz)
	var total int64
	var topDir string
	var files []FileEntry

	for {
		hdr, err := tr.Next()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("tar エントリの読み取りに失敗: %w", err)
		}

		cleanName := filepath.Clean(hdr.Name)
		// パストラバーサル（"../" や絶対パス）を拒否する。
		if strings.HasPrefix(cleanName, ".."+string(os.PathSeparator)) || cleanName == ".." || filepath.IsAbs(cleanName) {
			return nil, fmt.Errorf("不正なパスを検出: %q", hdr.Name)
		}

		// 先頭ディレクトリを記録する（最初のエントリの第 1 セグメント）。
		if topDir == "" {
			topDir = firstSegment(cleanName)
		}

		target := filepath.Join(destDir, cleanName)
		if !strings.HasPrefix(target, filepath.Clean(destDir)+string(os.PathSeparator)) && target != filepath.Clean(destDir) {
			return nil, fmt.Errorf("展開先が destDir の外を指しています: %q", hdr.Name)
		}

		switch hdr.Typeflag {
		case tar.TypeDir:
			if err := os.MkdirAll(target, 0o755); err != nil {
				return nil, fmt.Errorf("ディレクトリ作成に失敗: %w", err)
			}
		case tar.TypeReg:
			if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
				return nil, fmt.Errorf("親ディレクトリ作成に失敗: %w", err)
			}
			written, werr := writeFileCapped(target, tr, maxTotalBytes-total)
			total += written
			if werr != nil {
				return nil, werr
			}
			if total > maxTotalBytes {
				return nil, ErrTooLarge
			}
			rel := relToTop(cleanName, topDir)
			if rel != "" {
				files = append(files, FileEntry{Path: rel, Size: written})
			}
		default:
			// シンボリックリンク等は無視する（安全側）。
		}
	}

	rootDir := destDir
	if topDir != "" {
		rootDir = filepath.Join(destDir, topDir)
	}
	return &ExtractedRepo{RootDir: rootDir, Files: files}, nil
}

// writeFileCapped は src を target へ書き出し、書き込み量を remaining+1 バイトに制限する。
//
// remaining は「累計上限までの残量」。返り値の written が remaining を超えた場合、
// 呼び出し側で ErrTooLarge を判定する。
func writeFileCapped(target string, src io.Reader, remaining int64) (int64, error) {
	f, err := os.Create(target)
	if err != nil {
		return 0, fmt.Errorf("ファイル作成に失敗: %w", err)
	}
	defer f.Close()

	limit := remaining + 1
	if limit < 1 {
		limit = 1
	}
	written, err := io.Copy(f, io.LimitReader(src, limit))
	if err != nil {
		return written, fmt.Errorf("ファイル書き込みに失敗: %w", err)
	}
	return written, nil
}

// firstSegment はパスの第 1 セグメントを返す。
func firstSegment(p string) string {
	if i := strings.IndexByte(p, os.PathSeparator); i >= 0 {
		return p[:i]
	}
	return p
}

// relToTop は cleanName から先頭ディレクトリ topDir を取り除いた相対パスを返す。
// topDir そのもの（ディレクトリエントリ）に対しては空文字を返す。
func relToTop(cleanName, topDir string) string {
	if topDir == "" {
		return cleanName
	}
	if cleanName == topDir {
		return ""
	}
	prefix := topDir + string(os.PathSeparator)
	if strings.HasPrefix(cleanName, prefix) {
		return cleanName[len(prefix):]
	}
	return cleanName
}
