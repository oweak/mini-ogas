package localdb

import (
	"database/sql"
	"path/filepath"
	"testing"

	"mini-ogas/node-agent/internal/metrics"

	_ "modernc.org/sqlite"
)

func TestSaveMetricUsesParameterizedInsert(t *testing.T) {
	dbPath := filepath.Join(t.TempDir(), "node.db")
	store := NewSQLiteStore(dbPath)
	if err := store.Init(); err != nil {
		t.Fatalf("init sqlite store: %v", err)
	}
	defer store.Close()

	metric := metrics.Metric{
		NodeCode:         "node-01'); DROP TABLE node_metrics; --",
		WorkshopType:     "turning",
		CPUUsage:         41.2,
		MemoryUsage:      52.3,
		DiskUsage:        63.4,
		NetworkIn:        1200,
		NetworkOut:       800,
		DBLatencyMS:      24,
		APILatencyMS:     88,
		FinishedQuantity: 18,
		DefectQuantity:   1,
	}
	if err := store.SaveMetric(metric); err != nil {
		t.Fatalf("save metric: %v", err)
	}

	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	defer db.Close()

	var rowCount int
	if err := db.QueryRow("SELECT COUNT(*) FROM node_metrics").Scan(&rowCount); err != nil {
		t.Fatalf("query node_metrics: %v", err)
	}
	if rowCount != 1 {
		t.Fatalf("expected one metric row, got %d", rowCount)
	}
}
