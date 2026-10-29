"""Reading the grader library.

**This is the one function that knows where the graders live.** They live in metis-library,
which the wizard is allowed to depend on, so nothing here breaks the `wizard ↛ engine`
invariant in the root AGENTS.md. Keeping the location in one string is what made moving them
out of the engine a one-line change here.

The graders each live in their own `_`-prefixed module and are re-exported flat from
`metis.library.graders.__init__`, which documents that path as canonical and calls the file
layout semantically weightless. So this reads the classes the package re-exports rather than
walking submodules — walking the submodules would skip every `_`-prefixed file and find
almost nothing. The emitted FQN is the flat canonical path, `metis.library.graders.<Class>`,
which is what the engine resolves by ``import_module`` + ``getattr``.

Design-time metadata only. The wizard never instantiates a grader and never runs one: a
grader's parameters are the fields of its `args_model`, a Pydantic model the class declares, so
they are read from the class without calling anything. A model-based grader's `model` field is
left out, because the engine resolves it at run time from the specification's
`defaults.judge_model` or the environment. Its `max_input_tokens` is left out for the same
reason, and a `CriterionJudgeArgs` grader's `criterion` is left out because the engine fills it
from the criterion description.
"""

from __future__ import annotations

import inspect
import re
from enum import Enum
from functools import lru_cache
from importlib import import_module
from types import NoneType, UnionType
from typing import TYPE_CHECKING, Annotated, Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel
from pydantic_core import to_jsonable_python

from metis.library.grader import CriterionJudgeArgs, Grader, GraderArgs, JudgeArgs
from metis.wizard.contracts.grader_spec import (
    GraderParam,
    GraderSetting,
    GraderSettingKind,
    GraderSpec,
)

if TYPE_CHECKING:
    from pydantic.fields import FieldInfo

# The one string that says where the graders live.
GRADERS_PACKAGE = "metis.library.graders"


def _human_name(class_name: str) -> str:
    """`TurnBudgetGrader` → `Turn budget`. What the user sees on a criterion card."""
    stem = re.sub(r"Grader$", "", class_name)
    words = re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z]*|\d+", stem)
    if not words:
        return class_name
    return " ".join([words[0], *[w.lower() for w in words[1:]]])


def _summary(cls: type) -> str:
    doc = inspect.getdoc(cls) or ""
    return doc.split("\n\n")[0].replace("\n", " ").strip()


def _type_name(annotation: object) -> str:
    return getattr(annotation, "__name__", None) or str(annotation)


_TAXONOMY_SETTINGS = {
    "scope": "scopes",
    "judgment_form": "judgment_forms",
    "aggregation": "aggregations",
}
"""Each taxonomy setting in every args model, and the taxonomy field that lists its values."""


def _supported(cls: type[Grader[Any]], setting: str) -> tuple[Any, ...]:
    return getattr(getattr(cls, "taxonomy", None), _TAXONOMY_SETTINGS[setting], ())


_ENGINE_FILLED: dict[type[GraderArgs], tuple[str, ...]] = {
    # resolved by the engine, never chosen per criterion in the wizard
    JudgeArgs: ("model", "max_input_tokens"),
    # filled from the criterion description
    CriterionJudgeArgs: ("criterion",),
}
"""The args fields that the engine fills, for each args base that declares them."""


def _user_fields(cls: type[Grader[Any]]) -> dict[str, FieldInfo]:
    """The ``args_model`` fields a Criterion can set, in declaration order."""
    filled = {
        name
        for base, names in _ENGINE_FILLED.items()
        if issubclass(cls.args_model, base)
        for name in names
    }
    return {
        name: info
        for name, info in cls.args_model.model_fields.items()
        if name not in filled
    }


def _params(cls: type[Grader[Any]]) -> list[GraderParam]:
    """The grader's ``args_model`` fields, read from the class without building anything."""
    params = []
    for name, info in _user_fields(cls).items():
        if name in _TAXONOMY_SETTINGS and len(_supported(cls, name)) < 2:
            continue  # the grader supports one value, so there is nothing to choose
        required = info.is_required()
        params.append(
            GraderParam(
                name=name,
                type=_type_name(info.annotation),
                default=None
                if required
                else info.get_default(call_default_factory=True),
                required=required,
            )
        )
    return params


_KINDS: dict[object, GraderSettingKind] = {
    bool: GraderSettingKind.BOOLEAN,
    int: GraderSettingKind.INTEGER,
    float: GraderSettingKind.NUMBER,
    str: GraderSettingKind.TEXT,
    tuple: GraderSettingKind.LIST,
    list: GraderSettingKind.LIST,
    set: GraderSettingKind.LIST,
    frozenset: GraderSettingKind.LIST,
    dict: GraderSettingKind.OBJECT,
}
"""The setting kind of each plain type or generic origin. Any other type is TEXT."""


def _unwrap(annotation: Any) -> Any:
    """Remove ``Annotated`` and an optional ``None``, so ``Optional[Annotated[str, ...]]`` is ``str``."""
    while True:
        origin = get_origin(annotation)
        if origin is Annotated:
            annotation = get_args(annotation)[0]
            continue
        if origin in (Union, UnionType):
            members = [arg for arg in get_args(annotation) if arg is not NoneType]
            if len(members) == 1:
                annotation = members[0]
                continue
        return annotation


def _kind(annotation: Any) -> tuple[GraderSettingKind, list[str]]:
    """The setting kind of a field type, and the allowed values of a CHOICE."""
    value_type = _unwrap(annotation)
    if get_origin(value_type) is Literal:
        return GraderSettingKind.CHOICE, [str(value) for value in get_args(value_type)]
    if inspect.isclass(value_type) and issubclass(value_type, Enum):
        return GraderSettingKind.CHOICE, [str(member.value) for member in value_type]
    if inspect.isclass(value_type) and issubclass(value_type, BaseModel):
        return GraderSettingKind.OBJECT, []
    return _KINDS.get(get_origin(value_type) or value_type, GraderSettingKind.TEXT), []


def _setting(cls: type[Grader[Any]], name: str, info: FieldInfo) -> GraderSetting:
    kind, choices = _kind(info.annotation)
    if name in _TAXONOMY_SETTINGS:
        # a grader accepts only the taxonomy values it declares
        choices = [str(value) for value in _supported(cls, name)]
    required = info.is_required()
    return GraderSetting(
        name=name,
        kind=kind,
        required=required,
        default=None
        if required
        else to_jsonable_python(info.get_default(call_default_factory=True)),
        choices=choices,
        base=name in GraderArgs.model_fields,
        description=info.description,
    )


def _settings(cls: type[Grader[Any]]) -> list[GraderSetting]:
    """Every key a Criterion can set: the base settings, then the grader's own settings.

    The base settings are kept even when the grader declares one taxonomy value, so the user
    sees the full list of keys that the grader accepts.
    """
    fields = _user_fields(cls)
    own = [name for name in fields if name not in GraderArgs.model_fields]
    base = [name for name in GraderArgs.model_fields if name in fields]
    return [_setting(cls, name, fields[name]) for name in (*base, *own)]


def _is_grader(obj: object) -> bool:
    """A concrete Grader defined inside the library, not something it happens to import."""
    return (
        inspect.isclass(obj)
        and issubclass(obj, Grader)
        and not inspect.isabstract(obj)
        and obj.__module__.startswith(GRADERS_PACKAGE)
    )


@lru_cache(maxsize=1)
def library_catalogue() -> list[GraderSpec]:
    """Every grader the wizard may match against.

    Read from the classes `metis.library.graders` re-exports, so it is the full set the
    library publishes rather than whatever a submodule walk would happen to find.

    Cached: the catalogue cannot change within a run, and it is read once per interview start
    and once per matcher construction.
    """
    package = import_module(GRADERS_PACKAGE)
    specs: list[GraderSpec] = []

    for name, obj in vars(package).items():
        if not _is_grader(obj):
            continue
        specs.append(
            GraderSpec(
                fqn=f"{GRADERS_PACKAGE}.{name}",
                name=_human_name(name),
                description=_summary(obj),
                params=_params(obj),
                settings=_settings(obj),
                uses_criterion_description=issubclass(
                    obj.args_model, CriterionJudgeArgs
                ),
                taxonomy=getattr(obj, "taxonomy", None),
            )
        )

    return sorted(specs, key=lambda s: s.fqn)
