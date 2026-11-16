# SnapText

Copy text from anywhere on your screen: press a hotkey, drag a box, paste.

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![Platform: Windows](https://img.shields.io/badge/platform-Windows-0078D6)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
[![Tests](https://github.com/snasereddin2009-hue/snaptext/actions/workflows/tests.yml/badge.svg)](https://github.com/snasereddin2009-hue/snaptext/actions/workflows/tests.yml)

<!-- TODO: add a recording at docs/demo.gif and uncomment:
![SnapText demo](docs/demo.gif)
-->

SnapText is a small Windows tray app for text you cannot select: images, videos,
PDF scans, error dialogs, remote desktops. It screenshots the region you drag
over, runs OCR on it locally with [Tesseract](https://github.com/tesseract-ocr/tesseract),
and puts the result on your clipboard.

## Features

- **Global hotkey** (default `Ctrl+Shift+T`), configurable
- **Drag-to-select overlay** that is DPI aware and spans every monitor, including
  mixed scaling and monitors left of or above the primary one
- **Image preprocessing** before OCR (greyscale, dark-mode inversion, upscaling,
  Otsu thresholding) to improve accuracy on screen text
- **Clipboard and notification**: the text is copied and a "Copied!" toast confirms it
- **System tray icon** with Capture, Open Config and Quit
- **Config file** created with defaults on first run
- **File logging** with rotation
- **Single instance**: a second launch exits instead of registering the hotkey twice
- **Offline**: nothing leaves your machine
- **Benchmark tooling** to measure what preprocessing buys you

## Installation

### 1. Install Tesseract

SnapText needs the Tesseract OCR engine installed separately.

```powershell
winget install --id UB-Mannheim.TesseractOCR
```

Or download the installer from the
[UB Mannheim Tesseract page](https://github.com/UB-Mannheim/tesseract/wiki).
SnapText finds Tesseract on `PATH` or in its default install folder. Extra
languages can be selected in the installer.

### 2. Install SnapText

Requires Windows 10 or 11 and Python 3.11 or newer.

```powershell
git clone https://github.com/snasereddin2009-hue/snaptext.git
cd snaptext
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
```

## Usage

```powershell
python -m snaptext
```

SnapText starts in the system tray.

1. Press `Ctrl+Shift+T`, or click the tray icon.
2. Drag a box around the text. Press `Esc` to cancel.
3. Paste. The recognised text is on your clipboard.

Right-click the tray icon for **Capture**, **Open Config** and **Quit**.
Use `pythonw -m snaptext` to run without a console window.

### Standalone executable

Build a single `SnapText.exe` that runs without Python (Tesseract is still required):

```powershell
python -m pip install -e ".[build]"
python -m PyInstaller --noconfirm --onefile --windowed --name SnapText --paths src src/snaptext/__main__.py
```

The executable is written to `dist\SnapText.exe`.

## Configuration

The config file is created on first run at `%APPDATA%\SnapText\config.toml`.
Open it from the tray menu with **Open Config**, and restart SnapText after editing.

```toml
hotkey = "ctrl+shift+t"
language = "eng"
preprocess = true
```

| Key | Default | Description |
| --- | --- | --- |
| `hotkey` | `"ctrl+shift+t"` | Global capture hotkey. Modifiers: `ctrl`, `shift`, `alt`, `win`. Keys: `a`-`z`, `0`-`9`, `f1`-`f24`, and names such as `space`, `tab`, `insert`, `printscreen`. |
| `language` | `"eng"` | Tesseract language code. Combine several with `+`, for example `"eng+deu"`. The language data must be installed. |
| `preprocess` | `true` | Clean up the screenshot before OCR. |

If the file is invalid, or the hotkey is malformed or already taken by another
application, SnapText says so in a notification and keeps running: defaults are
used for a broken file, and capture stays available from the tray menu.

Logs are written to `%APPDATA%\SnapText\snaptext.log`.

## How it works

```text
hotkey / tray ──> overlay ──> capture ──> preprocessing ──> OCR ──> clipboard ──> notification
```

| Module | Responsibility |
| --- | --- |
| `app.py` | Wires the pipeline together and owns the UI thread |
| `hotkey.py` | Global hotkeys via the Win32 `RegisterHotKey` API |
| `overlay.py` | Fullscreen Tk window for dragging out a region |
| `capture.py` | Monitor geometry and region screenshots (mss) |
| `preprocessing.py` | Greyscale, inversion, upscaling, thresholding (Pillow) |
| `ocr.py` | Tesseract wrapper and error translation (pytesseract) |
| `clipboard.py` | Clipboard access (pyperclip) |
| `tray.py` | Tray icon, menu and notifications (pystray) |
| `config.py` | Config schema, validation and file locations |
| `single_instance.py` | Named-mutex guard against a second instance |
| `metrics.py` | Character and word accuracy for the benchmark |

A few design decisions worth knowing about:

- **Threading.** Tk must stay on the main thread, while the hotkey listener and
  tray icon each need their own message loop and OCR is slow enough to deserve a
  worker. Those threads never touch Tk; they post tasks to a queue that the Tk
  event loop drains.
- **DPI awareness.** The process opts in to per-monitor DPI awareness before any
  window exists, so the overlay and the screenshot share one coordinate system:
  physical pixels of the virtual screen. Without it, Windows would scale the
  overlay and selections would be offset on scaled displays.
- **Native hotkeys.** `RegisterHotKey` consumes the key combination, so
  `Ctrl+Shift+T` does not also reach the focused application, and it needs no
  keyboard hook.
- **Preprocessing.** Tesseract expects dark text on a light background at print
  resolution. Screen text is small and often light-on-dark, so the image is
  converted to greyscale, inverted when its background is dark, upscaled 3x and
  binarised with Otsu's method.

## Benchmark

`scripts/generate_samples.py` renders known text in several fonts, sizes and
colour themes; `scripts/benchmark.py` runs OCR on each image with and without
preprocessing and compares the output to the ground truth.

```powershell
python scripts/generate_samples.py --out samples
python scripts/benchmark.py samples
```

Accuracy is `1 - edit distance / length of the expected text`, computed over
characters and over words. To benchmark real screenshots, put each image in a
folder next to a `.txt` file of the same name containing its text.

| Mode | Character accuracy | Word accuracy | Avg. time per image |
| --- | --- | --- | --- |
| Raw screenshot | 98.9% | 94.0% | 103 ms |
| With preprocessing | 99.8% | 98.7% | 112 ms |

Character accuracy by category:

| Category | Images | Raw | With preprocessing |
| --- | --- | --- | --- |
| accent | 9 | 98.9% | 99.7% |
| dark | 9 | 99.3% | 99.6% |
| light | 9 | 99.2% | 100.0% |
| lowcontrast | 9 | 98.2% | 99.8% |

Measured with Tesseract `5.4.0` on 36 synthetic samples. Preprocessing cuts the
word error rate from 6.0% to 1.3% for about 9 ms extra per capture.

## Running tests

```powershell
python -m pip install -e ".[dev]"
python -m pytest
```

The tests cover configuration, preprocessing, accuracy metrics and hotkey parsing.
They do not need Tesseract.

## Roadmap

- [ ] Reload the config without restarting
- [ ] Adaptive thresholding for uneven or gradient backgrounds
- [ ] Automatic language detection
- [ ] Capture history
- [ ] Start with Windows
- [ ] Installer and signed releases

## License

[MIT](LICENSE)
