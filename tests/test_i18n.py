from __future__ import annotations


def test_dashboard_renders_korean_when_locale_query_is_supported(client):
    response = client.get("/?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<html lang="ko">' in text
    assert "대시보드" in text
    assert "원시 검침" in text
    assert "원시 적재" in text
    assert "표준화" in text
    assert "최근 재계산 사용량" in text
    assert "mdms_locale=ko" in response.headers.get("Set-Cookie", "")


def test_dashboard_falls_back_to_english_for_unsupported_locale(client):
    response = client.get("/?lang=ja")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<html lang="en">' in text
    assert "Dashboard" in text
    assert "Raw Reads" in text
    assert "mdms_locale=en" in response.headers.get("Set-Cookie", "")


def test_locale_cookie_persists_between_requests(client):
    client.get("/?lang=ko")

    response = client.get("/")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<html lang="ko">' in text
    assert "오류 큐" in text


def test_ingest_reads_error_payload_is_localized_from_accept_language(client):
    response = client.post(
        "/api/v1/ingest/reads",
        headers={"Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error_code": "json_payload_required",
        "message": "JSON 페이로드가 필요합니다.",
        "locale": "ko",
    }
