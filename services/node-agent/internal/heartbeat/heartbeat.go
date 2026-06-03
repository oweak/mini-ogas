package heartbeat

import (
	"context"
	"fmt"
	"time"

	"mini-ogas/node-agent/internal/centralapi"
)

const AgentVersion = "0.1.0"

type DBSizeReader interface {
	DBSizeBytes() int64
}

type Reporter struct {
	client    centralapi.Client
	nodeCode  string
	startedAt time.Time
	db        DBSizeReader
}

func NewReporter(client centralapi.Client, nodeCode string, startedAt time.Time, db DBSizeReader) Reporter {
	return Reporter{client: client, nodeCode: nodeCode, startedAt: startedAt, db: db}
}

func (reporter Reporter) Run(ctx context.Context) {
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()
	reporter.Send("online")
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			reporter.Send("online")
		}
	}
}

func (reporter Reporter) Send(status string) {
	reporter.sendWithRetry(status, 3)
}

func (reporter Reporter) sendWithRetry(status string, maxRetries int) {
	for attempt := 1; attempt <= maxRetries; attempt++ {
		err := reporter.client.SendHeartbeat(centralapi.Heartbeat{
			NodeCode:         reporter.nodeCode,
			AgentVersion:     AgentVersion,
			UptimeSeconds:    int64(time.Since(reporter.startedAt).Seconds()),
			LocalDBSizeBytes: reporter.db.DBSizeBytes(),
			Status:           status,
		})
		if err == nil {
			return
		}
		if attempt == maxRetries {
			fmt.Printf("heartbeat failed after %d attempts: %v\n", maxRetries, err)
			return
		}
		time.Sleep(time.Duration(attempt) * time.Second)
	}
}
