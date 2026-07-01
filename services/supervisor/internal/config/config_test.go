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

	path := filepath.Join("..", "..", "..", "..", "config", "supervisor.toml")
	cfg, err := Load(path)
	if err != nil {
		t.Fatalf("Load(project config) error = %v", err)
	}
	if len(cfg.Processes) != 8 {
		t.Fatalf("process count = %d, want 8", len(cfg.Processes))
	}
	for _, process := range cfg.Processes {
		if process.Health.Type == "http" && process.Health.Endpoint == "" {
			t.Fatalf("HTTP process %q has no endpoint", process.Name)
		}
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
