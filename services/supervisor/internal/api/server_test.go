package api

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"mini-ogas/supervisor/internal/process"
)

func TestComponentControlEndpointsFailClosed(t *testing.T) {
	server := NewServer(process.NewManager("test-session"))

	request := httptest.NewRequest(http.MethodPost, "/supervisor/stop/missing", nil)
	response := httptest.NewRecorder()
	server.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusNotFound || !strings.Contains(response.Body.String(), "unknown") {
		t.Fatalf("stop response = %d %q", response.Code, response.Body.String())
	}

	request = httptest.NewRequest(http.MethodPost, "/supervisor/start/missing", nil)
	response = httptest.NewRecorder()
	server.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusConflict || !strings.Contains(response.Body.String(), "unknown") {
		t.Fatalf("start response = %d %q", response.Code, response.Body.String())
	}

	request = httptest.NewRequest(http.MethodGet, "/supervisor/stop/missing", nil)
	response = httptest.NewRecorder()
	server.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusMethodNotAllowed {
		t.Fatalf("GET stop response = %d", response.Code)
	}
}
