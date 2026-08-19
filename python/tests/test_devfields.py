"""Developer-field tests: resolution, salvage variants, vendor registry (taxonomy #22)."""

import build_fit

import chiptime


def _records(result: chiptime.ParseResult) -> list:
    return [m for m in result.messages if m.name == "record"]


def test_stryd_known_vendor_resolution() -> None:
    result = chiptime.parse(build_fit.dev_fields_stryd())
    assert result.ok and not result.errors
    rec = _records(result)[0]
    power = rec.fields["power"]
    assert power.value == 250
    assert power.units == "Watts"
    assert power.developer is not None
    assert power.developer.vendor == "stryd"
    assert power.developer.canonical_name == "running_power"
    assert power.developer.application_id == bytes(range(16)).hex()
    lss = rec.fields["leg_spring_stiffness"]
    assert lss.value == 10.3  # scale 10 from field_description
    assert lss.developer is not None and lss.developer.canonical_name == "leg_spring_stiffness"


def test_missing_field_description_synthesizes() -> None:
    result = chiptime.parse(build_fit.dev_missing_description())
    assert result.ok
    rec = _records(result)[0]
    fv = rec.fields["dev_0_5"]
    assert fv.value is None and fv.raw == b"\x2c\x01"  # 300 LE, data preserved
    assert fv.developer is not None and fv.developer.vendor == "development"
    assert any(w.code == "DEV_FIELD_NAME_SYNTHESIZED" for w in result.warnings)


def test_no_developer_data_id_still_resolves() -> None:
    result = chiptime.parse(build_fit.dev_no_data_id())
    assert result.ok
    rec = _records(result)[0]
    fv = rec.fields["smo2ish"]
    assert fv.value == 60
    assert fv.developer is not None and fv.developer.vendor is None
    assert any(w.code == "DEV_DATA_ID_MISSING" for w in result.warnings)


def test_null_name_synthesizes_and_keeps_data() -> None:
    result = chiptime.parse(build_fit.dev_null_name())
    assert result.ok
    rec = _records(result)[0]
    fv = rec.fields["dev_0_7"]
    assert fv.raw == b"\x09\x03"  # 777 LE preserved (fitparse #62 would have crashed)
    assert any(w.code == "DEV_FIELD_NAME_SYNTHESIZED" for w in result.warnings)


def test_late_description_backfills() -> None:
    result = chiptime.parse(build_fit.dev_late_description())
    assert result.ok
    recs = _records(result)
    # all four records resolved, including the three that preceded the description
    for i, rec in enumerate(recs):
        assert rec.fields["power"].value == 260 + i, i
    assert any(p.code == "DEV_FIELD_RESOLVED_LATE" for p in result.provenance)


def test_dev_index_reused_by_second_app() -> None:
    result = chiptime.parse(build_fit.dev_index_reused())
    assert result.ok
    recs = _records(result)
    assert recs[0].fields["power"].developer.vendor == "stryd"
    ct = recs[1].fields["core_temperature"]
    assert ct.developer is not None and ct.developer.vendor == "greenteg"
    assert ct.developer.canonical_name == "core_temperature"
    assert any(w.code == "DEV_INDEX_REDEFINED" for w in result.warnings)


def test_streaming_iter_messages_no_backfill_but_no_crash() -> None:
    msgs = list(chiptime.iter_messages(build_fit.dev_late_description()))
    recs = [m for m in msgs if m.name == "record"]
    assert "dev_0_5" in recs[0].fields  # streaming keeps placeholder (documented)
    assert "power" in recs[3].fields  # post-description records resolve inline
