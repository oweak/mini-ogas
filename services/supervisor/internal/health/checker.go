package health

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

type Checker struct {
	httpClient *http.Client
}

type Status struct {
	Healthy bool
	Detail  string
}

type healthPayload struct {
	Status           string `json:"status"`
	SessionToken     string `json:"session_token"`
	ProcessID        int    `json:"process_id"`
	ProcessStartedAt string `json:"process_started_at"`
}

func NewChecker() *Checker {
	return &Checker{httpClient: &http.Client{Timeout: 3 * time.Second}}
}

// ProbeHTTP validates the Mini-OGAS HTTP health proof. A session-aware probe
// also requires process identity fields to reject a listener from an old run.
func (c *Checker) ProbeHTTP(endpoint string, timeout time.Duration, expectedToken string) Status {
	client := *c.httpClient
	client.Timeout = timeout

	resp, err := client.Get(endpoint)
	if err != nil {
		return Status{Healthy: false, Detail: fmt.Sprintf("connection failed: %v", err)}
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return Status{Healthy: false, Detail: fmt.Sprintf("HTTP %d", resp.StatusCode)}
	}

	var payload healthPayload
	decoder := json.NewDecoder(io.LimitReader(resp.Body, 64*1024))
	if err := decoder.Decode(&payload); err != nil {
		return Status{Healthy: false, Detail: fmt.Sprintf("invalid health JSON: %v", err)}
	}
	if strings.ToLower(payload.Status) != "ok" {
		return Status{Healthy: false, Detail: "health status is not ok"}
	}
	if expectedToken == "" {
		return Status{Healthy: true, Detail: "ok"}
	}
	if payload.SessionToken != expectedToken {
		return Status{Healthy: false, Detail: "session_token mismatch (stale process)"}
	}
	if payload.ProcessID <= 0 {
		return Status{Healthy: false, Detail: "missing process_id in health proof"}
	}
	if _, err := time.Parse(time.RFC3339, payload.ProcessStartedAt); err != nil {
		return Status{Healthy: false, Detail: "missing or invalid process_started_at in health proof"}
	}

	return Status{Healthy: true, Detail: "ok"}
}
