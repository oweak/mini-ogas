package api

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"time"

	"mini-ogas/supervisor/internal/process"
)

type Server struct {
	manager *process.Manager
}

func NewServer(manager *process.Manager) *Server {
	return &Server{manager: manager}
}

func (s *Server) ListenAndServe(port int) error {
	mux := http.NewServeMux()
	mux.HandleFunc("/supervisor/status", s.handleStatus)
	mux.HandleFunc("/supervisor/restart/", s.handleRestart)
	mux.HandleFunc("/supervisor/stopall", s.handleStopAll)
	mux.HandleFunc("/supervisor/session", s.handleSession)
	mux.HandleFunc("/health", s.handleHealth)

	addr := fmt.Sprintf("127.0.0.1:%d", port)
	log.Printf("supervisor: management API listening on %s", addr)
	return http.ListenAndServe(addr, mux)
}

func (s *Server) handleStatus(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, map[string]any{
		"session_id": s.manager.SessionID(),
		"processes":  s.manager.Status(),
	})
}

func (s *Server) handleRestart(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", 405)
		return
	}
	name := r.URL.Path[len("/supervisor/restart/"):]
	if name == "" {
		http.Error(w, "missing process name", 400)
		return
	}
	if err := s.manager.Restart(name); err != nil {
		http.Error(w, err.Error(), http.StatusNotFound)
		return
	}
	writeJSON(w, map[string]any{"restarted": name, "status": "restarted"})
}

func (s *Server) handleStopAll(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", 405)
		return
	}
	s.manager.StopAll()
	writeJSON(w, map[string]any{"status": "all processes stopped"})
	// Graceful exit after 1 second
	go func() {
		log.Println("supervisor: shutdown requested via API, exiting in 1s")
		time.Sleep(1 * time.Second)
		os.Exit(0)
	}()
}

func (s *Server) handleSession(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, map[string]any{"session_id": s.manager.SessionID()})
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, map[string]any{"status": "ok", "service": "supervisor", "session_id": s.manager.SessionID()})
}

func writeJSON(w http.ResponseWriter, data any) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(data)
}
