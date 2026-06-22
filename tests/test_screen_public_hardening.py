from pathlib import Path

from admin.api.main import app


ROOT = Path(__file__).resolve().parents[1]
SCREEN = ROOT / "admin" / "frontend-vue" / "src" / "views" / "Screen.vue"
STYLE = ROOT / "admin" / "frontend-vue" / "src" / "style.css"


def test_production_app_does_not_publish_openapi_docs():
    assert app.docs_url is None
    assert app.openapi_url is None


def test_production_openapi_path_does_not_fall_back_to_spa():
    from fastapi.testclient import TestClient

    client = TestClient(app)

    assert client.get("/api/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_screen_uses_local_font_stack_for_public_entry():
    style = STYLE.read_text(encoding="utf-8")

    assert "fonts.googleapis.com" not in style
    assert "fonts.gstatic.com" not in style


def test_screen_list_uses_same_mandatory_label_as_detail_modal():
    source = SCREEN.read_text(encoding="utf-8")

    assert "{{ mandatoryText(item.mandatory) }}" in source
    assert "item.mandatory==='mandatory'?'强制':'自愿'" not in source


def test_screen_makes_regional_inheritance_visible_to_users():
    source = SCREEN.read_text(encoding="utf-8")

    assert "区域/上级辖区适用" in source
    assert "合并 EU 等上级辖区的 verified 产品网络安全法规/认证" in source
    assert "contextItem.scope_origin" in source
    assert "来自${source}，适用于${target}" in source
    assert "inherited_verified_count" in source
    assert "本地+${inheritedCount}区域" in source


def test_screen_country_code_mapping_covers_small_and_high_value_countries():
    source = SCREEN.read_text(encoding="utf-8")

    for mapping in ("'702':'SG'", "'116':'KH'", "'634':'QA'", "'659':'KN'", "'180':'CD'"):
        assert mapping in source
