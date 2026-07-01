package config

import (
	"os"
	"strconv"
	"time"
)

type Config struct {
	NodeCode      string
	WorkshopType  string
	CentralAPIURL string
	APIToken      string
	LocalDBPath   string
	SessionToken  string
	Interval      time.Duration
}

func Load() Config {
	return Config{
		NodeCode:      env("NODE_CODE", "turning-workshop-01"),
		WorkshopType:  env("WORKSHOP_TYPE", "turning"),
		CentralAPIURL: env("CENTRAL_API_URL", "http://localhost:8080"),
		APIToken:      env("CENTRAL_API_TOKEN", ""),
		LocalDBPath:   env("LOCAL_DB_PATH", "/var/lib/mini-ogas/node.db"),
		SessionToken:  env("OGAS_SESSION_TOKEN", ""),
		Interval:      intervalFromEnv("COLLECT_INTERVAL_SECONDS", 5*time.Second),
	}
}

func env(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func intervalFromEnv(key string, fallback time.Duration) time.Duration {
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
