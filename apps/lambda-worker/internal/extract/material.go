package extract

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"unicode/utf8"

	"github.com/ojos/code-narrative/apps/lambda-worker/internal/model"
)

// truncateUTF8 は s を最大 maxBytes バイトへ切り詰める。
//
// マルチバイト文字の途中で切れないよう、有効な UTF-8 境界まで巻き戻す。
func truncateUTF8(s string, maxBytes int) string {
	if maxBytes <= 0 {
		return ""
	}
	if len(s) <= maxBytes {
		return s
	}
	cut := maxBytes
	for cut > 0 && !utf8.RuneStart(s[cut]) {
		cut--
	}
	return s[:cut]
}

// sourceExtensions は主要ソースファイル候補とみなす拡張子の集合。
var sourceExtensions = map[string]struct{}{
	".go": {}, ".py": {}, ".js": {}, ".ts": {}, ".tsx": {}, ".jsx": {},
	".java": {}, ".rb": {}, ".rs": {}, ".c": {}, ".cc": {}, ".cpp": {},
	".h": {}, ".hpp": {}, ".cs": {}, ".php": {}, ".kt": {}, ".swift": {},
	".scala": {}, ".sh": {}, ".sql": {},
}

// entryPointBases はエントリポイント推定に用いるベース名（拡張子除去）の集合。
var entryPointBases = map[string]struct{}{
	"main": {}, "index": {}, "app": {}, "server": {}, "cmd": {},
}

// excludedDirs は素材選定から除外するディレクトリ名の集合。
var excludedDirs = map[string]struct{}{
	".git": {}, "node_modules": {}, "vendor": {}, "dist": {}, "build": {},
	".next": {}, "target": {}, "__pycache__": {}, ".venv": {}, "venv": {},
}

// SelectMaterial は展開済みリポジトリとコミットログから物語素材を構築する。
//
// ディレクトリツリー・README・ヒューリスティックで選定した主要ソースファイル・
// コミットログを、合計 maxBytes を上限に優先順（ツリー → README → コミットログ →
// 主要ファイル）で詰める。第 2 返り値は DynamoDB 保存用の要旨
// （ディレクトリツリー + 選定ファイル名一覧、DigestMaxBytes で頭打ち）。
func SelectMaterial(repo *ExtractedRepo, commits []model.Commit, maxBytes int) (*model.Material, string, error) {
	if repo == nil {
		return nil, "", fmt.Errorf("展開済みリポジトリが nil です")
	}

	tree := buildTree(repo.Files)
	readmePath := findReadme(repo.Files)
	selected := selectSourceFiles(repo.Files, readmePath)

	remaining := maxBytes
	mat := &model.Material{}

	mat.DirectoryTree = takeBudget(tree, &remaining)

	if readmePath != "" {
		readme := readFileSafe(filepath.Join(repo.RootDir, readmePath))
		mat.Readme = takeBudget(readme, &remaining)
	}

	mat.CommitLog = takeBudget(formatCommits(commits), &remaining)

	mat.SelectedFiles = takeBudget(buildSelectedFiles(repo.RootDir, selected, remaining), &remaining)

	digest := buildDigest(tree, selected)
	return mat, digest, nil
}

// buildTree は全ファイルパス（相対）をソートし、改行区切りのツリー文字列にする。
func buildTree(files []FileEntry) string {
	paths := make([]string, 0, len(files))
	for _, f := range files {
		paths = append(paths, f.Path)
	}
	sort.Strings(paths)
	return strings.Join(paths, "\n")
}

// findReadme は README とみなせる最も浅いパスのファイルを返す（見つからなければ ""）。
func findReadme(files []FileEntry) string {
	best := ""
	bestDepth := 1 << 30
	for _, f := range files {
		base := strings.ToLower(filepath.Base(f.Path))
		if !strings.HasPrefix(base, "readme") {
			continue
		}
		depth := strings.Count(f.Path, string(os.PathSeparator))
		if depth < bestDepth {
			best = f.Path
			bestDepth = depth
		}
	}
	return best
}

// isExcluded はパスが除外ディレクトリ配下かどうかを判定する。
func isExcluded(path string) bool {
	for _, seg := range strings.Split(path, string(os.PathSeparator)) {
		if _, ok := excludedDirs[seg]; ok {
			return true
		}
	}
	return false
}

// scoreFile はファイルの主要度スコアを算出する（高いほど優先）。
func scoreFile(f FileEntry) int {
	ext := strings.ToLower(filepath.Ext(f.Path))
	if _, ok := sourceExtensions[ext]; !ok {
		return -1 // ソース候補外
	}
	score := 10
	base := strings.ToLower(strings.TrimSuffix(filepath.Base(f.Path), ext))
	if _, ok := entryPointBases[base]; ok {
		score += 100 // エントリポイント推定を最優先
	}
	// 浅い階層ほど加点（プロジェクト直下の主要ファイルを優先）。
	depth := strings.Count(f.Path, string(os.PathSeparator))
	score -= depth
	return score
}

// selectSourceFiles はヒューリスティックで主要ソースファイルを選定する。
//
// スコア降順、同スコアではサイズ昇順（読みやすい小さめのファイルを優先）で
// 並べ、上位 maxSelectedFiles 件を返す。readmePath と除外ディレクトリは対象外。
func selectSourceFiles(files []FileEntry, readmePath string) []FileEntry {
	type scored struct {
		entry FileEntry
		score int
	}
	candidates := make([]scored, 0, len(files))
	for _, f := range files {
		if f.Path == readmePath || isExcluded(f.Path) {
			continue
		}
		s := scoreFile(f)
		if s < 0 {
			continue
		}
		candidates = append(candidates, scored{entry: f, score: s})
	}
	sort.SliceStable(candidates, func(i, j int) bool {
		if candidates[i].score != candidates[j].score {
			return candidates[i].score > candidates[j].score
		}
		return candidates[i].entry.Size < candidates[j].entry.Size
	})
	limit := maxSelectedFiles
	if limit > len(candidates) {
		limit = len(candidates)
	}
	out := make([]FileEntry, 0, limit)
	for i := 0; i < limit; i++ {
		out = append(out, candidates[i].entry)
	}
	return out
}

// buildSelectedFiles は選定ファイルの内容を、与えられた budget に収まるだけ連結する。
func buildSelectedFiles(rootDir string, selected []FileEntry, budget int) string {
	var b strings.Builder
	for _, f := range selected {
		if budget <= 0 {
			break
		}
		content := readFileSafe(filepath.Join(rootDir, f.Path))
		block := fmt.Sprintf("--- %s ---\n%s\n\n", f.Path, content)
		trimmed := truncateUTF8(block, budget)
		b.WriteString(trimmed)
		budget -= len(trimmed)
	}
	return b.String()
}

// buildDigest は repo_digest（ツリー + 選定ファイル名一覧）を DigestMaxBytes で頭打ちして返す。
func buildDigest(tree string, selected []FileEntry) string {
	names := make([]string, 0, len(selected))
	for _, f := range selected {
		names = append(names, f.Path)
	}
	digest := fmt.Sprintf("# Directory tree\n%s\n\n# Selected files\n%s",
		tree, strings.Join(names, "\n"))
	return truncateUTF8(digest, DigestMaxBytes)
}

// formatCommits はコミット一覧を人間可読な行に整形する。
func formatCommits(commits []model.Commit) string {
	if len(commits) == 0 {
		return ""
	}
	var b strings.Builder
	for _, c := range commits {
		msg := c.Message
		if i := strings.IndexByte(msg, '\n'); i >= 0 {
			msg = msg[:i] // 1 行目のみ
		}
		fmt.Fprintf(&b, "- %s %s: %s\n", c.Date, c.Author, msg)
	}
	return b.String()
}

// takeBudget は s を remaining バイト以内へ切り詰め、消費分だけ remaining を減算する。
func takeBudget(s string, remaining *int) string {
	if *remaining <= 0 {
		return ""
	}
	out := truncateUTF8(s, *remaining)
	*remaining -= len(out)
	return out
}

// readFileSafe はファイルを読み、失敗時は空文字を返す（素材抽出は best-effort）。
func readFileSafe(path string) string {
	data, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	return string(data)
}
