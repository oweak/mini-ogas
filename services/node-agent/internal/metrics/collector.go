package metrics

import (
	"os"
	"runtime"
	"sync/atomic"
	"time"

	"github.com/shirou/gopsutil/v4/cpu"
	"github.com/shirou/gopsutil/v4/disk"
	"github.com/shirou/gopsutil/v4/load"
	"github.com/shirou/gopsutil/v4/mem"
	"github.com/shirou/gopsutil/v4/net"
)

type Metric struct {
	NodeCode         string  `json:"node_code"`
	WorkshopType     string  `json:"workshop_type"`
	CPUUsage         float64 `json:"cpu_usage"`
	MemoryUsage      float64 `json:"memory_usage"`
	DiskUsage        float64 `json:"disk_usage"`
	NetworkIn        int64   `json:"network_in"`
	NetworkOut       int64   `json:"network_out"`
	DBLatencyMS      int     `json:"db_latency_ms"`
	APILatencyMS     int     `json:"api_latency_ms"`
	FinishedQuantity int     `json:"finished_quantity"`
	DefectQuantity   int     `json:"defect_quantity"`
}

// LatencyTracker provides window-averaged API and DB latency values.
type LatencyTracker struct {
	apiTotal atomic.Int64
	apiCount atomic.Int64
	dbTotal  atomic.Int64
	dbCount  atomic.Int64
}

func (t *LatencyTracker) RecordAPI(d time.Duration) {
	t.apiTotal.Add(d.Milliseconds())
	t.apiCount.Add(1)
}

func (t *LatencyTracker) RecordDB(d time.Duration) {
	t.dbTotal.Add(d.Milliseconds())
	t.dbCount.Add(1)
}

func (t *LatencyTracker) APILatencyMS() int {
	c := t.apiCount.Load()
	if c == 0 {
		return 0
	}
	return int(t.apiTotal.Load() / c)
}

func (t *LatencyTracker) DBLatencyMS() int {
	c := t.dbCount.Load()
	if c == 0 {
		return 0
	}
	return int(t.dbTotal.Load() / c)
}

func (t *LatencyTracker) Reset() {
	t.apiTotal.Store(0)
	t.apiCount.Store(0)
	t.dbTotal.Store(0)
	t.dbCount.Store(0)
}

// ProductionCounters track local production stats (not derived from OS).
type ProductionCounters struct {
	Finished atomic.Int64
	Defect   atomic.Int64
}

type Collector struct {
	tracker    *LatencyTracker
	production *ProductionCounters
	prevNetIn  atomic.Int64
	prevNetOut atomic.Int64
	netInit    atomic.Bool
}

func NewCollector(tracker *LatencyTracker, production *ProductionCounters) Collector {
	return Collector{tracker: tracker, production: production}
}

func (collector *Collector) Collect(nodeCode string, workshopType string) Metric {
	cpuPct := realCPUPercent()
	memPct := realMemoryPercent()
	diskPct := realDiskPercent()
	netIn, netOut := realNetworkDelta(collector)

	apiLat := 0
	dbLat := 0
	if collector.tracker != nil {
		apiLat = collector.tracker.APILatencyMS()
		dbLat = collector.tracker.DBLatencyMS()
		collector.tracker.Reset()
	}

	finished := int64(0)
	defect := int64(0)
	if collector.production != nil {
		finished = collector.production.Finished.Load()
		defect = collector.production.Defect.Load()
	}

	return Metric{
		NodeCode:         nodeCode,
		WorkshopType:     workshopType,
		CPUUsage:         round1(cpuPct),
		MemoryUsage:      round1(memPct),
		DiskUsage:        round1(diskPct),
		NetworkIn:        netIn,
		NetworkOut:       netOut,
		DBLatencyMS:      dbLat,
		APILatencyMS:     apiLat,
		FinishedQuantity: int(finished),
		DefectQuantity:   int(defect),
	}
}

func NeedsLocalRepair(metric Metric) bool {
	return metric.DiskUsage >= 90 || metric.CPUUsage >= 92 || metric.APILatencyMS >= 850
}

// --- real OS readers --------------------------------------------------------

var (
	cpuCount, _ = cpu.Counts(true)
	rootPath    = realRootPath()
)

func realCPUPercent() float64 {
	// Percent(interval=0) returns a single snapshot since last call.
	// The first call returns 0; subsequent calls give the delta.
	percents, err := cpu.Percent(0, false)
	if err != nil || len(percents) == 0 {
		return fallbackCPULoad()
	}
	return percents[0]
}

func fallbackCPULoad() float64 {
	avg, err := load.Avg()
	if err != nil || cpuCount == 0 {
		return 0
	}
	// load1 / coreCount ≈ utilisation fraction
	pct := (avg.Load1 / float64(cpuCount)) * 100
	if pct > 100 {
		pct = 100
	}
	return pct
}

func realMemoryPercent() float64 {
	v, err := mem.VirtualMemory()
	if err != nil {
		return 0
	}
	return v.UsedPercent
}

func realDiskPercent() float64 {
	u, err := disk.Usage(rootPath)
	if err != nil {
		return 0
	}
	return u.UsedPercent
}

func realNetworkDelta(c *Collector) (int64, int64) {
	counters, err := net.IOCounters(false)
	if err != nil || len(counters) == 0 {
		return 0, 0
	}
	all := counters[0]
	in := int64(all.BytesRecv)
	out := int64(all.BytesSent)

	if !c.netInit.Load() {
		c.prevNetIn.Store(in)
		c.prevNetOut.Store(out)
		c.netInit.Store(true)
		return 0, 0
	}

	prevIn := c.prevNetIn.Swap(in)
	prevOut := c.prevNetOut.Swap(out)
	deltaIn := in - prevIn
	deltaOut := out - prevOut
	if deltaIn < 0 {
		deltaIn = 0
	}
	if deltaOut < 0 {
		deltaOut = 0
	}
	return deltaIn, deltaOut
}

func realRootPath() string {
	if runtime.GOOS == "windows" {
		return os.Getenv("SystemDrive")
	}
	return "/"
}

func round1(v float64) float64 {
	return float64(int(v*10+0.5)) / 10
}
