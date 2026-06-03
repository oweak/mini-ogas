# Development Tools

Mini-OGAS currently uses these local development tools:

- VS Code portable: `.runtime/tools/vscode`
- VS Code extensions: `.runtime/tools/vscode-extensions`
- Python virtual environments: each Python service owns a `.venv`
- Node dependencies: `services/dashboard/node_modules`
- Go SDK: `.runtime/tools/go`

Open the prepared workspace:

```powershell
.\scripts\open-vscode.ps1
```

Recommended editor workflow:

1. Run `Mini-OGAS: verify all` from VS Code tasks before larger edits.
2. Use `Central API (FastAPI)` launch config for backend debugging.
3. Use the dashboard terminal task or `npm run dev` for frontend work.
4. Use `Node Agent: build` to compile the Go child-node agent.

Full Visual Studio is not required for the current Python + Vue + Go stack. It is mainly useful if the project later adds C++, .NET, or native Windows desktop components.
