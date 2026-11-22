# capri-animated-cursors
Free animated cursor pack for Windows
Download and extract the archive.
Go to Windows Settings -> Mouse -> Additional mouse options -> "Pointers" tab.
Select the desired mode (e.g., "Normal Select") and click "Browse."
Specify the path to the corresponding .ani file from the folder.
Repeat for all modes.

Скачайте и распакуйте архив.
Зайдите в Настройки Windows -> Мышь -> Дополнительные параметры мыши -> вкладка «Указатели».
Выберите нужный режим (например, «Обычный указатель») и нажмите «Обзор».
Укажите путь к соответствующему файлу .ani из папки.
Повторите для всех режимов

## macOS

macOS can't use `.ani` files directly, so this pack also ships as a
Mousecape theme: [`mac/Capri.cape`](mac/Capri.cape). It is animated, has
Retina (2x) artwork, and keeps the original frame timings.

1. Install a cursor app that reads `.cape` files:
   - **macOS 15 Sequoia or earlier:** [Mousecape](https://github.com/alexzielenski/Mousecape/releases)
   - **macOS 26 Tahoe:** the original Mousecape doesn't work on Tahoe. Use
     [MaCursor](https://github.com/writronic/MaCursor), which imports `.cape` themes.
2. Open the app and import `mac/Capri.cape` (drag it in, or **File → Import**).
3. Select **Capri Animated** and click **Apply**.

How the Windows cursors map to macOS:

| Windows file | macOS cursor |
|---|---|
| `NormalSelect.ani` | Arrow (including Tahoe's new arrow) |
| `text select.ani` | I-beam (text) |
| `LinkSelect.ani` | Pointing hand (links) |
| `Busy.ani` | Wait / busy |
| `Move.ani` | Move |
| `horizontal.ani` | Left/right resize |
| `vertical.ani` | Up/down resize |
| `diagonal resize1.ani` | NW–SE window resize |
| `diagonal resize2.ani` | NE–SW window resize |

To rebuild the theme after editing the `.ani` files, run this script. It
needs Python 3 and no extra packages. If Python isn't installed yet, macOS
offers to install it the first time you run `python3`.

```bash
python3 mac/ani2cape.py
```

Add `--preview` to also write PNG frame strips to `mac/preview/`.
