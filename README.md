# NotifyXSOverlay

Windowsの通知をXSOverlayへ中継し、VR内で確実に視認できるようにするツールです。
通知元アプリのフィルタリングを中核機能とします。

## やること
- Windows通知の取得、整形、XSOverlayへの送信を安定動作させる。
- 通知元アプリの許可/拒否フィルタを提供し、ユーザーが安全に制御できるようにする。
- 失敗時はログとリトライ方針を明確化し、静かな失敗を避ける。

## やらないこと
- Windows通知の恒久的な保存やクラウド同期。
- 通知内容の外部送信（ユーザーが明示的に有効化した場合を除く）。
- 必須ではない常駐リソースの肥大化（過剰な常駐UIや無限ループ）。

## 使い方

### 前提
- Windows 10/11
- SteamVR と XSOverlay がインストール済み
- `uv` がインストール済み（未インストールの場合は公式手順: [Installing uv](https://docs.astral.sh/uv/getting-started/installation/)）

### 1) SteamVR起動時に自動起動させる
SteamVRが起動している状態で実行してください。

```powershell
uvx --from git+https://github.com/tyunta/notifyxsoverlay notifyxsoverlay install-steamvr
```

- これにより SteamVR の Startup Overlay Apps に登録され、自動起動が有効になります。
- 起動時は `uvx --refresh` で更新を確認し、失敗時はキャッシュで起動します。
- SteamVR起動ユーザーのPATHに `uvx` が無い場合は、`--uvx-path` を指定してください。
- 解除する場合は次を実行します。

```powershell
uvx --from git+https://github.com/tyunta/notifyxsoverlay notifyxsoverlay uninstall-steamvr
```

### 2) 手動で起動する

```powershell
uvx --from git+https://github.com/tyunta/notifyxsoverlay notifyxsoverlay run
```

### フィルタ仕様（予定）
評価順と優先度は次の通りです。

1. ブロックリストに一致した通知は常に除外する。
2. 許可リストが空でない場合は、許可リストに一致した通知のみ通す。
3. 許可リストが空の場合は、ブロックリストに該当しない通知を通す。

#### 学習モード（初期運用の方針）
- 初期状態は「学習モード」を想定し、未分類の通知は一旦表示する。
- 未分類の通知元は「未分類一覧」に蓄積し、後から許可/拒否へ移動できるようにする。
- 未分類の通知は「アプリごとに1日1回だけ表示」し、同一日の2回目以降は抑制する。
- 未分類一覧は24時間でクリアし、翌日は再び初回表示される。
- 判定は厳密なアプリ識別子で行い、ユーザーには分かりやすいアプリ名も並列で表示する。

## セットアップ/運用メモ
- Windows通知リスナーはユーザー許可が必要です。
- XSOverlayとの通信は公式API（WebSocket）に準拠します。

## 仕様メモ
- アプリキー: `com.tyunta.notifyxsoverlay`
- インストール時に `notifyxsoverlay.cmd` と `notifyxsoverlay.vrmanifest` を生成します。
- 生成先は `%LOCALAPPDATA%\NotifyXSOverlay` です。
- 設定ファイルは `%LOCALAPPDATA%\NotifyXSOverlay\config.json` を想定します。




