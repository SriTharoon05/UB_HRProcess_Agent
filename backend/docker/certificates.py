"""Generate machine-local development trust; the CA private key is never saved."""

import argparse
import datetime
import ipaddress
import os
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def generate(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    server = directory / "server"
    server.mkdir(mode=0o755, exist_ok=True)
    if any((directory / name).exists() for name in ("rootCA.pem", "server/localhost.pem", "server/localhost-key.pem")):
        raise SystemExit("Certificates already exist. Keep them, or remove .certs to deliberately regenerate and re-trust.")
    now = datetime.datetime.now(datetime.timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "TalentMatch machine-local development CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(now + datetime.timedelta(days=825))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=False, key_cert_sign=True,
                         key_agreement=False, content_commitment=False, data_encipherment=False,
                         crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
          .sign(ca_key, hashes.SHA256()))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
            .issuer_name(ca.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(now + datetime.timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"),
                           x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                           x509.IPAddress(ipaddress.ip_address("::1"))]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=True, key_cert_sign=False,
                           key_agreement=False, content_commitment=False, data_encipherment=False,
                           crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    (directory / "rootCA.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    (server / "localhost.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    private = server / "localhost-key.pem"
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption()))
    os.chmod(private, 0o640)
    # The unprivileged nginx image uses UID/GID 101; the bind is read-only.
    if os.geteuid() == 0:
        os.chown(private, 101, 101)
    print("Generated unique localhost certificate and public rootCA.pem; no CA signing key was stored.")
    print("Trust only rootCA.pem on this computer. Never transfer .certs/server/localhost-key.pem.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    generate(parser.parse_args().directory)
