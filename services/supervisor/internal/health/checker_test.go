package health

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestProbeHTTPRequiresFreshProcessProof(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status":"ok","session_token":"current-session","process_id":42,"process_started_at":"2026-06-23T00:00:00Z"}`))
	}))
	defer server.Close()

	result := NewChecker().ProbeHTTP(server.URL, time.Second, "current-session")
	if !result.Healthy {
		t.Fatalf("expected a valid health proof, got %q", result.Detail)
	}
}

func TestProbeHTTPRejectsMissingOrStaleProcessProof(t *testing.T) {
	tests := []struct {
		name string
		body string
	}{
		{
			name: "stale session",
			body: `{"status":"ok","session_token":"previous-session","process_id":42,"process_started_at":"2026-06-23T00:00:00Z"}`,
		},
		{
			name: "missing process identity",
			body: `{"status":"ok","session_token":"current-session"}`,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				w.Header().Set("Content-Type", "application/json")
				_, _ = w.Write([]byte(tt.body))
			}))
			defer server.Close()

			result := NewChecker().ProbeHTTP(server.URL, time.Second, "current-session")
			if result.Healthy {
				t.Fatalf("expected an invalid health proof to be rejected")
			}
		})
	}
}

func TestProbeHTTPStatusAcceptsThirdPartyLivenessEndpoint(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	result := NewChecker().ProbeHTTPStatus(server.URL, time.Second)
	if !result.Healthy {
		t.Fatalf("expected status-only health to pass, got %q", result.Detail)
	}
}
