package localdb

import (
	"database/sql"
	"os"
	"path/filepath"
	"time"

	"mini-ogas/node-agent/internal/metrics"

	_ "modernc.org/sqlite"
)

type SQLiteStore struct {
	path string
	db   *sql.DB
}

func NewSQLiteStore(path string) *SQLiteStore {
	return &SQLiteStore{path: path}
}

func (store *SQLiteStore) Init() error {
	if store.path == "" {
		return nil
	}
	if err := os.MkdirAll(filepath.Dir(store.path), 0o755); err != nil {
		return err
	}
	db, err := sql.Open("sqlite", store.path)
	if err != nil {
		return err
	}
	store.db = db

	schema := `
CREATE TABLE IF NOT EXISTS node_metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  collected_at TEXT NOT NULL,
  node_code TEXT NOT NULL,
  workshop_type TEXT NOT NULL,
  cpu_usage REAL NOT NULL,
  memory_usage REAL NOT NULL,
  disk_usage REAL NOT NULL,
  network_in INTEGER NOT NULL,
  network_out INTEGER NOT NULL,
  db_latency_ms INTEGER NOT NULL,
  api_latency_ms INTEGER NOT NULL,
  finished_quantity INTEGER NOT NULL,
  defect_quantity INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_node_metrics_collected_at ON node_metrics(collected_at);
`
	_, err = db.Exec(schema)
	return err
}

func (store *SQLiteStore) SaveMetric(metric metrics.Metric) error {
	if store.path == "" {
		return nil
	}
	db, closeAfter, err := store.connection()
	if err != nil {
		return err
	}
	if closeAfter {
		defer db.Close()
	}

	const insertMetricSQL = `INSERT INTO node_metrics (
  collected_at, node_code, workshop_type, cpu_usage, memory_usage, disk_usage,
  network_in, network_out, db_latency_ms, api_latency_ms, finished_quantity, defect_quantity
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);`
	_, err = db.Exec(
		insertMetricSQL,
		time.Now().UTC().Format(time.RFC3339),
		metric.NodeCode,
		metric.WorkshopType,
		metric.CPUUsage,
		metric.MemoryUsage,
		metric.DiskUsage,
		metric.NetworkIn,
		metric.NetworkOut,
		metric.DBLatencyMS,
		metric.APILatencyMS,
		metric.FinishedQuantity,
		metric.DefectQuantity,
	)
	return err
}

func (store *SQLiteStore) DBSizeBytes() int64 {
	if store.path == "" {
		return 0
	}
	stat, err := os.Stat(store.path)
	if err != nil {
		return 0
	}
	return stat.Size()
}

func (store *SQLiteStore) Close() error {
	if store.db == nil {
		return nil
	}
	err := store.db.Close()
	store.db = nil
	return err
}

func (store *SQLiteStore) connection() (*sql.DB, bool, error) {
	if store.db != nil {
		return store.db, false, nil
	}
	db, err := sql.Open("sqlite", store.path)
	return db, true, err
}
