package main

import (
	"crypto/rand"
	"encoding/hex"
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"

	"mini-ogas/supervisor/internal/api"
	"mini-ogas/supervisor/internal/config"
	"mini-ogas/supervisor/internal/process"
)

func main() {
	configPath := flag.String("config", "config/supervisor.toml", "path to supervisor config file")
	flag.Parse()

	cfg, err := config.Load(*configPath)
	if err != nil {
		log.Fatalf("supervisor: failed to load config: %v", err)
	}

	// Generate or inherit session token
	sessionID := os.Getenv("OGAS_SESSION_TOKEN")
	if sessionID == "" && cfg.SessionTokenAuto {
		sessionID = newSessionID()
	}
	os.Setenv("OGAS_SESSION_TOKEN", sessionID)
	log.Printf("supervisor: session %s starting", sessionID)

	// Build manager and register processes
	manager := process.NewManager(sessionID)
	manager.Register(cfg)

	// Start all processes in dependency order
	if err := manager.StartAll(); err != nil {
		log.Printf("supervisor: WARNING %v", err)
	}

	// Start management API
	server := api.NewServer(manager)
	go func() {
		if err := server.ListenAndServe(cfg.APIPort); err != nil {
			log.Printf("supervisor: API server error: %v", err)
		}
	}()

	fmt.Printf("\nsupervisor running — session %s — %d processes\n", sessionID, len(cfg.Processes))
	fmt.Printf("  API: http://127.0.0.1:%d/supervisor/status\n", cfg.APIPort)
	fmt.Println("  Press Ctrl+C to stop all services")

	// Wait for shutdown signal
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	<-sig

	log.Println("supervisor: received shutdown signal, stopping all processes...")
	manager.StopAll()
	log.Println("supervisor: shutdown complete")
}

func newSessionID() string {
	b := make([]byte, 16)
	rand.Read(b)
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return hex.EncodeToString(b[:4]) + "-" + hex.EncodeToString(b[4:6]) +
		"-" + hex.EncodeToString(b[6:8]) + "-" + hex.EncodeToString(b[8:10]) +
		"-" + hex.EncodeToString(b[10:])
}
