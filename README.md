# SimplePub

A simple, single-user EPUB reader web application built with Flask. SimplePub uniquely extracts EPUB files as ZIP archives and renders the contained HTML/CSS/images directly in the browser without specialized EPUB libraries.

## Features

- Upload and read EPUB files directly in your browser
- File-based storage (no database required)
- Automatic extraction of EPUB contents
- Chapter-based navigation
- Table of contents support
- Reading progress tracking
- Customizable reading experience (font size, line height, theme)
- Responsive design

## Requirements

- Python 3.13+
- Flask 3.1.0+

## Installation

Clone the repository and install dependencies:

```bash
# Setup Poetry environment
poetry install

# Activate the virtual environment
source .venv/bin/activate
```

## Usage

Run the application with:

```bash
python app.py
```

Then open your browser and navigate to:
```
http://localhost:5050
```

## How It Works

SimplePub approaches EPUB reading differently from most readers:

1. EPUBs are uploaded and extracted as ZIP archives
2. Content is served directly to the browser
3. HTML/CSS/images from the EPUB are displayed natively
4. Reading position is tracked and saved automatically
5. All data is stored in simple files (no database)

## Project Structure

- `/templates` - HTML templates for the application
- `/static` - CSS styles and client-side scripts
- `/uploads` - Temporary storage for uploaded EPUB files
- `/extracted` - Extracted EPUB content
- `/progress` - Reading progress tracking files

## use with poetry and python3.13

after install of python3.13 run poetry installer via python3.13

```bash
python3.13 -m poetry install
```

then run

```bash
poetry env use python3.13
poetry init
poetry install
poetry env activate
```
then copy terminal output to activate environment

```

