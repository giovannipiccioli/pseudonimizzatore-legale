"""Shared recall/precision metrics for the annotated evaluation corpus.

The corpus historically reports one assertion per surface form. That remains useful,
but it is not the privacy outcome: ``MALASPINA FERRUCCIO``, ``Ferruccio Malaspina`` and
``Malaspina`` are one identity, and leaving any occurrence of any spelling means that
identity was not anonymized.

Fixtures do not yet store their original identity clusters. They can nevertheless be
recovered exactly for the current generated corpus: aliases of one invented identity
share a non-connector name token, and the builder guarantees surnames are unique within
a document. A future explicit ``must_remove_entities`` field takes precedence over this
fallback, so the metric can survive a less constrained corpus.

Precision is measured over *actual replacement spans*. A predicted span is a hit when
it overlaps a gold sensitive span. Character precision additionally penalizes a wide
replacement which contains a correct entity plus unrelated text. ``must_keep`` survival
is reported separately; it is an important damage sentinel, but is not classical
precision because the keep assertions are not an exhaustive annotation of all
non-sensitive text.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import regex as re


_CONNECTORS = frozenset({"di", "de", "del", "della", "lo", "la", "il", "e"})


def present(needle: str, haystack: str) -> bool:
    """Whether one complete assertion remains anywhere in the output."""
    return bool(
        re.search(
            rf"(?<![\p{{L}}\p{{N}}]){re.escape(needle)}(?![\p{{L}}\p{{N}}])",
            haystack,
        )
    )


def _name_tokens(value: str) -> frozenset[str]:
    """Distinctive tokens usable to connect surface forms of the same name."""
    if re.search(r"[@\d]", value):
        return frozenset()  # identifier/address, not an alias spelling
    return frozenset(
        token.lower()
        for token in re.findall(r"[\p{L}]+", value)
        if len(token) >= 4 and token.lower() not in _CONNECTORS
    )


@dataclass(frozen=True)
class EntityGroup:
    """All gold surface forms belonging to one sensitive entity in one document."""

    values: tuple[str, ...]
    kind: str


def group_entities(gold: dict) -> list[EntityGroup]:
    """Return gold identities, using explicit groups or the generated-corpus fallback."""
    explicit = gold.get("must_remove_entities")
    if explicit is not None:
        groups = []
        covered = set()
        for index, item in enumerate(explicit):
            if isinstance(item, dict):
                values = item.get("values", [])
                kind = item.get("kind", "other")
            else:
                values = item
                kind = "other"
            if isinstance(values, str):
                values = [values]
            if not values:
                raise ValueError(f"empty must_remove_entities group at index {index}")
            duplicate = covered.intersection(values)
            if duplicate:
                raise ValueError(
                    f"surface appears in multiple entity groups: {sorted(duplicate)!r}"
                )
            groups.append(EntityGroup(tuple(values), kind))
            covered.update(values)
        for value in gold.get("must_remove", []):
            if value not in covered:
                groups.append(EntityGroup((value,), "name" if _name_tokens(value)
                                          else "identifier"))
        return groups

    values = remove_values(gold)
    parent = list(range(len(values)))
    tokens = [_name_tokens(value) for value in values]

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        a, b = root(left), root(right)
        if a != b:
            parent[b] = a

    for index in range(len(values)):
        for earlier in range(index):
            if tokens[index] & tokens[earlier]:
                union(index, earlier)

    grouped: dict[int, list[str]] = {}
    for index, value in enumerate(values):
        grouped.setdefault(root(index), []).append(value)
    return [
        EntityGroup(tuple(group), "name" if all(_name_tokens(v) for v in group)
                    else "identifier")
        for group in grouped.values()
    ]


def remove_values(gold: dict) -> list[str]:
    """Flatten sensitive surfaces from legacy or explicit entity-group gold."""
    values = list(gold.get("must_remove", []))
    for item in gold.get("must_remove_entities", []):
        grouped = item.get("values", []) if isinstance(item, dict) else item
        if isinstance(grouped, str):
            grouped = [grouped]
        for value in grouped:
            if value not in values:
                values.append(value)
    if not values and "must_remove" not in gold and "must_remove_entities" not in gold:
        raise ValueError("gold must define must_remove or must_remove_entities")
    return values


def value_spans(text: str, values: Iterable[str]) -> list[tuple[int, int]]:
    """Every occurrence of each gold value, including repeated mentions."""
    spans = set()
    for value in values:
        pattern = re.compile(
            rf"(?<![\p{{L}}\p{{N}}]){re.escape(value)}(?![\p{{L}}\p{{N}}])"
        )
        spans.update(match.span() for match in pattern.finditer(text))
    return sorted(spans)


def _merge(spans: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    valid = sorted((start, end) for start, end in spans if start < end)
    merged: list[list[int]] = []
    for start, end in valid:
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]


def _intersection_length(
    left: Iterable[tuple[int, int]], right: Iterable[tuple[int, int]]
) -> int:
    a, b = _merge(left), _merge(right)
    i = j = total = 0
    while i < len(a) and j < len(b):
        total += max(0, min(a[i][1], b[j][1]) - max(a[i][0], b[j][0]))
        if a[i][1] <= b[j][1]:
            i += 1
        else:
            j += 1
    return total


@dataclass(frozen=True)
class OutputMetrics:
    surface_ok: int
    surface_total: int
    entity_ok: int
    entity_total: int
    name_entity_ok: int
    name_entity_total: int
    identifier_entity_ok: int
    identifier_entity_total: int
    entity_partial: int
    entity_missed: int
    keep_ok: int
    keep_total: int
    prediction_ok: int
    prediction_total: int
    predicted_char_ok: int
    predicted_char_total: int
    leaked: tuple[str, ...]
    lost: tuple[str, ...]


def score_output(
    original: str,
    output: str,
    gold: dict,
    predicted_spans: Iterable[tuple[int, int]],
) -> OutputMetrics:
    """Score one anonymized document at surface, identity and prediction levels."""
    sensitive_values = remove_values(gold)
    leaked = tuple(value for value in sensitive_values if present(value, output))
    lost = tuple(value for value in gold["must_keep"] if not present(value, output))
    leaked_set = set(leaked)

    entity_ok = entity_partial = entity_missed = 0
    name_ok = name_total = identifier_ok = identifier_total = 0
    groups = group_entities(gold)
    for group in groups:
        removed = sum(value not in leaked_set for value in group.values)
        complete = removed == len(group.values)
        entity_ok += complete
        if removed == 0:
            entity_missed += 1
        elif not complete:
            entity_partial += 1
        if group.kind == "name":
            name_ok += complete
            name_total += 1
        else:
            identifier_ok += complete
            identifier_total += 1

    sensitive_spans = value_spans(original, sensitive_values)
    predictions = [(start, end) for start, end in predicted_spans if start < end]
    prediction_ok = sum(
        any(start < gold_end and gold_start < end
            for gold_start, gold_end in sensitive_spans)
        for start, end in predictions
    )
    merged_predictions = _merge(predictions)
    predicted_chars = sum(end - start for start, end in merged_predictions)

    return OutputMetrics(
        surface_ok=len(sensitive_values) - len(leaked),
        surface_total=len(sensitive_values),
        entity_ok=entity_ok,
        entity_total=len(groups),
        name_entity_ok=name_ok,
        name_entity_total=name_total,
        identifier_entity_ok=identifier_ok,
        identifier_entity_total=identifier_total,
        entity_partial=entity_partial,
        entity_missed=entity_missed,
        keep_ok=len(gold["must_keep"]) - len(lost),
        keep_total=len(gold["must_keep"]),
        prediction_ok=prediction_ok,
        prediction_total=len(predictions),
        predicted_char_ok=_intersection_length(merged_predictions, sensitive_spans),
        predicted_char_total=predicted_chars,
        leaked=leaked,
        lost=lost,
    )
