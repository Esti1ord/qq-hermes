from qq_hermes_bridge import app_helpers


def test_health_response_is_minimal_by_default():
    assert app_helpers.health_response(
        target_group_id=2,
        allowed_group_ids={3, 1, 2},
        bot_qq="12345",
        onebot_http_url="http://127.0.0.1:3000",
    ) == {"ok": True}


def test_detailed_health_response_avoids_endpoint_and_group_list_details():
    assert app_helpers.health_response(
        target_group_id=2,
        allowed_group_ids={3, 1, 2},
        bot_qq="12345",
        onebot_http_url="http://127.0.0.1:3000",
        detailed=True,
    ) == {
        "ok": True,
        "target_group_id": 2,
        "allowed_group_count": 3,
        "bot_qq_configured": True,
        "onebot_http_configured": True,
    }


def test_request_token_accepts_bearer_and_bridge_token_headers():
    assert app_helpers.request_token({"Authorization": "Bearer secret"}) == "secret"
    assert app_helpers.request_token({"authorization": "bearer secret"}) == "secret"
    assert app_helpers.request_token({"X-Bridge-Token": "other"}) == "other"
    assert app_helpers.request_token({"Authorization": "Basic secret"}) == ""


def test_request_is_authorized_only_enforces_configured_token():
    assert app_helpers.request_is_authorized({}, "")
    assert app_helpers.request_is_authorized({"Authorization": "Bearer secret"}, "secret")
    assert app_helpers.request_is_authorized({"X-Bridge-Token": "secret"}, "secret")
    assert not app_helpers.request_is_authorized({}, "secret")
    assert not app_helpers.request_is_authorized({"Authorization": "Bearer wrong"}, "secret")
