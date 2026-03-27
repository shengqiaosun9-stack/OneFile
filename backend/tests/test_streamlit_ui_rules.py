import state_manager
import ui_components


def test_is_valid_email_accepts_normalized_valid_inputs():
    assert state_manager.is_valid_email(" User@Example.com ") is True
    assert state_manager.is_valid_email("founder+onefile@company.co") is True


def test_is_valid_email_rejects_invalid_inputs():
    assert state_manager.is_valid_email("") is False
    assert state_manager.is_valid_email("not-an-email") is False
    assert state_manager.is_valid_email("a@b") is False


def test_primary_cta_labels_are_single_and_deterministic():
    assert ui_components.get_screen_primary_cta("landing", is_owner=False) == "进入项目空间"
    assert ui_components.get_screen_primary_cta("list_card", is_owner=True) == "查看完整档案"
    assert ui_components.get_screen_primary_cta("detail", is_owner=True) == "编辑项目"
    assert ui_components.get_screen_primary_cta("detail", is_owner=False) == "创建我的项目档案"
    assert ui_components.get_screen_primary_cta("share", is_owner=True) == "继续更新这个项目"
    assert ui_components.get_screen_primary_cta("share", is_owner=False) == "创建我的项目档案"
