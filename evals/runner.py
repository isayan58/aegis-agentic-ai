"""Run deterministic evaluation cases and save their observed outcomes."""

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from aegis.clarification import check_clarity
from aegis.schemas import ResearchBundle, ResearchRequest
from aegis.tools.calculators import (
    calculator,
    per_90,
    weighted_score,
)
from evals.schemas import EvalCase


# Resolve paths relative to this file, not the terminal/notebook location.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = PROJECT_ROOT / "evals" / "datasets" / "v1.jsonl"
RESULTS_DIRECTORY = PROJECT_ROOT / "evals" / "results"


# Dispatch only explicitly supported functions.
# Never dynamically import or execute a function name from the dataset.
TOOL_FUNCTIONS = {
    "per_90": per_90,
    "weighted_score": weighted_score,
    "calculator": calculator,
}


def parse_cases(text: str) -> list[EvalCase]:
    """Validate every JSONL record and require unique case IDs."""

    cases = []
    seen_ids = set()

    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue

        try:
            case = EvalCase.model_validate_json(line)
        except ValidationError as exc:
            raise ValueError(
                f"Invalid evaluation definition on line {line_number}"
            ) from exc

        if case.id in seen_ids:
            raise ValueError(f"Duplicate evaluation ID: {case.id}")

        seen_ids.add(case.id)
        cases.append(case)

    if not cases:
        raise ValueError("Evaluation dataset is empty")

    return cases


def load_cases(path: Path = DATASET_PATH) -> list[EvalCase]:
    """Load a dataset without executing its cases."""

    return parse_cases(Path(path).read_text(encoding="utf-8"))


def validation_errors(exc: ValidationError) -> list[dict]:
    """Keep useful diagnostics without dumping the original input."""

    return [
        {
            "type": item["type"],
            "location": list(item["loc"]),
            "message": item["msg"],
        }
        for item in exc.errors(include_input=False)
    ]


def observe(case: EvalCase) -> dict:
    """Run application behavior without consulting the expected answer."""

    # Catch validation errors only at the intended validation boundary.
    # Errors from unrelated code must not count as a successful rejection.
    try:
        if case.input.bundle is not None:
            ResearchBundle.model_validate(case.input.bundle)
            request = None
        else:
            request = ResearchRequest.model_validate(case.input.request)

    except ValidationError as exc:
        return {
            "outcome": "rejected",
            "clarification_fields": [],
            "tool_outputs": [],
            "errors": validation_errors(exc),
        }

    fields = []

    if request is not None:
        clarification = check_clarity(request)
        fields = [question.field for question in clarification.questions]

    outputs = []

    # An incomplete request should not proceed to calculation.
    if not fields:
        for call in case.input.tools:
            function = TOOL_FUNCTIONS[call.name]
            outputs.append(function(**call.arguments))

    return {
        "outcome": "clarification" if fields else "accepted",
        "clarification_fields": fields,
        "tool_outputs": outputs,
        "errors": [],
    }


def compare(case: EvalCase, actual: dict) -> list[str]:
    """Return all differences between expected and observed behavior."""

    expected = case.expected
    failures = []

    if actual["outcome"] != expected.outcome:
        failures.append(
            f"Expected outcome {expected.outcome!r}; "
            f"received {actual['outcome']!r}"
        )

    # Ignore question order but preserve duplicates during comparison.
    if sorted(actual["clarification_fields"]) != sorted(
        expected.clarification_fields
    ):
        failures.append(
            "Clarification fields differ: "
            f"expected {expected.clarification_fields}, "
            f"received {actual['clarification_fields']}"
        )

    if expected.outcome == "rejected":
        matched_error = any(
            error["type"] == expected.error_type
            and expected.error_contains.casefold()
            in error["message"].casefold()
            for error in actual["errors"]
        )

        if not matched_error:
            failures.append("Expected validation error was not observed")

    observed_outputs = actual["tool_outputs"]

    if len(observed_outputs) != len(expected.tool_outputs):
        failures.append("Number of tool outputs differs")
    else:
        for index, (observed, wanted) in enumerate(
            zip(observed_outputs, expected.tool_outputs),
            start=1,
        ):
            # Numeric comparisons allow insignificant floating-point drift.
            is_numeric = type(observed) in (int, float)

            if (
                not is_numeric
                or not math.isfinite(observed)
                or not math.isclose(
                    observed,
                    wanted,
                    rel_tol=1e-9,
                    abs_tol=1e-9,
                )
            ):
                failures.append(
                    f"Tool output {index}: expected {wanted}, "
                    f"received {observed}"
                )

    return failures


def evaluate_case(case: EvalCase) -> dict:
    """Evaluate one case; unexpected exceptions always fail the case."""

    try:
        actual = observe(case)
        failures = compare(case, actual)

    except Exception as exc:
        # Keep processing other cases, but never turn a crash into a pass.
        # Record the exception class without copying potentially sensitive
        # exception text into a result file.
        actual = {
            "outcome": "execution_error",
            "exception_type": type(exc).__name__,
        }
        failures = [
            f"Unexpected execution error: {type(exc).__name__}"
        ]

    return {
        "id": case.id,
        "category": case.category,
        "passed": not failures,
        "expected": case.expected.model_dump(mode="json"),
        "actual": actual,
        "failures": failures,
    }


def print_report(report: dict) -> None:
    """Print a compact table followed by actionable failure details."""

    print(f"{'CASE':<26} {'CATEGORY':<15} RESULT")
    print("-" * 48)

    for result in report["results"]:
        status = "PASS" if result["passed"] else "FAIL"

        print(
            f"{result['id']:<26} "
            f"{result['category']:<15} "
            f"{status}"
        )

        for failure in result["failures"]:
            print(f"  - {failure}")

    print()
    print(
        f"{report['passed']}/{report['total']} passed; "
        f"{report['failed']} failed"
    )


def run_suite(
    dataset_path: Path = DATASET_PATH,
    results_directory: Path = RESULTS_DIRECTORY,
) -> tuple[dict, Path]:
    """Evaluate one dataset snapshot and save a timestamped JSON report."""

    dataset_path = Path(dataset_path)
    results_directory = Path(results_directory)

    # Read once so the hash describes exactly the bytes we evaluated.
    raw = dataset_path.read_bytes()
    cases = parse_cases(raw.decode("utf-8"))

    started = datetime.now(timezone.utc)
    results = [evaluate_case(case) for case in cases]
    finished = datetime.now(timezone.utc)

    passed = sum(result["passed"] for result in results)

    report = {
        "dataset": dataset_path.name,
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_seconds": (finished - started).total_seconds(),
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": results,
    }

    results_directory.mkdir(parents=True, exist_ok=True)

    # UTC plus microseconds keeps normal successive runs distinct.
    filename = started.strftime("%Y%m%dT%H%M%S_%fZ") + ".json"
    output_path = results_directory / filename

    # Exclusive creation avoids silently overwriting an existing report.
    with output_path.open("x", encoding="utf-8") as handle:
        json.dump(
            report,
            handle,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )

    return report, output_path


def main() -> int:
    """Provide a terminal entry point with a meaningful exit status."""

    report, output_path = run_suite()
    print_report(report)
    print(f"Saved results: {output_path}")

    # A failing evaluation should also fail a future CI job.
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())