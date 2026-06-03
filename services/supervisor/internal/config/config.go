package config

import (
	"os"
	"strconv"
	"time"

	"github.com/BurntSushi/toml"
)

type HealthCheckConfig struct {
	Type     string `toml:"type"` // "http" or "process"
	Endpoint string `toml:"endpoint"`
	Interval int    `toml:"interval"` // seconds
	Timeout  int    `toml:"timeout"`  // seconds
	Retries  int    `toml:"retries"`
}

type ProcessSpec struct {
	Name       string            `toml:"name"`
	Command    string            `toml:"command"`
	Args       []string          `toml:"args"`
	Dir        string            `toml:"dir"`
	Env        map[string]string `toml:"env"`
	DependsOn  []string          `toml:"depends_on"`
	Health     HealthCheckConfig `toml:"health"`
}

type Config struct {
	SessionTokenAuto bool          `toml:"session_token_auto"`
	APIPort          int           `toml:"api_port"`
	Processes        []ProcessSpec `toml:"process"`
}

func Load(path string) (Config, error) {
	cfg := Config{
		SessionTokenAuto: true,
		APIPort:          9099,
	}

	data, err := os.ReadFile(path)
	if err != nil {
		return cfg, err
	}

	if err := toml.Unmarshal(data, &cfg); err != nil {
		return cfg, err
	}

	// Apply defaults
	for i := range cfg.Processes {
		p := &cfg.Processes[i]
		if p.Health.Type == "" {
			p.Health.Type = "http"
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

	return cfg, nil
}

// env helper used by callers
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
