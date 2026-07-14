#!/usr/bin/env bash
set -euo pipefail
sudo apt update
sudo apt install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-ind
printf '\nOCR installed. Test it with:\n  tesseract --list-langs\n'
