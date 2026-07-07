import jsonschema
import pytest

from lmdj_core_models.model import load_patch_schema

from tests.test_model import _sample_patch


def test_sample_patch_validates_against_schema():
    schema = load_patch_schema()
    jsonschema.validate(_sample_patch().to_dict(), schema)


def test_schema_rejects_unknown_action():
    schema = load_patch_schema()
    data = _sample_patch().to_dict()
    data["pads"][0]["action"] = "definitely_not_an_action"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_schema_rejects_wrong_schema_id():
    schema = load_patch_schema()
    data = _sample_patch().to_dict()
    data["schema"] = "lmdj.patch.v0"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)
