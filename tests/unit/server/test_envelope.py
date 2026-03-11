"""Unit tests for the response envelope builder."""

from dpmcore.server.envelope import build_meta, envelope, error_envelope


class TestBuildMeta:
    def test_defaults(self):
        meta = build_meta()
        assert "id" in meta
        assert "prepared" in meta
        assert meta["contentLanguage"] == "en"
        assert meta["offset"] == 0
        assert meta["limit"] == 100
        assert "totalCount" not in meta

    def test_with_total_count(self):
        meta = build_meta(total_count=42, offset=10, limit=20)
        assert meta["totalCount"] == 42
        assert meta["offset"] == 10
        assert meta["limit"] == 20

    def test_content_language(self):
        meta = build_meta(content_language="fr")
        assert meta["contentLanguage"] == "fr"


class TestEnvelope:
    def test_wraps_data(self):
        result = envelope({"releases": [{"code": "3.4"}]}, total_count=1)
        assert "meta" in result
        assert "data" in result
        assert result["data"]["releases"] == [{"code": "3.4"}]
        assert result["meta"]["totalCount"] == 1

    def test_pagination(self):
        result = envelope({"items": []}, offset=5, limit=10)
        assert result["meta"]["offset"] == 5
        assert result["meta"]["limit"] == 10


class TestErrorEnvelope:
    def test_structure(self):
        result = error_envelope(400, "Bad Request", "Something went wrong")
        assert "meta" in result
        assert "errors" in result
        assert len(result["errors"]) == 1
        err = result["errors"][0]
        assert err["code"] == 400
        assert err["title"] == "Bad Request"
        assert err["detail"] == "Something went wrong"
