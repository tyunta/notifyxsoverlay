# NotifyXSOverlay

Windows通知をXSOverlayへ中継し、アプリごとに通知の許可/拒否を制御できるツールです。

## はじめに（最短）
1. 必須要件: Windows 10/11 / SteamVR+XSOverlay / 通知アクセス許可 / `uv` / `git`（未導入なら「初回セットアップ」を参照）
2. SteamVRを起動して以下を実行
    ```powershell
    uvx --from git+https://github.com/tyunta/notifyxsoverlay notifyxsoverlay install-steamvr
    ```
3. SteamVRの Startup Overlay Apps に表示されることを確認
4. 次回SteamVR起動時に自動起動し、通知表示を確認

## 初回セットアップ

### uv のインストール
公式手順: [Installing uv](https://docs.astral.sh/uv/getting-started/installation/)

### git のインストール
- `git --version` が通ればOKです
- 公式手順: [Git - Downloads](https://git-scm.com/downloads)

## 日常運用

### 手動で起動する
```powershell
uvx --from git+https://github.com/tyunta/notifyxsoverlay notifyxsoverlay run
```
- オプションは「CLIコマンド一覧」を参照してください。
- 自動起動を使わない場合の手動実行です（詳細は「運用メモ」）

### CLIコマンド一覧

#### run
- 通知ブリッジを起動する
- 主要オプション: `--ws-url` / `--poll-interval`
- 例: `--ws-url "ws://127.0.0.1:42070" --poll-interval 1.0`
- 確認: `run_start` のログが出ること

#### install-steamvr
- SteamVRの自動起動に登録する
- 主要オプション: `--repo` / `--uvx-path`
- 例と確認手順は「はじめに（最短）」を参照

#### uninstall-steamvr
- SteamVRの自動起動から解除する
```powershell
uvx --from git+https://github.com/tyunta/notifyxsoverlay notifyxsoverlay uninstall-steamvr
```
- 確認: SteamVRの Startup Overlay Apps から消えること

## 設定

### 設定ファイル
- 保存先: `%LOCALAPPDATA%\NotifyXSOverlay\config.json`
- 必須: なし（未作成でも起動可。初回起動で自動生成）
- 迷ったら `filters.allow` / `filters.block` だけでOK（詳細は早見表）
- 自動管理の項目（learning.*の一部）は削除しても再生成されます
- エクスプローラで開く: `explorer "%LOCALAPPDATA%\\NotifyXSOverlay"`
- 破損時の復旧: `config.json` が壊れると `.bak` から復元を試み、失敗すると `.corrupt` に退避します

#### 設定ファイルを開く/保存する（PowerShell）
```powershell
notepad "$env:LOCALAPPDATA\\NotifyXSOverlay\\config.json"
```

#### 設定項目の早見表
| キー | 型 | 既定値 | 推奨 | 説明 |
| --- | --- | --- | --- | --- |
| `filters.allow` | list[str] | `["com.squirrel.Discord.Discord"]` | 必要なアプリだけ追加 | 許可リスト |
| `filters.block` | list[str] | `[]` | うるさいアプリを追加 | ブロックリスト |
| `learning.enabled` | bool | `true` | 初期は `true` | 学習モードの有効化 |
| `learning.last_reset` | str \| null | `null` | 自動管理 | 起動セッション識別（自動管理） |
| `learning.pending` | dict[str, str] | `{}` | 自動管理 | 未分類一覧（自動管理 / 編集不要） |
| `learning.shown_session` | dict[str, str] | `{}` | 自動管理 | 起動中の初回表示管理（自動管理 / 編集不要） |
| `xs_overlay.ws_url` | str | `ws://127.0.0.1:42070/?client=NotifyXSOverlay` | XSOverlay設定のURL | WebSocket URL（XSOverlay側と一致させる） |
| `xs_overlay.notification_timeout_seconds` | float | `3.0` | `3.0-5.0` | 表示秒数（0以上） |
| `xs_overlay.notification_opacity` | float | `0.6` | `0.6` | 透明度（0.0-1.0） |
| `steamvr.exit_on_shutdown` | bool | `true` | `true` | SteamVR終了で自動終了する |
| `poll_interval_seconds` | float | `1.0` | `1.0` | ポーリング間隔（秒、0より大きい値） |

#### 最小設定例（学習モードON）
```json
{
  "learning": { "enabled": true },
  "filters": { "allow": ["com.squirrel.Discord.Discord"], "block": [] }
}
```
※ 既定の許可リスト（Discord）を含んだ最小例です。

#### フル設定例（抜粋）
```json
{
  "filters": {
    "allow": ["com.squirrel.Discord.Discord"],
    "block": []
  },
  "learning": { "enabled": true },
  "xs_overlay": {
    "ws_url": "ws://127.0.0.1:42070/?client=NotifyXSOverlay",
    "notification_timeout_seconds": 3.0,
    "notification_opacity": 0.6
  },
  "steamvr": { "exit_on_shutdown": true },
  "poll_interval_seconds": 1.0
}
```

## トラブルシュート（よくある問題）
症状が出ているときは、まずここを確認してください。
| 症状 | 原因 | 対処 |
| --- | --- | --- |
| 通知が来ない | 通知アクセス未許可 | Windowsの「通知アクセス」を許可して再起動 |
| XSOverlayに届かない | XSOverlay未起動 / URL違い | XSOverlayを起動し、URL/ポートを確認 |
| install-steamvr が失敗する | SteamVR未起動 / uvx未検出 | SteamVR起動中に再実行。詳細は「運用メモ」 |
| ログが見たい | 実行時の状況を確認したい | 実行時の標準エラーにJSONログが出ます（例: `2> notifyxsoverlay.log` で保存） |
| 通知が二重に出る | 旧プロセスが残っている | すべて終了してから再起動 |

#### ログ保存の例（PowerShell）
```powershell
uvx --from git+https://github.com/tyunta/notifyxsoverlay notifyxsoverlay run 2> notifyxsoverlay.log
```

## FAQ
概念や設定の疑問はこちら。

**Q. 学習モードって何？**  
A. 未分類アプリを初回だけ表示し、一覧に保存して後から許可/拒否へ移す運用です。

**Q. Discordだけ通したい**  
A. `learning.enabled=false` にして `filters.allow=["com.squirrel.Discord.Discord"]` を設定してください。

## フィルタ仕様

### 概要
- ブロックリストに一致した通知は常に除外する。
- 学習モードON: ブロック → 許可 → まだ許可/拒否に入っていない通知は、起動中の初回だけ表示して学習リストに記録する。
- 学習モードOFF: ブロック → 許可（許可が空なら非ブロックを通す）。

### 運用の目安
- 初期は学習モードONで学習リストを集め、後から allow/block に移して学習モードOFF にする。

## 運用メモ
- Windows通知リスナーはユーザー許可が必要です。初回起動時の許可ダイアログで許可してください。
- 通知アクセスが拒否された場合は、Windows設定で通知へのアクセスを許可して再起動してください。
- Windowsの通知API（UserNotificationListener）はパッケージ化アプリ前提の制約があります。`uvx` での実行環境によっては通知が取得できない場合があります。
- XSOverlayが起動していないと送信に失敗します。
- WebSocket URLの既定値は `ws://127.0.0.1:42070` です。変更した場合は `--ws-url` か `xs_overlay.ws_url` を上書きしてください。
- `install-steamvr` は SteamVR 起動中に実行してください。
- SteamVR起動ユーザーで `uvx` が見つからない場合は `--uvx-path` を指定してください。
- 自動起動と手動起動の同時実行は想定していません。
- 同時起動を避けるため、起動時に単一インスタンス判定を行います。
- SteamVRの終了を検知したら即終了します（`steamvr.exit_on_shutdown=true`）。
- 既定の許可リストには Discord（`com.squirrel.Discord.Discord`）を含めています。
- 通知取得のポーリング間隔は `poll_interval_seconds` です。既定値は `1.0` 秒です。

## やること
- Windows通知の取得、整形、XSOverlayへの送信を安定動作させる。
- 通知元アプリの許可/拒否フィルタを提供し、ユーザーが安全に制御できるようにする。
- 失敗時はログとリトライ方針を明確化し、静かな失敗を避ける。

## やらないこと
- Windows通知の恒久的な保存やクラウド同期。
- 通知内容の外部送信（ユーザーが明示的に有効化した場合を除く）。
- 必須ではない常駐リソースの肥大化（過剰な常駐UIや無限ループ）。

## プライバシー
- 通知内容はローカルで処理し、外部サーバーへ送信しません（テレメトリなし）。
- XSOverlayへの送信はローカルWebSocketのみです（既定: 127.0.0.1）。`xs_overlay.ws_url` を外部に向ける場合は送信先に注意してください。
- 設定/学習リストはローカルの設定ファイルに保存されます（保存対象はアプリID/表示名で、通知本文は保存しません）。
- ログは標準エラー出力のみで、保存はリダイレクト時のみです（イベント名/アプリID/エラー程度）。
- 学習モードは未知アプリを初回だけ表示します。機密通知を避けたい場合は許可リスト運用に切り替えてください。
- 通知はオーバーレイ表示されるため、配信・録画・画面共有では内容が映る可能性があります。必要に応じてフィルタしてください。
- `install-steamvr` はSteamVRの自動起動に登録します（OS常駐サービス化はしません）。不要なら `uninstall-steamvr` で解除できます。
- 通知アクセスはWindowsの許可が必要で、許可がない場合は取得できません。
- 既定ではDiscordが許可リストに含まれます。不要なら削除してください。
- `uvx`/`git` でのインストール・更新時は、取得先としてGitHubにアクセスします。
- 配布元（GitHub）から取得して実行する性質上、更新時に供給網リスクがゼロではありません。
- 企業/学校など管理環境では通知アクセスが制限されることがあります。利用規約に従ってください。

## 仕様メモ
- アプリキー: `com.tyunta.notifyxsoverlay`
- インストール時に `notifyxsoverlay.cmd` と `notifyxsoverlay.vrmanifest` を生成します。
- 生成先は `%LOCALAPPDATA%\NotifyXSOverlay` です。

## 開発者向けノート
開発者向けの詳細は `README.dev.md` を参照してください。

## ライセンス
AGPL-3.0-or-later。詳細は `LICENSE` を参照してください。
