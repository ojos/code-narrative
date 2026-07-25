// Package logging は job_id を必ず含む構造化 JSON ログを提供する。
//
// CloudWatch Logs 上でジョブ単位の追跡（SPEC §7 可観測性）を可能にするため、
// 生成したロガーは全出力に job_id 属性を自動付与する。
package logging

import (
	"io"
	"log/slog"
	"os"
)

// Logger は job_id を固定属性として保持する構造化ロガーのラッパ。
type Logger struct {
	l *slog.Logger
}

// New は指定した jobID を全ログへ付与する JSON ロガーを標準出力向けに生成する。
func New(jobID string) *Logger {
	return NewWithWriter(os.Stdout, jobID)
}

// NewWithWriter は出力先を指定して Logger を生成する（テスト用途を含む）。
func NewWithWriter(w io.Writer, jobID string) *Logger {
	h := slog.NewJSONHandler(w, &slog.HandlerOptions{Level: slog.LevelInfo})
	return &Logger{l: slog.New(h).With("job_id", jobID)}
}

// Info は情報レベルのログを出力する。
func (lg *Logger) Info(msg string, args ...any) { lg.l.Info(msg, args...) }

// Warn は警告レベルのログを出力する。
func (lg *Logger) Warn(msg string, args ...any) { lg.l.Warn(msg, args...) }

// Error はエラーレベルのログを出力する。
func (lg *Logger) Error(msg string, args ...any) { lg.l.Error(msg, args...) }
