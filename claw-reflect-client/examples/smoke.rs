use claw_reflect_client::ReflectClient;

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let base_url = std::env::var("CLAW_REFLECT_BASE_URL")
        .unwrap_or_else(|_| "http://localhost:8090".to_string());
    let api_key = std::env::var("CLAW_REFLECT_API_KEY")?;
    let agent_id = std::env::var("CLAW_REFLECT_AGENT_ID").unwrap_or_else(|_| "agent_1".to_string());

    let client = ReflectClient::new(base_url, api_key)?;

    let preview = client.trigger_job("full", &agent_id, true).await?;
    println!(
        "dry-run status={} message={}",
        preview.status, preview.message
    );

    let facts = client.get_facts(&agent_id).await?;
    println!("facts={}", facts.len());

    let jobs = client
        .list_jobs(Some(&agent_id), None, Some(10), Some(0))
        .await?;
    println!("jobs={}", jobs.len());

    Ok(())
}
