package config

import (
	"testing"
	"time"
)

func TestLoadUsesDefaults(t *testing.T) {
	t.Setenv("NODE_CODE", "")
	t.Setenv("WORKSHOP_TYPE", "")
	t.Setenv("CENTRAL_API_URL", "")
	t.Setenv("CENTRAL_API_TOKEN", "")
	t.Setenv("LOCAL_DB_PATH", "")
	t.Setenv("COLLECT_INTERVAL_SECONDS", "")

	cfg := Load()

	if cfg.NodeCode != "turning-workshop-01" {
		t.Fatalf("unexpected default node code: %s", cfg.NodeCode)
	}
	if cfg.WorkshopType != "turning" {
		t.Fatalf("unexpected default workshop type: %s", cfg.WorkshopType)
	}
	if cfg.CentralAPIURL != "http://localhost:8080" {
		t.Fatalf("unexpected default central url: %s", cfg.CentralAPIURL)
	}
	if cfg.APIToken != "mini-ogas-dev-token" {
		t.Fatalf("unexpected default token: %s", cfg.APIToken)
	}
	if cfg.LocalDBPath != "/var/lib/mini-ogas/node.db" {
		t.Fatalf("unexpected default db path: %s", cfg.LocalDBPath)
	}
	if cfg.Interval != 5*time.Second {
		t.Fatalf("unexpected default interval: %s", cfg.Interval)
	}
}

func TestLoadReadsEnvironment(t *testing.T) {
	t.Setenv("NODE_CODE", "cloud-workshop-01")
	t.Setenv("WORKSHOP_TYPE", "milling")
	t.Setenv("CENTRAL_API_URL", "http://central:8080")
	t.Setenv("CENTRAL_API_TOKEN", "secret")
	t.Setenv("LOCAL_DB_PATH", "/data/node.db")
	t.Setenv("COLLECT_INTERVAL_SECONDS", "12")

	cfg := Load()

	if cfg.NodeCode != "cloud-workshop-01" {
		t.Fatalf("node code not read from env: %s", cfg.NodeCode)
	}
	if cfg.WorkshopType != "milling" {
		t.Fatalf("workshop type not read from env: %s", cfg.WorkshopType)
	}
	if cfg.CentralAPIURL != "http://central:8080" {
		t.Fatalf("central url not read from env: %s", cfg.CentralAPIURL)
	}
	if cfg.APIToken != "secret" {
		t.Fatalf("token not read from env: %s", cfg.APIToken)
	}
	if cfg.LocalDBPath != "/data/node.db" {
		t.Fatalf("db path not read from env: %s", cfg.LocalDBPath)
	}
	if cfg.Interval != 12*time.Second {
		t.Fatalf("interval not read from env: %s", cfg.Interval)
	}
}

func TestLoadFallsBackForInvalidInterval(t *testing.T) {
	t.Setenv("COLLECT_INTERVAL_SECONDS", "not-a-number")
	if cfg := Load(); cfg.Interval != 5*time.Second {
		t.Fatalf("invalid interval should fall back, got %s", cfg.Interval)
	}

	t.Setenv("COLLECT_INTERVAL_SECONDS", "0")
	if cfg := Load(); cfg.Interval != 5*time.Second {
		t.Fatalf("zero interval should fall back, got %s", cfg.Interval)
	}
}
