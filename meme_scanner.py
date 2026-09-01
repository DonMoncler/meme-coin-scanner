"""
Robinhood Chain Meme Coin Social Signal Scanner
-------------------------------------------------
Scans new/trending tokens on Robinhood Chain (incl. Long.xyz launches) and
scores them by Reddit + X (Twitter) social momentum and sentiment, combined
with on-chain liquidity/volume growth.

THIS IS A SIGNAL TOOL, NOT A PROFIT PREDICTOR. It surfaces early attention
and momentum spikes -- it does NOT guarantee any coin will be profitable.
Meme coins are extremely high risk; most go to zero. Use this as one input
among many, never as financial advice.

SETUP
-----
pip install -r requirements.txt

Set environment variables (locally via .env, or as GitHub Actions secrets):
    REDDIT_CLIENT_ID
    REDDIT_CLIENT_SECRET
    REDDIT_USER_AGENT
    X_BEARER_TOKEN
    COINGECKO_API_KEY   (optional, free demo key works with lower rate limits)

Run:
    python meme_scanner.py
Output:
    ranked_tokens.csv  -- sorted leaderboard of tokens by composite signal score
"""

import os
import time
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from dotenv import load_dotenv

load_dotenv()

REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "meme-coin-scanner/0.1")
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")

CRYPTO_SUBREDDITS = ["CryptoCurrency", "SatoshiStreetBets", "CryptoMoonShots", "solana", "memecoins"]
MAX_TOKENS_TO_SCAN = 25          # how many trending Robinhood Chain tokens to pull
REDDIT_LOOKBACK_HOURS = 48
X_LOOKBACK_HOURS = 48            # X recent-search endpoint only covers last 7 days max

analyzer = SentimentIntensityAnalyzer()


def get_robinhood_chain_tokens(limit=MAX_TOKENS_TO_SCAN):
    """
    Pull trending/new tokens on Robinhood Chain via CoinGecko's onchain API.
    Docs: https://www.coingecko.com/en/api/robinhood
    """
    url = "https://api.coingecko.com/api/v3/onchain/networks/robinhood-chain/trending_pools"
    headers = {"x-cg-demo-api-key": COINGECKO_API_KEY} if COINGECKO_API_KEY else {}
    params = {"page": 1}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except Exception as e:
        print(f"[warn] CoinGecko fetch failed: {e}")
        return []

    tokens = []
    for pool in data[:limit]:
        attrs = pool.get("attributes", {})
        name = attrs.get("name", "")
        base_symbol = name.split("/")[0].strip() if "/" in name else name
        tokens.append({
            "symbol": base_symbol,
            "name": name,
            "pool_address": attrs.get("address"),
            "volume_24h_usd": float(attrs.get("volume_usd", {}).get("h24", 0) or 0),
            "liquidity_usd": float(attrs.get("reserve_in_usd", 0) or 0),
            "price_change_24h_pct": float(attrs.get("price_change_percentage", {}).get("h24", 0) or 0),
        })
    return tokens


def get_reddit_client():
    import praw
    return praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent=REDDIT_USER_AGENT,
    )


def scan_reddit_mentions(reddit, ticker, name):
    """Search recent posts across target subreddits mentioning the ticker or name."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=REDDIT_LOOKBACK_HOURS)
    mentions = []
    query = f'"{ticker}" OR "{name}"'
    for sub in CRYPTO_SUBREDDITS:
        try:
            for submission in reddit.subreddit(sub).search(query, sort="new", time_filter="week", limit=30):
                created = datetime.fromtimestamp(submission.created_utc, tz=timezone.utc)
                if created < cutoff:
                    continue
                text = f"{submission.title} {submission.selftext or ''}"
                mentions.append({
                    "text": text,
                    "score": submission.score,
                    "created": created,
                })
        except Exception as e:
            print(f"[warn] Reddit search failed for r/{sub} ({ticker}): {e}")
        time.sleep(1)  # basic rate-limit courtesy
    return mentions


def scan_x_mentions(ticker):
    """Search recent X posts mentioning the ticker via X API v2 recent search."""
    if not X_BEARER_TOKEN:
        return []
    url = "https://api.x.com/2/tweets/search/recent"
    headers = {"Authorization": f"Bearer {X_BEARER_TOKEN}"}
    params = {
        "query": f"${ticker} OR #{ticker} -is:retweet lang:en",
        "max_results": 50,
        "tweet.fields": "created_at,public_metrics",
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except Exception as e:
        print(f"[warn] X search failed for {ticker}: {e}")
        return []

    mentions = []
    for tweet in data:
        mentions.append({
            "text": tweet.get("text", ""),
            "likes": tweet.get("public_metrics", {}).get("like_count", 0),
            "created": tweet.get("created_at"),
        })
    return mentions


def score_sentiment(texts):
    if not texts:
        return 0.0
    scores = [analyzer.polarity_scores(t)["compound"] for t in texts]
    return sum(scores) / len(scores)


def compute_composite_score(row):
    """
    Weighted composite: social velocity (40%), sentiment (25%),
    on-chain liquidity (20%), volume/price momentum (15%).
    Tune weights based on your own risk appetite.
    """
    social_velocity = row["reddit_mentions"] + row["x_mentions"]
    velocity_score = min(social_velocity / 20, 1.0) * 40      # cap at 20 mentions = max score
    sentiment_score = ((row["avg_sentiment"] + 1) / 2) * 25   # normalize -1..1 to 0..1
    liquidity_score = min(row["liquidity_usd"] / 50000, 1.0) * 20
    momentum_score = min(max(row["price_change_24h_pct"], 0) / 50, 1.0) * 15
    return round(velocity_score + sentiment_score + liquidity_score + momentum_score, 2)


def main():
    print("Fetching trending Robinhood Chain tokens...")
    tokens = get_robinhood_chain_tokens()
    if not tokens:
        print("No tokens returned -- check API key / network access.")
        return

    reddit = None
    if REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET:
        reddit = get_reddit_client()
    else:
        print("[warn] Reddit credentials missing -- skipping Reddit signal.")

    results = []
    for tok in tokens:
        ticker, name = tok["symbol"], tok["name"]
        print(f"Scanning social signal for {ticker}...")

        reddit_mentions = scan_reddit_mentions(reddit, ticker, name) if reddit else []
        x_mentions = scan_x_mentions(ticker)

        all_texts = [m["text"] for m in reddit_mentions] + [m["text"] for m in x_mentions]
        avg_sentiment = score_sentiment(all_texts)

        row = {
            **tok,
            "reddit_mentions": len(reddit_mentions),
            "x_mentions": len(x_mentions),
            "avg_sentiment": round(avg_sentiment, 3),
        }
        row["composite_score"] = compute_composite_score(row)
        results.append(row)
        time.sleep(1)

    df = pd.DataFrame(results).sort_values("composite_score", ascending=False)
    df.to_csv("ranked_tokens.csv", index=False)
    print("\nDone. Top signals:")
    print(df[["symbol", "composite_score", "reddit_mentions", "x_mentions",
              "avg_sentiment", "liquidity_usd", "price_change_24h_pct"]].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
