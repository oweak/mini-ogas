package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"mini-ogas/node-agent/internal/centralapi"
	"mini-ogas/node-agent/internal/commands"
	"mini-ogas/node-agent/internal/config"
	"mini-ogas/node-agent/internal/heartbeat"
	"mini-ogas/node-agent/internal/localdb"
	"mini-ogas/node-agent/internal/metrics"
)

func main() {
	cfg := config.Load()
	startedAt := time.Now()

	tracker := &metrics.LatencyTracker{}
	production := &metrics.ProductionCounters{}
	collector := metrics.NewCollector(tracker, production)
	client := centralapi.New(cfg.CentralAPIURL, cfg.APIToken, tracker)
	if cfg.SessionToken != "" {
		client.SetSessionToken(cfg.SessionToken)
	}
	store := localdb.NewSQLiteStore(cfg.LocalDBPath)
	if err := store.Init(); err != nil {
		fmt.Printf("local db init failed: %v\n", err)
		os.Exit(1)
	}

	ctx, cancel := context.WithCancel(context.Background())
	signals := make(chan os.Signal, 1)
	signal.Notify(signals, os.Interrupt, syscall.SIGTERM)
	defer signal.Stop(signals)

	var wg sync.WaitGroup
	heartbeatReporter := heartbeat.NewReporter(client, cfg.NodeCode, startedAt, store)
	wg.Add(1)
	go func() {
		defer wg.Done()
		heartbeatReporter.Run(ctx)
	}()
	commandExecutor := commands.NewExecutor(client, cfg.NodeCode)
	wg.Add(1)
	go func() {
		defer wg.Done()
		commandExecutor.Run(ctx)
	}()

	fmt.Printf("mini-ogas-node-agent started node=%s workshop=%s central=%s db=%s interval=%s\n", cfg.NodeCode, cfg.WorkshopType, cfg.CentralAPIURL, cfg.LocalDBPath, cfg.Interval)

	shutdown := func(reason string) {
		fmt.Printf("node-agent stopping node=%s reason=%s\n", cfg.NodeCode, reason)
		cancel()
		heartbeatReporter.Send("shutting_down")
		if err := store.Close(); err != nil {
			fmt.Printf("local db close failed: %v\n", err)
		}
		wg.Wait()
		fmt.Println("node-agent stopped gracefully")
	}

	ticker := time.NewTicker(cfg.Interval)
	defer ticker.Stop()

	for {
		select {
		case sig := <-signals:
			shutdown(fmt.Sprintf("signal=%s", sig))
			return
		case <-ticker.C:
		}

		metric := collector.Collect(cfg.NodeCode, cfg.WorkshopType)
		if err := store.SaveMetric(metric); err != nil {
			fmt.Printf("local db save failed: %v\n", err)
		}
		if metrics.NeedsLocalRepair(metric) {
			fmt.Printf("local repair candidate node=%s cpu=%.2f disk=%.2f api=%dms\n", cfg.NodeCode, metric.CPUUsage, metric.DiskUsage, metric.APILatencyMS)
		}
		if err := client.SubmitMetric(metric); err != nil {
			fmt.Printf("submit metric failed: %v\n", err)
		}
	}
}
