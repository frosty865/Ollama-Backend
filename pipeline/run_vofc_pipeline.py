import subprocess, json
from heuristic_pipeline import process_submission

prompt = input("Enter your document text or prompt:\n\n")

# Step 1: Run Ollama model
result = subprocess.run(
    ["ollama", "run", "vofc-heuristic", "--prompt", prompt],
    capture_output=True,
    text=True
)

# Step 2: Post-process with heuristic parser
output = result.stdout.strip()
structured = process_submission("manual-test", output, dry_run=True)

# Step 3: Print results
print(json.dumps(structured, indent=2))
