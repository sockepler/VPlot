# VPlot

アナログ回路シミュレーション波形ビューア。IEEE準拠のSI接頭辞フォーマットに対応。

Cadence Virtuoso、HSPICE、LTspiceなどのシミュレーション結果を素早く確認・論文用に出力するためのツールです。

## 特徴

- **IEEE準拠のSI接頭辞表示** — 目盛りは数値のみ（0, 5, 10...）、単位接頭辞（n, u, m...）は軸ラベルに表示（例：`time [ns]`、`[mV]`）。ズーム時に自動更新。
- **複数フォーマット対応** — CSV, VCSV (Virtuoso), PSF ASCII, TSV, DAT
- **CJK対応** — 中国語・日本語の信号名がレジェンド・ラベルに正しく表示
- **サブプロット分割・結合** — 信号を右クリックで独立サブプロットに分割（Virtuoso風）、または結合
- **信号削除** — 右クリックで個別の信号をビューから削除（Virtuoso風）
- **ラベル編集** — レジェンドのダブルクリックで名前変更、ツールバーから軸ラベル編集
- **ズーム履歴** — Back/Fwdボタンでズーム履歴を前後に移動
- **カーソル測定** — 2点クリックでΔx、Δy、周波数を表示
- **論文用エクスポート** — PNG (300 dpi)、PDF、SVG、EPS
- **スタイル設定** — フォントサイズ、線幅、太字、白黒線種、グリッド切替（スタイル変更時にズームを保持）

## インストール

### Linux

```bash
git clone https://github.com/sockepler/VPlot.git
cd VPlot
chmod +x install.sh
./install.sh
```

インストール後の起動コマンド：

```bash
vp
```

> `vp` が見つからない場合、`~/.local/bin` をPATHに追加：
> ```bash
> echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
> source ~/.bashrc
> ```

**前提条件**：tkinterが必要です：
| ディストロ | コマンド |
|---|---|
| Ubuntu / Debian | `sudo apt install python3-tk` |
| Fedora / RHEL | `sudo dnf install python3-tkinter` |
| Arch | `sudo pacman -S tk` |

### Windows

`VPlot.bat` をダブルクリックで起動できます。

または、インストールして `vp` コマンドで起動：

```cmd
pip install .
vp
```

### ソースから直接実行（インストール不要）

```bash
pip install numpy pandas matplotlib
python -m vplot
```

## 使い方

### ファイルを開く

起動後、**Open** ボタンまたは `Ctrl+O` でファイルを選択。

### 対応フォーマット

| フォーマット | 拡張子 | ソース |
|---|---|---|
| CSV | `.csv` | LTspice, HSPICE, 汎用 |
| VCSV | `.vcsv` | Cadence Virtuoso `selectResults()` |
| PSF ASCII | `.psf` | Cadence `psf2csv` 出力 |
| テキスト | `.txt .dat .tsv` | タブ/スペース/カンマ区切り |

### ツールバー

| ボタン | 機能 |
|---|---|
| **Select** | デフォルトモード — マウスオーバーで座標表示 |
| **Pan** | ドラッグで画面移動 |
| **Zoom** | 矩形ドラッグでズーム |
| **Cursor** | クリックで測定マーカー配置（最大2点） |
| **Home** | 全軸オートスケール |
| **Back / Fwd** | ズーム履歴を前後移動 |
| **PNG/PDF/SVG/EPS** | 現在の表示をエクスポート |

### レンジツールバー

- **X label / Y label**：軸ラベルのテキストを編集（Enterで適用）
- **X range / Y range**：SI接頭辞付きで値を入力（`5n`、`2.5u`、`100m`）してApplyクリック
- **Auto**：その軸をオートスケールに戻す
- **◄ ►**：サブプロット切替（Y range編集用）

### 信号パネル

- **チェックボックス**：信号の表示/非表示
- **ラベルクリック**：測定対象信号を選択
- **ラベルダブルクリック**：信号名を変更
- **右クリック**：サブプロットに分割、他のサブプロットに結合、またはビューから削除

### ショートカットキー

| キー | 機能 |
|---|---|
| `Ctrl+O` | ファイルを開く |
| `Home` | 全軸オートスケール |

## ライセンス

MIT
