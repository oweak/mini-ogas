package process

import (
	"context"
	"fmt"
	"log"
	"math/rand"
	"os"
	"os/exec"
	"sync"
	"time"

	"mini-ogas/supervisor/internal/config"
	"mini-ogas/supervisor/internal/health"
)

type State int

const (
	StateStopped State = iota
	StateStopping
	StateStarting
	StateRunning
	StateHealthy
	StateCrashed
)

func (s State) String() string {
	switch s {
	case StateStopped:
		return "stopped"
	case StateStopping:
		return "stopping"
	case StateStarting:
		return "starting"
	case StateRunning:
		return "running"
	case StateHealthy:
		return "healthy"
	case StateCrashed:
		return "crashed"
	default:
		return "unknown"
	}
}

type Manager struct {
	mu        sync.RWMutex
	processes map[string]*ManagedProcess
	sessionID string
	checker   *health.Checker
}

type ManagedProcess struct {
	Spec       config.ProcessSpec
	PID        int
	State      State
	StartedAt  time.Time
	CrashCount int
	Backoff    time.Duration
	Generation uint64
	mu         sync.Mutex
	cancel     context.CancelFunc
	exited     chan struct{}
}

type StatusSnapshot struct {
	Name       string `json:"name"`
	State      string `json:"state"`
	PID        int    `json:"pid"`
	CrashCount int    `json:"crash_count"`
	Uptime     string `json:"uptime"`
}

func NewManager(sessionID string) *Manager {
	return &Manager{
		processes: make(map[string]*ManagedProcess),
		sessionID: sessionID,
		checker:   health.NewChecker(),
	}
}

func (m *Manager) Register(cfg config.Config) {
	m.mu.Lock()
	defer m.mu.Unlock()
	for _, spec := range cfg.Processes {
		m.processes[spec.Name] = &ManagedProcess{Spec: spec, State: StateStopped}
	}
}

func (m *Manager) StartAll() error {
	m.mu.RLock()
	total := len(m.processes)
	m.mu.RUnlock()
	started := make(map[string]bool)
	deadline := time.Now().Add(60 * time.Second)

	for len(started) < total {
		var ready []string
		waitingForHealth := false
		m.mu.RLock()
		for name, proc := range m.processes {
			if started[name] {
				continue
			}
			depsMet := true
			for _, dependency := range proc.Spec.DependsOn {
				dependencyProcess := m.processes[dependency]
				dependencyProcess.mu.Lock()
				dependencyHealthy := dependencyProcess.State == StateHealthy
				dependencyProcess.mu.Unlock()
				if !started[dependency] || !dependencyHealthy {
					depsMet = false
					if started[dependency] {
						waitingForHealth = true
					}
					break
				}
			}
			if depsMet {
				ready = append(ready, name)
			}
		}
		m.mu.RUnlock()

		if len(ready) == 0 {
			if waitingForHealth {
				if time.Now().After(deadline) {
					return fmt.Errorf("dependency health timeout: %d processes remain", total-len(started))
				}
				time.Sleep(100 * time.Millisecond)
				continue
			}
			return fmt.Errorf("dependency deadlock: %d processes remain", total-len(started))
		}
		for _, name := range ready {
			if err := m.startOne(name); err != nil {
				return err
			}
			started[name] = true
		}
	}

	log.Printf("supervisor: all %d processes launched (session %s)", total, m.sessionID)
	return nil
}

func (m *Manager) startOne(name string) error {
	m.mu.RLock()
	proc, ok := m.processes[name]
	m.mu.RUnlock()
	if !ok {
		return fmt.Errorf("unknown process %q", name)
	}

	proc.mu.Lock()
	proc.Generation++
	generation := proc.Generation
	proc.State = StateStarting
	if proc.Backoff == 0 {
		proc.Backoff = time.Second
	}
	proc.mu.Unlock()

	ctx, cancel := context.WithCancel(context.Background())
	env := append([]string{}, os.Environ()...)
	env = append(env, "OGAS_SESSION_TOKEN="+m.sessionID)
	for key, value := range proc.Spec.Env {
		env = append(env, key+"="+value)
	}

	cmd := exec.CommandContext(ctx, proc.Spec.Command, proc.Spec.Args...)
	cmd.Env = env
	cmd.Dir = proc.Spec.Dir
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	log.Printf("supervisor: starting %s (%s %v)", name, proc.Spec.Command, proc.Spec.Args)
	if err := cmd.Start(); err != nil {
		cancel()
		proc.mu.Lock()
		if proc.Generation == generation {
			proc.State = StateCrashed
		}
		proc.mu.Unlock()
		return fmt.Errorf("start %s: %w", name, err)
	}

	proc.mu.Lock()
	if proc.Generation == generation {
		proc.PID = cmd.Process.Pid
		proc.StartedAt = time.Now()
		proc.State = StateRunning
		proc.cancel = cancel
		proc.exited = make(chan struct{})
	}
	exited := proc.exited
	proc.mu.Unlock()

	go m.monitor(name, proc, cmd, ctx, generation, exited)
	return nil
}

func (m *Manager) monitor(
	name string,
	proc *ManagedProcess,
	cmd *exec.Cmd,
	ctx context.Context,
	generation uint64,
	exited chan struct{},
) {
	defer close(exited)
	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()

	if proc.Spec.Health.Type == "process" {
		m.markHealthy(proc, generation)
		select {
		case err := <-done:
			log.Printf("supervisor: %s process exited: %v", name, err)
			m.restartProcess(name, generation)
		case <-ctx.Done():
			m.waitForExit(name, done)
		}
		return
	}

	// HTTP services need a short bind window before the first strict probe.
	time.Sleep(2 * time.Second)
	timeout := time.Duration(proc.Spec.Health.Timeout) * time.Second
	interval := time.Duration(proc.Spec.Health.Interval) * time.Second
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	consecutiveFails := 0

	for {
		select {
		case err := <-done:
			log.Printf("supervisor: %s process exited: %v", name, err)
			m.restartProcess(name, generation)
			return
		case <-ctx.Done():
			m.waitForExit(name, done)
			return
		case <-ticker.C:
			expectedSession := m.sessionID
			if proc.Spec.Health.SessionAgnostic {
				expectedSession = ""
			}
			result := health.Status{}
			if proc.Spec.Health.Type == "http-status" {
				result = m.checker.ProbeHTTPStatus(proc.Spec.Health.Endpoint, timeout)
			} else {
				result = m.checker.ProbeHTTP(proc.Spec.Health.Endpoint, timeout, expectedSession)
			}
			if result.Healthy {
				consecutiveFails = 0
				m.markHealthy(proc, generation)
				continue
			}
			consecutiveFails++
			if consecutiveFails < proc.Spec.Health.Retries {
				continue
			}
			log.Printf("supervisor: %s unhealthy after %d retries: %s", name, consecutiveFails, result.Detail)
			proc.mu.Lock()
			current := proc.Generation == generation
			cancel := proc.cancel
			proc.mu.Unlock()
			if current && cancel != nil {
				cancel()
				<-done
			}
			m.restartProcess(name, generation)
			return
		}
	}
}

func (m *Manager) waitForExit(name string, done <-chan error) {
	select {
	case <-done:
	case <-time.After(5 * time.Second):
		log.Printf("supervisor: timed out waiting for %s to exit", name)
	}
}

func (m *Manager) markHealthy(proc *ManagedProcess, generation uint64) {
	proc.mu.Lock()
	defer proc.mu.Unlock()
	if proc.Generation != generation || proc.State == StateStopped {
		return
	}
	proc.State = StateHealthy
	proc.CrashCount = 0
	proc.Backoff = time.Second
}

func (m *Manager) restartProcess(name string, generation uint64) {
	m.mu.RLock()
	proc, ok := m.processes[name]
	m.mu.RUnlock()
	if !ok {
		return
	}

	proc.mu.Lock()
	if proc.Generation != generation || proc.State == StateStopped {
		proc.mu.Unlock()
		return
	}
	proc.State = StateCrashed
	proc.CrashCount++
	const maxBackoff = 30 * time.Second
	delay := time.Duration(int64(1)<<min(proc.CrashCount, 5)) * time.Second
	if delay > maxBackoff {
		delay = maxBackoff
	}
	delay += time.Duration(rand.Intn(1000)) * time.Millisecond
	proc.Backoff = delay
	count := proc.CrashCount
	proc.mu.Unlock()

	log.Printf("supervisor: %s crashed (count=%d), restarting in %v", name, count, delay)
	time.Sleep(delay)
	proc.mu.Lock()
	current := proc.Generation == generation && proc.State == StateCrashed
	proc.mu.Unlock()
	if current {
		if err := m.startOne(name); err != nil {
			log.Printf("supervisor: %s restart failed: %v", name, err)
		}
	}
}

// Restart replaces one managed child. Incrementing Generation first makes a
// retiring monitor harmless even if its process exits after the replacement.
func (m *Manager) Restart(name string) error {
	if err := m.Stop(name); err != nil {
		return err
	}
	return m.Start(name)
}

// Stop retires one child without triggering its automatic crash restart.
func (m *Manager) Stop(name string) error {
	m.mu.RLock()
	proc, ok := m.processes[name]
	m.mu.RUnlock()
	if !ok {
		return fmt.Errorf("unknown process %q", name)
	}

	proc.mu.Lock()
	proc.Generation++
	cancel := proc.cancel
	exited := proc.exited
	proc.cancel = nil
	proc.State = StateStopping
	proc.mu.Unlock()
	if cancel != nil {
		cancel()
	}
	if exited != nil {
		select {
		case <-exited:
		case <-time.After(6 * time.Second):
			return fmt.Errorf("timed out waiting for process %q to stop", name)
		}
	}
	proc.mu.Lock()
	proc.PID = 0
	proc.State = StateStopped
	proc.StartedAt = time.Time{}
	proc.exited = nil
	proc.mu.Unlock()
	log.Printf("supervisor: stopped %s by management request", name)
	return nil
}

// Start launches one stopped child after confirming that its dependencies are healthy.
func (m *Manager) Start(name string) error {
	m.mu.RLock()
	proc, ok := m.processes[name]
	if !ok {
		m.mu.RUnlock()
		return fmt.Errorf("unknown process %q", name)
	}
	dependencies := append([]string(nil), proc.Spec.DependsOn...)
	m.mu.RUnlock()

	proc.mu.Lock()
	state := proc.State
	proc.mu.Unlock()
	if state != StateStopped {
		return fmt.Errorf("process %q is %s, not stopped", name, state)
	}
	for _, dependency := range dependencies {
		m.mu.RLock()
		dependencyProcess, exists := m.processes[dependency]
		m.mu.RUnlock()
		if !exists {
			return fmt.Errorf("process %q has unknown dependency %q", name, dependency)
		}
		dependencyProcess.mu.Lock()
		dependencyState := dependencyProcess.State
		dependencyProcess.mu.Unlock()
		if dependencyState != StateHealthy {
			return fmt.Errorf("dependency %q is %s, not healthy", dependency, dependencyState)
		}
	}
	return m.startOne(name)
}

func (m *Manager) Status() []StatusSnapshot {
	m.mu.RLock()
	defer m.mu.RUnlock()
	result := make([]StatusSnapshot, 0, len(m.processes))
	for _, proc := range m.processes {
		proc.mu.Lock()
		uptime := ""
		if proc.State != StateStopped && !proc.StartedAt.IsZero() {
			uptime = time.Since(proc.StartedAt).Truncate(time.Second).String()
		}
		result = append(result, StatusSnapshot{
			Name:       proc.Spec.Name,
			State:      proc.State.String(),
			PID:        proc.PID,
			CrashCount: proc.CrashCount,
			Uptime:     uptime,
		})
		proc.mu.Unlock()
	}
	return result
}

func (m *Manager) StopAll() {
	m.mu.RLock()
	defer m.mu.RUnlock()
	for name, proc := range m.processes {
		proc.mu.Lock()
		proc.Generation++
		cancel := proc.cancel
		proc.cancel = nil
		proc.State = StateStopped
		proc.mu.Unlock()
		if cancel != nil {
			cancel()
		}
		log.Printf("supervisor: stopped %s", name)
	}
}

func (m *Manager) SessionID() string { return m.sessionID }

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
