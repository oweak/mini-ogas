package centralapi

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"mini-ogas/node-agent/internal/metrics"
)

type Client struct {
	baseURL      string
	apiToken     string
	sessionToken string
	httpClient   *http.Client
	tracker      *metrics.LatencyTracker
}

type Heartbeat struct {
	NodeCode         string `json:"node_code"`
	AgentVersion     string `json:"agent_version"`
	UptimeSeconds    int64  `json:"uptime_seconds"`
	LocalDBSizeBytes int64  `json:"local_db_size_bytes"`
	Status           string `json:"status,omitempty"`
	SessionToken     string `json:"session_token,omitempty"`
}

type Command struct {
	ID          int    `json:"id"`
	NodeCode    string `json:"node_code"`
	CommandType string `json:"command_type"`
	RiskLevel   string `json:"risk_level"`
	Status      string `json:"status"`
	Operator    string `json:"operator"`
}

type CommandResult struct {
	CommandID   int    `json:"command_id"`
	CommandType string `json:"command_type"`
	Status      string `json:"status"`
	Message     string `json:"message"`
}

func New(baseURL string, apiToken string, tracker *metrics.LatencyTracker) Client {
	token := apiToken
	return Client{
		baseURL:      strings.TrimRight(baseURL, "/"),
		apiToken:     token,
		sessionToken: "", // set via SetSessionToken if available
		httpClient: &http.Client{
			Timeout: 10 * time.Second,
		},
		tracker: tracker,
	}
}

func (client *Client) SetSessionToken(token string) {
	client.sessionToken = token
}

func (client Client) SubmitMetric(metric metrics.Metric) error {
	return client.doJSON(http.MethodPost, "/metrics", metric, nil, true)
}

func (client Client) SendHeartbeat(heartbeat Heartbeat) error {
	heartbeat.SessionToken = client.sessionToken
	return client.doJSON(http.MethodPut, "/api/nodes/"+url.PathEscape(heartbeat.NodeCode)+"/heartbeat", heartbeat, nil, false)
}

func (client Client) PendingCommands(nodeCode string) ([]Command, error) {
	var commands []Command
	err := client.doJSON(http.MethodGet, "/api/nodes/"+url.PathEscape(nodeCode)+"/pending-commands", nil, &commands, false)
	return commands, err
}

func (client Client) ReportCommandResult(nodeCode string, result CommandResult) error {
	return client.doJSON(http.MethodPost, "/api/nodes/"+url.PathEscape(nodeCode)+"/command-results", result, nil, false)
}

func (client Client) doJSON(method string, path string, payload any, target any, track bool) error {
	var body io.Reader
	if payload != nil {
		encoded, err := json.Marshal(payload)
		if err != nil {
			return err
		}
		body = bytes.NewReader(encoded)
	}
	request, err := http.NewRequest(method, client.baseURL+path, body)
	if err != nil {
		return err
	}
	request.Header.Set("X-OGAS-Token", client.apiToken)
	if client.sessionToken != "" {
		request.Header.Set("X-OGAS-Session-Token", client.sessionToken)
	}
	if payload != nil {
		request.Header.Set("Content-Type", "application/json")
	}

	started := time.Now()
	resp, err := client.httpClient.Do(request)
	elapsed := time.Since(started)
	if track && client.tracker != nil {
		client.tracker.RecordAPI(elapsed)
	}

	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		// Drain body to allow connection reuse
		io.Copy(io.Discard, resp.Body)
		return fmt.Errorf("central api returned %s", resp.Status)
	}
	if target == nil {
		io.Copy(io.Discard, resp.Body)
		return nil
	}
	return json.NewDecoder(resp.Body).Decode(target)
}
