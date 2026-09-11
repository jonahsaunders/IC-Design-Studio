"""Host identity persistence and invitation trust boundaries, without GUI state."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from cryptography import x509
from cryptography.hazmat.primitives import hashes

from icstudio.capture_ops import transform
from icstudio.live_protocol import invitation_link, parse_invitation, parse_invitation_details
from icstudio.model import clone, device, example, uid, validate
from icstudio.network_tls import (decode_certificate, encode_certificate,
                                 host_certificates, load_pair, private_address, save_pair)


class NetworkHostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_private_network_addresses_only(self):
        for value in ('10.8.0.2', '172.16.4.3', '192.168.1.8', '100.64.2.3'):
            self.assertEqual(private_address(value), value)
        for value in ('127.0.0.1', '0.0.0.0', '169.254.1.8', '224.0.0.1', '8.8.8.8', '::1', '192.168.1.2:80', 'localhost'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                private_address(value)

    def test_restart_reuses_identity_and_address_change_renews_only_leaf(self):
        path, certificate = host_certificates(self.root, '192.168.1.8')
        identity, leaf = (self.root/'authority.pem').read_bytes(), path.read_bytes()
        self.assertEqual(host_certificates(self.root, '192.168.1.8'), (path, certificate))
        self.assertEqual(path.read_bytes(), leaf)
        new_path, new_certificate = host_certificates(self.root, '10.8.0.2')
        self.assertEqual(new_certificate, certificate)
        self.assertEqual((self.root/'authority.pem').read_bytes(), identity)
        self.assertNotEqual(new_path.read_bytes(), leaf)
        _, renewed = load_pair(new_path)
        renewed.verify_directly_issued_by(decode_certificate(certificate))
        addresses = renewed.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        self.assertIn('10.8.0.2', [str(a) for a in addresses.get_values_for_type(x509.IPAddress)])

    def test_leaf_renewal_keeps_existing_invitations_trusted(self):
        path, certificate = host_certificates(self.root, '192.168.1.8')
        key, authority = load_pair(self.root/'authority.pem')
        leaf_key, leaf = load_pair(path)
        now = datetime.now(timezone.utc)
        builder = (x509.CertificateBuilder().subject_name(leaf.subject).issuer_name(authority.subject)
                   .public_key(leaf_key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now-timedelta(days=80)).not_valid_after(now+timedelta(days=1)))
        for extension in leaf.extensions:
            builder = builder.add_extension(extension.value, extension.critical)
        expiring = builder.sign(key, hashes.SHA256())
        save_pair(path, leaf_key, expiring)
        self.assertEqual(host_certificates(self.root, '192.168.1.8')[1], certificate)
        renewed = load_pair(path)[1]
        self.assertGreater(renewed.not_valid_after_utc, now+timedelta(days=80))
        renewed.verify_directly_issued_by(authority)

    def test_corrupt_saved_identity_is_not_replaced(self):
        path = self.root/'authority.pem'
        path.write_bytes(b'corrupt identity')
        with self.assertRaises(ValueError):
            host_certificates(self.root, '192.168.1.8')
        self.assertEqual(path.read_bytes(), b'corrupt identity')
        self.assertFalse((self.root/'server.pem').exists())

    def test_invitation_round_trip_and_legacy_links(self):
        _, cert = host_certificates(self.root, '192.168.1.8')
        server, workspace, secret = 'https://192.168.1.8:4567', uid(), 'i'*48
        link = invitation_link(server, workspace, secret, cert)
        self.assertTrue(link.startswith('icstudio://join?'))
        self.assertEqual(parse_invitation_details(link), (server, workspace, secret, cert))
        self.assertEqual(parse_invitation(link), (server, workspace, secret))
        legacy = invitation_link('http://127.0.0.1:8765', workspace, secret)
        self.assertEqual(parse_invitation_details(legacy)[3], '')
        for bad in (link+'&cert='+cert, link+'&unexpected=1', link.replace('https%3A', 'http%3A')):
            with self.assertRaises(ValueError):
                parse_invitation_details(bad)
        with self.assertRaises(ValueError):
            invitation_link('http://127.0.0.1:8765', workspace, secret, cert)

    def test_leaf_malformed_and_expired_certificates_are_rejected(self):
        path, cert = host_certificates(self.root, '192.168.1.8')
        for bad in ('', 'x'*3001, cert+'=', cert+'!', encode_certificate(load_pair(path)[1])):
            with self.subTest(value=bad[:30]), self.assertRaises(ValueError):
                decode_certificate(bad)
        key, authority = load_pair(self.root/'authority.pem')
        now = datetime.now(timezone.utc)
        expired = (x509.CertificateBuilder().subject_name(authority.subject).issuer_name(authority.subject)
                   .public_key(key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now-timedelta(days=10)).not_valid_after(now-timedelta(days=1))
                   .add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
                   .sign(key, hashes.SHA256()))
        with self.assertRaisesRegex(ValueError, 'valid dates'):
            decode_certificate(encode_certificate(expired))


class AnnotationTransformTests(unittest.TestCase):
    def test_note_move_copy_keeps_circuit_and_import_source_identity(self):
        p = example('empty');cell = p['cells'][0]
        cell['devices'] = [device('R', 'R1', 500, 200)]
        cell['annotations'] = [dict(id=uid(), x=10, y=20, text='Bias point', xschem_record=4)]
        validate(p)
        circuit = clone(cell['devices'])
        identity = cell['annotations'][0]['id']
        transform(p, cell['id'], [identity], dx=20, dy=-10)
        self.assertEqual((cell['annotations'][0]['x'], cell['annotations'][0]['y']), (30, 10))
        self.assertEqual(cell['annotations'][0]['xschem_record'], 4)
        copied = transform(p, cell['id'], [identity], dx=40, copy=True)
        self.assertEqual(copied, [cell['annotations'][1]['id']])
        self.assertNotEqual(copied[0], identity)
        self.assertNotIn('xschem_record', cell['annotations'][1])
        self.assertEqual(cell['annotations'][1]['x'], 70)
        self.assertEqual(cell['devices'], circuit)
        validate(p)


if __name__ == '__main__':
    unittest.main()
