import jsonschema
import pytest

from lmdj_core_models.materials import load_material_schema
from lmdj_core_models.model import load_patch_schema

from tests.test_materials import sample_material_package
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


def test_schema_rejects_any_pad_count_other_than_16():
    schema = load_patch_schema()
    data = _sample_patch().to_dict()
    for pads in (data["pads"][:15], data["pads"] + [data["pads"][-1]]):
        invalid = {**data, "pads": pads}
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)


def test_material_package_validates_against_schema():
    jsonschema.validate(sample_material_package().to_dict(), load_material_schema())


def test_material_schema_rejects_unsafe_path_and_wrong_decision_count():
    schema = load_material_schema()
    data = sample_material_package().to_dict()
    data["materials"][0]["audio_path"] = "../kick.wav"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)

    data = sample_material_package().to_dict()
    data["slot_decisions"].pop()
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)
