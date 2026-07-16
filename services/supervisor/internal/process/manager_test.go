package process

import (
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"os"
	"path/filepath"
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

func TestManualStopAndStartDoNotTriggerCrashRestart(t *testing.T) {
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
	if err := manager.Stop("helper"); err != nil {
		t.Fatalf("Stop() error = %v", err)
	}
	stopped := manager.Status()[0]
	if stopped.State != StateStopped.String() || stopped.PID != 0 {
		t.Fatalf("manual stop state = %#v", stopped)
	}
	if err := manager.Start("helper"); err != nil {
		t.Fatalf("Start() error = %v", err)
	}
	second := waitForHealthy(t, manager, first.PID)
	if second.PID == first.PID {
		t.Fatalf("manual start kept PID %d", first.PID)
	}
}

func TestManualStartRejectsRunningAndUnknownProcesses(t *testing.T) {
	manager := NewManager("test-session")
	if err := manager.Start("missing"); err == nil {
		t.Fatal("Start() succeeded for unknown process")
	}
	if err := manager.Stop("missing"); err == nil {
		t.Fatal("Stop() succeeded for unknown process")
	}
}

func TestStartAllWaitsForHealthyDependencies(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	port := listener.Addr().(*net.TCPAddr).Port
	listener.Close()
	marker := filepath.Join(t.TempDir(), "child-started-before-parent-health")
	endpoint := fmt.Sprintf("http://127.0.0.1:%d/health", port)

	manager := NewManager("test-session")
	manager.Register(config.Config{Processes: []config.ProcessSpec{
		{
			Name:    "parent",
			Command: os.Args[0],
			Args:    []string{"-test.run=TestSupervisorHelperProcess"},
			Env: map[string]string{
				"GO_WANT_SUPERVISOR_HELPER": "1",
				"SUPERVISOR_HELPER_MODE":    "delayed-http",
				"SUPERVISOR_HELPER_PORT":    fmt.Sprint(port),
			},
			Health: config.HealthCheckConfig{Type: "http", Endpoint: endpoint, Interval: 1, Timeout: 1, Retries: 5},
		},
		{
			Name:      "child",
			Command:   os.Args[0],
			Args:      []string{"-test.run=TestSupervisorHelperProcess"},
			DependsOn: []string{"parent"},
			Env: map[string]string{
				"GO_WANT_SUPERVISOR_HELPER": "1",
				"SUPERVISOR_HELPER_MODE":    "dependency-probe",
				"SUPERVISOR_PARENT_URL":     endpoint,
				"SUPERVISOR_FAILURE_MARKER": marker,
			},
			Health: config.HealthCheckConfig{Type: "process", Interval: 1, Timeout: 1, Retries: 1},
		},
	}})
	if err := manager.StartAll(); err != nil {
		t.Fatalf("StartAll() error = %v", err)
	}
	defer manager.StopAll()
	time.Sleep(500 * time.Millisecond)
	if _, err := os.Stat(marker); err == nil {
		t.Fatal("dependent process started before parent health check passed")
	} else if !os.IsNotExist(err) {
		t.Fatal(err)
	}
}

func TestSupervisorHelperProcess(t *testing.T) {
	if os.Getenv("GO_WANT_SUPERVISOR_HELPER") != "1" {
		return
	}
	switch os.Getenv("SUPERVISOR_HELPER_MODE") {
	case "delayed-http":
		time.Sleep(300 * time.Millisecond)
		http.HandleFunc("/health", func(writer http.ResponseWriter, _ *http.Request) {
			_ = json.NewEncoder(writer).Encode(map[string]any{
				"status":             "ok",
				"session_token":      "test-session",
				"process_id":         os.Getpid(),
				"process_started_at": time.Now().UTC().Format(time.RFC3339),
			})
		})
		_ = http.ListenAndServe("127.0.0.1:"+os.Getenv("SUPERVISOR_HELPER_PORT"), nil)
		return
	case "dependency-probe":
		response, err := http.Get(os.Getenv("SUPERVISOR_PARENT_URL"))
		if err != nil {
			_ = os.WriteFile(os.Getenv("SUPERVISOR_FAILURE_MARKER"), []byte(err.Error()), 0o600)
			os.Exit(2)
		}
		response.Body.Close()
	}
	for {
		time.Sleep(time.Hour)
	}
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
