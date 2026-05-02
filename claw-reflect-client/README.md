# claw-reflect-client

Small async Rust client for `claw-reflect`.

## Install

```toml
[dependencies]
claw-reflect-client = "0.1.0"
```

## Usage

```rust
use claw_reflect_client::ReflectClient;

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let client = ReflectClient::new("http://localhost:8090", "YOUR_API_KEY")?;

    let queued = client.trigger_job("full", "agent_123", false).await?;
    println!("queued job: {} ({})", queued.job_id, queued.status);

    let preview = client.trigger_job("full", "agent_123", true).await?;
    println!("dry-run: {}", preview.message);

    let facts = client.get_facts("agent_123").await?;
    println!("facts count: {}", facts.len());

    let jobs = client
        .list_jobs(Some("agent_123"), Some("completed"), Some(20), Some(0))
        .await?;
    println!("jobs count: {}", jobs.len());

    Ok(())
}
```

## API Mapping

- `trigger_job(..., dry_run=false)` -> `POST /api/v1/reflect/trigger`
- `trigger_job(..., dry_run=true)` -> `POST /api/v1/reflect/trigger/dry-run`
- `get_facts(workspace_id)` -> `GET /api/v1/profiles/{workspace_id}`
- `list_jobs(...)` -> `GET /api/v1/jobs`
- `get_job(job_id)` -> `GET /api/v1/jobs/{job_id}`
- `get_preferences(workspace_id)` -> `GET /api/v1/profiles/{workspace_id}/preferences`
- `get_contradictions(workspace_id)` -> `GET /api/v1/profiles/{workspace_id}/contradictions`
- `resolve_contradiction(...)` -> `POST /api/v1/profiles/{workspace_id}/contradictions/{contradiction_id}/resolve`

Note: The Python API path currently uses `agent_id` in the profile route. This crate keeps your requested method signature and passes `workspace_id` through that route parameter.

## Integration Tests

```bash
cargo test
```

## Example Binary

```bash
CLAW_REFLECT_API_KEY=... CLAW_REFLECT_AGENT_ID=agent_123 cargo run --example smoke
```
