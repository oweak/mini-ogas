package config

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestLoadDefaultsNodeWithoutEndpointToProcessHealth(t *testing.T) {
	t.Setenv("SUPERVISOR_TEST_TOKEN", "test-token")
	path := writeConfig(t, `
[[process]]
name = "node"
command = "python"
args = ["simulator.py"]
[process.env]
OGAS_API_TOKEN = "${SUPERVISOR_TEST_TOKEN}"
`)

	cfg, err := Load(path)
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	if got := cfg.Processes[0].Health.Type; got != "process" {
		t.Fatalf("health type = %q, want process", got)
	}
	if got := cfg.Processes[0].Env["OGAS_API_TOKEN"]; got != "test-token" {
		t.Fatalf("expanded token = %q, want test-token", got)
	}
}

func TestLoadRejectsHTTPHealthWithoutEndpoint(t *testing.T) {
	path := writeConfig(t, `
[[process]]
name = "api"
command = "python"
[process.health]
type = "http"
`)

	_, err := Load(path)
	if err == nil || !strings.Contains(err.Error(), "endpoint") {
		t.Fatalf("Load() error = %v, want missing HTTP endpoint error", err)
	}
}

func TestProjectSupervisorConfigParses(t *testing.T) {
	t.Setenv("OGAS_API_TOKEN", "test-token")
	t.Setenv("API_ACCESS_TOKEN", "test-token")
	t.Setenv("NODE_INGEST_TOKEN", "test-token")
	t.Setenv("POSTGRES_DSN", "postgresql://test")
	t.Setenv("JWT_SECRET", "test-jwt-secret")
	t.Setenv("AUTH_BOOTSTRAP_PASSWORD", "test-password")
	t.Setenv("OGAS_RUN_ID", "RUN-TEST-001")
	t.Setenv("NATS_SERVER_BIN", "nats-server")
	t.Setenv("NATS_CONFIG_PATH", "nats-server.conf")
	t.Setenv("NATS_AUTH_TOKEN", "test-nats-token")
	t.Setenv("NATS_STORE_DIR", "test-nats-store")
	t.Setenv("NATS_ENABLED", "true")
	t.Setenv("REDIS_SERVER_BIN", "memurai")
	t.Setenv("REDIS_CONFIG_PATH", "memurai.conf")
	t.Setenv("REDIS_URL", "redis://:test@127.0.0.1:6379/0")
	t.Setenv("MINIO_SERVER_BIN", "minio")
	t.Setenv("MINIO_DATA_DIR", "test-minio-data")
	t.Setenv("MINIO_ROOT_USER", "test-minio-user")
	t.Setenv("MINIO_ROOT_PASSWORD", "test-minio-password")
	t.Setenv("CENTRAL_API_PYTHON", "python")

	path := filepath.Join("..", "..", "..", "..", "config", "supervisor.toml")
	cfg, err := Load(path)
	if err != nil {
		t.Fatalf("Load(project config) error = %v", err)
	}
	if len(cfg.Processes) != 11 {
		t.Fatalf("process count = %d, want 11", len(cfg.Processes))
	}
	foundSessionAgnostic := false
	foundNATSEnabled := false
	foundDataPlatform := false
	foundMinIOProbe := false
	for _, process := range cfg.Processes {
		if (process.Health.Type == "http" || process.Health.Type == "http-status") && process.Health.Endpoint == "" {
			t.Fatalf("HTTP process %q has no endpoint", process.Name)
		}
		if process.Name == "nats-server" {
			foundSessionAgnostic = process.Health.SessionAgnostic
		}
		if process.Name == "central-api" {
			foundNATSEnabled = process.Env["NATS_ENABLED"] == "true"
			foundDataPlatform = process.Env["REDIS_ENABLED"] == "true" &&
				process.Env["OBJECT_STORAGE_ENABLED"] == "true"
		}
		if process.Name == "minio-object-store" {
			foundMinIOProbe = process.Health.Type == "http-status"
		}
	}
	if !foundSessionAgnostic {
		t.Fatal("nats-server health must be session agnostic")
	}
	if !foundNATSEnabled {
		t.Fatal("central-api must receive the configured NATS_ENABLED value")
	}
	if !foundDataPlatform {
		t.Fatal("central-api must receive enabled Redis and object-storage settings")
	}
	if !foundMinIOProbe {
		t.Fatal("MinIO must use the third-party HTTP status health probe")
	}
}

func writeConfig(t *testing.T, body string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "supervisor.toml")
	if err := os.WriteFile(path, []byte(body), 0o600); err != nil {
		t.Fatalf("write config: %v", err)
	}
	return path
}
