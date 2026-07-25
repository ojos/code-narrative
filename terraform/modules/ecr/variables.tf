variable "repository_name" {
  description = "ECR リポジトリ名(例: code-narrative-api)"
  type        = string
}

variable "image_tag_mutability" {
  description = "タグの上書き可否。CI が :latest を差し替える運用のため既定は MUTABLE"
  type        = string
  default     = "MUTABLE"

  validation {
    condition     = contains(["MUTABLE", "IMMUTABLE"], var.image_tag_mutability)
    error_message = "image_tag_mutability は MUTABLE または IMMUTABLE を指定してください。"
  }
}

variable "force_delete" {
  description = "イメージが残っていてもリポジトリ削除を許可するか。既定は安全側の false"
  type        = bool
  default     = false
}

variable "untagged_expire_days" {
  description = "未タグイメージを失効させるまでの日数"
  type        = number
  default     = 14
}
