"""Tests for the static reference-data seeds."""

from dpmcore.loaders.xbrl.seeds import (
    DATA_TYPE_ROWS,
    DPM_ATTRIBUTE_ROWS,
    DPM_CLASS_ROWS,
    LANGUAGE_ROWS,
    OPERATOR_ROWS,
    ensure_data_types,
    ensure_dpm_attributes,
    ensure_dpm_classes,
    ensure_languages,
    ensure_operators,
)
from dpmcore.orm.infrastructure import DataType, DpmClass, Language
from dpmcore.orm.operations import Operator


class TestEnsureDpmClasses:
    def test_creates_all_classes_on_fresh_db(self, schema_session):
        class_ids = ensure_dpm_classes(schema_session)
        assert len(class_ids) == len(DPM_CLASS_ROWS)
        assert class_ids["Item"] == 5
        assert class_ids["Release"] == 28
        assert class_ids["SubCategoryItem"] == 30

    def test_is_idempotent(self, schema_session):
        ensure_dpm_classes(schema_session)
        again = ensure_dpm_classes(schema_session)
        count = schema_session.query(DpmClass).count()
        assert count == len(DPM_CLASS_ROWS)
        assert again["Framework"] == 6

    def test_reuses_pre_existing_rows(self, schema_session):
        schema_session.add(DpmClass(class_id=999, name="Item"))
        schema_session.flush()
        class_ids = ensure_dpm_classes(schema_session)
        assert class_ids["Item"] == 999


class TestEnsureDpmAttributes:
    def test_creates_translation_attributes(self, schema_session):
        attrs = ensure_dpm_attributes(schema_session)
        assert attrs[("Item", "Name")] == 30
        assert attrs[("HeaderVersion", "Label")] == 105
        assert len(attrs) == len(DPM_ATTRIBUTE_ROWS)

    def test_is_idempotent(self, schema_session):
        first = ensure_dpm_attributes(schema_session)
        second = ensure_dpm_attributes(schema_session)
        assert first == second


class TestEnsureDataTypes:
    def test_creates_the_thirteen_data_types(self, schema_session):
        codes = ensure_data_types(schema_session)
        assert len(codes) == len(DATA_TYPE_ROWS)
        assert codes["m"] == 9
        assert codes["e"] == 8
        assert codes["s"] == 3

    def test_parent_links_are_preserved(self, schema_session):
        ensure_data_types(schema_session)
        enumeration = (
            schema_session.query(DataType)
            .filter(DataType.code == "e")
            .one()
        )
        assert enumeration.parent_data_type_id == 3

    def test_is_idempotent(self, schema_session):
        ensure_data_types(schema_session)
        ensure_data_types(schema_session)
        assert schema_session.query(DataType).count() == len(DATA_TYPE_ROWS)


class TestEnsureOperators:
    def test_creates_all_operators(self, schema_session):
        created = ensure_operators(schema_session)
        assert created == len(OPERATOR_ROWS)
        addition = (
            schema_session.query(Operator)
            .filter(Operator.name == "Addition")
            .one()
        )
        assert addition.operator_id == 2
        assert addition.symbol == "+"

    def test_is_idempotent(self, schema_session):
        ensure_operators(schema_session)
        assert ensure_operators(schema_session) == 0


class TestEnsureLanguages:
    def test_creates_en_fr_nl(self, schema_session):
        codes = ensure_languages(schema_session)
        assert codes == {"en": 1, "fr": 2, "nl": 3}
        assert schema_session.query(Language).count() == len(LANGUAGE_ROWS)

    def test_reuses_existing_language_rows_by_name(self, schema_session):
        schema_session.add(Language(language_code=7, name="English"))
        schema_session.flush()
        codes = ensure_languages(schema_session)
        assert codes["en"] == 7
        # New rows are allocated above the existing maximum.
        assert codes["fr"] == 8
        assert codes["nl"] == 9

    def test_is_idempotent(self, schema_session):
        first = ensure_languages(schema_session)
        second = ensure_languages(schema_session)
        assert first == second


class TestEnsureDpmAttributesEdgeCases:
    def test_ignores_attributes_of_unknown_classes(self, schema_session):
        from dpmcore.orm.infrastructure import DpmAttribute

        schema_session.add(
            DpmAttribute(attribute_id=9999, class_id=None, name="Stray")
        )
        schema_session.flush()
        attrs = ensure_dpm_attributes(schema_session)
        assert ("Stray", "Stray") not in attrs
        assert attrs[("Item", "Name")] == 30
