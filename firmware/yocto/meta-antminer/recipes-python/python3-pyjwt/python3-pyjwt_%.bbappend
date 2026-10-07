# python3-cryptography pulls the whole Rust toolchain (rust-llvm-native, ~1 h) and large target
# libs. OpenPLC's REST API signs JWTs with HS256 (HMAC), which PyJWT does with hashlib alone,
# so the optional RSA/EC backend is dropped from the feed.
RDEPENDS:${PN}:remove = "python3-cryptography"
