"""Private-network certificates; trust stays with an invitation/session, never global."""
import base64
from datetime import datetime, timedelta, timezone
import ipaddress
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from .model import atomic_write


def private_address(value):
    address = ipaddress.IPv4Address(value)
    if address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified or address.is_reserved or address.is_global:
        raise ValueError('Choose a private IPv4 address on your local network or VPN.')
    return str(address)


def encode_certificate(cert):
    return base64.urlsafe_b64encode(cert.public_bytes(serialization.Encoding.DER)).decode().rstrip('=')


def decode_certificate(value):
    if not isinstance(value, str) or not 100 <= len(value) <= 3000:
        raise ValueError('The invitation certificate is missing or invalid. Ask for a new invitation.')
    import re
    if not re.fullmatch('[A-Za-z0-9_-]+', value):
        raise ValueError('Invalid invitation certificate encoding.')
    raw = base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
    cert = x509.load_der_x509_certificate(raw)
    if cert.public_bytes(serialization.Encoding.DER) != raw:
        raise ValueError('Invalid invitation certificate data.')
    try:
        constraints = cert.extensions.get_extension_for_class(x509.BasicConstraints).value
    except x509.ExtensionNotFound:
        raise ValueError('The invitation does not contain a host authority certificate.') from None
    if not constraints.ca or constraints.path_length != 0:
        raise ValueError('The invitation does not contain an IC Design Studio host certificate.')
    if not cert.not_valid_before_utc <= datetime.now(timezone.utc) < cert.not_valid_after_utc:
        raise ValueError('The host certificate is outside its valid dates. Check your clock and ask the host for a new invitation.')
    return cert


def certificate_pem(value):
    return decode_certificate(value).public_bytes(serialization.Encoding.PEM)


def load_pair(path):
    data = Path(path).read_bytes()
    key = serialization.load_pem_private_key(data, password=None)
    marker = b'-----BEGIN CERTIFICATE-----'
    cert = x509.load_pem_x509_certificate(marker + data.split(marker, 1)[1])
    if key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo) != cert.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo):
        raise ValueError('The saved host key and certificate do not match. Restore your host backup.')
    return key, cert


def save_pair(path, key, cert, chain=b''):
    data = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    atomic_write(path, data + cert.public_bytes(serialization.Encoding.PEM) + chain)
    Path(path).chmod(0o600)


def host_certificates(directory, address):
    """Keep the invitation authority stable; renew address-specific leaves safely."""
    directory = Path(directory)
    address = private_address(address)
    now = datetime.now(timezone.utc)
    authority_path = directory / 'authority.pem'
    if authority_path.exists():
        authority_key, authority = load_pair(authority_path)
    else:
        authority_key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'IC Design Studio private host')])
        authority = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                     .public_key(authority_key.public_key()).serial_number(x509.random_serial_number())
                     .not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=3650))
                     .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
                     .add_extension(x509.KeyUsage(True, False, False, False, False, True, True, False, False), critical=True)
                     .sign(authority_key, hashes.SHA256()))
        save_pair(authority_path, authority_key, authority)
    if not authority.not_valid_before_utc <= now < authority.not_valid_after_utc-timedelta(days=1):
        raise ValueError('The saved host certificate is outside its valid dates. Check your clock or restore a valid host backup.')
    decode_certificate(encode_certificate(authority))
    path = directory / 'server.pem'
    leaf = None
    if path.exists():
        _, leaf = load_pair(path)
        try:
            addresses = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.IPAddress)
            leaf.verify_directly_issued_by(authority)
            if ipaddress.ip_address(address) not in addresses or leaf.not_valid_before_utc > now or leaf.not_valid_after_utc < now+timedelta(days=7):
                leaf = None
        except (ValueError, x509.ExtensionNotFound):
            leaf = None
    if leaf is None:
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'IC Design Studio session')])
        leaf = (x509.CertificateBuilder().subject_name(name).issuer_name(authority.subject)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now-timedelta(minutes=5)).not_valid_after(min(now+timedelta(days=90), authority.not_valid_after_utc))
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(address)), x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), critical=False)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                .add_extension(x509.KeyUsage(True, False, False, False, False, False, False, False, False), critical=True)
                .sign(authority_key, hashes.SHA256()))
        save_pair(path, key, leaf, authority.public_bytes(serialization.Encoding.PEM))
    return path, encode_certificate(authority)


def network_addresses():
    from PySide6.QtNetwork import QNetworkInterface
    choices = []
    for interface in QNetworkInterface.allInterfaces():
        if not interface.flags() & QNetworkInterface.IsUp or interface.flags() & QNetworkInterface.IsLoopBack:
            continue
        for entry in interface.addressEntries():
            try:
                address = private_address(entry.ip().toString())
            except ValueError:
                continue
            if address not in [v[0] for v in choices]:
                choices.append((address, interface.humanReadableName()))
    return choices
