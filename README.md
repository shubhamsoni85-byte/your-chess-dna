# Your Chess DNA — Public Beta

A zero-paid-API public Streamlit MVP.

## Local Windows test

```cmd
cd /d "C:\Personal Documents\chess_coach_public_v2"
pip install -r requirements.txt
python -m streamlit run app.py
```

The app automatically checks:
`C:\stockfish\stockfish-windows-x86-64-universal.exe`

You can also set `STOCKFISH_PATH`.

## Free public deployment

1. Create a GitHub repository.
2. Upload this project preserving the `engine/` folder.
3. Deploy `app.py` on Streamlit Community Cloud.
4. `packages.txt` installs the Linux `stockfish` package on the host.
5. Share the resulting `*.streamlit.app` URL.

## Architecture

Chess.com public games / PGN
→ Stockfish depth-13 scan
→ board/candidate feature extraction
→ selective depth-18 verification
→ deterministic evidence-backed diagnosis
→ cross-game pattern aggregation
→ report
→ training from the player's own positions

No paid LLM or external AI API is required.

## Important interpretation rule

The app reports evidence-backed coaching hypotheses, not direct observations of the player's thought process. A label is not assigned solely because a move lost evaluation; narrower labels require supporting board/engine features.
