# Intake 判定 Reason Code

intake の要否を判定する際に、その根拠を分類するためのコード体系です。

判定結果を人間が追跡できるようにすることが目的です。「なぜ intake を求められたのか」「なぜ免除されたのか」を、判断ごとに言い直すのではなく、共通の語彙で示します。

## 適用範囲

- 新規 intake 経路と、既存 issue を流用する経路の両方に適用します。
- 判定を機構（フック等）で実装するか、ロールの判断として運用するかは問いません。この文書はコード体系のみを定めます。

## 命名規則

- `SCREAMING_SNAKE_CASE` を使用します。
- 1 コード 1 意味を維持します。
- 既存コードは原則維持し、挙動変更は実装側で吸収します。

## コード分類

### 1) Intake 必須: 実装経路

| reason_code | intake 要否 | 説明 |
|---|---:|---|
| IMPLEMENTATION_MISSING_GOAL | 必要 | 実装依頼に対して `goal` が不足している。 |
| IMPLEMENTATION_MISSING_ACCEPTANCE | 必要 | 実装依頼に対して `acceptance` が不足している。 |
| IMPLEMENTATION_MISSING_SCOPE_IN | 必要 | 実装依頼に対して `scope.in` が不足している。 |
| IMPLEMENTATION_MISSING_SCOPE_OUT | 必要 | 文脈上必要な `scope.out` が不足している。 |
| IMPLEMENTATION_MISSING_CONSTRAINTS | 必要 | 安全実行に必要な制約情報が不足している。 |
| IMPLEMENTATION_MISSING_GOAL_ACCEPTANCE | 必要 | `goal` と `acceptance` が同時に不足している。 |
| IMPLEMENTATION_MISSING_MULTIPLE | 必要 | 必須項目が 3 つ以上不足している。 |
| IMPLEMENTATION_EXISTING_ISSUE_UNCLEAR | 必要 | 既存 issue を参照しているが流用可否を判定できない。 |
| IMPLEMENTATION_NEEDS_INTAKE_CONFIRMATION | 必要 | 下書きはあるが正式な確認が未完了。 |

### 2) Intake 不要: 免除経路

| reason_code | intake 要否 | 説明 |
|---|---:|---|
| QUESTION_EXEMPT | 不要 | 質問のみで実装依頼ではない。 |
| EXPLAIN_EXEMPT | 不要 | 説明要求のみで実装依頼ではない。 |
| INVESTIGATE_EXEMPT | 不要 | 調査要求のみで実装依頼ではない。 |
| SMALL_FIX_EXEMPT_MEETS_CRITERIA | 不要 | 軽微修正候補が免除条件を満たす。 |
| IMPLEMENTATION_EXISTING_ISSUE_REUSABLE | 不要 | 既存 issue に必須項目が揃っており流用可能。 |

### 3) 免除不成立: Intake 必須へフォールバック

| reason_code | intake 要否 | 説明 |
|---|---:|---|
| SMALL_FIX_REQUIRES_INTAKE | 必要 | 軽微修正候補だが免除条件を満たさない。 |
| EXEMPTION_UNCLEAR_FALLBACK_INTAKE | 必要 | 免除判定が不明瞭なため intake 必須へフォールバック。 |

### 4) Bypass ポリシー

| reason_code | intake 要否 | 説明 |
|---|---:|---|
| BYPASS_APPROVED_EMERGENCY | 不要 | 緊急障害対応として bypass を許可。 |
| BYPASS_APPROVED_EXTERNAL_FACTOR | 不要 | 外部要因で intake 完了待ちが不可能なため bypass を許可。 |
| BYPASS_REJECTED_INVALID_REASON | 必要 | bypass 理由が無効または未対応のため拒否。 |
| BYPASS_UNNECESSARY_INTAKE_COMPLETE | 不要 | intake が既に充足しており bypass が不要。 |

## 不足項目の分類

不足を報告する際は、対象項目とその理由を添えます。

対象項目:

- `goal`
- `scope.in`
- `scope.out`
- `acceptance`
- `priority`
- `constraints`

理由:

- `missing` — 記述がない
- `insufficient_detail` — 記述はあるが検証可能でない
- `conflicting_with_existing_issue` — 既存 issue と矛盾する
- `required_for_risk_control` — リスク制御上必要

## 判定を機構で実装する場合の出力契約（任意）

判定をフック等で実装する場合は、次の形を推奨します。この契約は必須ではありません。

```json
{
  "intake_required": true,
  "reason_code": "IMPLEMENTATION_MISSING_ACCEPTANCE",
  "reason_message": "実装依頼には受け入れ条件が必要です。",
  "missing_fields": [
    {
      "field": "acceptance",
      "reason": "missing",
      "prompt_hint": "具体的な完了条件を列挙してください。"
    }
  ]
}
```

## 安全側の既定

- 未知の `reason_code` を受けた場合は、intake 必須側へフォールバックします。
- 判定が不明瞭な場合も intake 必須側へ倒します。免除の誤りは、要件未確定のまま実装が進む形で表面化し、発見が遅れるためです。

## 互換性方針

- 追加（新コード・新項目）は後方互換とします。
- 既存コードの改名・削除は破壊的変更とし、バージョン管理の対象とします。

## 関連

- ロール契約: [intake-manager](../role-contracts/intake-manager.md)
