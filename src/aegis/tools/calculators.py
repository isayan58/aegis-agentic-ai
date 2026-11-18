"""Deterministic calculations independent of any LLM or research domain."""

import ast
import math
import operator
from typing import Literal


def _number(value: float) -> float:
    """Accept finite real numbers while rejecting booleans."""

    if type(value) not in (int, float):
        raise ValueError("Expected a real number")

    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError("Number is too large") from exc

    if not math.isfinite(result):
        raise ValueError("Number must be finite")

    return result


def _mapping(values: dict[str, float]) -> dict[str, float]:
    """Validate a non-empty mapping of names to finite numbers."""

    if not values:
        raise ValueError("At least one value is required")

    if any(not isinstance(key, str) or not key.strip() for key in values):
        raise ValueError("Names must be non-empty strings")

    return {key: _number(value) for key, value in values.items()}


def per_90(value: float, minutes: float) -> float:
    """Calculate a non-negative event count per 90 minutes."""

    value = _number(value)
    minutes = _number(minutes)

    if value < 0:
        raise ValueError("Event count cannot be negative")

    if minutes <= 0:
        raise ValueError("Minutes must be greater than zero")

    # Multiply before dividing. (value / minutes) * 90 divides first, and
    # the small fraction it produces (e.g. 12 / 1800 = 0.00666...) cannot be
    # stored exactly as a binary float; multiplying by 90 then makes the
    # error visible (0.6000000000000001 instead of 0.6). Dividing once, at
    # the end, keeps the result as accurate as floats allow.
    # Callers must still compare results with a tolerance, never with ==.
    return _number((value * 90) / minutes)


def normalize(
    values: dict[str, float],
    direction: Literal["higher", "lower"],
) -> dict[str, float]:
    """Scale a comparison group to 0–1, where 1 is always better."""

    values = _mapping(values)

    if direction not in ("higher", "lower"):
        raise ValueError("Direction must be 'higher' or 'lower'")

    low = min(values.values())
    high = max(values.values())

    # Equal observations contain no relative preference.
    if high == low:
        return {key: 0.5 for key in values}

    span = _number(high - low)

    if direction == "higher":
        return {
            key: (value - low) / span
            for key, value in values.items()
        }

    return {
        key: (high - value) / span
        for key, value in values.items()
    }


def weighted_score(
    scores: dict[str, float],
    weights: dict[str, float],
) -> float:
    """Combine normalized factor scores using weights summing to one."""

    scores = _mapping(scores)
    weights = _mapping(weights)

    if set(scores) != set(weights):
        raise ValueError("Scores and weights must have identical factors")

    if any(not 0 <= value <= 1 for value in scores.values()):
        raise ValueError("Scores must be normalized to 0–1")

    if any(value < 0 for value in weights.values()):
        raise ValueError("Weights cannot be negative")

    total = math.fsum(weights.values())

    if not math.isclose(total, 1.0, rel_tol=0, abs_tol=1e-9):
        raise ValueError("Weights must sum to 1")

    # Remove tiny accepted floating-point drift in the weight total.
    return math.fsum(
        scores[factor] * (weights[factor] / total)
        for factor in scores
    )


def rank(scores: dict[str, float]) -> list[dict]:
    """Rank descending; exact ties share ranks such as 1, 1, 3."""

    scores = _mapping(scores)

    # Alphabetical order makes tied rows deterministic.
    ordered = sorted(
        scores.items(),
        key=lambda item: (-item[1], item[0]),
    )

    result = []
    previous_score = None
    current_rank = 0

    for position, (subject, score) in enumerate(ordered, start=1):
        if position == 1 or score != previous_score:
            current_rank = position

        result.append(
            {
                "subject": subject,
                "score": score,
                "rank": current_rank,
            }
        )

        previous_score = score

    return result


def sensitivity_check(
    scores: dict[str, dict[str, float]],
    weights: dict[str, float],
) -> dict:
    """Check winner-set changes under relative ±10% weight changes."""

    if not scores:
        raise ValueError("At least one subject is required")

    def calculate(candidate_weights):
        """Score every subject using the same candidate weights."""

        return {
            subject: weighted_score(factors, candidate_weights)
            for subject, factors in scores.items()
        }

    def winners(totals):
        """Preserve all tied winners rather than picking arbitrarily."""

        return [
            row["subject"]
            for row in rank(totals)
            if row["rank"] == 1
        ]

    # This also validates each subject's factors and the base weights.
    base_scores = calculate(weights)
    base_winners = winners(base_scores)
    scenarios = []

    for factor in sorted(weights):
        for multiplier in (0.9, 1.1):
            changed = dict(weights)
            changed[factor] *= multiplier

            # Restore a valid sum of one after perturbing one weight.
            total = math.fsum(changed.values())
            changed = {
                key: value / total
                for key, value in changed.items()
            }

            changed_scores = calculate(changed)
            changed_winners = winners(changed_scores)

            scenarios.append(
                {
                    "factor": factor,
                    "multiplier": multiplier,
                    "weights": changed,
                    "winners": changed_winners,
                    "winner_changed": changed_winners != base_winners,
                }
            )

    return {
        "base_scores": base_scores,
        "base_winners": base_winners,
        "winner_changed": any(
            item["winner_changed"] for item in scenarios
        ),
        "scenarios": scenarios,
    }


# Only these arithmetic operations are permitted.
_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}

_UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def calculator(expression: str) -> float:
    """Evaluate bounded numeric arithmetic without executing Python code."""

    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("Expression must be non-empty text")

    # Bound work before parsing unusually large input.
    if len(expression) > 200:
        raise ValueError("Expression is too long")

    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except (SyntaxError, RecursionError) as exc:
        raise ValueError("Invalid arithmetic expression") from exc

    if sum(1 for _ in ast.walk(tree)) > 100:
        raise ValueError("Expression is too complex")

    def visit(node):
        """Interpret allowed syntax nodes recursively."""

        if isinstance(node, ast.Expression):
            return visit(node.body)

        if isinstance(node, ast.Constant):
            return _number(node.value)

        if isinstance(node, ast.UnaryOp):
            operation = _UNARY_OPERATORS.get(type(node.op))

            if operation is None:
                raise ValueError("Unsupported unary operator")

            return _number(operation(visit(node.operand)))

        if isinstance(node, ast.BinOp):
            operation = _BINARY_OPERATORS.get(type(node.op))

            if operation is None:
                raise ValueError("Unsupported arithmetic operator")

            left = visit(node.left)
            right = visit(node.right)

            if isinstance(node.op, ast.Div) and right == 0:
                raise ValueError("Division by zero")

            return _number(operation(left, right))

        # Function calls, variables, attributes, indexing, and other
        # Python constructs never reach an execution mechanism.
        raise ValueError("Only numeric arithmetic is allowed")

    return visit(tree)