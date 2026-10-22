from app.security import hash_password, hash_token, new_session_token, verify_password


def test_hash_is_salted_and_verifies():
    first = hash_password("correct horse battery")
    second = hash_password("correct horse battery")
    assert first != second  # random salt
    assert first.startswith("scrypt$")
    assert "correct horse battery" not in first
    assert verify_password("correct horse battery", first)
    assert verify_password("correct horse battery", second)


def test_wrong_password_does_not_verify():
    stored = hash_password("correct horse battery")
    assert not verify_password("correct horse batterz", stored)
    assert not verify_password("", stored)


def test_malformed_hash_never_verifies():
    for bad in ("", "plain", "scrypt$1$2", "bcrypt$x$y$z$a$b", "scrypt$a$b$c$d$e"):
        assert not verify_password("anything", bad)


def test_session_tokens_are_unique_and_stored_hashed():
    token = new_session_token()
    assert token != new_session_token()
    assert len(token) >= 40
    assert hash_token(token) == hash_token(token)
    assert hash_token(token) != token
    assert len(hash_token(token)) == 64
