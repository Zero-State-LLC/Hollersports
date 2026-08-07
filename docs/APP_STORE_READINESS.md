# App Store readiness (Apple scrutiny)

HollerSports today is primarily a **local Python + Next.js operator workbench**, not a shipping iOS binary. This checklist maps **App Store Review Guidelines** pressure points onto the product so a future iOS / Mac Catalyst / WebView shell does not fail review on gambling-adjacent grounds.

**Related:** [legal/](legal/README.md) · [SYSTEM_CONTRACT.md](SYSTEM_CONTRACT.md)

---

## Reviewer narrative (paste into App Review notes)

```text
HollerSports is a paper-only sports market intelligence and advisory workbench.
It does not accept real money, does not place wagers, and does not connect to
sportsbooks for execution. “Book”, stake, bankroll, PnL, and ROI refer to
paper simulation used to score advisory quality. Users must acknowledge
age (18+/21+ where applicable) and jurisdiction notices on first launch.
No IAP, no ads, no account required for the default local product.
```

---

## Guideline map

| Apple area | Risk for HollerSports | Current posture | Before consumer ship |
|------------|----------------------|-----------------|----------------------|
| **5.3 Gambling** | Tip/advisory apps can be treated as gambling-related | No real money; guards + CI ban live UX | Confirm category; age rating 17+; no Kids |
| **2.3 Accurate metadata** | “Book”, ROI, win language can mislead | Paper labels in UI + README | Store screenshots must say **paper/sim** |
| **3.1.1 IAP** | Virtual currency for real-world gambling forbidden patterns | No IAP in product | Do not sell “credits” redeemable for real bets |
| **5.1.1 Privacy** | Required privacy policy URL | Draft [legal/PRIVACY.md](legal/PRIVACY.md) | Host policy URL; fill App Privacy labels |
| **1.1.6 False claims** | Guaranteed picks / “lock of the day” | Contract forbids invented certainty | Ban guarantee language in ASO + creatives |
| **4.2 Minimum functionality** | Empty shell / demo-only | Full operator loop on fixtures | Ship offline fixture path for reviewers |
| **Safety / age** | Under-age access | First-run compliance gate | Keep gate; consider server-side age if multi-user |

---

## Copy rules (store + in-app)

### Prefer

- “Paper simulation”, “advisory candidates”, “market intelligence”  
- “Simulated stake / paper portfolio”  
- “Past paper performance is not a prediction of future results”  
- “Not a sportsbook · no real money”  

### Avoid (store and marketing)

- “Place bet”, “cash out”, “deposit”, “withdraw”, “sure win”, “lock”, “guaranteed ROI”  
- Bare “ROI +45%” without **paper**, **sample size**, and **date**  
- Implying licensed sportsbook status  
- Kids / family positioning  

### UI naming note

Nav label **Book** means **paper book / ticket book**, not a sportsbook. Always pair with lede: “Advisory candidates only — paper sim… No book placement.” Do not rename routes without a design pass; do strengthen surrounding copy (done in Workbench).

---

## Engineering guardrails (must stay green)

| Guard | Location |
|-------|----------|
| Forbidden strings `Place bet` \| `LIVE_APPROVED` \| `placeBet` | `.github/workflows/ci.yml` + packet locks |
| `capital_authority` / `execution_authority` always false | API deps + smoke scripts |
| Mode never `LIVE_APPROVED` | `packages/hollersports` |
| First-run compliance acknowledgment | `packages/operator-web` `ComplianceGate` |

Expand CI greps when new risky phrases appear in marketing.

---

## Pre-submission checklist (iOS / Mac)

### Product

- [ ] Offline fixture day runs without network (reviewer path)  
- [ ] First-run age + jurisdiction + paper-only acknowledgment required  
- [ ] Every performance surface shows **paper/sim** + sample size  
- [ ] No live book deep links that complete a wager  

### Legal / ASC

- [ ] Hosted Privacy Policy URL  
- [ ] Terms URL  
- [ ] Age rating questionnaire completed (expect 17+)  
- [ ] App Privacy nutrition labels match reality (network, none if fully offline build)  
- [ ] Support URL / contact  

### Metadata

- [ ] Subtitle avoids “casino / real money sportsbook” unless licensed  
- [ ] Description opens with paper-only sentence  
- [ ] Screenshots watermarked or captioned “Paper simulation — no real money”  
- [ ] Review notes include the narrative block above  
- [ ] Demo account N/A if no login — document fixture steps  

### Build hygiene

- [ ] No test “Place bet” strings in Release  
- [ ] No unused gambling payment SDKs  
- [ ] Encryption export answers accurate  
- [ ] Version / build monotone  

---

## Explicit non-claims (keep forever unless counsel rewrites contract)

- Not a licensed sportsbook  
- Not a payment or wallet product  
- Not financial advice  
- Not guaranteed alpha / edge  

---

## If Apple rejects

Typical fixes:

1. Soften subtitle/description away from “betting app” → “sports market paper simulator”  
2. Add more in-UI disclaimers on ROI tables  
3. Raise age rating / add parental gate if required  
4. Provide screen recording of fixture-only paper loop  
5. Confirm no external URL that completes a real wager  

Do **not** “fix” rejection by adding real-money placement.
