use claw_reflect_client::ReflectClient;
use serde_json::json;
use wiremock::matchers::{header, method, path, query_param};
use wiremock::{Mock, MockServer, ResponseTemplate};

#[tokio::test]
async fn trigger_job_returns_queued_job() {
    let server = MockServer::start().await;

    Mock::given(method("POST"))
        .and(path("/api/v1/reflect/trigger"))
        .and(header("X-Claw-Api-Key", "test-key"))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "job_id": "job_123",
            "status": "queued",
            "progress_pct": 0.0,
            "message": "Reflection job queued"
        })))
        .mount(&server)
        .await;

    let client = ReflectClient::new(server.uri(), "test-key").expect("client init should succeed");
    let job = client
        .trigger_job("full", "agent_1", false)
        .await
        .expect("trigger should succeed");

    assert_eq!(job.job_id, "job_123");
    assert_eq!(job.status, "queued");
}

#[tokio::test]
async fn get_facts_returns_flattened_entries() {
    let server = MockServer::start().await;

    Mock::given(method("GET"))
        .and(path("/api/v1/profiles/agent_1"))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "agent_id": "agent_1",
            "preferences": {},
            "facts": {"timezone": "UTC", "theme": "dark"},
            "behaviour_patterns": {},
            "last_updated_at": "2026-01-01T00:00:00Z",
            "memory_count": 0,
            "profile_version": 1
        })))
        .mount(&server)
        .await;

    let client = ReflectClient::new(server.uri(), "test-key").expect("client init should succeed");
    let facts = client
        .get_facts("agent_1")
        .await
        .expect("get_facts should succeed");

    assert_eq!(facts.len(), 2);
    assert!(facts.iter().any(|f| f.key == "timezone"));
    assert!(facts.iter().any(|f| f.key == "theme"));
}

#[tokio::test]
async fn list_jobs_and_get_job_work() {
    let server = MockServer::start().await;

    Mock::given(method("GET"))
        .and(path("/api/v1/jobs"))
        .and(query_param("agent_id", "agent_1"))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!([
            {
                "id": "job_123",
                "agent_id": "agent_1",
                "status": "completed",
                "job_type": "full",
                "started_at": "2026-01-01T00:00:00Z",
                "completed_at": "2026-01-01T00:01:00Z",
                "memories_processed": 4,
                "memories_updated": 2,
                "memories_archived": 1,
                "error_message": null
            }
        ])))
        .mount(&server)
        .await;

    Mock::given(method("GET"))
        .and(path("/api/v1/jobs/job_123"))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "job": {
                "id": "job_123",
                "agent_id": "agent_1",
                "status": "completed",
                "job_type": "full",
                "started_at": "2026-01-01T00:00:00Z",
                "completed_at": "2026-01-01T00:01:00Z",
                "memories_processed": 4,
                "memories_updated": 2,
                "memories_archived": 1,
                "error_message": null
            },
            "results": [
                {
                    "id": "res_1",
                    "job_id": "job_123",
                    "memory_id": "mem_1",
                    "result_type": "summary",
                    "output": {"ok": true},
                    "confidence": 0.9,
                    "applied": true
                }
            ]
        })))
        .mount(&server)
        .await;

    let client = ReflectClient::new(server.uri(), "test-key").expect("client init should succeed");

    let jobs = client
        .list_jobs(Some("agent_1"), None, None, None)
        .await
        .expect("list_jobs should succeed");
    assert_eq!(jobs.len(), 1);

    let details = client
        .get_job("job_123")
        .await
        .expect("get_job should succeed");
    assert_eq!(details.job.id, "job_123");
    assert_eq!(details.results.len(), 1);
}

#[tokio::test]
async fn preferences_and_contradictions_work() {
    let server = MockServer::start().await;

    Mock::given(method("GET"))
        .and(path("/api/v1/profiles/agent_1/preferences"))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "agent_id": "agent_1",
            "preferences": [
                {
                    "id": "pref_1",
                    "agent_id": "agent_1",
                    "category": "style",
                    "key": "tone",
                    "value": "concise",
                    "confidence": 0.8,
                    "confirmation_count": 2,
                    "is_active": true,
                    "first_seen_at": "2026-01-01T00:00:00Z"
                }
            ]
        })))
        .mount(&server)
        .await;

    Mock::given(method("GET"))
        .and(path("/api/v1/profiles/agent_1/contradictions"))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!([
            {
                "id": "con_1",
                "agent_id": "agent_1",
                "memory_id_a": "m1",
                "memory_id_b": "m2",
                "field": "tone",
                "value_a": "short",
                "value_b": "long",
                "detected_at": "2026-01-01T00:00:00Z",
                "resolved": false
            }
        ])))
        .mount(&server)
        .await;

    Mock::given(method("POST"))
        .and(path(
            "/api/v1/profiles/agent_1/contradictions/con_1/resolve",
        ))
        .respond_with(ResponseTemplate::new(200).set_body_json(json!({
            "id": "con_1",
            "agent_id": "agent_1",
            "memory_id_a": "m1",
            "memory_id_b": "m2",
            "field": "tone",
            "value_a": "short",
            "value_b": "long",
            "detected_at": "2026-01-01T00:00:00Z",
            "resolved": true
        })))
        .mount(&server)
        .await;

    let client = ReflectClient::new(server.uri(), "test-key").expect("client init should succeed");

    let prefs = client
        .get_preferences("agent_1")
        .await
        .expect("get_preferences should succeed");
    assert_eq!(prefs.len(), 1);

    let contradictions = client
        .get_contradictions("agent_1")
        .await
        .expect("get_contradictions should succeed");
    assert_eq!(contradictions.len(), 1);

    let resolved = client
        .resolve_contradiction("agent_1", "con_1", "keep_a", None)
        .await
        .expect("resolve_contradiction should succeed");
    assert!(resolved.resolved);
}
