from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


_SOLIDITY_SUFFIX = ".sol"
_SKIP_DIR_NAMES = {
    ".git",
    ".proof-of-audit",
    "artifacts",
    "broadcast",
    "cache",
    "lib",
    "node_modules",
    "out",
}
_ACCESS_CONTROL_MARKERS = (
    "onlyowner",
    "onlyadmin",
    "onlyoperator",
    "hasrole",
    "msg.sender ==",
    "msg.sender==",
    "msg.sender !=",
    "msg.sender!=",
)
_FUNCTION_RE = re.compile(r"^\s*function\s+([A-Za-z_]\w*)")
_CALL_RE = re.compile(r"\.call\s*\{")
_ASSIGNED_CALL_RE = re.compile(r"\(\s*bool\s+([A-Za-z_]\w*)\s*,")
_REQUIRE_BOOL_RE = re.compile(r"\b(?:require|assert)\s*\(\s*([A-Za-z_]\w*)\b")
_STATE_WRITE_RE = re.compile(r"\bbalances\s*\[.*\]\s*[-+*/]?=")
_ADMIN_WRITE_RE = re.compile(r"^\s*(owner|admin)\s*=")


@dataclass(frozen=True)
class LiveFinding:
    title: str
    severity: str
    category: str
    description: str
    impact: str
    recommendation: str
    confidence: str
    affected_function: str | None
    source_path: str
    start_line: int
    end_line: int
    detector: str

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "severity": self.severity,
            "category": self.category,
            "description": self.description,
            "impact": self.impact,
            "recommendation": self.recommendation,
            "confidence": self.confidence,
            "affected_function": self.affected_function,
            "source_path": self.source_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "detector": self.detector,
        }


@dataclass
class _FunctionBlock:
    name: str
    signature_line: int
    lines: list[tuple[int, str]]


ALL_DETECTORS = frozenset({"reentrancy", "access_control", "unchecked_external_call"})


def analyze_repository(
    repo_path: Path,
    *,
    detectors: frozenset[str] | None = None,
) -> dict[str, object]:
    """Run static analysis on all Solidity files in *repo_path*.

    Args:
        repo_path: Root of the Solidity project.
        detectors: Detector families to run.  ``None`` or ``{"*"}`` means
            run all families; otherwise only the listed families execute.
    """
    active_detectors = _resolve_detectors(detectors)
    findings: list[LiveFinding] = []
    for source_file in _solidity_files(repo_path):
        findings.extend(_analyze_source_file(repo_path, source_file, active_detectors))

    scope_label = ", ".join(sorted(active_detectors)) if active_detectors != ALL_DETECTORS else "all"
    if findings:
        summary = (
            f"Live source analysis identified {len(findings)} potential issue"
            f"{'' if len(findings) == 1 else 's'} across the supported checks"
            f" (detectors: {scope_label})."
        )
        confidence = "medium"
    else:
        summary = (
            "Live source analysis did not confirm a supported issue in the submitted"
            f" Solidity sources (detectors: {scope_label})."
        )
        confidence = "low"

    return {
        "benchmark_id": "agent-forge-live",
        "summary": summary,
        "confidence": confidence,
        "findings": [finding.to_dict() for finding in findings],
        "supported_checks": sorted(active_detectors),
    }


def _resolve_detectors(detectors: frozenset[str] | None) -> frozenset[str]:
    """Normalise a user-supplied detector set to a concrete set of families."""
    if detectors is None or detectors == frozenset({"*"}):
        return ALL_DETECTORS
    unknown = detectors - ALL_DETECTORS - {"*"}
    if unknown:
        raise ValueError(f"Unknown detector families: {', '.join(sorted(unknown))}")
    return detectors & ALL_DETECTORS or ALL_DETECTORS


def _solidity_files(repo_path: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(repo_path.rglob(f"*{_SOLIDITY_SUFFIX}")):
        relative_parts = path.relative_to(repo_path).parts
        if any(part in _SKIP_DIR_NAMES for part in relative_parts):
            continue
        files.append(path)
    return files


def _analyze_source_file(
    repo_path: Path,
    source_file: Path,
    active_detectors: frozenset[str],
) -> list[LiveFinding]:
    lines = source_file.read_text(encoding="utf-8").splitlines()
    relative_path = str(source_file.relative_to(repo_path))
    findings: list[LiveFinding] = []
    for function in _extract_functions(lines):
        if "reentrancy" in active_detectors:
            findings.extend(_detect_reentrancy(relative_path, function))
        if "access_control" in active_detectors:
            findings.extend(_detect_access_control(relative_path, function))
        if "unchecked_external_call" in active_detectors:
            findings.extend(_detect_unchecked_external_call(relative_path, function))
    return findings


def _extract_functions(lines: list[str]) -> list[_FunctionBlock]:
    functions: list[_FunctionBlock] = []
    current: _FunctionBlock | None = None
    brace_balance = 0
    for line_number, raw_line in enumerate(lines, start=1):
        if current is None:
            match = _FUNCTION_RE.match(raw_line)
            if match is None:
                continue
            current = _FunctionBlock(
                name=match.group(1),
                signature_line=line_number,
                lines=[(line_number, raw_line)],
            )
            brace_balance = raw_line.count("{") - raw_line.count("}")
            if brace_balance <= 0:
                functions.append(current)
                current = None
            continue

        current.lines.append((line_number, raw_line))
        brace_balance += raw_line.count("{") - raw_line.count("}")
        if brace_balance <= 0:
            functions.append(current)
            current = None
    return functions


def _detect_reentrancy(source_path: str, function: _FunctionBlock) -> list[LiveFinding]:
    findings: list[LiveFinding] = []
    call_line: int | None = None
    for line_number, raw_line in function.lines:
        line = _strip_comments(raw_line)
        if call_line is None and _CALL_RE.search(line):
            call_line = line_number
            continue
        if call_line is not None and _STATE_WRITE_RE.search(line):
            findings.append(
                LiveFinding(
                    title="Potential reentrancy after external call",
                    severity="high",
                    category="reentrancy",
                    description="This function performs an external call before updating balance-like state.",
                    impact="A malicious callee may re-enter before state is fully updated and drain funds.",
                    recommendation="Apply checks-effects-interactions or add a reentrancy guard before the external call.",
                    confidence="medium",
                    affected_function=f"{function.name}()",
                    source_path=source_path,
                    start_line=call_line,
                    end_line=line_number,
                    detector="agent_forge.static.reentrancy",
                )
            )
            break
    return findings


def _detect_access_control(source_path: str, function: _FunctionBlock) -> list[LiveFinding]:
    normalized_lines = " ".join(_strip_comments(raw_line).lower() for _, raw_line in function.lines)
    if any(marker in normalized_lines for marker in _ACCESS_CONTROL_MARKERS):
        return []
    for line_number, raw_line in function.lines[1:]:
        line = _strip_comments(raw_line)
        match = _ADMIN_WRITE_RE.match(line)
        if match is None:
            continue
        target = match.group(1)
        return [
            LiveFinding(
                title=f"Unrestricted {target} mutation",
                severity="high",
                category="access_control",
                description=f"This externally callable function updates `{target}` without an obvious access-control check.",
                impact=f"Any caller may be able to seize control by changing `{target}`.",
                recommendation=f"Restrict writes to `{target}` with an ownership or role-based guard.",
                confidence="medium",
                affected_function=f"{function.name}()",
                source_path=source_path,
                start_line=line_number,
                end_line=line_number,
                detector="agent_forge.static.access_control",
            )
        ]
    return []


def _detect_unchecked_external_call(
    source_path: str,
    function: _FunctionBlock,
) -> list[LiveFinding]:
    findings: list[LiveFinding] = []
    assigned_bool_name: str | None = None
    call_line_number: int | None = None
    for index, (line_number, raw_line) in enumerate(function.lines):
        line = _strip_comments(raw_line)
        if not _CALL_RE.search(line):
            continue
        assigned_match = _ASSIGNED_CALL_RE.search(line)
        if assigned_match is None:
            findings.append(
                LiveFinding(
                    title="Unchecked low-level call result",
                    severity="medium",
                    category="unchecked_external_call",
                    description="This function issues a low-level call without checking the returned success flag.",
                    impact="Execution may continue after a failed external interaction, leaving the system in an unexpected state.",
                    recommendation="Capture the boolean result of the call and revert or handle the failure explicitly.",
                    confidence="medium",
                    affected_function=f"{function.name}()",
                    source_path=source_path,
                    start_line=line_number,
                    end_line=line_number,
                    detector="agent_forge.static.unchecked_external_call",
                )
            )
            continue
        assigned_bool_name = assigned_match.group(1)
        call_line_number = line_number
        lookahead = function.lines[index + 1 : index + 4]
        if not any(
            _REQUIRE_BOOL_RE.search(_strip_comments(candidate_line) or "") and
            _REQUIRE_BOOL_RE.search(_strip_comments(candidate_line) or "").group(1) == assigned_bool_name
            for _, candidate_line in lookahead
        ):
            findings.append(
                LiveFinding(
                    title="Unchecked low-level call result",
                    severity="medium",
                    category="unchecked_external_call",
                    description="This function captures a low-level call result but does not appear to validate it before continuing.",
                    impact="External failures may be ignored and produce inconsistent behavior.",
                    recommendation="Require the call success flag or handle the failure explicitly before continuing.",
                    confidence="medium",
                    affected_function=f"{function.name}()",
                    source_path=source_path,
                    start_line=call_line_number,
                    end_line=lookahead[-1][0] if lookahead else call_line_number,
                    detector="agent_forge.static.unchecked_external_call",
                )
            )
    return findings


def _strip_comments(line: str) -> str:
    return line.split("//", 1)[0]
