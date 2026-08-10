# Hollersports

A Sports Wagering assistant that uses Abraxas Symbolic intelligence engine and utilizes ABX-Core.

## Overview

HollerSports is a deterministic, provenance-tracked betting engine that prevents slate leakage and ensures reproducible analysis. Built with ABX-Core compliance, it provides:

- **State Isolation**: Each slate gets fresh state with no carryover from prior runs
- **Provenance Tracking**: Complete audit trail of all inputs and transformations
- **Deterministic Processing**: Same inputs always produce same outputs
- **Controlled Calibration**: Explicit opt-in for cross-slate adjustments

## Architecture

```
engine/
├── reset_state.py       # Core state management (prevents slate leakage)
├── slate_runner.py      # Main orchestrator
├── simulation.py        # Monte Carlo simulation engine
└── picks_generator.py   # Pick selection and optimization

tests/
└── test_state_isolation.py   # State isolation verification

examples/
└── basic_usage.py       # Usage examples
```

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/scrimshawlife-ctrl/Hollersports.git
cd Hollersports

# Install dependencies
pip install -r requirements.txt
```

### Basic Usage

```python
from engine.slate_runner import SlateRunner
from engine.reset_state import make_market_key

# Define slate inputs
games_payload = {
    "games": [
        {
            "game_id": "NBA_20251217_LAL_BOS",
            "home_team": "BOS",
            "away_team": "LAL",
            "venue": "home",
        }
    ]
}

lines_payload = {
    make_market_key("NBA", "NBA_20251217_LAL_BOS", "player_123", "PTS", 25.5, "OVER"): {
        "sport": "NBA",
        "game_id": "NBA_20251217_LAL_BOS",
        "player_id": "player_123",
        "player_name": "LeBron James",
        "market": "PTS",
        "line": 25.5,
    }
}

# Initialize runner
runner = SlateRunner(
    slate_id="NBA_2025-12-17_EVENING",
    sport="NBA",
    provider="PrizePicks",
    games_payload=games_payload,
    lines_payload=lines_payload,
)

# Run full pipeline
results = runner.run_full_pipeline(
    sim_iterations=10000,
    pick_strategy="edge",
    min_edge=0.05,
)

print(f"Generated {len(results['picks'])} picks")
```

### Run Example

```bash
python examples/basic_usage.py
```

## Key Features

### 1. State Isolation

Every slate gets a fresh `RunState` with no artifacts from previous slates:

```python
state = init_new_slate_state(
    slate_id="NBA_2025-12-17_EVENING",
    sport="NBA",
    provider="PrizePicks",
    games_payload=games,
    lines_payload=lines,
)
```

### 2. Input Validation

Prevent accidental reuse of stale state:

```python
# Raises RuntimeError if inputs don't match state
assert_state_matches_inputs(
    state,
    games_payload=games,
    lines_payload=lines,
    provider="PrizePicks",
)
```

### 3. Provenance Tracking

Complete audit trail of all processing:

```python
print(state.provenance["reset_policy"])
# {
#   "no_slate_bleed": True,
#   "keep_calibration_memory": False,
#   "calibration_merge_mode": "discard"
# }
```

### 4. Controlled Calibration

Opt-in calibration memory with explicit control:

```python
runner = SlateRunner(
    ...,
    keep_calibration_memory=True,  # Must be explicit
    prior_calibration=previous_calibration,
)
```

## Documentation

- **[Integration Guide](INTEGRATION_GUIDE.md)**: Comprehensive integration documentation
- **[API Reference](engine/)**: Inline documentation in each module
- **[Examples](examples/)**: Working code examples

## Testing

Run the test suite to verify state isolation:

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test
python -m pytest tests/test_state_isolation.py -v

# Run with coverage
python -m pytest tests/ --cov=engine --cov-report=html
```

## Development

### Project Structure

```
Hollersports/
├── engine/                  # Core engine modules
│   ├── __init__.py
│   ├── reset_state.py      # State management
│   ├── slate_runner.py     # Main orchestrator
│   ├── simulation.py       # Monte Carlo engine
│   └── picks_generator.py  # Pick selection
├── tests/                   # Test suite
│   ├── __init__.py
│   └── test_state_isolation.py
├── examples/                # Usage examples
│   ├── __init__.py
│   └── basic_usage.py
├── INTEGRATION_GUIDE.md    # Integration documentation
├── requirements.txt        # Python dependencies
├── LICENSE
└── README.md
```

### Core Principles

1. **No Slate Leakage**: Each slate is processed independently
2. **Determinism**: Same inputs → same outputs
3. **Provenance**: Full audit trail of all transformations
4. **ABX-Core Compliance**: No mock placeholders, explicit semantics

## Integration Points

### Custom Simulation Engine

Replace placeholder simulation logic in `engine/simulation.py`:

```python
def _get_player_base_stats(sport, player_id, market_type, sim_engine):
    if sim_engine and hasattr(sim_engine, "get_player_stats"):
        return sim_engine.get_player_stats(sport, player_id, market_type)

    # Your custom logic here
    return {"mean": 20.0, "std": 6.0}
```

### Custom Pick Selection

Extend pick selection in `engine/picks_generator.py`:

```python
def select_optimal_picks(state, strategy="edge", min_edge=0.05):
    # Your custom pick selection logic
    for market_key, sim_result in state.simulations.items():
        # Calculate edges, apply filters, etc.
        pass
```

### Custom Game Context

Implement game context computation in `engine/slate_runner.py`:

```python
def compute_game_context(self):
    for game in self._games_payload.get("games", []):
        context = {
            # Your custom context factors
            "venue": game.get("venue"),
            "pace_factor": compute_pace_factor(game),
            "defensive_rating": get_defensive_rating(game),
        }
        self.state.game_context.by_game_id[game["game_id"]] = context
```

## License

See [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please ensure:

1. All tests pass: `python -m pytest tests/`
2. State isolation is maintained
3. Provenance tracking is preserved
4. Documentation is updated

## Support

For issues, questions, or feature requests, please open an issue on GitHub.

## Roadmap

- [ ] Integration with real player databases
- [ ] ABX-Core symbolic engine connection
- [ ] Advanced calibration strategies
- [ ] Backtest framework with result tracking
- [ ] Real-time line monitoring
- [ ] Multi-provider support
- [ ] Bankroll management optimization
- [ ] Web UI dashboard


## License

Copyright © 2026 Zero State LLC. All Rights Reserved. Licensed under the Zero State Proprietary License v1.0. See [`LICENSE`](LICENSE).

Third-party components remain subject to their respective licenses.
