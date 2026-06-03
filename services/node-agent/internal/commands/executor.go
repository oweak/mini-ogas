package commands

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"mini-ogas/node-agent/internal/centralapi"
)

type Executor struct {
	client   centralapi.Client
	nodeCode string
	tempDir  string
}

func NewExecutor(client centralapi.Client, nodeCode string) Executor {
	return Executor{client: client, nodeCode: nodeCode, tempDir: "/tmp"}
}

func NewExecutorWithTempDir(client centralapi.Client, nodeCode string, tempDir string) Executor {
	return Executor{client: client, nodeCode: nodeCode, tempDir: tempDir}
}

func (executor Executor) Run(ctx context.Context) {
	ticker := time.NewTicker(10 * time.Second)
	defer ticker.Stop()
	executor.pollOnce()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			executor.pollOnce()
		}
	}
}

func (executor Executor) pollOnce() {
	pending, err := executor.client.PendingCommands(executor.nodeCode)
	if err != nil {
		fmt.Printf("poll pending commands failed: %v\n", err)
		return
	}
	for _, command := range pending {
		result := executor.Execute(command)
		if err := executor.client.ReportCommandResult(executor.nodeCode, result); err != nil {
			fmt.Printf("report command result failed command_id=%d: %v\n", command.ID, err)
		}
	}
}

func (executor Executor) Execute(command centralapi.Command) centralapi.CommandResult {
	switch command.CommandType {
	case "clean_temp_cache":
		deleted, err := executor.cleanTempCache()
		if err != nil {
			return centralapi.CommandResult{
				CommandID:   command.ID,
				CommandType: command.CommandType,
				Status:      "failed",
				Message:     err.Error(),
			}
		}
		return centralapi.CommandResult{
			CommandID:   command.ID,
			CommandType: command.CommandType,
			Status:      "executed",
			Message:     fmt.Sprintf("deleted %d temporary files", deleted),
		}
	case "restart_workshop_scheduler":
		return centralapi.CommandResult{
			CommandID:   command.ID,
			CommandType: command.CommandType,
			Status:      "executed",
			Message:     "workshop scheduler restart acknowledged",
		}
	default:
		return centralapi.CommandResult{
			CommandID:   command.ID,
			CommandType: command.CommandType,
			Status:      "unsupported",
			Message:     "unsupported command type",
		}
	}
}

func (executor Executor) cleanTempCache() (int, error) {
	matches, err := filepath.Glob(filepath.Join(executor.tempDir, "mini-ogas-*.tmp"))
	if err != nil {
		return 0, err
	}
	deleted := 0
	for _, path := range matches {
		if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
			return deleted, err
		}
		deleted++
	}
	return deleted, nil
}
