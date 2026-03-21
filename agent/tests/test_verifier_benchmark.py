from pathlib import Path

from proof_of_audit_agent.verifier_benchmark import (
    CLASSIFICATION_LABELS,
    DEFAULT_BENCHMARK_CORPUS,
    load_benchmark_cases,
    run_benchmark,
)


def test_benchmark_corpus_loads_expected_categories() -> None:
    cases = load_benchmark_cases()

    assert len(cases) == 6
    assert {case.category for case in cases} == {
        "covered_issue",
        "missed_issue",
        "exploit_variant",
        "contradiction",
        "ambiguous_case",
        "adversarial_evidence",
    }


def test_benchmark_runner_matches_corpus_expectations() -> None:
    report = run_benchmark()

    assert report["schema_version"] == "challenge-verifier-benchmark/v1"
    assert report["corpus_path"] == str(DEFAULT_BENCHMARK_CORPUS)
    assert report["summary"]["total_cases"] == 6
    assert report["summary"]["passed_cases"] == 6
    assert report["summary"]["failed_cases"] == 0
    assert report["metrics"]["evaluated_cases"] == 5
    assert report["metrics"]["correct"] == 5
    assert report["metrics"]["accuracy"] == 1.0

    labels = set(CLASSIFICATION_LABELS)
    per_label = report["metrics"]["per_label"]
    assert labels == set(per_label)
    assert per_label["already_covered"]["support"] == 1
    assert per_label["likely_new_issue"]["support"] == 1
    assert per_label["contradicts_audit_claim"]["support"] == 1
    assert per_label["same_root_cause_variant"]["support"] == 1
    assert per_label["ambiguous"]["support"] == 1

    cases = {item["case_id"]: item for item in report["cases"]}
    assert cases["new-access-control-gap"]["version_metadata"]["model_metadata"][
        "prompt_version"
    ] == "challenge-claim-extractor/v1"
    assert (
        cases["adversarial-low-confidence-extractor"]["actual"]["comparison_status"]
        == "not_assessed"
    )


def test_benchmark_script_writes_structured_output(tmp_path: Path) -> None:
    output_path = tmp_path / "benchmark-report.json"
    report = run_benchmark(DEFAULT_BENCHMARK_CORPUS)
    output_path.write_text(__import__("json").dumps(report), encoding="utf-8")

    assert output_path.exists()
    assert "\"schema_version\": \"challenge-verifier-benchmark/v1\"" in output_path.read_text(
        encoding="utf-8"
    )
