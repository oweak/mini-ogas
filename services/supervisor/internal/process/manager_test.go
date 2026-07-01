package process

import (
	"os"
	"testing"
	"time"

	"mini-ogas/supervisor/internal/config"
)

func TestProcessHealthAndManualRestart(t *testing.T) {
	manager := NewManager("test-session")
	manager.Register(config.Config{Processes: []config.ProcessSpec{{
		Name:    "helper",
		Command: os.Args[0],
		Args:    []string{"-test.run=TestSupervisorHelperProcess"},
		Env:     map[string]string{"GO_WANT_SUPERVISOR_HELPER": "1"},
		Health:  config.HealthCheckConfig{Type: "process", Interval: 1, Timeout: 1, Retries: 1},
	}}})
	if err := manager.StartAll(); err != nil {
		t.Fatalf("StartAll() error = %v", err)
	}
	defer manager.StopAll()

	first := waitForHealthy(t, manager, 0)
	if err := manager.Restart("helper"); err != nil {
		t.Fatalf("Restart() error = %v", err)
	}
	second := waitForHealthy(t, manager, first.PID)
	if second.PID == first.PID {
		t.Fatalf("restart kept PID %d", first.PID)
	}
}

func TestRestartUnknownProcessFails(t *testing.T) {
	if err := NewManager("test-session").Restart("missing"); err == nil {
		t.Fatal("Restart() succeeded for an unknown process")
	}
}

func TestSupervisorHelperProcess(t *testing.T) {
	if os.Getenv("GO_WANT_SUPERVISOR_HELPER") != "1" {
		return
	}
	select {}
}

func waitForHealthy(t *testing.T, manager *Manager, differentFrom int) StatusSnapshot {
	t.Helper()
	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		for _, status := range manager.Status() {
			if status.Name == "helper" && status.State == StateHealthy.String() && status.PID != differentFrom {
				return status
			}
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatal("managed helper did not become healthy")
	return StatusSnapshot{}
}
