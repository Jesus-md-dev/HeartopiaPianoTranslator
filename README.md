# Heartopia Piano Translator

Windows desktop app that converts Heartopia music page notation into the translated piano key format.

## Download EXE

[Download HeartopiaPianoTranslator.exe](https://github.com/Jesus-md-dev/HeartopiaPianoTranslator/raw/main/dist/HeartopiaPianoTranslator.exe)

## Included

- `HEARTOPIA_PIANO_TRANSLATOR.py`: source code
- `HeartopiaPianoTranslator.spec`: PyInstaller build file
- `dist/HeartopiaPianoTranslator.exe`: standalone Windows executable

## Features

- Paste a Heartopia music page URL and translate it
- Open the official music page from the launcher
- Toggle the launcher UI between English and Spanish
- Show the translated result in a separate always-on-top window

## Build

```powershell
python -m PyInstaller --noconfirm --onefile --windowed --name HeartopiaPianoTranslator HEARTOPIA_PIANO_TRANSLATOR.py
```
