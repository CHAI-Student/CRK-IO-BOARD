# IO Board

Embedded I/O control system with real-time Server-Sent Events (SSE) streaming, loadcell monitoring, and door control.

## Quick Links

- **[Getting Started](docs/GETTING_STARTED.md)** - Installation, setup, and first use
- **[API Documentation](docs/API.md)** - REST and SSE endpoint reference
- **[Streaming Guide](docs/STREAMING.md)** - Server-Sent Events detailed specification and examples
- **[Architecture](docs/ARCHITECTURE.md)** - System design and data flow
- **[Protocol Reference](docs/PROTOCOL.md)** - Binary communication protocol
- **[Operations Guide](docs/OPERATIONS.md)** - Configuration, deployment, and troubleshooting
- **[Changelog](CHANGELOG.md)** - Version history, features, and breaking changes

## Documentation Structure

```
docs/
├── GETTING_STARTED.md       # Start here
├── API.md                   # REST endpoints
├── STREAMING.md             # SSE streaming guide
├── ARCHITECTURE.md          # System design
├── PROTOCOL.md              # Binary protocol
├── OPERATIONS.md            # Operations & config
├── OVERVIEW.md              # Overview documentation
└── advanced/
    └── SSE_ARCHITECTURE.md  # Deep dive: SSE async flows

guides/
├── TESTING.md               # Testing setup and commands
└── VERIFICATION_CHECKLIST.md # Quality assurance checklist

reference/
├── INDEX.md                 # Master documentation index
└── SSE_DOCUMENTATION_INDEX.md # SSE docs index

specs/                       # Hardware specifications (CSV/PDF)
```

## Features

- Real-time loadcell streaming with configurable filtering
- Door/deadbolt status monitoring
- Exponential and Kalman filter implementations
- Threshold-based change detection
- Multiple data stream aggregation

## Testing

Run the test suite:

```bash
pytest
```

See [Testing Guide](guides/TESTING.md) for detailed instructions.

## License

Internal project - CRK Rewrite Initiative
