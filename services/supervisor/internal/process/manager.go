package process

import (
	"context"
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
	StateStopped  State = iota
	StateStarting State = iota
	StateRunning  State = iota
	StateHealthy  State = iota
	StateCrashed  State = iota
)

func (s State) String() string {
	switch s {
	case StateStopped:
		return "stopped"
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
	mu         sync.Mutex
	cancel     context.CancelFunc
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
		m.processes[spec.Name] = &ManagedProcess{
			Spec:  spec,
			State: StateStopped,
		}
	}
}

func (m *Manager) StartAll() error {
	m.mu.RLock()
	total := len(m.processes)
	m.mu.RUnlock()
	started := make(map[string]bool)

	for len(started) < total {
		var ready []string
		m.mu.RLock()
		for name, proc := range m.processes {
			if started[name] {
				continue
			}
			depsMet := true
			for _, dep := range proc.Spec.DependsOn {
				if !started[dep] {
					depsMet = false
					break
				}
			}
			if depsMet {
				ready = append(ready, name)
			}
		}
		m.mu.RUnlock()

		if len(ready) == 0 {
			log.Printf("supervisor: WARNING dependency deadlock — %d processes remain", total-len(started))
			break
		}

		for _, name := range ready {
			if err := m.startOne(name); err != nil {
				log.Printf("supervisor: ERROR starting %s: %v", name, err)
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
		log.Printf("supervisor: unknown process %q", name)
		return nil
	}

	proc.mu.Lock()
	proc.State = StateStarting
	if proc.Backoff == 0 {
		proc.Backoff = 1 * time.Second
	}
	proc.mu.Unlock()

	ctx, cancel := context.WithCancel(context.Background())

	env := os.Environ()
	env = append(env, "OGAS_SESSION_TOKEN="+m.sessionID)
	for k, v := range proc.Spec.Env {
		env = append(env, k+"="+v)
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
		proc.State = StateCrashed
		proc.mu.Unlock()
		log.Printf("supervisor: %s failed to start: %v", name, err)
		return nil
	}

	proc.mu.Lock()
	proc.PID = cmd.Process.Pid
	proc.StartedAt = time.Now()
	proc.State = StateRunning
	proc.cancel = cancel
	proc.mu.Unlock()

	// Goroutine: wait for exit + health polling
	go m.monitor(name, cmd, ctx)

	return nil
}

func (m *Manager) monitor(name string, cmd *exec.Cmd, ctx context.Context) {
	proc := m.processes[name]
	spec := proc.Spec
	timeout := time.Duration(spec.Health.Timeout) * time.Second
	interval := time.Duration(spec.Health.Interval) * time.Second

	// Wait for port binding
	time.Sleep(2 * time.Second)

	consecutiveFails := 0
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	// Channel to detect process exit
	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()

	for {
		select {
		case err := <-done:
			log.Printf("supervisor: %s process exited: %v", name, err)
			proc.mu.Lock()
			proc.State = StateCrashed
			proc.mu.Unlock()
			m.restartProcess(name)
			return

		case <-ctx.Done():
			return

		case <-ticker.C:
			result := m.checker.ProbeHTTP(spec.Health.Endpoint, timeout, m.sessionID)
			if result.Healthy {
				consecutiveFails = 0
				proc.mu.Lock()
				proc.State = StateHealthy
				proc.CrashCount = 0
				proc.Backoff = 1 * time.Second
				proc.mu.Unlock()
			} else {
				consecutiveFails++
				if consecutiveFails >= spec.Health.Retries {
					log.Printf("supervisor: %s unhealthy after %d retries: %s", name, consecutiveFails, result.Detail)
					proc.cancel() // kill the process
					cmd.Wait()    // reap
					proc.mu.Lock()
					proc.State = StateCrashed
					proc.mu.Unlock()
					m.restartProcess(name)
					return
				}
			}
		}
	}
}

func (m *Manager) restartProcess(name string) {
	proc, ok := m.processes[name]
	if !ok {
		return
	}

	proc.mu.Lock()
	proc.CrashCount++
	const maxBackoff = 30 * time.Second
	d := time.Duration(int64(1)<<min(proc.CrashCount, 5)) * time.Second
	if d > maxBackoff {
		d = maxBackoff
	}
	d += time.Duration(rand.Intn(1000)) * time.Millisecond
	proc.Backoff = d
	count := proc.CrashCount
	proc.mu.Unlock()

	log.Printf("supervisor: %s crashed (count=%d), restarting in %v", name, count, d)
	time.Sleep(d)
	m.startOne(name)
}

func (m *Manager) Status() []StatusSnapshot {
	m.mu.RLock()
	defer m.mu.RUnlock()
	var result []StatusSnapshot
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
	for name := range m.processes {
		proc := m.processes[name]
		proc.mu.Lock()
		if proc.cancel != nil {
			proc.cancel()
		}
		proc.State = StateStopped
		proc.mu.Unlock()
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
