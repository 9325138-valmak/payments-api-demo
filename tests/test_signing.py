import pytest

from payments_demo import signing

SECRET = "whsec_test"
BODY = b'{"id":"evt_1","type":"payment.succeeded"}'


def test_valid_signature_passes():
    header = signing.sign(BODY, SECRET, timestamp=1_000)
    signing.verify(header, BODY, SECRET, now=1_010)


def test_tampered_payload_is_rejected():
    header = signing.sign(BODY, SECRET, timestamp=1_000)
    with pytest.raises(signing.SignatureError, match="mismatch"):
        signing.verify(header, BODY + b" ", SECRET, now=1_010)


def test_wrong_secret_is_rejected():
    header = signing.sign(BODY, "other-secret", timestamp=1_000)
    with pytest.raises(signing.SignatureError, match="mismatch"):
        signing.verify(header, BODY, SECRET, now=1_010)


def test_old_timestamp_is_rejected_as_possible_replay():
    header = signing.sign(BODY, SECRET, timestamp=1_000)
    with pytest.raises(signing.SignatureError, match="tolerance"):
        signing.verify(header, BODY, SECRET, tolerance=300, now=1_000 + 301)


@pytest.mark.parametrize("header", ["", None, "garbage", "t=abc,v1=deadbeef", "v1=deadbeef"])
def test_missing_or_malformed_header_is_rejected(header):
    with pytest.raises(signing.SignatureError):
        signing.verify(header, BODY, SECRET, now=1_000)
