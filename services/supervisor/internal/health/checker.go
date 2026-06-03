package health

import (
	"fmt"
	"net/http"
	"time"
)

type Checker struct {
	httpClient *http.Client
}

type Status struct {
	Healthy bool
	Detail  string
}

func NewChecker() *Checker {
	return &Checker{
		httpClient: &http.Client{Timeout: 3 * time.Second},
	}
}

// ProbeHTTP calls GET <endpoint> and checks for 200 OK.
// It also optionally checks the session_token field if expectedToken is non-empty.
func (c *Checker) ProbeHTTP(endpoint string, timeout time.Duration, expectedToken string) Status {
	client := *c.httpClient
	client.Timeout = timeout

	resp, err := client.Get(endpoint)
	if err != nil {
		return Status{Healthy: false, Detail: fmt.Sprintf("connection failed: %v", err)}
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return Status{Healthy: false, Detail: fmt.Sprintf("HTTP %d", resp.StatusCode)}
	}

	// Session token check is optional — only if we have a token to verify
	if expectedToken != "" {
		// Read enough of the body to extract the session_token field
		// This is a lightweight check — we don't need a full JSON parse
		buf := make([]byte, 4096)
		n, _ := resp.Body.Read(buf)
		body := string(buf[:n])
		// Simple substring match for the session token in the JSON
		if !containsToken(body, expectedToken) {
			return Status{Healthy: false, Detail: "session_token mismatch (stale process)"}
		}
	}

	return Status{Healthy: true, Detail: "ok"}
}

func containsToken(body, token string) bool {
	// Fast path: the token appears literally in the JSON body
	for i := 0; i < len(body)-len(token); i++ {
		if body[i:i+len(token)] == token {
			return true
		}
	}
	return false
}
