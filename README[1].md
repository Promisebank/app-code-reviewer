# AI Code Reviewer

Paste Python or JavaScript, get an annotated review (bugs, security, efficiency, readability, best practices).

## Run locally
```
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...        # Windows PowerShell: $env:OPENAI_API_KEY="sk-..."
streamlit run app.py
```

## Deploy on Streamlit Cloud
1. Create a GitHub repo and upload everything in this folder. NEVER upload your API key.
2. Go to share.streamlit.io, sign in with GitHub, click "Create app".
3. Pick your repo, branch `main`, main file `app.py`.
4. Open "Advanced settings" > "Secrets" and paste:  `OPENAI_API_KEY = "sk-..."`
5. Click Deploy. Your public link appears in 1-3 minutes.

## Run the benchmark
1. Review each file in `benchmark/snippets/` yourself first. Note the time you take.
2. Edit `benchmark/manual_reviews.json` with your findings and times.
3. Run: `python benchmark/benchmark.py` (needs OPENAI_API_KEY)
4. Read `benchmark/summary.md` and `benchmark/results.csv`.
