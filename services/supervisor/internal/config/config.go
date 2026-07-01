package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/BurntSushi/toml"
)

type HealthCheckConfig struct {
	Type     string `toml:"type"`
	Endpoint string `toml:"endpoint"`
	Interval int    `toml:"interval"`
	Timeout  int    `toml:"timeout"`
	Retries  int    `toml:"retries"`
}

type ProcessSpec struct {
	Name      string            `toml:"name"`
	Command   string            `toml:"command"`
	Args      []string          `toml:"args"`
	Dir       string            `toml:"dir"`
	Env       map[string]string `toml:"env"`
	DependsOn []string          `toml:"depends_on"`
	Health    HealthCheckConfig `toml:"health"`
}

type Config struct {
	SessionTokenAuto bool          `toml:"session_token_auto"`
	APIPort          int           `toml:"api_port"`
	Processes        []ProcessSpec `toml:"process"`
}

func Load(path string) (Config, error) {
	cfg := Config{SessionTokenAuto: true, APIPort: 9099}
	data, err := os.ReadFile(path)
	if err != nil {
		return cfg, err
	}
	if err := toml.Unmarshal(data, &cfg); err != nil {
		return cfg, err
	}

	for i := range cfg.Processes {
		p := &cfg.Processes[i]
		p.Name = strings.TrimSpace(p.Name)
		p.Command = os.ExpandEnv(strings.TrimSpace(p.Command))
		p.Dir = os.ExpandEnv(strings.TrimSpace(p.Dir))
		for index, arg := range p.Args {
			p.Args[index] = os.ExpandEnv(arg)
		}
		for key, value := range p.Env {
			p.Env[key] = os.ExpandEnv(value)
		}
		p.Health.Endpoint = os.ExpandEnv(strings.TrimSpace(p.Health.Endpoint))
		p.Health.Type = strings.ToLower(strings.TrimSpace(p.Health.Type))
		if p.Health.Type == "" {
			if p.Health.Endpoint == "" {
				p.Health.Type = "process"
			} else {
				p.Health.Type = "http"
			}
		}
		if p.Health.Interval == 0 {
			p.Health.Interval = 5
		}
		if p.Health.Timeout == 0 {
			p.Health.Timeout = 3
		}
		if p.Health.Retries == 0 {
			p.Health.Retries = 3
		}
	}

	if err := validate(cfg); err != nil {
		return cfg, err
	}
	return cfg, nil
}

func validate(cfg Config) error {
	known := make(map[string]struct{}, len(cfg.Processes))
	for _, process := range cfg.Processes {
		if process.Name == "" {
			return fmt.Errorf("process name is required")
		}
		if process.Command == "" {
			return fmt.Errorf("process %q command is required", process.Name)
		}
		if _, exists := known[process.Name]; exists {
			return fmt.Errorf("duplicate process name %q", process.Name)
		}
		known[process.Name] = struct{}{}
		if process.Health.Type != "http" && process.Health.Type != "process" {
			return fmt.Errorf("process %q has unsupported health type %q", process.Name, process.Health.Type)
		}
		if process.Health.Type == "http" && process.Health.Endpoint == "" {
			return fmt.Errorf("process %q HTTP health check requires an endpoint", process.Name)
		}
		if process.Health.Interval <= 0 || process.Health.Timeout <= 0 || process.Health.Retries <= 0 {
			return fmt.Errorf("process %q health interval, timeout, and retries must be positive", process.Name)
		}
	}
	for _, process := range cfg.Processes {
		for _, dependency := range process.DependsOn {
			if _, exists := known[dependency]; !exists {
				return fmt.Errorf("process %q depends on unknown process %q", process.Name, dependency)
			}
		}
	}
	return nil
}

func EnvDefault(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func IntervalFromEnv(key string, fallback time.Duration) time.Duration {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	seconds, err := strconv.Atoi(value)
	if err != nil || seconds <= 0 {
		return fallback
	}
	return time.Duration(seconds) * time.Second
}
