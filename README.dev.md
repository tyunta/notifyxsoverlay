# NotifyXSOverlay (Developer Notes)

## 概要
- ユーザー向けの手順は `README.md` を参照してください。
- 本ファイルは開発・保守向けの補足情報をまとめます。

## ログ
- ログは標準エラーにJSONで出力されます。
- 主要イベント: `run_start`, `notification_sent`, `notification_suppressed`, `notification_poll_failed`

| event | 意味 |
| --- | --- |
| `run_start` | ブリッジ開始 |
| `notification_sent` | 通知送信成功 |
| `notification_suppressed` | フィルタ/学習モードで抑制 |
| `notification_poll_failed` | 取得失敗 |

## 依存/制約
- XSOverlay連携はWebSocket経由です（`xs_overlay.ws_url`）。
- SteamVR連携はOpenVRのAPI呼び出しに依存します。
- Windows通知APIはパッケージ化アプリ前提の制約があります。

## テスト
- `uv run --extra test --with pytest pytest`
- カバレッジ: `uv run --extra test --with pytest-cov pytest --cov=src/notifyxsoverlay --cov-report=term-missing:skip-covered`

## 開発メモ
- 設定は `config.json` とバックアップ（`.bak`）で運用されます。
- 破損時は `.corrupt` に退避し、復旧ログを出します。
