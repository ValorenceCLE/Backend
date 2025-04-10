#!/bin/bash

set -e

CERT_DIR="/app/certs"
CERT_FILE="${CERT_DIR}/cert.pem"
KEY_FILE="${CERT_DIR}/key.pem"

# Create the certs directory if it doesn't exist
mkdir -p "${CERT_DIR}"

# Only generate new certs if they don't already exist
if [ ! -f "${CERT_FILE}" ] || [ ! -f "${KEY_FILE}" ]; then
    echo "Generating self-signed certificates..."

    # Generate a self-signed certificate valid for 10 years
    openssl req -x509 -newkey rsa:4096 -keyout ${KEY_FILE} -out ${CERT_FILE} -days 3650 -nodes -subj "/CN=localhost" -addext "subjectAltName=IP:127.0.0.1,IP:0.0.0.0"
    
    # Set proper permissions
    chmod 600 ${KEY_FILE}
    chmod 644 ${CERT_FILE}
    
    echo "Certificate generation complete!"
else
    echo "Certificates already exist, skipping generation."
fi