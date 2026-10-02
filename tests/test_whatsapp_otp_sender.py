"""OTP sender selection and the MSG91 request shape."""
from types import SimpleNamespace

from services.whatsapp_channel import otp_sender


def _cfg(**kw):
    base = {"otp_provider": "", "msg91_auth_key": None, "msg91_otp_template_id": None, "msg91_otp_var": "var1"}
    base.update(kw)
    return SimpleNamespace(**base)


def test_no_provider_means_no_sender():
    assert otp_sender.build_otp_sender(_cfg()) is None


def test_unknown_provider_means_no_sender():
    assert otp_sender.build_otp_sender(_cfg(otp_provider="carrier-pigeon")) is None


def test_msg91_without_credentials_means_no_sender():
    assert otp_sender.build_otp_sender(_cfg(otp_provider="msg91")) is None


def test_mock_sender_records_codes():
    sender = otp_sender.build_otp_sender(_cfg(otp_provider="mock"))
    assert sender.send("+911111111111", "123456") is True
    assert sender.sent == [("+911111111111", "123456")]


def test_msg91_mobile_format_matches_main_backend():
    assert otp_sender._msg91_mobile("9876543210") == "919876543210"
    assert otp_sender._msg91_mobile("+91 98765-43210") == "919876543210"


def test_msg91_sends_flow_request(monkeypatch):
    captured = {}

    class _Resp:
        status_code = 200
        text = '{"type":"success"}'

        def json(self):
            return {"type": "success"}

    def fake_post(url, json, headers, timeout):
        captured.update(url=url, json=json, headers=headers)
        return _Resp()

    monkeypatch.setattr(otp_sender.requests, "post", fake_post)
    sender = otp_sender.build_otp_sender(
        _cfg(otp_provider="msg91", msg91_auth_key="k", msg91_otp_template_id="t-1")
    )
    assert sender.send("9876543210", "482913") is True
    assert captured["url"] == "https://control.msg91.com/api/v5/flow/"
    assert captured["headers"]["authkey"] == "k"
    assert captured["json"] == {"template_id": "t-1", "recipients": [{"mobiles": "919876543210", "var1": "482913"}]}


def test_msg91_error_response_is_a_failure(monkeypatch):
    class _Resp:
        status_code = 200
        text = '{"type":"error"}'

        def json(self):
            return {"type": "error", "message": "bad template"}

    monkeypatch.setattr(otp_sender.requests, "post", lambda *a, **k: _Resp())
    sender = otp_sender.Msg91OtpSender("k", "t-1")
    assert sender.send("9876543210", "482913") is False
    