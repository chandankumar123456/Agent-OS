package crypto

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/hex"
	"encoding/pem"
	"fmt"
	"log"
	"math/big"
	"os"
	"path/filepath"
	"time"
)

const certValidityYears = 10

// CryptoManager handles certificate and key generation for local TLS
type CryptoManager struct {
	dataDir string
}

// NewCryptoManager creates a new crypto manager
func NewCryptoManager(dataDir string) *CryptoManager {
	return &CryptoManager{dataDir: dataDir}
}

// certPath returns the path for a certificate file
func (c *CryptoManager) certPath(name string) string {
	return filepath.Join(c.dataDir, "certs", name)
}

// EnsureCertsExist generates TLS certificates if they don't exist
func (c *CryptoManager) EnsureCertsExist() error {
	certDir := filepath.Join(c.dataDir, "certs")
	if err := os.MkdirAll(certDir, 0755); err != nil {
		return fmt.Errorf("failed to create certs directory: %w", err)
	}

	caCertPath := c.certPath("ca.crt")
	caKeyPath := c.certPath("ca.key")
	serverCertPath := c.certPath("server.crt")
	serverKeyPath := c.certPath("server.key")
	clientCertPath := c.certPath("client.crt")
	clientKeyPath := c.certPath("client.key")

	// Check if CA cert exists
	if _, err := os.Stat(caCertPath); os.IsNotExist(err) {
		log.Printf("Generating new CA certificate...")
		if err := c.generateCA(caCertPath, caKeyPath); err != nil {
			return fmt.Errorf("failed to generate CA: %w", err)
		}
	}

	// Check if server cert exists
	if _, err := os.Stat(serverCertPath); os.IsNotExist(err) {
		log.Printf("Generating new server certificate...")
		if err := c.generateServerCert(caCertPath, caKeyPath, serverCertPath, serverKeyPath); err != nil {
			return fmt.Errorf("failed to generate server cert: %w", err)
		}
	}

	// Check if client cert exists
	if _, err := os.Stat(clientCertPath); os.IsNotExist(err) {
		log.Printf("Generating new client certificate...")
		if err := c.generateClientCert(caCertPath, caKeyPath, clientCertPath, clientKeyPath); err != nil {
			return fmt.Errorf("failed to generate client cert: %w", err)
		}
	}

	return nil
}

// GetServerTLSConfig returns TLS config for the gRPC server
func (c *CryptoManager) GetServerTLSConfig() (*tls.Config, error) {
	serverCertPath := c.certPath("server.crt")
	serverKeyPath := c.certPath("server.key")
	caCertPath := c.certPath("ca.crt")

	serverCert, err := tls.LoadX509KeyPair(serverCertPath, serverKeyPath)
	if err != nil {
		return nil, fmt.Errorf("failed to load server cert: %w", err)
	}

	caCertPEM, err := os.ReadFile(caCertPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read CA cert: %w", err)
	}

	caCertPool := x509.NewCertPool()
	if !caCertPool.AppendCertsFromPEM(caCertPEM) {
		return nil, fmt.Errorf("failed to parse CA cert")
	}

	return &tls.Config{
		Certificates: []tls.Certificate{serverCert},
		ClientCAs:    caCertPool,
		ClientAuth:   tls.RequireAndVerifyClientCert,
		MinVersion:   tls.VersionTLS13,
	}, nil
}

// GetClientTLSConfig returns TLS config for gRPC clients
func (c *CryptoManager) GetClientTLSConfig() (*tls.Config, error) {
	clientCertPath := c.certPath("client.crt")
	clientKeyPath := c.certPath("client.key")
	caCertPath := c.certPath("ca.crt")

	clientCert, err := tls.LoadX509KeyPair(clientCertPath, clientKeyPath)
	if err != nil {
		return nil, fmt.Errorf("failed to load client cert: %w", err)
	}

	caCertPEM, err := os.ReadFile(caCertPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read CA cert: %w", err)
	}

	caCertPool := x509.NewCertPool()
	if !caCertPool.AppendCertsFromPEM(caCertPEM) {
		return nil, fmt.Errorf("failed to parse CA cert")
	}

	return &tls.Config{
		Certificates: []tls.Certificate{clientCert},
		RootCAs:      caCertPool,
		ServerName:   "localhost",
		MinVersion:   tls.VersionTLS13,
	}, nil
}

// GetCACertPath returns the path to the CA certificate
func (c *CryptoManager) GetCACertPath() string {
	return c.certPath("ca.crt")
}

// GenerateAPIKey generates a secure random API key
func GenerateAPIKey() (string, error) {
	bytes := make([]byte, 32)
	if _, err := rand.Read(bytes); err != nil {
		return "", fmt.Errorf("failed to generate API key: %w", err)
	}
	return hex.EncodeToString(bytes), nil
}

// generateCA creates a self-signed CA certificate
func (c *CryptoManager) generateCA(certPath, keyPath string) error {
	ca := &x509.Certificate{
		SerialNumber: big.NewInt(1),
		Subject: pkix.Name{
			Organization: []string{"AgentOS Local CA"},
			CommonName:   "AgentOS Local CA",
		},
		NotBefore:             time.Now(),
		NotAfter:              time.Now().AddDate(certValidityYears, 0, 0),
		IsCA:                  true,
		KeyUsage:              x509.KeyUsageCertSign | x509.KeyUsageCRLSign,
		BasicConstraintsValid: true,
	}

	caKey, err := rsa.GenerateKey(rand.Reader, 4096)
	if err != nil {
		return fmt.Errorf("failed to generate CA key: %w", err)
	}

	caCertBytes, err := x509.CreateCertificate(rand.Reader, ca, ca, &caKey.PublicKey, caKey)
	if err != nil {
		return fmt.Errorf("failed to create CA cert: %w", err)
	}

	if err := c.writeCert(certPath, caCertBytes); err != nil {
		return err
	}
	if err := c.writeKey(keyPath, caKey); err != nil {
		return err
	}

	return nil
}

// generateServerCert creates a server certificate signed by the CA
func (c *CryptoManager) generateServerCert(caCertPath, caKeyPath, certPath, keyPath string) error {
	caCertPEM, err := os.ReadFile(caCertPath)
	if err != nil {
		return err
	}
	caKeyPEM, err := os.ReadFile(caKeyPath)
	if err != nil {
		return err
	}

	caCertBlock, _ := pem.Decode(caCertPEM)
	caKeyBlock, _ := pem.Decode(caKeyPEM)

	caCert, err := x509.ParseCertificate(caCertBlock.Bytes)
	if err != nil {
		return err
	}
	caKey, err := x509.ParsePKCS1PrivateKey(caKeyBlock.Bytes)
	if err != nil {
		return err
	}

	serverTemplate := &x509.Certificate{
		SerialNumber: big.NewInt(2),
		Subject: pkix.Name{
			Organization: []string{"AgentOS"},
			CommonName:   "localhost",
		},
		NotBefore:   time.Now(),
		NotAfter:    time.Now().AddDate(certValidityYears, 0, 0),
		KeyUsage:    x509.KeyUsageDigitalSignature | x509.KeyUsageKeyEncipherment,
		ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		DNSNames:    []string{"localhost"},
	}

	serverKey, err := rsa.GenerateKey(rand.Reader, 4096)
	if err != nil {
		return fmt.Errorf("failed to generate server key: %w", err)
	}

	serverCertBytes, err := x509.CreateCertificate(rand.Reader, serverTemplate, caCert, &serverKey.PublicKey, caKey)
	if err != nil {
		return fmt.Errorf("failed to create server cert: %w", err)
	}

	if err := c.writeCert(certPath, serverCertBytes); err != nil {
		return err
	}
	if err := c.writeKey(keyPath, serverKey); err != nil {
		return err
	}

	return nil
}

// generateClientCert creates a client certificate signed by the CA
func (c *CryptoManager) generateClientCert(caCertPath, caKeyPath, certPath, keyPath string) error {
	caCertPEM, err := os.ReadFile(caCertPath)
	if err != nil {
		return err
	}
	caKeyPEM, err := os.ReadFile(caKeyPath)
	if err != nil {
		return err
	}

	caCertBlock, _ := pem.Decode(caCertPEM)
	caKeyBlock, _ := pem.Decode(caKeyPEM)

	caCert, err := x509.ParseCertificate(caCertBlock.Bytes)
	if err != nil {
		return err
	}
	caKey, err := x509.ParsePKCS1PrivateKey(caKeyBlock.Bytes)
	if err != nil {
		return err
	}

	clientTemplate := &x509.Certificate{
		SerialNumber: big.NewInt(3),
		Subject: pkix.Name{
			Organization: []string{"AgentOS"},
			CommonName:   "agentos-client",
		},
		NotBefore:   time.Now(),
		NotAfter:    time.Now().AddDate(certValidityYears, 0, 0),
		KeyUsage:    x509.KeyUsageDigitalSignature,
		ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth},
	}

	clientKey, err := rsa.GenerateKey(rand.Reader, 4096)
	if err != nil {
		return fmt.Errorf("failed to generate client key: %w", err)
	}

	clientCertBytes, err := x509.CreateCertificate(rand.Reader, clientTemplate, caCert, &clientKey.PublicKey, caKey)
	if err != nil {
		return fmt.Errorf("failed to create client cert: %w", err)
	}

	if err := c.writeCert(certPath, clientCertBytes); err != nil {
		return err
	}
	if err := c.writeKey(keyPath, clientKey); err != nil {
		return err
	}

	return nil
}

func (c *CryptoManager) writeCert(path string, certBytes []byte) error {
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0644)
	if err != nil {
		return err
	}
	defer file.Close()

	return pem.Encode(file, &pem.Block{Type: "CERTIFICATE", Bytes: certBytes})
}

func (c *CryptoManager) writeKey(path string, key *rsa.PrivateKey) error {
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0600)
	if err != nil {
		return err
	}
	defer file.Close()

	return pem.Encode(file, &pem.Block{Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(key)})
}
