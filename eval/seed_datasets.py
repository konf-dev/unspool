"""Upload eval test cases to Langfuse datasets for experiment tracking.

Reads eval/cases/*.yaml and creates corresponding Langfuse dataset items,
enabling Langfuse's experiment runner to compare results across changes.

Usage:
    python eval/seed_datasets.py                # Upload all cases
    python eval/seed_datasets.py --dataset v2   # Custom dataset name
"""

import argparse
import json
import os
import sys
from base64 import b64encode
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")

LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "")
LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY", "")

CASES_DIR = Path(__file__).parent / "cases"


def _auth() -> str:
    return b64encode(f"{LANGFUSE_PUBLIC_KEY}:{LANGFUSE_SECRET_KEY}".encode()).decode()


def _post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = Request(
        f"{LANGFUSE_HOST}/api/public{path}",
        data=data,
        headers={
            "Authorization": f"Basic {_auth()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        body_text = e.read().decode() if e.fp else ""
        print(f"  HTTP {e.code}: {body_text[:200]}")
        raise


def create_dataset(name: str, description: str = "") -> dict:
    return _post("/datasets", {"name": name, "description": description})


def create_dataset_item(
    dataset_name: str,
    input_data: dict,
    expected_output: dict | None = None,
    metadata: dict | None = None,
) -> dict:
    body: dict = {
        "datasetName": dataset_name,
        "input": input_data,
    }
    if expected_output:
        body["expectedOutput"] = expected_output
    if metadata:
        body["metadata"] = metadata
    return _post("/dataset-items", body)


def load_cases(yaml_path: Path) -> list[dict]:
    with open(yaml_path) as f:
        return yaml.safe_load(f) or []


def main():
    parser = argparse.ArgumentParser(description="Seed Langfuse datasets from eval cases")
    parser.add_argument("--dataset", default="unspool-eval-v2", help="Dataset name prefix")
    args = parser.parse_args()

    if not all([LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY]):
        sys.exit("Set LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY")

    yaml_files = sorted(CASES_DIR.glob("*.yaml"))
    if not yaml_files:
        sys.exit(f"No .yaml files found in {CASES_DIR}")

    total_items = 0

    for yaml_path in yaml_files:
        category = yaml_path.stem  # e.g., "intent", "extraction"
        dataset_name = f"{args.dataset}-{category}"

        cases = load_cases(yaml_path)
        if not cases:
            print(f"  {category}: no cases, skipping")
            continue

        print(f"\n{category}: {len(cases)} cases → dataset '{dataset_name}'")

        try:
            create_dataset(dataset_name, f"Unspool eval cases: {category}")
        except HTTPError:
            print(f"  Dataset may already exist, continuing...")

        for case in cases:
            desc = case.get("description", "")
            message = case.get("vars", {}).get("message", "")
            turns = case.get("vars", {}).get("turns", [])
            assertions = case.get("assert", [])

            if not message and not turns:
                continue

            input_data = {"message": message} if message else {"turns": turns}

            # Extract expected behavior from assertions for the dataset
            expected_behaviors = []
            for assertion in assertions:
                if assertion.get("type") == "llm-rubric":
                    expected_behaviors.append(assertion.get("value", ""))
                elif assertion.get("type") == "not-contains":
                    expected_behaviors.append(f"should NOT contain: {assertion.get('value', '')}")
                elif assertion.get("type") == "contains":
                    expected_behaviors.append(f"should contain: {assertion.get('value', '')}")

            expected_output = {"behaviors": expected_behaviors} if expected_behaviors else None

            metadata = {
                "description": desc,
                "category": category,
                "tags": case.get("tags", []),
            }

            try:
                create_dataset_item(dataset_name, input_data, expected_output, metadata)
                total_items += 1
            except HTTPError:
                print(f"  Failed to create item: {desc}")

    print(f"\n{'='*40}")
    print(f"Seeded {total_items} items across {len(yaml_files)} datasets")


if __name__ == "__main__":
    main()
