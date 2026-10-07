# Demo & Recording Guide

## 1. Setup (5 minutes, needs internet)
```
pip install -r requirements.txt
python test_shield.py                      # should print "All tests passed."
python shield.py "pip install requests"    # live check against PyPI
streamlit run app.py                       # opens the web demo in your browser
```
If the live command prints [ALLOW] for `requests`, everything works.

## 2. Make the demo REAL (important)
`hallucinated_names.json` contains SAMPLE names only. Before recording:
1. Ask ChatGPT / Gemini / Claude ~30 coding questions
   ("how to read PDF in Python", "send email in Python", "scrape a website", "parse Excel", ...).
2. Copy every package name from `pip install ...` lines into one list.
3. Run each through the tool: `python shield.py "pip install <name>"`.
4. Any that print [BLOCK] "does NOT exist" are REAL hallucinations. Add them to
   `hallucinated_names.json` and screenshot the AI's reply showing that invented name.
Use the real ones in your recording. The "does not exist" check is live, so it
always reflects reality; never claim a name is fake without running it first.

## 3. Recording script (about 2 minutes)
1. (15s) Show the problem: screenshot/clip of an AI suggesting a package that doesn't exist.
2. (15s) Say: "A hacker can register that name with a virus. Anyone who copies the command gets infected."
3. (30s) Open the web demo, paste a command with one safe + one invented package. Show green and red results and the "Did you mean".
4. (20s) Point at the score reasons: new, no repo, in hallucination DB.
5. (20s) Show your harvested list of real hallucinated names.
6. (20s) Say future scope: VS Code plugin, CI check, more languages.

Tips: increase browser zoom to 125%, use a dark-free clean desktop, test once before recording.
