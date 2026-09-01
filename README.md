# Meme Coin Scanner (Robinhood Chain)

Scans trending/new tokens on Robinhood Chain (including Long.xyz launches) and
scores them by Reddit + X (Twitter) social momentum, sentiment, and on-chain
liquidity/volume growth.

> **This is a signal tool, not a profit predictor.** It surfaces early attention
> and momentum spikes only. Meme coins are extremely high risk and most go to
> zero. Never treat output from this tool as financial advice.

## What it does

1. Pulls trending Robinhood Chain token pools via CoinGecko's onchain API.
2. Searches Reddit (r/CryptoCurrency, r/SatoshiStreetBets, r/CryptoMoonShots,
   r/solana, r/memecoins) for recent mentions of each ticker.
3. Searches X for recent posts mentioning each ticker.
4. Scores sentiment on collected text with VADER.
5. Combines everything into a composite score: 40% social velocity, 25%
   sentiment, 20% on-chain liquidity, 15% price momentum.
6. Outputs a ranked leaderboard to `ranked_tokens.csv`.

## Setup

### 1. Add repository secrets

Go to **Settings -> Secrets and variables -> Actions -> New repository secret**
and add:

| Secret | Where to get it |
|---|---|
| `REDDIT_CLIENT_ID` | reddit.com/prefs/apps (free) |
| `REDDIT_CLIENT_SECRET` | reddit.com/prefs/apps (free) |
| `REDDIT_USER_AGENT` | any string, e.g. `meme-coin-scanner/0.1 by u/yourusername` |
| `X_BEARER_TOKEN` | developer.x.com -- free tier is very rate-limited, paid Basic tier ($200/mo) recommended for real volume |
| `COINGECKO_API_KEY` | coingecko.com/en/api -- free demo key works |

### 2. Run it

- **Automatically**: the included GitHub Actions workflow (`.github/workflows/scan.yml`)
  runs every 6 hours and commits the updated `ranked_tokens.csv` back to this repo.
- **Manually**: go to the **Actions** tab -> **Meme Coin Scanner** -> **Run workflow**.
- **Locally**:
  ```bash
  pip install -r requirements.txt
  # create a .env file with the same keys as above
  python meme_scanner.py
  ```

## Tuning

Edit the weights in `compute_composite_score()` inside `meme_scanner.py` to
change how much social velocity vs. sentiment vs. on-chain liquidity matters
to you.
