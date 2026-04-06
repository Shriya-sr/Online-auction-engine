"""
================================================================================
SSL CERTIFICATE GENERATOR - Create Self-Signed Certificates
================================================================================
PURPOSE:
  - Generate self-signed SSL/TLS certificates for secure server communication
  - Creates pair: server.crt (certificate) and server.key (private key)
  - Required before running the auction server

NEED IT BECAUSE:
  - All client-server communication uses SSL/TLS encryption
  - Self-signed certificates are sufficient for internal/testing use
  - Production would use CA-signed certificates

WHAT IT CREATES:
  1. server.key - RSA 2048-bit private key (public-private key)
     - Used by server to decrypt client messages
     - Used to sign communications
     - KEEP SECRET!

  2. server.crt - Self-signed X.509 certificate (365-day validity) (This certificate is like give my public key to clients in a structured, trusted way)
     - Contains: Subject CN (localhost), Organization, Country, etc.
     - Public key wrapped in certificate format
     - Distributed to clients for verification

CERTIFICATE DETAILS:
  - Public Key: RSA 2048-bit
  - Hash Algorithm: SHA256
  - Validity: 365 days from generation
  - Subject: CN=localhost, O=AuctionApp, L=Bangalore, ST=Karnataka, C=IN
  - Self-signed: No external Certificate Authority needed

USAGE:
  1. Before first run:
     python generate_cert.py
     # Creates: server.crt and server.key in current directory

  2. Server uses it:
     context.load_cert_chain(certfile='server.crt', keyfile='server.key')

  3. Clients verify it:
     ctx.load_verify_locations(cafile='server.crt')

REGENERATION:
  - If cert expires after 365 days, regenerate:
    python generate_cert.py
  - Replaces old server.crt and server.key
  - All clients/server must be restarted with new cert

SECURITY NOTES:
  - Appropriate for testing/internal networks
  - For production: Use CA-signed certificates from trusted authority
  - Never share server.key with clients or untrusted parties
  - Self-signed certs produce browser warnings (expected in testing)
================================================================================
"""

from cryptography import x509  # X.509 certificate creation
from cryptography.x509.oid import NameOID  # OID constants for certificate fields
from cryptography.hazmat.primitives import serialization, hashes  # For key serialization and hashing
from cryptography.hazmat.primitives.asymmetric import rsa  # For RSA key generation
import datetime  # For date/time handling


# Generate private key (RSA 2048-bit)
key = rsa.generate_private_key(
  public_exponent=65537,  # Standard public exponent
  key_size=2048,          # Key size in bits
)


# Create self-signed certificate subject/issuer fields
subject = issuer = x509.Name([
  x509.NameAttribute(NameOID.COUNTRY_NAME, u"IN"),              # Country
  x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"Karnataka"),  # State
  x509.NameAttribute(NameOID.LOCALITY_NAME, u"Bangalore"),      # Locality/City
  x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"AuctionApp"), # Organization
  x509.NameAttribute(NameOID.COMMON_NAME, u"localhost"),        # Common Name (hostname)
])


# Build and sign the certificate
cert = x509.CertificateBuilder().subject_name(subject)  # Set subject
cert = cert.issuer_name(issuer)                        # Set issuer (self-signed)
cert = cert.public_key(key.public_key())               # Set public key
cert = cert.serial_number(x509.random_serial_number()) # Unique serial number
cert = cert.not_valid_before(datetime.datetime.utcnow())  # Valid from now
cert = cert.not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))  # Valid for 1 year
cert = cert.sign(key, hashes.SHA256())                # Sign with private key (SHA256)
# above => certificate data is hashed using SHA256 and hash is signed using our private key

# Write private key to file (PEM, unencrypted) #server.key shouldn't be shared!
with open("server.key", "wb") as f:
  f.write(key.private_bytes(
    encoding=serialization.Encoding.PEM,  # PEM format - base64 (outer look)
    format=serialization.PrivateFormat.TraditionalOpenSSL,  # OpenSSL format(internally structured)
    encryption_algorithm=serialization.NoEncryption(),      # No encryption
  ))


# Write certificate to file (PEM)
with open("server.crt", "wb") as f:
  f.write(cert.public_bytes(serialization.Encoding.PEM))

print("SSL certificate and key generated!")  # Success message
