"""Closed passive material scope; never infer authority from receipt paths."""
from copy import deepcopy

from scripts.version import P1_BUILD_MATERIAL_FILES

P1_MATERIAL_SCOPE = {"schema": "lmdj.candidate-material-scope.v1",
                     "profile": "creator-p1"}
LEGACY_FILES = frozenset({"products/lmdj/version.json", "products/lmdj/assembly.json",
    "products/lmdj/assembly.lock.json", "products/lmdj/src/compiled_assembly.cpp",
    "products/lmdj/generated/web-runtime-identity.json",
    "products/lmdj/generated/web-runtime-identity.mjs"})
HEADER_INPUTS = frozenset({"apps/docs-site/docs/operations/creator-changelog.mdx",
                         "apps/docs-site/docs/operations/runtime-changelog.mdx"})


def material_scope(value):
    if value is None:
        return None
    if type(value) is not dict or value != P1_MATERIAL_SCOPE:
        raise ValueError("why: candidate material scope is unknown; remedy: use the explicitly authorized closed creator-p1 profile")
    return deepcopy(P1_MATERIAL_SCOPE)


def scope_fields(value):
    scope = material_scope(value)
    return {} if scope is None else {"material_scope": scope}


def material_files(value):
    return LEGACY_FILES if material_scope(value) is None else LEGACY_FILES | P1_BUILD_MATERIAL_FILES
