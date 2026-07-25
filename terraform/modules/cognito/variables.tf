variable "user_pool_name" {
  description = "Cognito User Pool 名"
  type        = string
}

variable "client_name" {
  description = "User Pool Client 名"
  type        = string
}

variable "hosted_ui_domain_prefix" {
  description = "Hosted UI のドメインプレフィックス(<prefix>.auth.<region>.amazoncognito.com)。アカウント/リージョンで一意"
  type        = string
}

variable "callback_urls" {
  description = "Authorization Code フローのコールバック URL 一覧"
  type        = list(string)
}

variable "logout_urls" {
  description = "ログアウト後のリダイレクト URL 一覧"
  type        = list(string)
}
