# Privacy Policy (HollerSports)

**Status:** Draft for local / internal advisory beta. Publish a hosted URL before any App Store consumer listing.  
**Owner:** Zero State / product operator  
**Last updated:** 2026-08-07

## Summary

HollerSports is designed as a **local operator tool**. The default configuration does **not** require user accounts, does **not** process payments, and does **not** place sportsbook wagers.

## Data the product may process

| Category | Examples | Where it stays (default) |
|----------|----------|---------------------------|
| Sports market observations | Odds, lines, event IDs, source health | Local process / operator-chosen storage |
| Paper simulation metrics | Paper stake, sim PnL, sim ROI, hit rate | Local ledgers / JSONL |
| Calibration evidence | Settlement bank rows, reliability flags | Local |
| Optional network sources | ESPN free endpoints; Odds API if operator sets a key | Transient HTTP; key held in operator env only |
| UI session cache | Last competition packet in browser `sessionStorage` | Local browser |

## Data we do not process in the current product

- Payment cards, bank accounts, or wallets  
- Sportsbook login credentials  
- Real-money deposit / withdrawal flows  
- Precise continuous location tracking  
- Advertising ID / ATT tracking (no ad SDK in this repo)  
- Child-directed data collection (product is **not** for under-age users — see [AGE_AND_JURISDICTION.md](AGE_AND_JURISDICTION.md))

## Third parties

- **Optional:** The Odds API (if the operator configures a key) — subject to that vendor’s terms.  
- **Optional:** ESPN public scoreboard / free endpoints for observation and settlement — public web content; no account.  
- No analytics SDK is required for core paper operation.

## Operator responsibilities

If you deploy HollerSports beyond a personal machine (hosted API, multi-user, cloud logs), **you** become the controller for that deployment: publish your own privacy notice, retention policy, and access controls.

## Contact

For privacy questions about this repository’s default product, contact the repository owner / Zero State.

## Changes

Material changes to data practices should bump this document’s date and, if listed on an app store, the App Privacy questionnaire.
