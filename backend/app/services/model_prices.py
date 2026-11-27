"""Model token prices used to estimate the cost of each Agent call (USD per 1M tokens).

Source: Azure Retail Prices API (https://prices.azure.com/api/retail/prices), service "Foundry Models",
Global Standard meters, effective 2026-09-01; checked 2026-11-25. Our gpt-6-luna deployment is
GlobalStandard. If a deployment moves to Data Zone (about 10% more) or another model, update this file.

Short-context prices only: the long-context tier (roughly double) starts far above our request sizes.
Cache writes are not in the Responses API usage, so they are not counted; estimates run slightly low.
"""
from dataclasses import dataclass
from decimal import Decimal

PER_TOKENS = 1_000_000


@dataclass(frozen=True)
class ModelPrice:
    input: Decimal
    cached_input: Decimal
    output: Decimal


PRICES: dict[str, ModelPrice] = {
    "gpt-6-luna": ModelPrice(input=Decimal("0.10"), cached_input=Decimal("0.01"), output=Decimal("0.50")),
}


def price_for(model: str | None) -> ModelPrice | None:
    """The listed price for a model name, also matching dated names such as gpt-6-luna-2026-09-22."""
    if not model:
        return None
    if model in PRICES:
        return PRICES[model]
    matches = [name for name in PRICES if model.startswith(name + "-")]
    return PRICES[max(matches, key=len)] if matches else None


def estimate_cost(model: str | None, input_tokens: int | None, cached_tokens: int | None,
                  output_tokens: int | None) -> Decimal | None:
    """USD for one call. Reasoning tokens are already part of output_tokens. None if unknown."""
    price = price_for(model)
    if price is None or input_tokens is None or output_tokens is None:
        return None
    cached = min(cached_tokens or 0, input_tokens)
    total = ((input_tokens - cached) * price.input + cached * price.cached_input
             + output_tokens * price.output)
    return total / PER_TOKENS
