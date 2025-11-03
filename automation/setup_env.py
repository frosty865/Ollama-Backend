#!/usr/bin/env python3
"""
Helper script to create .env file from template.
"""

import os

ENV_TEMPLATE = """# Ollama Configuration
OLLAMA_URL=https://ollama.frostech.site

# Supabase Configuration
SUPABASE_URL=https://YOURPROJECT.supabase.co
SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_KEY

# Folder Configuration - Uses data directory (aligned with Flask server)
WATCH_FOLDER=C:/Users/frost/AppData/Local/Ollama/data/incoming
PROCESSED_FOLDER=C:/Users/frost/AppData/Local/Ollama/data/processed
ERROR_FOLDER=C:/Users/frost/AppData/Local/Ollama/data/errors
LIBRARY_FOLDER=C:/Users/frost/AppData/Local/Ollama/data/library
LOG_DIR=C:/Users/frost/AppData/Local/Ollama/automation/logs

# Model Configuration
MODEL=vofc-engine

# Optional: Processing Settings
LOG_LEVEL=INFO
"""

def main():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    
    if os.path.exists(env_path):
        print(f".env file already exists at {env_path}")
        response = input("Overwrite? (y/N): ")
        if response.lower() != 'y':
            print("Skipping .env creation")
            return
    
    with open(env_path, 'w') as f:
        f.write(ENV_TEMPLATE)
    
    print(f"✅ Created .env file at {env_path}")
    print("⚠️  Please edit .env and update SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")

if __name__ == "__main__":
    main()

