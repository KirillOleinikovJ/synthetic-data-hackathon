"""Split a fictional name so a degree is never used as the surname."""

from __future__ import annotations

from dataclasses import dataclass

_PREFIX = {
    "dr",
    "dr.",
    "dr.med",
    "prof",
    "prof.",
    "prof.dr",
    "prof.dr.",
    "univ.prof",
    "univ.-prof",
    "pd",
    "mag",
    "dipl.-ing",
    "dipl.-kfm",
    "ing",
    "herr",
    "frau",
}
_SUFFIX = {
    "b.sc",
    "b.sc.",
    "m.sc",
    "m.sc.",
    "b.a",
    "b.a.",
    "m.a",
    "m.a.",
    "b.eng",
    "b.eng.",
    "m.eng",
    "m.eng.",
    "ph.d",
    "ph.d.",
    "phd",
    "mba",
    "dipl",
    "dipl.",
    "ing",
    "ing.",
    "med",
    "med.",
    "bsc",
    "msc",
    "beng",
    "meng",
}


def _key(token: str) -> str:
    return token.lower().replace(" ", "").rstrip(".")


def _is_prefix(token: str) -> bool:
    return _key(token) in _PREFIX


def _is_suffix(token: str) -> bool:
    return _key(token) in _SUFFIX


@dataclass(frozen=True)
class PersonName:
    first_name: str
    last_name: str
    academic_title: str


def split_person(full_name: str) -> PersonName:
    tokens = [part for part in full_name.replace(",", " ").split() if part]
    prefix: list[str] = []
    suffix: list[str] = []
    while tokens and _is_prefix(tokens[0]):
        prefix.append(tokens.pop(0))
    while tokens and _is_suffix(tokens[-1]):
        suffix.insert(0, tokens.pop())
    title = " ".join(prefix + suffix)
    if not tokens:
        return PersonName(first_name="", last_name=full_name.strip() or "Patient", academic_title=title)
    return PersonName(
        first_name=" ".join(tokens[:-1]),
        last_name=tokens[-1],
        academic_title=title,
    )


def family_name(full_name: str) -> str:
    return split_person(full_name).last_name


def greeting_line(salutation: str, last_name: str) -> str:
    if salutation.strip().lower() == "herr":
        return f"Sehr geehrter Herr {last_name},"
    if salutation.strip().lower() == "frau":
        return f"Sehr geehrte Frau {last_name},"
    return f"Guten Tag {last_name},"


def display_name(person: PersonName) -> str:
    body = " ".join(part for part in (person.first_name, person.last_name) if part)
    title = person.academic_title.strip()
    if not title:
        return body or "Patient"
    prefixes: list[str] = []
    suffixes: list[str] = []
    for token in title.split():
        if _is_prefix(token):
            prefixes.append(token)
        else:
            suffixes.append(token)
    shown = " ".join(part for part in (" ".join(prefixes), body) if part)
    if suffixes:
        shown = f"{shown}, {' '.join(suffixes)}" if shown else " ".join(suffixes)
    return shown or "Patient"
