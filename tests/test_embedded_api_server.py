from app.runtime.api_server import EmbeddedApiServer


def test_embedded_api_base_url() -> None:
    server = EmbeddedApiServer(host="127.0.0.1", port=8123)
    assert server.base_url == "http://127.0.0.1:8123"


def test_stop_is_safe_when_server_is_not_owned() -> None:
    server = EmbeddedApiServer()
    server.stop()
    assert server.owns_server is False
