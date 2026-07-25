terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.70, < 7.0"
      # ACM 証明書は CloudFront 用に us-east-1 で発行する必要があるため、
      # 呼び出し側から us-east-1 のエイリアスプロバイダを受け取る。
      configuration_aliases = [aws.us_east_1]
    }
  }
}
