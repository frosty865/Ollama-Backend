# Ollama Automation Pipeline

Automated document processing pipeline for VOFC extraction using multiple Ollama models.

## Directory Structure

```
automation/
├── ollama_auto_processor.py     ← Watcher script (monitors incoming folder)
├── vofc_pipeline.py             ← Intelligent extraction pipeline
├── .env                         ← Configuration file (create this)
├── logs/                        ← Runtime logs
├── incoming/                    ← Drop PDF/DOCX files here
├── processed/                   ← JSON results saved here
├── errors/                      ← Failed processing moved here
└── library/                     ← Processed originals moved here
```

## Setup

### 1. Install Dependencies

```bash
pip install watchdog python-dotenv requests pdfplumber python-docx
```

### 2. Create `.env` File

Create a `.env` file in this directory with the following:

```env
# Ollama Configuration
OLLAMA_URL=https://ollama.frostech.site

# Supabase Configuration
SUPABASE_URL=https://YOURPROJECT.supabase.co
SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_KEY

# Folder Configuration
WATCH_FOLDER=C:/Users/frost/AppData/Local/Ollama/automation/incoming
PROCESSED_FOLDER=C:/Users/frost/AppData/Local/Ollama/automation/processed
ERROR_FOLDER=C:/Users/frost/AppData/Local/Ollama/automation/errors
LIBRARY_FOLDER=C:/Users/frost/AppData/Local/Ollama/automation/library
LOG_DIR=C:/Users/frost/AppData/Local/Ollama/automation/logs

# Model Configuration
MODEL=vofc-engine

# Optional: Processing Settings
LOG_LEVEL=INFO
```

### 3. Ensure Ollama is Running

Make sure Ollama is running and has these models available:
- `vofc-engine:latest`
- `mistral:latest`
- `llama3:latest`

## Usage

### Start the Watcher

```bash
cd "C:\Users\frost\AppData\Local\Ollama\automation"
python ollama_auto_processor.py
```

You should see:
```
📡 Watching folder for new files...
```

### Process a File Manually

```bash
python vofc_pipeline.py --file "path/to/document.pdf"
```

### Drop Files for Auto-Processing

1. Copy any PDF or DOCX file to the `incoming/` folder
2. The watcher will automatically:
   - Detect the new file
   - Process it with multiple Ollama models
   - Save JSON results to `processed/`
   - Move original to `library/`
   - Update Supabase with metadata
   - Move to `errors/` if processing fails

## Processing Flow

1. **File Detection**: Watcher detects new PDF/DOCX in `incoming/`
2. **Text Extraction**: Extracts text using pdfplumber or python-docx
3. **Multi-Model Processing**: Processes with 3 models in parallel:
   - `vofc-engine:latest` (primary, 60% weight)
   - `mistral:latest` (validation, 25% weight)
   - `llama3:latest` (cross-check, 15% weight)
4. **Result Combination**: Combines and deduplicates results
5. **Save Results**: Saves JSON to `processed/` folder
6. **Update Supabase**: Updates submission records
7. **Archive**: Moves original file to `library/` folder

## Logs

Logs are saved to the `logs/` directory:
- `watcher_YYYYMMDD.log` - Watcher activity
- `pipeline_YYYYMMDD.log` - Processing activity

## Troubleshooting

- **"Ollama not running"**: Start Ollama server
- **"Models not found"**: Pull required models with `ollama pull <model-name>`
- **"pdfplumber not installed"**: Run `pip install pdfplumber python-docx`
- **"File processing fails"**: Check logs in `logs/` directory

